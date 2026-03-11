from __future__ import annotations

import os
from pathlib import Path

from controllers.camera_controller import CameraController, RealCameraSettings
from controllers.mock_camera_controller import MockCameraController
from controllers.mock_slm_controller import MockSLMController
from core.data_manager import DataManager
from core.experiment_runner import run_experiment
from core.logger import setup_logger
from core.scan_plan import AppConfig
from utils.naming import make_run_id

# 本地快速覆盖配置（开发调试用）。
# 设为具体值会覆盖 YAML；设为 None 则使用 YAML 中的值。
MAIN_OVERRIDES = {
    # 示例: "config/real_jai_small_scan.yaml"
    "config_path": None,
    # 示例: "D:/oam_runs"
    "data_root": None,
    # 相机模式，可选: "mock" | "real"
    "camera_mode": None,
    # 相机后端，可选: "jai"
    "camera_backend": "jai",
    # eBUS Python 模块名，可选: "eBUS" | "ebus"
    "camera_sdk_module": "eBUS",
    # 设备 ID，留空表示第一台发现设备
    "camera_device_id": None,
    # 曝光时间（微秒）
    "camera_exposure_us": None,
    # ROI 参数
    "camera_width": None,
    "camera_height": None,
    "camera_offset_x": None,
    "camera_offset_y": None,
}


def _apply_main_overrides(config: AppConfig) -> None:
    if MAIN_OVERRIDES["data_root"] is not None:
        config.paths.data_root = Path(str(MAIN_OVERRIDES["data_root"]))

    if MAIN_OVERRIDES["camera_mode"] is not None:
        config.camera.mode = str(MAIN_OVERRIDES["camera_mode"])
    if MAIN_OVERRIDES["camera_backend"] is not None:
        config.camera.backend = str(MAIN_OVERRIDES["camera_backend"])
    if MAIN_OVERRIDES["camera_sdk_module"] is not None:
        config.camera.sdk_module = str(MAIN_OVERRIDES["camera_sdk_module"])
    if MAIN_OVERRIDES["camera_device_id"] is not None:
        config.camera.device_id = str(MAIN_OVERRIDES["camera_device_id"])
    if MAIN_OVERRIDES["camera_exposure_us"] is not None:
        config.camera.exposure_us = float(MAIN_OVERRIDES["camera_exposure_us"])
    if MAIN_OVERRIDES["camera_width"] is not None:
        config.camera.width = int(MAIN_OVERRIDES["camera_width"])
    if MAIN_OVERRIDES["camera_height"] is not None:
        config.camera.height = int(MAIN_OVERRIDES["camera_height"])
    if MAIN_OVERRIDES["camera_offset_x"] is not None:
        config.camera.offset_x = int(MAIN_OVERRIDES["camera_offset_x"])
    if MAIN_OVERRIDES["camera_offset_y"] is not None:
        config.camera.offset_y = int(MAIN_OVERRIDES["camera_offset_y"])


def main() -> int:
    override_config_path = MAIN_OVERRIDES["config_path"]
    config_path = Path(
        str(override_config_path)
        if override_config_path is not None
        else os.environ.get("OAM_CONFIG", "config/default_config.yaml")
    )
    config = AppConfig.from_yaml(config_path)
    _apply_main_overrides(config)
    config.validate()

    run_id = make_run_id(config.experiment_name)
    logger = setup_logger(config.paths.logs_root, run_id)
    logger.info("Loaded config: %s", config_path)
    logger.info(
        "Timing policy: no extra delay after SLM1 switch; wait slm2_settle_ms=%d before each capture",
        config.scan.slm2_settle_ms,
    )

    if config.mode != "mock":
        raise RuntimeError(
            "Current stage supports mock experiment workflow only. "
            "Real SLM controllers are placeholders."
        )

    data_manager = DataManager(
        data_root=config.paths.data_root,
        run_id=run_id,
        save_format=config.scan.save_format,
    )
    slm1_controller = MockSLMController(name="SLM1", logger=logger)
    slm2_controller = MockSLMController(name="SLM2", logger=logger)
    if config.camera.mode == "mock":
        camera_controller = MockCameraController(
            width=config.camera.width or 0,
            height=config.camera.height or 0,
            bit_depth=config.camera.bit_depth,
            logger=logger,
        )
    else:
        camera_controller = CameraController(
            settings=RealCameraSettings(
                backend=config.camera.backend,
                device_id=config.camera.device_id,
                sdk_module=config.camera.sdk_module,
                width=config.camera.width,
                height=config.camera.height,
                offset_x=config.camera.offset_x,
                offset_y=config.camera.offset_y,
                bit_depth=config.camera.bit_depth,
                pixel_format=config.camera.pixel_format,
                exposure_us=config.camera.exposure_us,
                gain_db=config.camera.gain_db,
                trigger_mode=config.camera.trigger_mode,
                frame_timeout_ms=config.camera.frame_timeout_ms,
                warmup_frames=config.camera.warmup_frames,
            ),
            logger=logger,
        )

    result = run_experiment(
        config=config,
        slm1_controller=slm1_controller,
        slm2_controller=slm2_controller,
        camera_controller=camera_controller,
        data_manager=data_manager,
        logger=logger,
    )

    logger.info(
        "Run finished: status=%s, total_frames=%s, successful_frames=%s, output=%s",
        result["status"],
        result["total_frames"],
        result["successful_frames"],
        data_manager.run_dir,
    )
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
