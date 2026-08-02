from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.regions import clamp_region, expand_region


class TemplateSelectionView(QWidget):
    selection_changed = Signal(dict)

    _HANDLE_NAMES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")

    def __init__(self, pixmap: QPixmap, initial_region: dict[str, int]) -> None:
        super().__init__()
        self._pixmap = pixmap
        self._selection = QRectF(
            float(initial_region["left"]),
            float(initial_region["top"]),
            float(initial_region["width"]),
            float(initial_region["height"]),
        )
        self._image_rect = QRectF()
        self._interaction = ""
        self._active_handle = ""
        self._press_image_point = QPointF()
        self._starting_selection = QRectF()
        self.setMinimumSize(760, 480)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def selection(self) -> dict[str, int]:
        normalized = self._selection.normalized()
        return clamp_region(
            {
                "left": math.floor(normalized.left()),
                "top": math.floor(normalized.top()),
                "width": max(1, math.ceil(normalized.width())),
                "height": max(1, math.ceil(normalized.height())),
            },
            bounds_width=self._pixmap.width(),
            bounds_height=self._pixmap.height(),
        )

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#15191d"))
        self._image_rect = self._fitted_image_rect()
        painter.drawPixmap(self._image_rect, self._pixmap, QRectF(self._pixmap.rect()))

        selection_rect = self._image_to_widget_rect(self._selection)
        shade = QColor(0, 0, 0, 145)
        image = self._image_rect
        painter.fillRect(QRectF(image.left(), image.top(), image.width(), max(0.0, selection_rect.top() - image.top())), shade)
        painter.fillRect(QRectF(image.left(), selection_rect.bottom(), image.width(), max(0.0, image.bottom() - selection_rect.bottom())), shade)
        painter.fillRect(QRectF(image.left(), selection_rect.top(), max(0.0, selection_rect.left() - image.left()), selection_rect.height()), shade)
        painter.fillRect(QRectF(selection_rect.right(), selection_rect.top(), max(0.0, image.right() - selection_rect.right()), selection_rect.height()), shade)

        painter.setPen(QPen(QColor("#ffd54f"), 2.0))
        painter.drawRect(selection_rect)
        painter.setPen(QPen(QColor("#222222"), 1.0))
        painter.setBrush(QColor("#fff3b0"))
        for point in self._handle_points(selection_rect).values():
            painter.drawRect(QRectF(point.x() - 5, point.y() - 5, 10, 10))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._image_rect.contains(event.position()):
            return
        self.setFocus()
        self._press_image_point = self._widget_to_image(event.position())
        self._starting_selection = QRectF(self._selection)
        handle = self._handle_at(event.position())
        selection_widget_rect = self._image_to_widget_rect(self._selection)
        if handle:
            self._interaction = "resize"
            self._active_handle = handle
        elif selection_widget_rect.contains(event.position()):
            self._interaction = "move"
        else:
            self._interaction = "create"
            self._selection = QRectF(self._press_image_point, self._press_image_point)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._interaction:
            self._update_cursor(event.position())
            return

        current = self._widget_to_image(event.position(), clamp=True)
        if self._interaction == "create":
            self._selection = QRectF(self._press_image_point, current).normalized()
        elif self._interaction == "move":
            delta = current - self._press_image_point
            moved = QRectF(self._starting_selection)
            moved.translate(delta)
            if moved.left() < 0:
                moved.translate(-moved.left(), 0)
            if moved.top() < 0:
                moved.translate(0, -moved.top())
            if moved.right() > self._pixmap.width():
                moved.translate(self._pixmap.width() - moved.right(), 0)
            if moved.bottom() > self._pixmap.height():
                moved.translate(0, self._pixmap.height() - moved.bottom())
            self._selection = moved
        else:
            self._selection = self._resized_selection(current)

        self._ensure_minimum_selection()
        self.selection_changed.emit(self.selection())
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._interaction:
            self._ensure_minimum_selection()
            self.selection_changed.emit(self.selection())
        self._interaction = ""
        self._active_handle = ""
        self._update_cursor(event.position())
        self.update()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._image_rect = self._fitted_image_rect()

    def _fitted_image_rect(self) -> QRectF:
        available = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        if self._pixmap.isNull() or available.width() <= 0 or available.height() <= 0:
            return QRectF()
        scale = min(
            available.width() / self._pixmap.width(),
            available.height() / self._pixmap.height(),
        )
        width = self._pixmap.width() * scale
        height = self._pixmap.height() * scale
        return QRectF(
            available.center().x() - width / 2,
            available.center().y() - height / 2,
            width,
            height,
        )

    def _widget_to_image(self, point: QPointF, *, clamp: bool = False) -> QPointF:
        if self._image_rect.width() <= 0 or self._image_rect.height() <= 0:
            return QPointF()
        x = (point.x() - self._image_rect.left()) * self._pixmap.width() / self._image_rect.width()
        y = (point.y() - self._image_rect.top()) * self._pixmap.height() / self._image_rect.height()
        if clamp:
            x = max(0.0, min(float(self._pixmap.width()), x))
            y = max(0.0, min(float(self._pixmap.height()), y))
        return QPointF(x, y)

    def _image_to_widget_rect(self, rect: QRectF) -> QRectF:
        if self._pixmap.width() <= 0 or self._pixmap.height() <= 0:
            return QRectF()
        x_scale = self._image_rect.width() / self._pixmap.width()
        y_scale = self._image_rect.height() / self._pixmap.height()
        return QRectF(
            self._image_rect.left() + rect.left() * x_scale,
            self._image_rect.top() + rect.top() * y_scale,
            rect.width() * x_scale,
            rect.height() * y_scale,
        )

    def _handle_points(self, rect: QRectF) -> dict[str, QPointF]:
        center = rect.center()
        return {
            "nw": rect.topLeft(),
            "n": QPointF(center.x(), rect.top()),
            "ne": rect.topRight(),
            "e": QPointF(rect.right(), center.y()),
            "se": rect.bottomRight(),
            "s": QPointF(center.x(), rect.bottom()),
            "sw": rect.bottomLeft(),
            "w": QPointF(rect.left(), center.y()),
        }

    def _handle_at(self, point: QPointF) -> str:
        for name, handle_point in self._handle_points(self._image_to_widget_rect(self._selection)).items():
            if abs(point.x() - handle_point.x()) <= 10 and abs(point.y() - handle_point.y()) <= 10:
                return name
        return ""

    def _resized_selection(self, current: QPointF) -> QRectF:
        start = self._starting_selection.normalized()
        left, top, right, bottom = start.left(), start.top(), start.right(), start.bottom()
        handle = self._active_handle
        if "w" in handle:
            left = min(current.x(), right - 2)
        if "e" in handle:
            right = max(current.x(), left + 2)
        if "n" in handle:
            top = min(current.y(), bottom - 2)
        if "s" in handle:
            bottom = max(current.y(), top + 2)
        left = max(0.0, left)
        top = max(0.0, top)
        right = min(float(self._pixmap.width()), right)
        bottom = min(float(self._pixmap.height()), bottom)
        return QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()

    def _ensure_minimum_selection(self) -> None:
        selection = self.selection()
        width = min(self._pixmap.width(), max(2, selection["width"]))
        height = min(self._pixmap.height(), max(2, selection["height"]))
        left = min(selection["left"], self._pixmap.width() - width)
        top = min(selection["top"], self._pixmap.height() - height)
        self._selection = QRectF(
            float(left),
            float(top),
            float(width),
            float(height),
        )

    def _update_cursor(self, point: QPointF) -> None:
        handle = self._handle_at(point)
        cursors = {
            "nw": Qt.CursorShape.SizeFDiagCursor,
            "se": Qt.CursorShape.SizeFDiagCursor,
            "ne": Qt.CursorShape.SizeBDiagCursor,
            "sw": Qt.CursorShape.SizeBDiagCursor,
            "n": Qt.CursorShape.SizeVerCursor,
            "s": Qt.CursorShape.SizeVerCursor,
            "e": Qt.CursorShape.SizeHorCursor,
            "w": Qt.CursorShape.SizeHorCursor,
        }
        if handle:
            self.setCursor(cursors[handle])
        elif self._image_to_widget_rect(self._selection).contains(point):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)


