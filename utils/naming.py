from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def make_run_id(experiment_name: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{experiment_name}_{ts}"


def sanitize_token(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    return cleaned.strip("._-") or "unknown"


def make_frame_name(frame_index: int, slm1_name: str, slm2_name: str, ext: str) -> str:
    safe_1 = sanitize_token(Path(slm1_name).stem)
    safe_2 = sanitize_token(Path(slm2_name).stem)
    clean_ext = ext.lower().lstrip(".")
    return f"f{frame_index:05d}_s1_{safe_1}_s2_{safe_2}.{clean_ext}"
