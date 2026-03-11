from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from controllers.base import BaseCameraController


@dataclass
class RealCameraSettings:
    backend: str = "jai"
    device_id: str = ""
    sdk_module: str = "eBUS"
    width: Optional[int] = None
    height: Optional[int] = None
    offset_x: int = 0
    offset_y: int = 0
    bit_depth: int = 8
    pixel_format: str = "Mono8"
    exposure_us: float = 2000.0
    gain_db: float = 0.0
    trigger_mode: str = "software"
    frame_timeout_ms: int = 1000
    warmup_frames: int = 0


class CameraController(BaseCameraController):
    """Real JAI/eBUS camera controller for main experiment workflow."""

    def __init__(self, settings: RealCameraSettings, logger: logging.Logger) -> None:
        self.settings = settings
        self._logger = logger
        self._sdk: Any | None = None
        self._system: Any | None = None
        self._device: Any | None = None
        self._stream: Any | None = None
        self._pipeline: Any | None = None
        self._connected = False
        self._acquiring = False
        self._stream_enabled = False
        self._acquisition_started = False
        self._pixel_format = self.settings.pixel_format
        self._last_error = ""
        self._sdk_module_name = ""

    @staticmethod
    def list_devices(backend: str = "jai", sdk_module: str = "eBUS") -> List[Dict[str, str]]:
        if backend.lower() != "jai":
            raise ValueError(f"Unsupported backend: {backend}")
        sdk, _, _ = CameraController._load_sdk_with_fallback(sdk_module)
        if sdk is None or not hasattr(sdk, "PvSystem"):
            return []

        system = sdk.PvSystem()
        CameraController._safe_call(system, "Find")
        return CameraController._discover_devices(system)

    def connect(self) -> None:
        if self.settings.backend.lower() != "jai":
            raise ValueError(f"Unsupported backend: {self.settings.backend}")

        self._sdk, self._sdk_module_name, tried = self._load_sdk_with_fallback(self.settings.sdk_module)
        if self._sdk is None:
            raise RuntimeError(
                "Unable to import eBUS Python wrapper. "
                f"Tried modules: {', '.join(tried)}. "
                "Please provide a working module name via camera.sdk_module or share "
                "the output of `python -c \"import eBUS,sys; print(eBUS.__file__); print(sys.executable)\"`."
            )
        if not hasattr(self._sdk, "PvSystem") or not hasattr(self._sdk, "PvDevice") or not hasattr(self._sdk, "PvStream"):
            raise RuntimeError("eBUS SDK missing required APIs: PvSystem/PvDevice/PvStream")

        self._system = self._sdk.PvSystem()
        self._safe_call(self._system, "Find")
        devices = self._discover_devices(self._system)
        if not devices:
            raise RuntimeError("No JAI devices discovered")

        target = self._select_device(devices, self.settings.device_id)
        connection_id = target.get("connection_id", "").strip()
        if not connection_id:
            raise RuntimeError("Selected device has empty connection_id")

        dev_ret = self._sdk.PvDevice.CreateAndConnect(connection_id)
        str_ret = self._sdk.PvStream.CreateAndOpen(connection_id)
        self._device = self._extract_sdk_obj(dev_ret, "GetParameters")
        self._stream = self._extract_sdk_obj(str_ret, "QueueBuffer")
        if self._device is None or self._stream is None:
            raise RuntimeError("Failed to connect device or open stream")

        if hasattr(self._sdk, "PvPipeline"):
            self._pipeline = self._sdk.PvPipeline(self._stream)
            self._safe_call(self._pipeline, "SetBufferCount", 16)
        else:
            self._pipeline = None

        self._connected = True
        self._pixel_format = self.settings.pixel_format
        self._logger.info(
            "Camera connected (real): sdk=%s model=%s display_id=%s connection_id=%s",
            self._sdk_module_name,
            target.get("model", ""),
            target.get("display_id", ""),
            connection_id,
        )
        self.configure()

    def configure(self) -> None:
        if not self._connected:
            raise RuntimeError("Camera must be connected before configure")

        params: Dict[str, Any] = {
            "ExposureTime": float(self.settings.exposure_us),
            "PixelFormat": str(self.settings.pixel_format),
        }
        if self.settings.width is not None:
            params["Width"] = int(self.settings.width)
        if self.settings.height is not None:
            params["Height"] = int(self.settings.height)
        # Only apply ROI offset when width/height are explicitly provided.
        if self.settings.width is not None and self.settings.height is not None:
            params["OffsetX"] = int(self.settings.offset_x)
            params["OffsetY"] = int(self.settings.offset_y)
        if self.settings.gain_db >= 0:
            params["Gain"] = float(self.settings.gain_db)
        self._apply_parameters(params)

    def start_acquisition(self) -> None:
        if not self._connected:
            raise RuntimeError("Camera must be connected before acquisition")
        if self._acquiring:
            return

        if self._pipeline is not None:
            self._safe_call(self._pipeline, "Start")

        enabled, enable_msg = self._call_first_available(self._device, ["StreamEnable", "EnableStream"])
        if not enabled:
            enabled, enable_msg = self._call_first_available(self._stream, ["Enable"])
        self._stream_enabled = enabled
        if not enabled:
            self._logger.warning("Stream enable did not report success: %s", enable_msg)

        started = False
        node_map = self._safe_call(self._device, "GetParameters")
        if node_map is not None:
            node = self._safe_call(node_map, "Get", "AcquisitionStart")
            if node is not None:
                started, _ = self._execute_command_node(node)
        if not started:
            started, start_msg = self._call_first_available(
                self._device, ["AcquisitionStart", "StartAcquisition"]
            )
            if not started:
                raise RuntimeError(f"Failed to start acquisition: {start_msg}")

        self._acquisition_started = True
        self._acquiring = True

        for _ in range(max(0, int(self.settings.warmup_frames))):
            self._grab_numpy_frame(timeout_ms=max(20, self.settings.frame_timeout_ms))

    def stop_acquisition(self) -> None:
        if not self._connected or not self._acquiring:
            return

        if self._device is not None and self._acquisition_started:
            node_map = self._safe_call(self._device, "GetParameters")
            if node_map is not None:
                node = self._safe_call(node_map, "Get", "AcquisitionStop")
                if node is not None:
                    self._execute_command_node(node)
            self._call_first_available(self._device, ["AcquisitionStop", "StopAcquisition"])
        self._acquisition_started = False

        if self._stream_enabled:
            self._call_first_available(self._device, ["StreamDisable", "DisableStream"])
            self._call_first_available(self._stream, ["Disable"])
        self._stream_enabled = False

        if self._pipeline is not None:
            self._safe_call(self._pipeline, "Stop")
        self._acquiring = False

    def disconnect(self) -> None:
        if not self._connected:
            return
        try:
            self.stop_acquisition()
        except Exception:
            self._logger.exception("Failed while stopping acquisition during disconnect")

        if self._stream is not None:
            self._safe_call(self._stream, "Close")
        if self._device is not None:
            self._safe_call(self._device, "Disconnect")

        self._pipeline = None
        self._stream = None
        self._device = None
        self._system = None
        self._connected = False
        self._acquiring = False
        self._stream_enabled = False
        self._acquisition_started = False
        self._logger.info("Camera disconnected (real)")

    def capture_frame(self, timeout_ms: int | None = None) -> Image.Image:
        if not self._connected:
            raise RuntimeError("Camera is not connected")

        stop_after_capture = False
        if not self._acquiring:
            self.start_acquisition()
            stop_after_capture = True

        try:
            timeout = int(timeout_ms or self.settings.frame_timeout_ms)
            np_image = self._grab_numpy_frame(timeout_ms=max(1, timeout))
            return self.numpy_to_pil(np_image)
        except Exception as exc:
            self._last_error = str(exc)
            raise
        finally:
            if stop_after_capture:
                self.stop_acquisition()

    def get_status(self) -> Dict[str, Any]:
        return {
            "backend": self.settings.backend,
            "sdk_module": self._sdk_module_name,
            "connected": self._connected,
            "acquiring": self._acquiring,
            "pixel_format": self._pixel_format,
            "last_error": self._last_error,
        }

    def _grab_numpy_frame(self, timeout_ms: int) -> np.ndarray:
        if self._pipeline is None:
            raise RuntimeError("Pipeline is unavailable, cannot retrieve frame")

        result = self._safe_call(self._pipeline, "RetrieveNextBuffer", int(max(1, timeout_ms)))
        if result is None:
            raise RuntimeError(f"RetrieveNextBuffer timeout ({timeout_ms} ms)")

        buffer_obj = self._extract_buffer_obj(result)
        if buffer_obj is None:
            raise RuntimeError("Failed to parse buffer object from SDK return value")

        try:
            image_obj = self._safe_call(buffer_obj, "GetImage")
            if image_obj is None:
                raise RuntimeError("GetImage returned None")
            return self._image_to_numpy(image_obj, self._pixel_format)
        finally:
            self._call_first_available(self._pipeline, ["ReleaseBuffer"], buffer_obj)

    def _apply_parameters(self, params: Dict[str, Any]) -> None:
        if self._device is None:
            raise RuntimeError("Device is not connected")

        node_map = self._safe_call(self._device, "GetParameters")
        if node_map is None:
            raise RuntimeError("Cannot access camera node map")

        ordered_keys = ["Width", "Height", "OffsetX", "OffsetY", "ExposureTime", "Gain", "PixelFormat"]
        applied = set()
        for name in ordered_keys + list(params.keys()):
            if name in applied or name not in params:
                continue
            applied.add(name)
            value = params[name]
            node = self._safe_call(node_map, "Get", name)
            if node is None:
                continue
            self._set_node_value(node, value)
            if name == "PixelFormat":
                self._pixel_format = str(value)

    @staticmethod
    def numpy_to_pil(image: np.ndarray) -> Image.Image:
        arr = np.asarray(image)
        if arr.dtype == np.uint8:
            return Image.fromarray(arr, mode="L")
        if arr.dtype == np.uint16:
            return Image.fromarray(arr.astype(np.uint16), mode="I;16")
        if arr.max(initial=0) <= 255:
            return Image.fromarray(arr.astype(np.uint8), mode="L")
        return Image.fromarray(arr.astype(np.uint16), mode="I;16")

    @staticmethod
    def _select_device(devices: List[Dict[str, str]], device_id: str) -> Dict[str, str]:
        if not device_id:
            return devices[0]
        key = device_id.strip().lower()
        for dev in devices:
            if (
                dev.get("connection_id", "").lower() == key
                or dev.get("display_id", "").lower() == key
                or dev.get("model", "").lower() == key
            ):
                return dev
        raise RuntimeError(f"Requested device_id not found: {device_id}")

    @staticmethod
    def _discover_devices(system_obj: Any) -> List[Dict[str, str]]:
        devices: List[Dict[str, str]] = []
        iface_count = int(CameraController._safe_call(system_obj, "GetInterfaceCount") or 0)
        for i in range(iface_count):
            iface = CameraController._safe_call(system_obj, "GetInterface", i)
            if iface is None:
                continue
            dev_count = int(CameraController._safe_call(iface, "GetDeviceCount") or 0)
            for j in range(dev_count):
                info = CameraController._safe_call(iface, "GetDeviceInfo", j)
                if info is None:
                    continue
                devices.append(
                    {
                        "connection_id": str(CameraController._safe_call(info, "GetConnectionID") or ""),
                        "display_id": str(CameraController._safe_call(info, "GetDisplayID") or ""),
                        "vendor": str(CameraController._safe_call(info, "GetVendorName") or ""),
                        "model": str(CameraController._safe_call(info, "GetModelName") or ""),
                    }
                )
        return devices

    @staticmethod
    def _extract_buffer_obj(result: Any) -> Optional[Any]:
        if result is None:
            return None
        if isinstance(result, tuple):
            for item in result:
                if hasattr(item, "GetImage"):
                    return item
            return None
        if hasattr(result, "GetImage"):
            return result
        return None

    @staticmethod
    def _extract_sdk_obj(result: Any, probe_method: str) -> Optional[Any]:
        if result is None:
            return None
        if hasattr(result, probe_method):
            return result
        if isinstance(result, tuple):
            for item in result:
                if hasattr(item, probe_method):
                    return item
        return None

    @staticmethod
    def _call_first_available(obj: Any, methods: List[str], *args: Any) -> Tuple[bool, str]:
        for method in methods:
            fn = getattr(obj, method, None) if obj is not None else None
            if fn is None:
                continue
            try:
                fn(*args)
                return True, f"{method}: ok"
            except Exception as exc:
                return False, f"{method}: {exc}"
        return False, f"methods not available: {methods}"

    @staticmethod
    def _execute_command_node(node: Any) -> Tuple[bool, str]:
        return CameraController._call_first_available(node, ["Execute", "Run", "Invoke"])

    @staticmethod
    def _set_node_value(node: Any, value: Any) -> None:
        if hasattr(node, "SetValue"):
            node.SetValue(value)
            return
        if hasattr(node, "SetValueString"):
            node.SetValueString(str(value))
            return
        if hasattr(node, "SetValueFloat"):
            node.SetValueFloat(float(value))
            return
        if hasattr(node, "SetValueInt"):
            node.SetValueInt(int(value))
            return
        raise RuntimeError("Node object does not support SetValue API")

    @staticmethod
    def _image_to_numpy(image_obj: Any, pixel_format: str) -> np.ndarray:
        width = CameraController._safe_call(image_obj, "GetWidth")
        height = CameraController._safe_call(image_obj, "GetHeight")
        if width is None or height is None:
            raise RuntimeError("Cannot read image dimensions")
        width_i = int(width)
        height_i = int(height)

        data = CameraController._safe_call(image_obj, "GetDataPointer")
        if data is None:
            data = CameraController._safe_call(image_obj, "GetData")
        if data is None:
            raise RuntimeError("Cannot access image data")

        raw = bytes(data)
        pf = (pixel_format or "Mono8").strip().lower()
        if pf in {"mono8", "mono8signed"}:
            arr = np.frombuffer(raw, dtype=np.uint8, count=width_i * height_i).reshape((height_i, width_i))
            return arr.copy()
        if pf in {"mono12", "mono16"}:
            need_bytes = width_i * height_i * 2
            if len(raw) < need_bytes:
                raise RuntimeError(
                    f"Image bytes too short for {pixel_format}: need={need_bytes} got={len(raw)}"
                )
            arr = np.frombuffer(raw, dtype=np.uint16, count=width_i * height_i).reshape((height_i, width_i))
            if pf == "mono12":
                arr = np.bitwise_and(arr, 0x0FFF)
            return arr.copy()

        bits = CameraController._safe_call(image_obj, "GetBitsPerPixel")
        if bits is not None and int(bits) > 8:
            arr = np.frombuffer(raw, dtype=np.uint16, count=width_i * height_i).reshape((height_i, width_i))
            return arr.copy()
        arr = np.frombuffer(raw, dtype=np.uint8, count=width_i * height_i).reshape((height_i, width_i))
        return arr.copy()

    @staticmethod
    def _safe_call(obj: Any, method: str, *args: Any) -> Any:
        if obj is None:
            return None
        fn = getattr(obj, method, None)
        if fn is None:
            return None
        try:
            return fn(*args)
        except Exception:
            return None

    @staticmethod
    def _try_import_sdk(module_name: str) -> Optional[Any]:
        try:
            return importlib.import_module(module_name)
        except Exception:
            return None

    @staticmethod
    def _load_sdk_with_fallback(preferred_module: str) -> Tuple[Optional[Any], str, List[str]]:
        tried: List[str] = []
        for name in [preferred_module, "eBUS", "ebus"]:
            if not name or name in tried:
                continue
            tried.append(name)
            sdk = CameraController._try_import_sdk(name)
            if sdk is not None:
                return sdk, name, tried
        return None, "", tried
