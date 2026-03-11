from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, List

from controllers.base import BaseCameraController, BaseSLMController
from core.data_manager import DataManager
from core.scan_plan import AppConfig
from utils.file_utils import create_placeholder_masks, list_mask_files
from utils.naming import make_frame_name, sanitize_token, utc_now_iso
from utils.timing import elapsed_ms, sleep_seconds


def _load_masks_or_placeholder(
    mask_dir: Path,
    prefix: str,
    placeholder_count: int,
    max_count: int | None,
    auto_create: bool,
    logger: logging.Logger,
) -> List[Path]:
    masks = list_mask_files(mask_dir)
    if not masks and auto_create:
        create_placeholder_masks(mask_dir, prefix=prefix, count=placeholder_count)
        logger.warning("Mask directory is empty, created placeholder masks: %s", mask_dir)
        masks = list_mask_files(mask_dir)

    if not masks:
        raise RuntimeError(
            f"No mask files found in {mask_dir}. "
            "Please add mask files or enable placeholder creation."
        )

    if max_count is not None:
        masks = masks[:max_count]
    return masks


def run_experiment(
    config: AppConfig,
    slm1_controller: BaseSLMController,
    slm2_controller: BaseSLMController,
    camera_controller: BaseCameraController,
    data_manager: DataManager,
    logger: logging.Logger,
) -> Dict[str, int | str]:
    start_time = utc_now_iso()
    slm1_masks: List[Path] = []
    slm2_masks: List[Path] = []
    frame_index = 0
    success_count = 0
    status = "failed"

    try:
        slm1_masks = _load_masks_or_placeholder(
            mask_dir=config.paths.slm1_mask_dir,
            prefix="slm1_mask",
            placeholder_count=config.scan.placeholder_slm1_count,
            max_count=config.scan.max_slm1_masks,
            auto_create=config.scan.auto_create_placeholder_masks,
            logger=logger,
        )
        slm2_masks = _load_masks_or_placeholder(
            mask_dir=config.paths.slm2_mask_dir,
            prefix="slm2_mask",
            placeholder_count=config.scan.placeholder_slm2_count,
            max_count=config.scan.max_slm2_masks,
            auto_create=config.scan.auto_create_placeholder_masks,
            logger=logger,
        )

        logger.info(
            "Starting scan: camera_mode=%s, slm1_masks=%d, slm2_masks=%d, total_frames=%d, slm2_settle_ms=%d",
            config.camera.mode,
            len(slm1_masks),
            len(slm2_masks),
            len(slm1_masks) * len(slm2_masks),
            config.scan.slm2_settle_ms,
        )

        slm1_controller.connect()
        slm2_controller.connect()
        camera_controller.connect()

        for slm1_mask in slm1_masks:
            slm1_controller.apply_mask(slm1_mask)

            for slm2_mask in slm2_masks:
                frame_index += 1
                t0 = time.perf_counter()
                row = {
                    "timestamp": utc_now_iso(),
                    "slm1_mask": slm1_mask.name,
                    "slm2_mask": slm2_mask.name,
                    "image_path": "",
                    "success": False,
                    "error_message": "",
                    "elapsed_ms": 0.0,
                }

                try:
                    slm2_controller.apply_mask(slm2_mask)
                    sleep_seconds(config.scan.slm2_settle_ms / 1000.0)

                    image = camera_controller.capture(slm1_mask.name, slm2_mask.name)
                    frame_name = make_frame_name(
                        frame_index=frame_index,
                        slm1_name=slm1_mask.name,
                        slm2_name=slm2_mask.name,
                        ext=config.scan.save_format,
                    )
                    relative_image_name = f"{sanitize_token(slm1_mask.stem)}/{frame_name}"
                    image_path = data_manager.save_image(image, relative_image_name)

                    row["image_path"] = data_manager.relative_to_run(image_path)
                    row["success"] = True
                    success_count += 1
                except Exception as exc:
                    row["error_message"] = str(exc)
                    logger.exception(
                        "Frame capture failed at slm1=%s slm2=%s",
                        slm1_mask.name,
                        slm2_mask.name,
                    )
                finally:
                    row["elapsed_ms"] = round(elapsed_ms(t0), 3)
                    data_manager.append_scan_log(row)

        status = "success" if success_count == frame_index else "failed"
        return {
            "status": status,
            "total_frames": frame_index,
            "successful_frames": success_count,
        }
    finally:
        end_time = utc_now_iso()

        for device in (camera_controller, slm2_controller, slm1_controller):
            try:
                device.disconnect()
            except Exception:
                logger.exception("Device disconnect failed")

        metadata = {
            "run_id": data_manager.run_id,
            "experiment_name": config.experiment_name,
            "output_dir": str(data_manager.run_dir),
            "slm1_mask_dir": str(config.paths.slm1_mask_dir),
            "slm2_mask_dir": str(config.paths.slm2_mask_dir),
            "slm1_mask_count": len(slm1_masks),
            "slm2_mask_count": len(slm2_masks),
            "camera_mode": config.camera.mode,
            "save_format": config.scan.save_format,
            "start_time": start_time,
            "end_time": end_time,
            "total_frames": frame_index,
            "status": status,
        }
        data_manager.save_metadata(metadata)
