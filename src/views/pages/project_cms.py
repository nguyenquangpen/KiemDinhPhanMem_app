from functools import partial
from typing import List, Dict, Optional

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from asset import tokens
from models.data_classes import Project, User
from models.database import DataManager
from services.logging_config import get_logger
from views.components import icons, ui_kit
from views.components.table import (
    ActionColumnConfig,
    BaseColumnConfig,
    DataTableWidget,
    IndexColumnConfig,
    NumberCalculation,
    NumberColumnConfig,
    SelectColumnConfig,
    SelectType,
    TableModel,
    TextColumnConfig,
)
from pathlib import Path

logger = get_logger("project_cms")


class ProjectDialog(QDialog):
    """A dialog for creating or editing a project with all its fields."""

    def __init__(self, project: Optional[Project] = None, parent=None):
        super().__init__(parent)
        self.project = project
        self.is_edit_mode = self.project is not None

        self.setWindowTitle(
            "Edit Project" if self.is_edit_mode else "Create New Project"
        )

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 20)
        self.main_layout.setSpacing(14)
        self.form_layout = QVBoxLayout()
        self.form_layout.setSpacing(12)

        # Create input fields
        self.name_edit = QLineEdit(self)
        self.url_edit = QLineEdit(self)
        self.description_edit = QLineEdit(self)
        self.login_id_edit = QLineEdit(self)
        self.password_edit = QLineEdit(self)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        # Updated placeholders to indicate all fields are required
        self.name_edit.setPlaceholderText("Project name (Required)")
        self.url_edit.setPlaceholderText("Project URL (Required)")
        self.description_edit.setPlaceholderText("Brief description (Optional)")
        self.login_id_edit.setPlaceholderText("Login username (Optional)")

        if self.is_edit_mode:
            self.password_edit.setPlaceholderText(
                "Leave blank to keep current password"
            )
        else:
            self.password_edit.setPlaceholderText("Login password (Optional)")

        # Labels sit above their inputs
        self.main_layout.addWidget(
            ui_kit.label("Edit project" if self.is_edit_mode else "New project", "CardTitle")
        )
        self.main_layout.addWidget(
            ui_kit.label("The AI agent uses the login details before each run.", "MutedText", wrap=True)
        )
        self.form_layout.addWidget(ui_kit.field("Project name", self.name_edit))
        self.form_layout.addWidget(ui_kit.field("Login URL", self.url_edit))
        self.form_layout.addWidget(ui_kit.field("Description", self.description_edit))
        credentials = QHBoxLayout()
        credentials.setSpacing(12)
        credentials.addWidget(ui_kit.field("Login ID", self.login_id_edit))
        credentials.addWidget(ui_kit.field("Password", self.password_edit))
        self.form_layout.addLayout(credentials)

        # Standard dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Save changes" if self.is_edit_mode else "Create project")
        ok_btn.setObjectName("PrimaryButton")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # Connect all fields to the validation method
        self.name_edit.textChanged.connect(self._validate_inputs)
        self.url_edit.textChanged.connect(self._validate_inputs)
        self.description_edit.textChanged.connect(self._validate_inputs)

        self.main_layout.addLayout(self.form_layout)
        self.main_layout.addSpacing(6)
        self.main_layout.addWidget(self.button_box)
        self.setMinimumWidth(480)

        # Populate fields if in edit mode
        if self.is_edit_mode and self.project:
            self.name_edit.setText(self.project.name)
            self.url_edit.setText(self.project.url or "")
            self.description_edit.setText(self.project.description or "")
            self.login_id_edit.setText(self.project.login_id or "")
            # Do not populate password for security

        # Set initial button state based on current field values
        self._validate_inputs()

    def _validate_inputs(self):
        """
        Checks if all *required* fields are filled and enables/disables the OK button.
        """
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if not ok_button:
            return

        is_valid = all(
            [
                self.name_edit.text().strip(),
                self.url_edit.text().strip(),
            ]
        )

        ok_button.setEnabled(is_valid)

    def get_data(self) -> Dict[str, str]:
        data = {
            "name": self.name_edit.text().strip(),
            "url": self.url_edit.text().strip(),
            "description": self.description_edit.text().strip(),
        }

        login_id = self.login_id_edit.text().strip()
        if login_id:
            data["login_id"] = login_id

        password = self.password_edit.text()
        if password:
            data["password"] = password

        return data


