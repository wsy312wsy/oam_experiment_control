from __future__ import annotations

import hashlib
import logging

import numpy as np
from PIL import Image

from controllers.base import BaseCameraController


class MockCameraController(BaseCameraController):
    def __init__(self, width: int, height: int, bit_depth: int, logger: logging.Logger) -> None:
        self.width = width
        self.height = height
        self.bit_depth = bit_depth
        self._logger = logger
        self._connected = False
        if bit_depth > 8 and bit_depth != 16:
            self._logger.warning(
                "Mock camera bit_depth=%s will be stored as 16-bit image container",
                bit_depth,
            )

    def connect(self) -> None:
        self._connected = True
        self._logger.info("Camera connected (mock)")

    def disconnect(self) -> None:
        self._connected = False
        self._logger.info("Camera disconnected (mock)")

    def capture(self, slm1_mask: str, slm2_mask: str) -> Image.Image:
        seed_bytes = f"{slm1_mask}|{slm2_mask}|{self.width}|{self.height}".encode("utf-8")
        return self._capture_by_seed(seed_bytes)

    def capture_frame(self, timeout_ms: int | None = None) -> Image.Image:
        # Real camera controller supports timeout; mock controller keeps deterministic behavior.
        seed_bytes = f"default|default|{self.width}|{self.height}".encode("utf-8")
        return self._capture_by_seed(seed_bytes)

    def _capture_by_seed(self, seed_bytes: bytes) -> Image.Image:
        if not self._connected:
            raise RuntimeError("Camera is not connected")

        seed = int(hashlib.sha256(seed_bytes).hexdigest()[:16], 16)
        rng = np.random.default_rng(seed)

        x = np.linspace(0.0, 1.0, self.width, dtype=np.float32)
        y = np.linspace(0.0, 1.0, self.height, dtype=np.float32)
        xx, yy = np.meshgrid(x, y)

        freq_x = 2 + (seed % 7)
        freq_y = 3 + ((seed >> 3) % 9)
        phase = ((seed >> 8) % 360) * np.pi / 180.0

        base = 0.5 + 0.3 * np.sin(2 * np.pi * (freq_x * xx + freq_y * yy) + phase)
        ring_center_x = ((seed >> 12) % 1000) / 1000.0
        ring_center_y = ((seed >> 22) % 1000) / 1000.0
        radius = np.sqrt((xx - ring_center_x) ** 2 + (yy - ring_center_y) ** 2)
        ring = 0.25 * np.cos(25 * radius)

        # Deterministic micro-noise improves texture without changing reproducibility.
        noise = rng.normal(0.0, 0.02, size=(self.height, self.width)).astype(np.float32)

        img = np.clip(base + ring + noise, 0.0, 1.0)
        max_value = (1 << self.bit_depth) - 1 if self.bit_depth <= 16 else 255
        arr = (img * max_value).astype(np.uint8 if self.bit_depth <= 8 else np.uint16)

        mode = "L" if arr.dtype == np.uint8 else "I;16"
        return Image.fromarray(arr, mode=mode)
