from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .exceptions import TemplateLoadError
from .models import TemplateStatus
from .modes import list_modes
from .paths import TEMPLATES_DIR


class TemplateManager:
    def __init__(self, templates_dir: Path = TEMPLATES_DIR) -> None:
        self.templates_dir = templates_dir

    def ensure_directory(self) -> None:
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def get_path(self, filename: str) -> Path:
        return self.templates_dir / filename

    def _read_image(self, filename: str, flags: int) -> np.ndarray | None:
        path = self.get_path(filename)
        if not path.exists():
            return None

        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]

        decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flags)
        return decoded

    def load_grayscale(self, filename: str) -> np.ndarray:
        image = self._read_image(filename, cv2.IMREAD_GRAYSCALE)
        path = self.get_path(filename)

        if not path.exists():
            raise TemplateLoadError(f"Missing template: {path}")
        if image is None:
            raise TemplateLoadError(f"Failed to load template: {path}")
        return image

    def get_required_template_statuses(self) -> list[TemplateStatus]:
        statuses: list[TemplateStatus] = []
        for mode in list_modes():
            for filename in mode.template_files:
                path = self.get_path(filename)
                image = self._read_image(filename, cv2.IMREAD_UNCHANGED)
                statuses.append(
                    TemplateStatus(
                        mode_key=mode.key,
                        mode_name=mode.name,
                        filename=filename,
                        path=str(path),
                        exists=path.exists(),
                        readable=image is not None,
                        error="" if image is not None or not path.exists() else "OpenCV could not decode this file.",
                    )
                )
        return statuses
