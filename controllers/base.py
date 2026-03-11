from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image


class BaseSLMController(ABC):
    """Abstract controller for one SLM device."""

    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def apply_mask(self, mask_path: Path) -> None:
        pass


class BaseCameraController(ABC):
    """Abstract controller for camera capture."""

    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    def configure(self) -> None:
        """Optional one-time configuration after connect."""

    def start_acquisition(self) -> None:
        """Optional continuous acquisition start hook."""

    def stop_acquisition(self) -> None:
        """Optional continuous acquisition stop hook."""

    @abstractmethod
    def capture_frame(self, timeout_ms: int | None = None) -> Image.Image:
        pass

    def capture(self, slm1_mask: str, slm2_mask: str) -> Image.Image:
        """Backward-compatible wrapper used by current experiment runner."""
        return self.capture_frame()
