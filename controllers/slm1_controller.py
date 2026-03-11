from __future__ import annotations

import logging
from pathlib import Path

from controllers.base import BaseSLMController
from core.slm_display_mapping import DEFAULT_MAPPING_PATH, load_slm_display_mapping


class SLM1Controller(BaseSLMController):
    """Reserved for future real Holoeye SDK integration."""

    def __init__(
        self,
        mapping_path: Path | str = DEFAULT_MAPPING_PATH,
        logger: logging.Logger | None = None,
    ) -> None:
        self.mapping_path = Path(mapping_path)
        self.monitor_id: str | None = None
        self._logger = logger

    def connect(self) -> None:
        mapping = load_slm_display_mapping(self.mapping_path)
        self.monitor_id = mapping.slm1_monitor_id
        if self._logger is not None:
            self._logger.info("SLM1 display binding loaded: monitor_id=%s", self.monitor_id)
        raise NotImplementedError("Real SLM1 controller is not integrated yet")

    def disconnect(self) -> None:
        raise NotImplementedError("Real SLM1 controller is not integrated yet")

    def apply_mask(self, mask_path):
        raise NotImplementedError("Real SLM1 controller is not integrated yet")
