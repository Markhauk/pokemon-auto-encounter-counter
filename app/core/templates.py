from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .filters import FilterDefinition
from .exceptions import TemplateLoadError
from .models import TemplateStatus
from .paths import TEMPLATES_DIR


class TemplateManager:
    def __init__(self, templates_dir: Path = TEMPLATES_DIR) -> None:
        self.templates_dir = templates_dir

    def ensure_directory(self) -> None:
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def get_path(self, filename: str) -> Path:
        path = Path(filename)
        if path.is_absolute():
            return path
        if path.parts and path.parts[0].lower() == "templates":
            return self.templates_dir.parent / path
        return self.templates_dir / path

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

    def get_filter_template_statuses(self, filters: list[FilterDefinition]) -> list[TemplateStatus]:
        statuses: list[TemplateStatus] = []
        for filter_definition in filters:
            path = self.get_path(filter_definition.template_path)
            image = self._read_image(filter_definition.template_path, cv2.IMREAD_UNCHANGED)
            statuses.append(
                TemplateStatus(
                    filter_id=filter_definition.id,
                    filter_name=filter_definition.name,
                    filename=Path(filter_definition.template_path).name,
                    path=str(path),
                    exists=path.exists(),
                    readable=image is not None,
                    event_type=filter_definition.event_type,
                    error="" if image is not None or not path.exists() else "OpenCV could not decode this file.",
                )
            )
        return statuses