class TemplateCropDialog(QDialog):
    def __init__(
        self,
        *,
        source_path: str,
        filter_name: str,
        monitor_summary: str,
        initial_region: dict[str, int],
        search_padding: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Make Template - {filter_name}")
        self.resize(1100, 760)
        self._pixmap = QPixmap(str(Path(source_path)))
        if self._pixmap.isNull():
            raise ValueError(f"Could not load the monitor screenshot: {source_path}")

        layout = QVBoxLayout(self)
        instructions = QLabel(
            "Drag over the exact battle text. Drag inside the yellow rectangle to move it, "
            "or drag a square handle to resize it. The darker area is only context and will not be saved."
        )
        instructions.setWordWrap(True)
        monitor_label = QLabel(monitor_summary)
        monitor_label.setWordWrap(True)

        self.selection_view = TemplateSelectionView(self._pixmap, initial_region)
        self.padding_spin = QSpinBox()
        self.padding_spin.setRange(0, 300)
        self.padding_spin.setValue(max(0, int(search_padding)))
        self.padding_spin.setSuffix(" px")
        self.padding_spin.setToolTip(
            "Extra area searched around the tight template. 20 pixels is a good starting point."
        )
        self.selection_label = QLabel()
        self.selection_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Search padding", self.padding_spin)
        form.addRow("Selection", self.selection_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save Template")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(instructions)
        layout.addWidget(monitor_label)
        layout.addWidget(self.selection_view, 1)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.selection_view.selection_changed.connect(self._refresh_summary)
        self.padding_spin.valueChanged.connect(self._refresh_summary)
        self._refresh_summary()

    def result_data(self) -> dict[str, object]:
        return {
            "template_region": self.selection_view.selection(),
            "search_padding": self.padding_spin.value(),
        }

    def _refresh_summary(self, _value=None) -> None:  # type: ignore[no-untyped-def]
        selected = self.selection_view.selection()
        search_region = expand_region(
            selected,
            padding=self.padding_spin.value(),
            bounds_width=self._pixmap.width(),
            bounds_height=self._pixmap.height(),
        )
        self.selection_label.setText(
            f"Template: left={selected['left']}, top={selected['top']}, "
            f"{selected['width']} x {selected['height']} px\n"
            f"Automatic search region: left={search_region['left']}, top={search_region['top']}, "
            f"{search_region['width']} x {search_region['height']} px"
        )
