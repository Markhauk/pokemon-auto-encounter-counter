from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import POST_DETECTION_COOLDOWN_SECONDS
from app.core.filters import FilterDefinition, GameDefinition
from app.services.app_controller import AppController

from .template_crop_dialog import TemplateCropDialog


class FiltersTab(QWidget):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self._games: list[GameDefinition] = []
        self._filters: list[FilterDefinition] = []
        self._selected_game_id = ""
        self._selected_filter_id = ""
        self._loading = False
        self._build_ui()
        self._connect_signals()
        self.refresh()

    def _build_ui(self) -> None:
        root_layout = QHBoxLayout(self)

        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        game_group = QGroupBox("Games")
        game_layout = QVBoxLayout(game_group)
        game_controls = QHBoxLayout()
        self.game_combo = QComboBox()
        self.add_game_button = QPushButton("Add Game")
        self.delete_game_button = QPushButton("Delete Game")
        game_controls.addWidget(self.game_combo, 1)
        game_controls.addWidget(self.add_game_button)
        game_controls.addWidget(self.delete_game_button)

        self.game_help_label = QLabel(
            "Select a game first. The filters list below only shows filters for the selected game."
        )
        self.game_help_label.setWordWrap(True)
        game_layout.addLayout(game_controls)
        game_layout.addWidget(self.game_help_label)

        self.filter_list = QListWidget()
        self.add_button = QPushButton("Add Filter")
        self.delete_button = QPushButton("Delete Filter")
        self.refresh_button = QPushButton("Refresh")

        left_panel.addWidget(game_group)
        left_panel.addWidget(QLabel("Configured Filters"))
        left_panel.addWidget(self.filter_list, 1)
        left_panel.addWidget(self.add_button)
        left_panel.addWidget(self.delete_button)
        left_panel.addWidget(self.refresh_button)

        editor_group = QGroupBox("Filter Details")
        editor_layout = QVBoxLayout(editor_group)
        form = QFormLayout()

        self.enabled_checkbox = QCheckBox("Enabled")
        self.game_name_value = QLabel("No game selected.")
        self.name_edit = QLineEdit()
        self.event_type_combo = QComboBox()
        for event_type in self.controller.get_filter_event_types():
            self.event_type_combo.addItem(event_type, event_type)
        self.template_path_edit = QLineEdit()
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.01, 1.0)
        self.threshold_spin.setDecimals(3)
        self.threshold_spin.setSingleStep(0.01)
        self.cooldown_spin = QDoubleSpinBox()
        self.cooldown_spin.setRange(0.0, 3600.0)
        self.cooldown_spin.setDecimals(1)
        self.cooldown_spin.setSingleStep(0.5)

        self.region_left_spin = QSpinBox()
        self.region_top_spin = QSpinBox()
        self.region_width_spin = QSpinBox()
        self.region_height_spin = QSpinBox()
        for spin in (self.region_left_spin, self.region_top_spin, self.region_width_spin, self.region_height_spin):
            spin.setRange(0, 10000)
        self.region_width_spin.setRange(1, 10000)
        self.region_height_spin.setRange(1, 10000)

        form.addRow("", self.enabled_checkbox)
        form.addRow("Game", self.game_name_value)
        form.addRow("Name", self.name_edit)
        form.addRow("Event type", self.event_type_combo)
        form.addRow("Template path", self.template_path_edit)
        form.addRow("Threshold", self.threshold_spin)
        form.addRow("Cooldown (seconds)", self.cooldown_spin)
        form.addRow("Region left", self.region_left_spin)
        form.addRow("Region top", self.region_top_spin)
        form.addRow("Region width", self.region_width_spin)
        form.addRow("Region height", self.region_height_spin)

        button_row = QHBoxLayout()
        self.save_filter_button = QPushButton("Save Filter")
        self.preview_button = QPushButton("Capture Preview")
        self.make_template_button = QPushButton("Make Template...")
        button_row.addWidget(self.save_filter_button)
        button_row.addWidget(self.preview_button)
        button_row.addWidget(self.make_template_button)

        self.filter_status_label = QLabel("No filter selected.")
        self.filter_status_label.setWordWrap(True)

        editor_layout.addLayout(form)
        editor_layout.addLayout(button_row)
        editor_layout.addWidget(self.filter_status_label)

        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel("Capture a preview for the selected filter.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(420, 240)
        self.preview_label.setStyleSheet("border: 1px solid #666;")
        self.preview_info = QLabel("No preview available.")
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_label)
        preview_layout.addWidget(self.preview_info)

        right_panel.addWidget(editor_group)
        right_panel.addWidget(preview_group, 1)

        root_layout.addLayout(left_panel, 1)
        root_layout.addLayout(right_panel, 2)

    def _connect_signals(self) -> None:
        self.game_combo.currentIndexChanged.connect(self._handle_game_changed)
        self.filter_list.currentItemChanged.connect(self._handle_selection_changed)
        self.add_game_button.clicked.connect(self._add_game)
        self.delete_game_button.clicked.connect(self._delete_game)
        self.add_button.clicked.connect(self._add_filter)
        self.delete_button.clicked.connect(self._delete_filter)
        self.refresh_button.clicked.connect(self.refresh)
        self.save_filter_button.clicked.connect(self._save_filter)
        self.preview_button.clicked.connect(self._capture_preview)
        self.make_template_button.clicked.connect(self._make_template)

        self.controller.config_changed.connect(self._handle_config_changed)
        self.controller.preview_captured.connect(self._handle_preview_captured)
        self.controller.error_occurred.connect(self._show_error)

    def refresh(self) -> None:
        self._games = self.controller.get_games()
        self._selected_game_id = self.controller.get_active_game_id()
        self._filters = self.controller.get_filters(game_id=self._selected_game_id)

        self._loading = True
        try:
            self.game_combo.clear()
            for game_definition in self._games:
                self.game_combo.addItem(game_definition.name, game_definition.id)

            selected_game_index = self.game_combo.findData(self._selected_game_id)
            if selected_game_index >= 0:
                self.game_combo.setCurrentIndex(selected_game_index)

            self.filter_list.clear()
            for filter_definition in self._filters:
                item = QListWidgetItem(filter_definition.name)
                item.setData(Qt.ItemDataRole.UserRole, filter_definition.id)
                if not filter_definition.enabled:
                    item.setText(f"{filter_definition.name} (Disabled)")
                self.filter_list.addItem(item)
        finally:
            self._loading = False

        self._refresh_game_controls()
        filter_id_to_select = self._selected_filter_id or (self._filters[0].id if self._filters else "")
        self._select_filter(filter_id_to_select)
        self._update_status_label()

    def _refresh_game_controls(self) -> None:
        current_game = self._current_game()
        has_game = current_game is not None
        self.add_button.setEnabled(has_game)
        self.delete_game_button.setEnabled(bool(current_game is not None and not current_game.built_in))
        self.game_name_value.setText(current_game.name if current_game is not None else "No game selected.")
        self.game_help_label.setText(
            "Select a game first. The filters list below only shows filters for the selected game."
            if has_game
            else "Create a game to start organizing filters."
        )

    def _select_filter(self, filter_id: str) -> None:
        self._selected_filter_id = filter_id
        for index in range(self.filter_list.count()):
            item = self.filter_list.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole)) == filter_id:
                self.filter_list.setCurrentRow(index)
                return
        self._populate_form(None)

    def _handle_game_changed(self, _index: int) -> None:
        if self._loading:
            return
        selected_game_id = str(self.game_combo.currentData() or "")
        if not selected_game_id:
            return
        self._selected_game_id = selected_game_id
        self._selected_filter_id = ""
        self.controller.set_active_game_id(selected_game_id)

    def _handle_selection_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if self._loading:
            return
        filter_id = str(current.data(Qt.ItemDataRole.UserRole)) if current is not None else ""
        self._selected_filter_id = filter_id
        self._populate_form(self._current_filter())
        self._update_status_label()

    def _current_game(self) -> GameDefinition | None:
        for game_definition in self._games:
            if game_definition.id == self._selected_game_id:
                return game_definition
        return None

    def _current_filter(self) -> FilterDefinition | None:
        for filter_definition in self._filters:
            if filter_definition.id == self._selected_filter_id:
                return filter_definition
        return None

    def _populate_form(self, filter_definition: FilterDefinition | None) -> None:
        self._loading = True
        try:
            if filter_definition is None:
                self.enabled_checkbox.setChecked(False)
                self.name_edit.clear()
                self.template_path_edit.clear()
                self.threshold_spin.setValue(0.85)
                self.cooldown_spin.setValue(POST_DETECTION_COOLDOWN_SECONDS)
                self.region_left_spin.setValue(0)
                self.region_top_spin.setValue(0)
                self.region_width_spin.setValue(1)
                self.region_height_spin.setValue(1)
                self.event_type_combo.setCurrentIndex(0)
                self.delete_button.setEnabled(False)
                return

            self.enabled_checkbox.setChecked(filter_definition.enabled)
            self.name_edit.setText(filter_definition.name)
            self.template_path_edit.setText(filter_definition.template_path)
            self.threshold_spin.setValue(filter_definition.threshold)
            self.cooldown_spin.setValue(filter_definition.cooldown_seconds)
            event_index = self.event_type_combo.findData(filter_definition.event_type)
            if event_index >= 0:
                self.event_type_combo.setCurrentIndex(event_index)

            region = filter_definition.capture_region
            self.region_left_spin.setValue(int(region["left"]))
            self.region_top_spin.setValue(int(region["top"]))
            self.region_width_spin.setValue(int(region["width"]))
            self.region_height_spin.setValue(int(region["height"]))
            self.delete_button.setEnabled(not filter_definition.built_in)
        finally:
            self._loading = False

    def _save_filter(self) -> None:
        filter_definition = self._current_filter()
        if filter_definition is None:
            return

        metadata = dict(filter_definition.metadata)
        metadata["game_id"] = self._selected_game_id
        updated_filter = FilterDefinition(
            id=filter_definition.id,
            name=self.name_edit.text().strip() or filter_definition.name,
            enabled=self.enabled_checkbox.isChecked(),
            event_type=str(self.event_type_combo.currentData()),
            template_path=self.template_path_edit.text().strip() or filter_definition.template_path,
            capture_region={
                "left": self.region_left_spin.value(),
                "top": self.region_top_spin.value(),
                "width": self.region_width_spin.value(),
                "height": self.region_height_spin.value(),
            },
            threshold=float(self.threshold_spin.value()),
            cooldown_seconds=float(self.cooldown_spin.value()),
            built_in=filter_definition.built_in,
            description=filter_definition.description,
            metadata=metadata,
        )
        self.controller.save_filter(updated_filter)
        self._selected_filter_id = updated_filter.id
        self.refresh()

    def _add_game(self) -> None:
        name, accepted = QInputDialog.getText(self, "Add Game", "Game name:")
        if not accepted:
            return
        game_name = name.strip()
        if not game_name:
            self._show_error("Game name cannot be empty.")
            return
        game_definition = self.controller.create_game(name=game_name)
        self._selected_game_id = game_definition.id
        self._selected_filter_id = ""
        self.refresh()

    def _delete_game(self) -> None:
        game_definition = self._current_game()
        if game_definition is None or game_definition.built_in:
            return

        response = QMessageBox.question(
            self,
            "Delete Game",
            f"Delete '{game_definition.name}' and all of its filters?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        try:
            self.controller.delete_game(game_definition.id)
        except Exception as exc:
            self._show_error(str(exc))
            return

        self._selected_filter_id = ""
        self.refresh()

    def _add_filter(self) -> None:
        if not self._selected_game_id:
            self._show_error("Select a game before adding filters.")
            return
        filter_definition = self.controller.create_filter(game_id=self._selected_game_id)
        self._selected_filter_id = filter_definition.id
        self.refresh()

    def _delete_filter(self) -> None:
        filter_definition = self._current_filter()
        if filter_definition is None or filter_definition.built_in:
            return
        self.controller.delete_filter(filter_definition.id)
        self._selected_filter_id = ""
        self.refresh()

    def _capture_preview(self) -> None:
        filter_definition = self._current_filter()
        if filter_definition is None:
            return
        self._save_filter()
        refreshed_filter = self.controller.get_filter(filter_definition.id)
        if refreshed_filter is None:
            return
        try:
            payload = self.controller.capture_test_screenshot(filter_definition=refreshed_filter)
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._apply_preview(payload)

    def _make_template(self) -> None:
        filter_definition = self._current_filter()
        if filter_definition is None:
            return
        self._save_filter()
        try:
            source = self.controller.capture_template_source(filter_definition.id)
        except Exception as exc:
            self._show_error(str(exc))
            return

        try:
            dialog = TemplateCropDialog(
                source_path=str(source["source_path"]),
                filter_name=str(source["filter_name"]),
                monitor_summary=str(source["monitor_summary"]),
                initial_region=dict(source["initial_region"]),  # type: ignore[arg-type]
                search_padding=int(source["search_padding"]),
                parent=self,
            )
        except Exception as exc:
            self._show_error(str(exc))
            return

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result_data = dialog.result_data()
        try:
            result = self.controller.save_template_crop(
                filter_id=filter_definition.id,
                template_region=dict(result_data["template_region"]),  # type: ignore[arg-type]
                search_padding=int(result_data["search_padding"]),
            )
        except Exception as exc:
            self._show_error(str(exc))
            return

        QMessageBox.information(
            self,
            "Template Saved",
            f"Template: {result['path']}\n"
            f"Template region: {result['template_region']}\n"
            f"Search region: {result['capture_region']}",
        )
        self.refresh()

    def _update_status_label(self) -> None:
        filter_definition = self._current_filter()
        game_definition = self._current_game()
        if filter_definition is None:
            self.filter_status_label.setText("No filter selected.")
            return

        template_status = next(
            (
                status
                for status in self.controller.get_template_statuses(game_id=self._selected_game_id)
                if status.filter_id == filter_definition.id
            ),
            None,
        )
        if template_status is None:
            self.filter_status_label.setText("Template status unavailable.")
            return

        lines = [
            f"Game: {game_definition.name if game_definition is not None else self._selected_game_id}",
            f"ID: {filter_definition.id}",
            f"Event type: {filter_definition.event_type}",
            f"Cooldown: {filter_definition.cooldown_seconds:.1f}s",
            f"Template status: {template_status.status_label()}",
            f"Template path: {template_status.path}",
        ]
        if template_status.error:
            lines.append(f"Note: {template_status.error}")
        if filter_definition.built_in:
            lines.append("Built-in filter: yes")
        self.filter_status_label.setText("\n".join(lines))

    def _handle_preview_captured(self, payload: dict[str, object]) -> None:
        if str(payload.get("filter_id", "")) != self._selected_filter_id:
            return
        self._apply_preview(payload)

    def _apply_preview(self, payload: dict[str, object]) -> None:
        preview_path = Path(str(payload.get("path", self.controller.get_debug_frame_path())))
        self._load_pixmap(preview_path)
        template_match = payload.get("template_match", {})
        if isinstance(template_match, dict) and template_match.get("available"):
            calibration = (
                f"Live template score: {float(template_match.get('score', 0.0)):.3f} "
                f"(threshold {float(template_match.get('threshold', 0.0)):.3f}, "
                f"found={bool(template_match.get('found', False))})"
            )
        elif isinstance(template_match, dict):
            calibration = f"Live template score unavailable: {template_match.get('error', 'unknown reason')}"
        else:
            calibration = "Live template score unavailable."

        self.preview_info.setText(
            f"Filter: {payload.get('filter_name', '')}\n"
            f"Event type: {payload.get('event_type', '')}\n"
            f"Relative region: {payload.get('region', {})}\n"
            f"Absolute region: {payload.get('absolute_region', {})}\n"
            f"Monitor: {payload.get('monitor_summary', '')}\n"
            f"Stats: {payload.get('stats', {})}\n"
            f"{calibration}"
        )

    def _load_pixmap(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview_label.setText(f"Could not load preview image from {path}")
            return
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        preview_path = Path(self.controller.get_debug_frame_path())
        if preview_path.exists():
            self._load_pixmap(preview_path)

    def _handle_config_changed(self, _config: dict[str, object]) -> None:
        self.refresh()

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Filters", message)
