from __future__ import annotations

import logging
from pathlib import Path

from controllers.base import BaseSLMController


class MockSLMController(BaseSLMController):
    def __init__(self, name: str, logger: logging.Logger) -> None:
        self.name = name
        self._logger = logger
        self._connected = False
        self.current_mask: Path | None = None

    def connect(self) -> None:
        self._connected = True
        self._logger.info("%s connected (mock)", self.name)

    def disconnect(self) -> None:
        self._connected = False
        self._logger.info("%s disconnected (mock)", self.name)

    def apply_mask(self, mask_path: Path) -> None:
        if not self._connected:
            raise RuntimeError(f"{self.name} is not connected")
        self.current_mask = mask_path
        self._logger.debug("%s apply mask: %s", self.name, mask_path.name)
