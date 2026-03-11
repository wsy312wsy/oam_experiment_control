from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

MASK_SUFFIXES = {".png", ".bmp", ".jpg", ".jpeg", ".tif", ".tiff", ".npy", ".txt"}


def ensure_dir(path: Path | str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_mask_files(mask_dir: Path | str) -> List[Path]:
    directory = Path(mask_dir)
    if not directory.exists():
        return []
    return sorted(
        [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in MASK_SUFFIXES],
        key=lambda x: x.name.lower(),
    )


def write_json(path: Path | str, payload: dict) -> None:
    p = Path(path)
    with p.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_jsonl_line(path: Path | str, row: dict) -> None:
    p = Path(path)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def create_placeholder_masks(mask_dir: Path | str, prefix: str, count: int) -> Iterable[Path]:
    directory = ensure_dir(mask_dir)
    created = []
    for i in range(1, count + 1):
        p = directory / f"{prefix}_{i:03d}.txt"
        if not p.exists():
            p.write_text(f"placeholder mask {i}\n", encoding="utf-8")
        created.append(p)
    return created
