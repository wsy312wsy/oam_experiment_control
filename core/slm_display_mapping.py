from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml


DEFAULT_MAPPING_PATH = Path("config/slm_display_mapping.yaml")


@dataclass(frozen=True)
class SLMDisplayMapping:
    slm1_monitor_id: str
    slm2_monitor_id: str
    calibration_time: str
    monitor_summary: List[Dict[str, Any]]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_slm_display_mapping(mapping_path: Path | str = DEFAULT_MAPPING_PATH) -> SLMDisplayMapping:
    path = Path(mapping_path)
    if not path.exists():
        raise FileNotFoundError(f"SLM display mapping file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw: Dict[str, Any] = yaml.safe_load(f) or {}

    slm1_monitor_id = str(raw.get("slm1_monitor_id", "")).strip()
    slm2_monitor_id = str(raw.get("slm2_monitor_id", "")).strip()
    if not slm1_monitor_id or not slm2_monitor_id:
        raise ValueError("slm1_monitor_id and slm2_monitor_id are required")
    if slm1_monitor_id == slm2_monitor_id:
        raise ValueError("slm1_monitor_id and slm2_monitor_id must be different")

    calibration_time = str(raw.get("calibration_time", "")).strip() or utc_now_iso()
    monitor_summary = list(raw.get("monitor_summary", []))
    return SLMDisplayMapping(
        slm1_monitor_id=slm1_monitor_id,
        slm2_monitor_id=slm2_monitor_id,
        calibration_time=calibration_time,
        monitor_summary=monitor_summary,
    )


def save_slm_display_mapping(
    slm1_monitor_id: str,
    slm2_monitor_id: str,
    monitor_summary: List[Dict[str, Any]],
    mapping_path: Path | str = DEFAULT_MAPPING_PATH,
) -> Path:
    slm1 = str(slm1_monitor_id).strip()
    slm2 = str(slm2_monitor_id).strip()
    if not slm1 or not slm2:
        raise ValueError("slm1_monitor_id and slm2_monitor_id are required")
    if slm1 == slm2:
        raise ValueError("slm1_monitor_id and slm2_monitor_id must be different")

    path = Path(mapping_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "slm1_monitor_id": slm1,
        "slm2_monitor_id": slm2,
        "calibration_time": utc_now_iso(),
        "monitor_summary": monitor_summary,
    }
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=False)
    return path

