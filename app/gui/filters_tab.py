from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
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
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import POST_DETECTION_COOLDOWN_SECONDS
from app.core.filters import FilterDefinition, GameDefinition
from app.services.app_controller import AppController

from .frame_styles import mark_as_interface_frame
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
        self._preview_path: Path | None = None
        self._preview_request_number = 0
        self._preview_pending_when_shown = False
        self._displayed_filter_id = ""
        self._build_ui()
        self._connect_signals()
        self.refresh()

    def _build_ui(self) -> None:
        root_layout = QHBoxLayout(self)

        workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        workspace_splitter.setChildrenCollapsible(False)

        self.library_group = QGroupBox("Filter Library")
        mark_as_interface_frame(self.library_group)
        library_layout = QVBoxLayout(self.library_group)

        library_layout.addWidget(QLabel("Game"))
        self.game_combo = QComboBox()
        self.game_combo.setMinimumWidth(250)
        library_layout.addWidget(self.game_combo)

        game_button_row = QHBoxLayout()
        self.add_game_button = QPushButton("New Game")
        self.delete_game_button = QPushButton("Remove Game")
        game_button_row.addWidget(self.add_game_button)
        game_button_row.addWidget(self.delete_game_button)
        library_layout.addLayout(game_button_row)

        self.game_help_label = QLabel(
            "Choose or create a game to manage its filters."
        )
        self.game_help_label.setWordWrap(True)
        self.game_help_label.setVisible(False)
        library_layout.addWidget(self.game_help_label)

        filter_header_row = QHBoxLayout()
        filter_header = QLabel("Filters")
        filter_header.setStyleSheet("font-weight: 600;")
        self.filter_count_label = QLabel("0")
        self.filter_count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.filter_count_label.setStyleSheet("color: #b8b8b8;")
        filter_header_row.addWidget(filter_header)
        filter_header_row.addWidget(self.filter_count_label, 1)
        library_layout.addLayout(filter_header_row)

        self.filter_list = QListWidget()
        self.filter_list.setMinimumWidth(250)
        self.filter_list.setSpacing(2)
        library_layout.addWidget(self.filter_list, 1)

        self.add_button = QPushButton("New Filter")
        self.delete_button = QPushButton("Remove Filter")
        filter_button_row = QHBoxLayout()
        filter_button_row.addWidget(self.add_button)
        filter_button_row.addWidget(self.delete_button)
        library_layout.addLayout(filter_button_row)

        self.workspace_group = QGroupBox("Selected Filter")
        mark_as_interface_frame(self.workspace_group)
        workspace_layout = QVBoxLayout(self.workspace_group)

        editor_heading_row = QHBoxLayout()
        editor_heading_text = QVBoxLayout()
        self.selected_filter_heading = QLabel("Select a filter to continue")
        self.selected_filter_heading.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.game_name_value = QLabel("No game selected.")
        self.game_name_value.setStyleSheet("color: #b8b8b8;")
        editor_heading_text.addWidget(self.selected_filter_heading)
        editor_heading_text.addWidget(self.game_name_value)
        self.enabled_state_label = QLabel("")
        self.enabled_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor_heading_row.addLayout(editor_heading_text, 1)
        editor_heading_row.addWidget(self.enabled_state_label)
        workspace_layout.addLayout(editor_heading_row)

        self.workspace_tabs = QTabWidget()
        workspace_layout.addWidget(self.workspace_tabs, 1)

        self.preview_tab = QWidget()
        preview_layout = QVBoxLayout(self.preview_tab)

        self.filter_status_label = QLabel("Select a filter to check its template.")
        self.filter_status_label.setWordWrap(True)
        self.filter_status_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        preview_layout.addWidget(self.filter_status_label)

        self.preview_label = QLabel("Select a filter to capture its screen area.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(420, 260)
        self.preview_label.setStyleSheet("border: 1px solid #666;")
        preview_layout.addWidget(self.preview_label, 1)

        self.preview_info = QLabel("No preview available.")
        self.preview_info.setWordWrap(True)
        self.preview_info.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        preview_layout.addWidget(self.preview_info)

        preview_button_row = QHBoxLayout()
        self.make_template_button = QPushButton("Make Template...")
        self.preview_button = QPushButton("Refresh Preview")
        preview_button_row.addWidget(self.make_template_button)
        preview_button_row.addWidget(self.preview_button)
        preview_button_row.addStretch(1)
        preview_layout.addLayout(preview_button_row)

        self.settings_tab = QWidget()
        settings_layout = QVBoxLayout(self.settings_tab)

        form = QFormLayout()
        self.enabled_checkbox = QCheckBox("Use this filter while scanning")
        self.name_edit = QLineEdit()
        self.event_type_combo = QComboBox()
        event_type_labels = {
            "encounter_start": "Encounter starts (add encounters)",
            "catch": "Pokemon caught (add encounters and a catch)",
            "fled": "Pokemon fled (add encounters)",
            "info": "Information only (do not count)",
            "label": "Set active label (do not count)",
        }
        for event_type in self.controller.get_filter_event_types():
            self.event_type_combo.addItem(event_type_labels.get(event_type, event_type), event_type)
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.01, 1.0)
        self.threshold_spin.setDecimals(3)
        self.threshold_spin.setSingleStep(0.01)
        self.threshold_spin.setToolTip(
            "How closely the live capture must match the template. Higher values are stricter."
        )
        self.cooldown_spin = QDoubleSpinBox()
        self.cooldown_spin.setRange(0.0, 3600.0)
        self.cooldown_spin.setDecimals(1)
        self.cooldown_spin.setSingleStep(0.5)
        self.cooldown_spin.setSuffix(" s")
        self.cooldown_spin.setToolTip(
            "How long this filter waits after a match before it can count again."
        )

        form.addRow("Scanning", self.enabled_checkbox)
        form.addRow("Name", self.name_edit)
        form.addRow("When matched", self.event_type_combo)
        form.addRow("Threshold", self.threshold_spin)
        form.addRow("Cooldown", self.cooldown_spin)
        settings_layout.addLayout(form)

        self.advanced_toggle = QPushButton("Show advanced settings")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolTip(
            "Show the template filename and exact capture coordinates. Most users can leave these hidden."
        )
        settings_layout.addWidget(self.advanced_toggle)

        self.advanced_widget = QWidget()
        advanced_form = QFormLayout(self.advanced_widget)
        advanced_form.setContentsMargins(12, 4, 0, 4)
        self.template_path_edit = QLineEdit()

        self.region_left_spin = QSpinBox()
        self.region_top_spin = QSpinBox()
        self.region_width_spin = QSpinBox()
        self.region_height_spin = QSpinBox()
        for spin in (self.region_left_spin, self.region_top_spin, self.region_width_spin, self.region_height_spin):
            spin.setRange(0, 10000)
        self.region_width_spin.setRange(1, 10000)
        self.region_height_spin.setRange(1, 10000)

        advanced_form.addRow("Template filename", self.template_path_edit)
        advanced_form.addRow("Capture left (px)", self.region_left_spin)
        advanced_form.addRow("Capture top (px)", self.region_top_spin)
        advanced_form.addRow("Capture width (px)", self.region_width_spin)
        advanced_form.addRow("Capture height (px)", self.region_height_spin)
        self.advanced_widget.setVisible(False)
        settings_layout.addWidget(self.advanced_widget)

        button_row = QHBoxLayout()
        self.save_filter_button = QPushButton("Save Filter")
        button_row.addStretch(1)
        button_row.addWidget(self.save_filter_button)
        settings_layout.addStretch(1)
        settings_layout.addLayout(button_row)

        self.workspace_tabs.addTab(self.preview_tab, "Preview")
        self.workspace_tabs.addTab(self.settings_tab, "Settings")

        workspace_splitter.addWidget(self.library_group)
        workspace_splitter.addWidget(self.workspace_group)
        workspace_splitter.setStretchFactor(0, 1)
        workspace_splitter.setStretchFactor(1, 3)
        workspace_splitter.setSizes([280, 920])
        root_layout.addWidget(workspace_splitter)

    def _connect_signals(self) -> None:
        self.game_combo.currentIndexChanged.connect(self._handle_game_changed)
        self.filter_list.currentItemChanged.connect(self._handle_selection_changed)
        self.add_game_button.clicked.connect(self._add_game)
        self.delete_game_button.clicked.connect(self._delete_game)
        self.add_button.clicked.connect(self._add_filter)
        self.delete_button.clicked.connect(self._delete_filter)
        self.save_filter_button.clicked.connect(self._save_filter)
        self.preview_button.clicked.connect(self._capture_preview)
        self.make_template_button.clicked.connect(self._make_template)
        self.advanced_toggle.toggled.connect(self._toggle_advanced_settings)

        self.controller.config_changed.connect(self._handle_config_changed)
        self.controller.preview_captured.connect(self._handle_preview_captured)
        self.controller.error_occurred.connect(self._show_error)

    def refresh(self) -> None:
        self._games = self.controller.get_games()
        self._selected_game_id = self.controller.get_active_game_id()
        self._filters = self.controller.get_filters(game_id=self._selected_game_id)
        template_statuses = {
            status.filter_id: status
            for status in self.controller.get_template_statuses(game_id=self._selected_game_id)
        }

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
                template_status = template_statuses.get(filter_definition.id)
                enabled_text = "Enabled" if filter_definition.enabled else "Disabled"
                template_text = (
                    "Template ready"
                    if template_status is not None and template_status.status_label() == "Found"
                    else "Template missing"
                )
                item = QListWidgetItem(filter_definition.name)
                item.setData(Qt.ItemDataRole.UserRole, filter_definition.id)
                item.setToolTip(
                    f"{filter_definition.name}\n"
                    f"Counts as: {filter_definition.event_type}\n"
                    f"{template_text}"
                )
                self.filter_list.addItem(item)
        finally:
            self._loading = False

        self._refresh_game_controls()
        self.filter_count_label.setText(str(len(self._filters)))
        filter_id_to_select = self._selected_filter_id or (self._filters[0].id if self._filters else "")
        self._select_filter(
            filter_id_to_select,
            open_preview=filter_id_to_select != self._displayed_filter_id,
        )

    def _refresh_game_controls(self) -> None:
        current_game = self._current_game()
        has_game = current_game is not None
        self.add_button.setEnabled(has_game)
        self.filter_list.setEnabled(has_game)
        self.delete_game_button.setEnabled(bool(current_game is not None and not current_game.built_in))
        self.game_name_value.setText(
            f"Game: {current_game.name}" if current_game is not None else "No game selected."
        )
        self.game_help_label.setText(
            "Choose or create a game to manage its filters."
        )
        self.game_help_label.setVisible(not has_game)

    def _select_filter(self, filter_id: str, *, open_preview: bool) -> None:
        self._selected_filter_id = filter_id
        for index in range(self.filter_list.count()):
            item = self.filter_list.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole)) == filter_id:
                self._loading = True
                try:
                    self.filter_list.setCurrentRow(index)
                finally:
                    self._loading = False
                self._activate_selected_filter(open_preview=open_preview)
                return
        self.filter_list.clearSelection()
        self._activate_selected_filter(open_preview=open_preview)

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
        self._activate_selected_filter(open_preview=True)

    def _activate_selected_filter(self, *, open_preview: bool) -> None:
        filter_definition = self._current_filter()
        self._displayed_filter_id = filter_definition.id if filter_definition is not None else ""
        self._populate_form(filter_definition)
        self._update_status_label()
        self._clear_preview(filter_definition)
        if filter_definition is not None:
            if open_preview:
                self.workspace_tabs.setCurrentWidget(self.preview_tab)
            self._queue_automatic_preview(filter_definition.id)

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
                self.workspace_group.setEnabled(False)
                self.selected_filter_heading.setText("Select a filter to continue")
                self.enabled_state_label.clear()
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
                self.preview_button.setEnabled(False)
                self.make_template_button.setEnabled(False)
                self.save_filter_button.setEnabled(False)
                return

            self.workspace_group.setEnabled(True)
            self.selected_filter_heading.setText(filter_definition.name)
            self.enabled_state_label.setText("Enabled" if filter_definition.enabled else "Disabled")
            self.enabled_state_label.setStyleSheet(
                "padding: 4px 8px; border-radius: 3px; "
                + (
                    "color: #d8f3dc; background-color: #23382a;"
                    if filter_definition.enabled
                    else "color: #c8c8c8; background-color: #3a3a3a;"
                )
            )
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
            self.preview_button.setEnabled(True)
            self.make_template_button.setEnabled(True)
            self.save_filter_button.setEnabled(True)
        finally:
            self._loading = False

    def _save_filter(self) -> FilterDefinition | None:
        filter_definition = self._current_filter()
        if filter_definition is None:
            return None

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
        self._selected_filter_id = updated_filter.id
        self.controller.save_filter(updated_filter)
        return self.controller.get_filter(updated_filter.id)

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
        self.workspace_tabs.setCurrentWidget(self.settings_tab)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _delete_filter(self) -> None:
        filter_definition = self._current_filter()
        if filter_definition is None or filter_definition.built_in:
            return
        self.controller.delete_filter(filter_definition.id)
        self._selected_filter_id = ""
        self.refresh()

    def _capture_preview(self) -> None:
        self._preview_request_number += 1
        refreshed_filter = self._save_filter()
        if refreshed_filter is None:
            return
        self._preview_request_number += 1
        self._capture_preview_for_filter(refreshed_filter.id, show_error_dialog=True)

    def _capture_preview_for_filter(self, filter_id: str, *, show_error_dialog: bool) -> None:
        if filter_id != self._selected_filter_id:
            return
        if self.controller.is_running():
            self.preview_label.clear()
            self.preview_label.setText("Stop scanning to refresh this preview.")
            self.preview_info.setText(
                "The saved preview and filter settings remain available while the scanner is running."
            )
            return
        filter_definition = self.controller.get_filter(filter_id)
        if filter_definition is None:
            return
        self.preview_label.clear()
        self.preview_label.setText("Capturing the selected screen area...")
        self.preview_info.setText("Checking the capture area and template match.")
        try:
            payload = self.controller.capture_test_screenshot(filter_definition=filter_definition)
        except Exception as exc:
            self.preview_label.clear()
            self.preview_label.setText("Preview could not be captured.")
            self.preview_info.setText(
                f"{exc}\n\nCheck the selected capture monitor, then try Refresh Preview."
            )
            if show_error_dialog:
                self._show_error(str(exc))
            return
        self._apply_preview(payload)

    def _queue_automatic_preview(self, filter_id: str) -> None:
        self._preview_request_number += 1
        request_number = self._preview_request_number
        if not self.isVisible():
            self._preview_pending_when_shown = True
            return

        self._preview_pending_when_shown = False

        def capture_if_current() -> None:
            if request_number != self._preview_request_number or filter_id != self._selected_filter_id:
                return
            if not self.isVisible():
                self._preview_pending_when_shown = True
                return
            self._capture_preview_for_filter(filter_id, show_error_dialog=False)

        QTimer.singleShot(150, capture_if_current)

    def _clear_preview(self, filter_definition: FilterDefinition | None) -> None:
        self._preview_path = None
        self.preview_label.clear()
        if filter_definition is None:
            self.preview_label.setText("Select a filter to capture its screen area.")
            self.preview_info.setText("No preview available.")
            return
        self.preview_label.setText("Preparing a live preview...")
        self.preview_info.clear()

    def _make_template(self) -> None:
        filter_definition = self._current_filter()
        if filter_definition is None:
            return
        refreshed_filter = self._save_filter()
        if refreshed_filter is None:
            return
        self._preview_request_number += 1
        try:
            source = self.controller.capture_template_source(refreshed_filter.id)
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
                filter_id=refreshed_filter.id,
                template_region=dict(result_data["template_region"]),  # type: ignore[arg-type]
                search_padding=int(result_data["search_padding"]),
            )
        except Exception as exc:
            self._show_error(str(exc))
            return

        # Do not let the automatic preview run while this modal confirmation is
        # covering the game window. A fresh preview is queued after it closes.
        self._preview_request_number += 1
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
        if filter_definition is None:
            self.filter_status_label.setText("Select a filter to check its template.")
            self.filter_status_label.setStyleSheet(
                "padding: 8px; border: 1px solid #666; border-radius: 3px;"
            )
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
            self.make_template_button.setText("Make Template...")
            return

        status = template_status.status_label()
        if status == "Found":
            self.filter_status_label.setText(
                f"Template ready: {filter_definition.template_path}"
            )
            self.make_template_button.setText("Replace Template...")
            self.filter_status_label.setStyleSheet(
                "padding: 6px; color: #d8f3dc; background-color: #23382a; "
                "border: 1px solid #5fbf70; border-radius: 3px;"
            )
        else:
            issue = template_status.error or "No usable template image was found."
            self.filter_status_label.setText(
                f"Template {status.lower()}: {filter_definition.template_path}. {issue}"
            )
            self.make_template_button.setText("Make Template...")
            self.filter_status_label.setStyleSheet(
                "padding: 6px; color: #fff0c2; background-color: #45381f; "
                "border: 1px solid #d9a441; border-radius: 3px;"
            )

    def _handle_preview_captured(self, payload: dict[str, object]) -> None:
        if str(payload.get("filter_id", "")) != self._selected_filter_id:
            return
        self._apply_preview(payload)

    def _apply_preview(self, payload: dict[str, object]) -> None:
        preview_path = Path(str(payload.get("path", self.controller.get_debug_frame_path())))
        self._preview_path = preview_path
        self._load_pixmap(preview_path)
        template_match = payload.get("template_match", {})
        if isinstance(template_match, dict) and template_match.get("available"):
            score = float(template_match.get("score", 0.0))
            threshold = float(template_match.get("threshold", 0.0))
            match_result = "detected" if bool(template_match.get("found", False)) else "not detected"
            calibration = (
                f"Template check: {match_result} (score {score:.3f}, required {threshold:.3f})"
            )
        elif isinstance(template_match, dict):
            calibration = (
                "Template check unavailable: "
                f"{template_match.get('error', 'unknown reason')}. "
                "Use Make Template if one has not been created yet."
            )
        else:
            calibration = "Template check unavailable."

        region = payload.get("region", {})
        if isinstance(region, dict):
            capture_size = f"{region.get('width', 0)} x {region.get('height', 0)} pixels"
        else:
            capture_size = "Unknown size"
        stats = payload.get("stats", {})
        brightness = ""
        if isinstance(stats, dict):
            brightness = f" | average brightness {float(stats.get('mean', 0.0)):.1f}"
        self.preview_info.setText(
            f"Captured area: {capture_size} on {payload.get('monitor_summary', 'the selected monitor')}"
            f"{brightness}\n"
            f"{calibration}"
        )

    def _load_pixmap(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview_label.clear()
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
        if self._preview_path is not None and self._preview_path.exists():
            self._load_pixmap(self._preview_path)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        if self._preview_pending_when_shown and self._selected_filter_id:
            self._queue_automatic_preview(self._selected_filter_id)

    def _toggle_advanced_settings(self, visible: bool) -> None:
        self.advanced_widget.setVisible(visible)
        self.advanced_toggle.setText(
            "Hide advanced settings" if visible else "Show advanced settings"
        )

    def _handle_config_changed(self, _config: dict[str, object]) -> None:
        self.refresh()

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Filters", message)
