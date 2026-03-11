from __future__ import annotations

from pathlib import Path
from typing import Dict

from PIL import Image

from utils.file_utils import ensure_dir, write_json, write_jsonl_line


class DataManager:
    def __init__(self, data_root: Path, run_id: str, save_format: str) -> None:
        self.run_id = run_id
        self.save_format = save_format.lower().lstrip(".")

        self.run_dir = ensure_dir(data_root / run_id)
        self.frames_dir = ensure_dir(self.run_dir / "frames")
        self.scan_log_path = self.run_dir / "scan_log.jsonl"
        self.metadata_path = self.run_dir / "metadata.json"

    def save_image(self, image: Image.Image, relative_name: str) -> Path:
        save_path = self.frames_dir / relative_name
        ensure_dir(save_path.parent)
        image.save(save_path)
        return save_path

    def relative_to_run(self, path: Path) -> str:
        return str(path.relative_to(self.run_dir)).replace("\\", "/")

    def append_scan_log(self, row: Dict) -> None:
        write_jsonl_line(self.scan_log_path, row)

    def save_metadata(self, metadata: Dict) -> None:
        write_json(self.metadata_path, metadata)
