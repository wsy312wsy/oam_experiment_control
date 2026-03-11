from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass
class PathsConfig:
    data_root: Path
    logs_root: Path
    slm1_mask_dir: Path
    slm2_mask_dir: Path


@dataclass
class ScanConfig:
    slm2_settle_ms: int
    save_format: str
    auto_create_placeholder_masks: bool
    placeholder_slm1_count: int
    placeholder_slm2_count: int
    max_slm1_masks: Optional[int]
    max_slm2_masks: Optional[int]


@dataclass
class CameraConfig:
    mode: str
    backend: str
    device_id: str
    sdk_module: str
    width: Optional[int]
    height: Optional[int]
    offset_x: int
    offset_y: int
    bit_depth: int
    pixel_format: str
    exposure_us: float
    gain_db: float
    trigger_mode: str
    frame_timeout_ms: int
    warmup_frames: int


@dataclass
class AppConfig:
    experiment_name: str
    mode: str
    paths: PathsConfig
    scan: ScanConfig
    camera: CameraConfig

    @classmethod
    def from_yaml(cls, config_path: Path | str) -> "AppConfig":
        path = Path(config_path)
        with path.open("r", encoding="utf-8") as f:
            raw: Dict[str, Any] = yaml.safe_load(f) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AppConfig":
        paths = raw.get("paths", {})
        scan = raw.get("scan", {})
        camera = raw.get("camera", {})
        placeholder = scan.get("placeholder_mask_count", {})
        slm2_settle_ms_raw = scan.get("slm2_settle_ms")
        if slm2_settle_ms_raw in (None, ""):
            legacy_settle_time_s = scan.get("settle_time_s")
            if legacy_settle_time_s in (None, ""):
                slm2_settle_ms_raw = 300
            else:
                slm2_settle_ms_raw = round(float(legacy_settle_time_s) * 1000.0)

        return cls(
            experiment_name=str(raw.get("experiment_name", "oam_mock_scan")),
            mode=str(raw.get("mode", "mock")),
            paths=PathsConfig(
                data_root=Path(paths.get("data_root", "data")),
                logs_root=Path(paths.get("logs_root", "logs")),
                slm1_mask_dir=Path(paths.get("slm1_mask_dir", "data/mock_masks/slm1")),
                slm2_mask_dir=Path(paths.get("slm2_mask_dir", "data/mock_masks/slm2")),
            ),
            scan=ScanConfig(
                slm2_settle_ms=int(slm2_settle_ms_raw),
                save_format=str(scan.get("save_format", "png")).lower(),
                auto_create_placeholder_masks=bool(scan.get("auto_create_placeholder_masks", True)),
                placeholder_slm1_count=int(placeholder.get("slm1", 3)),
                placeholder_slm2_count=int(placeholder.get("slm2", 4)),
                max_slm1_masks=(
                    int(scan.get("max_slm1_masks"))
                    if scan.get("max_slm1_masks") not in (None, "")
                    else None
                ),
                max_slm2_masks=(
                    int(scan.get("max_slm2_masks"))
                    if scan.get("max_slm2_masks") not in (None, "")
                    else None
                ),
            ),
            camera=CameraConfig(
                mode=str(camera.get("mode", "mock")),
                backend=str(camera.get("backend", "jai")),
                device_id=str(camera.get("device_id", "")),
                sdk_module=str(camera.get("sdk_module", "eBUS")),
                width=(
                    int(camera.get("width"))
                    if camera.get("width") not in (None, "")
                    else None
                ),
                height=(
                    int(camera.get("height"))
                    if camera.get("height") not in (None, "")
                    else None
                ),
                offset_x=int(camera.get("offset_x", 0)),
                offset_y=int(camera.get("offset_y", 0)),
                bit_depth=int(camera.get("bit_depth", 8)),
                pixel_format=str(camera.get("pixel_format", "Mono8")),
                exposure_us=float(camera.get("exposure_us", 2000.0)),
                gain_db=float(camera.get("gain_db", 0.0)),
                trigger_mode=str(camera.get("trigger_mode", "software")),
                frame_timeout_ms=int(camera.get("frame_timeout_ms", 1000)),
                warmup_frames=int(camera.get("warmup_frames", 0)),
            ),
        )

    def validate(self) -> None:
        if self.scan.slm2_settle_ms < 0:
            raise ValueError("scan.slm2_settle_ms must be >= 0")
        if self.camera.mode == "mock":
            if self.camera.width is None or self.camera.height is None:
                raise ValueError("mock mode requires camera.width and camera.height")
            if self.camera.width <= 0 or self.camera.height <= 0:
                raise ValueError("camera.width and camera.height must be > 0")
        else:
            if self.camera.width is not None and self.camera.width <= 0:
                raise ValueError("camera.width must be > 0 when provided")
            if self.camera.height is not None and self.camera.height <= 0:
                raise ValueError("camera.height must be > 0 when provided")
        if self.camera.offset_x < 0 or self.camera.offset_y < 0:
            raise ValueError("camera.offset_x and camera.offset_y must be >= 0")
        if self.camera.bit_depth not in (8, 10, 12, 14, 16):
            raise ValueError("camera.bit_depth must be one of: 8, 10, 12, 14, 16")
        if self.camera.mode not in {"mock", "real"}:
            raise ValueError("camera.mode must be 'mock' or 'real'")
        if self.camera.exposure_us <= 0:
            raise ValueError("camera.exposure_us must be > 0")
        if self.camera.frame_timeout_ms <= 0:
            raise ValueError("camera.frame_timeout_ms must be > 0")
        if self.camera.warmup_frames < 0:
            raise ValueError("camera.warmup_frames must be >= 0")
        if self.scan.placeholder_slm1_count <= 0 or self.scan.placeholder_slm2_count <= 0:
            raise ValueError("scan.placeholder_mask_count values must be > 0")
        if self.scan.max_slm1_masks is not None and self.scan.max_slm1_masks <= 0:
            raise ValueError("scan.max_slm1_masks must be > 0 when set")
        if self.scan.max_slm2_masks is not None and self.scan.max_slm2_masks <= 0:
            raise ValueError("scan.max_slm2_masks must be > 0 when set")