class LoadProjectsWorkerSignals(QObject):
    finished = Signal(list)
    error = Signal(str)


class LoadProjectsWorker(QRunnable):
    def __init__(self, db: DataManager):
        super().__init__()
        self.db = db
        self.signals = LoadProjectsWorkerSignals()

    @Slot()
    def run(self):
        try:
            projects = self.db.get_all_projects_sync()
            self.signals.finished.emit(projects)
        except Exception as e:
            self.signals.error.emit(str(e))


class ProjectCMS(QWidget):
    project_selected = Signal(Project)
    project_created = Signal(Project)
    project_edit = Signal(Project)

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self.db = data_manager

        self.all_projects: List[Project] = []
        self.displayed_projects: List[Project] = []
        self.project_id_map: Dict[str, Project] = {}
        self.ng_only = False

        self.thread_pool = QThreadPool.globalInstance()
        self._configure_table_columns()
        self.table_model = TableModel([])
        self.table_widget = DataTableWidget(
            self.column_configs,
            self.table_model,
            items_per_page=15,
            item_height=52,
            header_height=46,
            highlight_selected_row=True,
        )
        self.setObjectName("PageWidget")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._build_ui()
        self._connect_signals()
        QTimer.singleShot(0, self.refresh_data_async)
        self._connect_global_signals()
    
    def _connect_global_signals(self):
        # self.db.signals.project_edited.connect(self.refresh_data_async)
        if hasattr(self.db.signals, 'current_user_changed'):
            self.db.signals.current_user_changed.connect(self._on_auth_state_changed)
        # self.search_edit.textChanged.connect(self._handle_search)
        # self.ui.newProjectButton.clicked.connect(self._handle_project_create)
    
    def _on_auth_state_changed(self, user):
        """Handling when login status changes"""
        if user:
            self.refresh_data_async()
        else:
            self.all_projects = []
            self.populate_table([])
            self._update_total_cards([])

    def showEvent(self, event):
        super().showEvent(event)
        logger.debug("ProjectCMS is now visible, refreshing data.")
        self.refresh_data_async()

    def refresh_data_async(self):
        current_user = self.db.get_all_projects_sync()
        if not current_user:
            logger.warning("refresh_data_async called but NO USER logged in. Skipping.")
            return

        worker = LoadProjectsWorker(self.db)
        worker.signals.finished.connect(self._on_data_loaded)
        worker.signals.error.connect(self._on_data_load_error)
        self.thread_pool.start(worker)

    def _on_data_loaded(self, projects: list[Project]):
        self.all_projects = projects
        self.project_id_map = {p.project_id: p for p in projects if p.project_id}
        self.populate_table(projects)
        self._update_total_cards(projects)
        if not projects:
            logger.info("ℹ️ Project list is empty. This might be a new user.")

    def _on_data_load_error(self, message: str):
        logger.error(f"Error loading projects: {message}")
        QMessageBox.critical(self, "Error", f"Failed to load projects: {message}")
        self.all_projects = []
        self.project_id_map = {}
        self.populate_table([])
        self._update_total_cards([])

    def populate_table(self, projects: list[Project]):
        if self.ng_only:
            projects = [p for p in projects if (p.ng_testcase_count or 0) > 0]
        self.displayed_projects = projects
        table_data = [
            [
                None,  # IndexColumnConfig - widget generates this
                p.name,
                p.total_testcase_count or 0,
                p.executed_testcase_count or 0,
                p.ok_testcase_count or 0,
                p.ng_testcase_count or 0,
                (p.executed_testcase_count or 0, p.total_testcase_count or 0, p.ng_testcase_count or 0),
                None,  # ActionColumnConfig
            ]
            for p in projects
        ]
        self.table_widget.blockSignals(True)
        self.table_model.set_data(table_data)
        self.table_widget.blockSignals(False)

    # ------------------------------------------------------------------ layout
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(24)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("SearchLineEdit")
        self.search_edit.setPlaceholderText("Search project...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(
            icons.icon("search", tokens.TEXT_MUTED, 16), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_edit.setFixedWidth(280)
        self.new_project_button = ui_kit.button("New project", "primary", "plus")
        root.addWidget(
            ui_kit.page_header(
                "Projects",
                "Choose a project to open it in Test Studio.",
                [self.search_edit, self.new_project_button],
            )
        )

        body = QHBoxLayout()
        body.setSpacing(24)
        body.addWidget(self.table_widget, 1)

        side = QVBoxLayout()
        side.setSpacing(24)
        side.addWidget(self._build_overview_card())
        side.addWidget(self._build_last_opened_card())
        side.addStretch(1)
        side_box = QWidget()
        side_box.setLayout(side)
        side_box.setFixedWidth(280)
        side.setContentsMargins(0, 0, 0, 0)
        body.addWidget(side_box)
        root.addLayout(body, 1)

    def _build_overview_card(self) -> QWidget:
        card = ui_kit.Card(padding=0, spacing=0)
        self.overview_head = ui_kit.centered_header("Total test cases", "0", "across 0 projects", big_role="HeroNumber")
        card.body.addWidget(self.overview_head)

        stats = ui_kit.CardSection(padding=(24, 18, 24, 18), spacing=12)
        stats.body.addWidget(ui_kit.label("Execution", "CardEyebrow", align=Qt.AlignmentFlag.AlignHCenter))
        self.stat_executed = ui_kit.StatRow("Executed", "0", "ok")
        self.stat_ok = ui_kit.StatRow("OK", "0", "ok")
        self.stat_ng = ui_kit.StatRow("NG", "0", "ng")
        self.stat_not_run = ui_kit.StatRow("Not run yet", "0", "none")
        for row in (self.stat_executed, self.stat_ok, self.stat_ng, self.stat_not_run):
            stats.body.addWidget(row)
        card.body.addWidget(stats)

        divider_box = QHBoxLayout()
        divider_box.setContentsMargins(24, 0, 24, 0)
        divider_box.addWidget(ui_kit.divider(dotted=True))
        card.body.addLayout(divider_box)

        rate = ui_kit.CardSection(padding=(24, 16, 24, 22), spacing=8)
        center = Qt.AlignmentFlag.AlignHCenter
        rate.body.addWidget(ui_kit.label("Pass rate", "CardEyebrow", align=center))
        rate.body.addWidget(ui_kit.label("OK ÷ executed cases", "MutedText", align=center))
        self.pass_rate_box = ui_kit.label("—", "ValueBox", align=Qt.AlignmentFlag.AlignCenter)
        rate.body.addWidget(self.pass_rate_box)
        self.pass_rate_bar = ui_kit.progress(0)
        rate.body.addWidget(self.pass_rate_bar)
        self.ng_projects_label = ui_kit.label("", "BodyText", wrap=True, align=center)
        rate.body.addSpacing(4)
        rate.body.addWidget(self.ng_projects_label)
        self.ng_filter_button = ui_kit.button("Show NG only", "secondary", small=True)
        self.ng_filter_button.setCheckable(True)
        self.ng_filter_button.toggled.connect(self._toggle_ng_filter)
        rate.body.addWidget(self.ng_filter_button, 0, center)
        card.body.addWidget(rate)
        return card

    def _build_last_opened_card(self) -> QWidget:
        card = ui_kit.Card(padding=0, spacing=0)
        self.last_opened_head = ui_kit.centered_header("Current project", "", "", line=False)
        card.body.addWidget(self.last_opened_head)
        action_box = ui_kit.CardSection(padding=(24, 0, 24, 24))
        self.continue_button = ui_kit.button("Continue testing", "primary", "arrow-right", icon_right=True)
        self.continue_button.clicked.connect(self._continue_current_project)
        action_box.body.addWidget(self.continue_button)
        card.body.addWidget(action_box)
        self.last_opened_card = card
        self._refresh_last_opened()
        return card

    def _refresh_last_opened(self, *_args):
        project = None
        try:
            project = self.db.get_current_project()
        except Exception as e:  # noqa: BLE001 - informational card only
            logger.debug("Could not read current project: %s", e)
        head = self.last_opened_head
        if project:
            head.big_label.setText(project.name)
            head.big_label.setVisible(True)
            head.caption_label.setText(project.url or "")
            head.caption_label.setVisible(bool(project.url))
            self.continue_button.setVisible(True)
        else:
            head.big_label.setVisible(False)
            head.caption_label.setText("No project opened yet. Open one from the list.")
            head.caption_label.setVisible(True)
            self.continue_button.setVisible(False)

    def _continue_current_project(self):
        project = self.db.get_current_project()
        if project:
            self.project_selected.emit(project)

    def _toggle_ng_filter(self, checked: bool):
        self.ng_only = checked
        self.ng_filter_button.setText("Show all projects" if checked else "Show NG only")
        self._handle_search(self.search_edit.text())

    def _update_total_cards(self, projects: list[Project]):
        total_projects = len(projects)
        total = sum(p.total_testcase_count or 0 for p in projects)
        executed = sum(p.executed_testcase_count or 0 for p in projects)
        ok = sum(p.ok_testcase_count or 0 for p in projects)
        ng = sum(p.ng_testcase_count or 0 for p in projects)
        ng_projects = sum(1 for p in projects if (p.ng_testcase_count or 0) > 0)

        self.overview_head.big_label.setText(f"{total:,}")
        noun = "project" if total_projects == 1 else "projects"
        self.overview_head.caption_label.setText(f"across {total_projects} {noun}")
        self.stat_executed.set_value(f"{executed:,}")
        self.stat_ok.set_value(f"{ok:,}")
        self.stat_ng.set_value(f"{ng:,}")
        self.stat_not_run.set_value(f"{max(total - executed, 0):,}")

        if executed:
            rate = ok / executed * 100
            self.pass_rate_box.setText(f"{rate:.1f}%")
            self.pass_rate_bar.setValue(round(rate))
        else:
            self.pass_rate_box.setText("—")
            self.pass_rate_bar.setValue(0)

        if ng_projects:
            noun = "project has" if ng_projects == 1 else "projects have"
            self.ng_projects_label.setText(f"{ng_projects} {noun} NG cases.")
        else:
            self.ng_projects_label.setText("No NG cases. Nice work.")
        self.ng_filter_button.setVisible(bool(ng_projects) or self.ng_only)

    # ------------------------------------------------------------- table cells
    def _create_actions_widget(self, cell_data, row_index):
        _ = cell_data
        actions_widget = QWidget()
        layout = QHBoxLayout(actions_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        view_button = ui_kit.button("Open", "secondary", "arrow-right", icon_right=True, small=True)
        view_button.clicked.connect(partial(self._handle_project_selected, row_index))
        edit_button = ui_kit.icon_button(
            "edit", "Edit project", on_click=partial(self._handle_project_edit, row_index)
        )
        delete_button = ui_kit.icon_button(
            "trash", "Delete project", danger=True,
            on_click=partial(self._handle_project_delete, row_index),
        )
        layout.addStretch(1)
        layout.addWidget(view_button)
        layout.addWidget(edit_button)
        layout.addWidget(delete_button)
        return actions_widget

    def _create_ng_test_cases_widget(self, cell_data, row_index):
        _ = row_index
        has_ng = str(cell_data).isdigit() and int(cell_data) > 0
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        icon_lbl = QLabel()
        status = "ng" if has_ng else "ok"
        icon_lbl.setPixmap(icons.pixmap(icons.status_icon_name(status), icons.status_color(status), 17))
        layout.addStretch(1)
        layout.addWidget(icon_lbl)
        if has_ng:
            label = QLabel(str(cell_data))
            label.setProperty("class", "ngCount")
            label.setProperty("has_ng", "true")
            layout.addWidget(label)
        else:
            icon_lbl.setToolTip("No NG cases")
        layout.addStretch(1)
        return box

    def _create_progress_widget(self, cell_data, row_index):
        _ = row_index
        executed, total, ng = cell_data if isinstance(cell_data, tuple) else (0, 0, 0)
        pct = round(executed / total * 100) if total else 0
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addStretch(1)
        layout.addWidget(ui_kit.progress(pct, "ng" if ng else "ok"))
        layout.addWidget(ui_kit.label(f"{pct}% executed", "MutedText"))
        layout.addStretch(1)
        return box

    def _create_clickable_project_name_widget(self, cell_data, row_index):
        label = QLabel(str(cell_data))
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        label.setProperty("class", "projectName")
        label.setToolTip("Open project")
        label.mousePressEvent = lambda _e, r=row_index: self._handle_project_selected(r)
        return label

    def _configure_table_columns(self):
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        self.column_configs: List[BaseColumnConfig] = [
            IndexColumnConfig(
                header="No.",
                editable=False,
                default_width=0.05,
                min_width=48,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            TextColumnConfig(
                header="Project",
                editable=True,
                min_width=140,
                default_width=0.25,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                default_value="New Project",
                widget_factory=self._create_clickable_project_name_widget,
            ),
            NumberColumnConfig(
                header="Cases",
                editable=False,
                default_width=0.08,
                min_width=60,
                alignment=right,
                calculation=NumberCalculation.SUM,
                decimal_places=0,
            ),
            NumberColumnConfig(
                header="Executed",
                editable=False,
                default_width=0.09,
                min_width=64,
                alignment=right,
                calculation=NumberCalculation.SUM,
                decimal_places=0,
            ),
            NumberColumnConfig(
                header="OK",
                editable=False,
                default_width=0.07,
                min_width=48,
                alignment=right,
                calculation=NumberCalculation.SUM,
                decimal_places=0,
            ),
            NumberColumnConfig(
                header="NG",
                editable=False,
                default_width=0.07,
                min_width=48,
                alignment=Qt.AlignmentFlag.AlignCenter,
                default_value=0,
                widget_factory=self._create_ng_test_cases_widget,
                calculation=NumberCalculation.SUM,
                decimal_places=0,
            ),
            BaseColumnConfig(
                header="Progress",
                editable=False,
                default_width=0.14,
                min_width=90,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                widget_factory=self._create_progress_widget,
            ),
            ActionColumnConfig(
                header="Actions",
                editable=False,
                resizable=False,
                default_width=0.18,
                min_width=180,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                widget_factory=self._create_actions_widget,
            ),
        ]

    def _connect_signals(self):
        self.search_edit.textChanged.connect(self._handle_search)
        self.new_project_button.clicked.connect(self._handle_project_create)
        self.db.signals.project_edited.connect(self.refresh_data_async)
        self.db.signals.current_project_changed.connect(self._refresh_last_opened)

    def _handle_row_selection_changed(self, selected_indices: List[int]):
        if selected_indices:
            data_row_index = selected_indices[0]
            self._handle_project_selected(data_row_index)

    def refresh_data(self):
        try:
            self.all_projects = self.db.get_all_projects_sync()
            self.project_id_map = {
                p.project_id: p for p in self.all_projects if p.project_id
            }
            self.populate_table(self.all_projects)
            self._update_total_cards(self.all_projects)
        except Exception as e:
            logger.error("Error refreshing data: %s", e, exc_info=True)
            self.all_projects = []
            self.project_id_map = {}
            self.populate_table([])
            self._update_total_cards([])

    def _handle_search(self, text: str):
        if not text.strip():
            filtered_projects = self.all_projects
        else:
            search_text = text.lower().strip()
            filtered_projects = [
                p for p in self.all_projects if search_text in p.name.lower()
            ]
        self.populate_table(filtered_projects)
        self._update_total_cards(filtered_projects)

    def _handle_project_selected(self, data_row_index: int):
        try:
            if not (0 <= data_row_index < len(self.displayed_projects)):
                logger.warning(f"Selected row index {data_row_index} is out of bounds.")
                return
            project_from_full_list = self.displayed_projects[data_row_index]
            project_id = project_from_full_list.project_id
            project = self.db.get_project_by_id_sync(
                project_id if project_id is not None else ""
            )
            if project:
                logger.info(
                    "Project selected: ID=%s, Name='%s'",
                    project.project_id,
                    project.name,
                )
                self.project_selected.emit(project)
            else:
                logger.warning("Project with ID=%s not found in database.", project_id)
                QMessageBox.warning(self, "Error", "Project not found in database.")
        except Exception as e:
            logger.error(f"Error selecting project: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error selecting project: {str(e)}")

    def _handle_project_edit(self, data_row_index: int):
        """Handles project editing by opening a detailed dialog."""
        try:
            if not (0 <= data_row_index < len(self.displayed_projects)):
                logger.warning(f"Edit attempt on invalid row index: {data_row_index}")
                return
            project_to_edit = self.displayed_projects[data_row_index]
            project_id = project_to_edit.project_id
            if not project_id:
                logger.error("Attempted to edit a project with no ID.")
                QMessageBox.critical(
                    self, "Error", "Cannot edit project: missing project ID."
                )
                return
            dialog = ProjectDialog(project=project_to_edit, parent=self)
            if dialog.exec():
                updated_data = dialog.get_data()
                
                for key, value in updated_data.items():
                    setattr(project_to_edit, key, value)

                success = self.db.update_project_sync( 
                    project_to_edit
                )
                if success:
                    # Update table view
                    self.table_model.update_cell(
                        data_row_index, 1, updated_data["name"]
                    )
                    # Update in-memory project object for consistency
                    for key, value in updated_data.items():
                        setattr(project_to_edit, key, value)

                    self.project_edit.emit(project_to_edit)

                    logger.info(
                        f"Project updated: ID={project_id}, Name='{updated_data['name']}'"
                    )
                    QMessageBox.information(
                        self, "Thành công", f"Dự án '{project_to_edit.name}' đã được cập nhật."
                    )
                else:
                    logger.error(
                        f"Failed to update project in database: ID={project_id}"
                    )
                    QMessageBox.warning(self, "Error", "Failed to update project.")

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"An error occurred while editing the project: {str(e)}"
            )
            logger.error(f"Error editing project: {e}", exc_info=True)


    def _handle_project_delete(self, data_row_index: int):
        try:
            if not (0 <= data_row_index < len(self.displayed_projects)):
                return

            project_to_delete = self.displayed_projects[data_row_index]
            project_id = project_to_delete.project_id
            project_name = project_to_delete.name

            if not project_id:
                return

            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete project '{project_name}'?\n\nThis action cannot be undone and will delete all associated test cases.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                success = self.db.delete_project_sync(project_id)
                if success:
                    logger.info(
                        f"Project deleted: ID={project_id}, Name='{project_name}'"
                    )
                    project_in_all_list = next((p for p in self.all_projects if p.project_id == project_id), None)
                    if project_in_all_list:
                        self.all_projects.remove(project_in_all_list)

                    self._handle_search(self.search_edit.text())
                    # self.refresh_data()
                    QMessageBox.information(
                        self, "Success", f"Project '{project_name}' has been deleted."
                    )
                else:
                    logger.warning(f"Delete project failed: ID={project_id}")
                    QMessageBox.warning(
                        self,
                        "Delete Failed",
                        f"Could not delete project '{project_name}'.",
                    )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete project: {str(e)}")
            logger.error(f"Error deleting project: {e}", exc_info=True)

    
    def _handle_project_create(self):
        try:
            dialog = ProjectDialog(parent=self)
            if dialog.exec():
                project_data = dialog.get_data()
                result = self.db.add_project_sync(**project_data)

                if result is None:
                    QMessageBox.critical(
                        self, "Error", "Failed to create project. Please ensure you are logged in."
                    )
                    return

                new_project, status = result

                if isinstance(new_project, Project):
                    logger.info(
                        f"Project created: ID={new_project.project_id}, Name='{new_project.name}'"
                    )
                    self.project_created.emit(new_project)

                    self.search_edit.clear()
                    
                    self.all_projects.insert(0, new_project)
                    
                    self.populate_table(self.all_projects)
                    self._update_total_cards(self.all_projects)

                    # self.refresh_data()
                    # self.search_edit.clear()
                    QMessageBox.information(
                        self,
                        "Success",
                        f"Project '{new_project.name}' has been created.",
                    )
                else:
                    if status == 409:
                        QMessageBox.critical(
                            self, "Error", "Failed to create project in the database. Project with this name already exists"
                        )
                    elif status == 422:
                        QMessageBox.critical(
                            self, "Error", "Failed to create project in the database. Strings must have at least 3 characters"
                        )
                    else:
                        QMessageBox.critical(
                            self, "Error", "Failed to create project in the database."
                        )
                    logger.error(
                        "db.add_project_sync failed to return a valid Project object."
                    )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create project: {str(e)}")
            logger.error(f"Error creating project: {e}", exc_info=True)
