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

from models.data_classes import Project, User
from models.database import DataManager
from services.logging_config import get_logger
from ui.build.ui_project_cms import Ui_ProjectCmsWidget
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
from views.components.total_card import DotColor, TotalCard
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
        self.form_layout = QFormLayout()

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

        # Add rows to the form layout
        self.form_layout.addRow("Name:", self.name_edit)
        self.form_layout.addRow("URL:", self.url_edit)
        self.form_layout.addRow("Description:", self.description_edit)
        self.form_layout.addRow("Login ID:", self.login_id_edit)
        self.form_layout.addRow("Password:", self.password_edit)

        # Standard dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # Connect all fields to the validation method
        self.name_edit.textChanged.connect(self._validate_inputs)
        self.url_edit.textChanged.connect(self._validate_inputs)
        self.description_edit.textChanged.connect(self._validate_inputs)

        self.main_layout.addLayout(self.form_layout)
        self.main_layout.addWidget(self.button_box)
        self.setMinimumWidth(350)

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
        self.ui = Ui_ProjectCmsWidget()
        self.ui.setupUi(self)

        self.all_projects: List[Project] = []
        self.displayed_projects: List[Project] = []
        self.project_id_map: Dict[str, Project] = {}

        self.thread_pool = QThreadPool.globalInstance()
        self._configure_table_columns()
        self.table_model = TableModel([])
        self.table_widget = DataTableWidget(
            self.column_configs,
            self.table_model,
            items_per_page=15,
            highlight_selected_row=True,
        )

        self.table_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        self.setObjectName("PageWidget")

        container_layout = QVBoxLayout(self.ui.tableContainerWidget)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.table_widget)

        self._setup_total_cards()
        self._connect_signals()
        QTimer.singleShot(0, self.refresh_data_async)
        self._connect_global_signals()
    
    def _connect_global_signals(self):
        # self.db.signals.project_edited.connect(self.refresh_data_async)
        if hasattr(self.db.signals, 'current_user_changed'):
            self.db.signals.current_user_changed.connect(self._on_auth_state_changed)
        # self.ui.searchLineEdit.textChanged.connect(self._handle_search)
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
        self.displayed_projects = projects
        table_data = [
            [
                # None,  # Data for SelectColumnConfig (index 0)
                None,  # Data for IndexColumnConfig (index 1) - widget generates this
                p.name,
                p.total_testcase_count or 0,
                p.executed_testcase_count or 0,
                p.ok_testcase_count or 0,
                p.ng_testcase_count or 0,
                None,  # Data for ActionColumnConfig (index 7)
            ]
            for p in projects
        ]
        self.table_widget.blockSignals(True)
        self.table_model.set_data(table_data)
        self.table_widget.blockSignals(False)

    def _setup_total_cards(self):
        self.total_projects_card = TotalCard(color=DotColor.Gray, name="Total Projects")
        self.total_testcases_card = TotalCard(
            color=DotColor.Gray, name="Total Test Cases"
        )
        self.executed_testcases_card = TotalCard(
            color=DotColor.Black, name="Executed Cases"
        )
        self.ok_testcases_card = TotalCard(color=DotColor.Green, name="OK Test Cases")
        self.ng_testcases_card = TotalCard(color=DotColor.Red, name="NG Test Cases")

        self.ui.totalWidgetLayout.addWidget(self.total_projects_card)
        self.ui.totalWidgetLayout.addWidget(self.total_testcases_card)
        self.ui.totalWidgetLayout.addWidget(self.executed_testcases_card)
        self.ui.totalWidgetLayout.addWidget(self.ok_testcases_card)
        self.ui.totalWidgetLayout.addWidget(self.ng_testcases_card)

    def _update_total_cards(self, projects: list[Project]):
        if not projects:
            self.total_projects_card.set_value(0)
            self.total_testcases_card.set_value(0)
            self.executed_testcases_card.set_value(0)
            self.ok_testcases_card.set_value(0)
            self.ng_testcases_card.set_value(0)
            return

        total_projects = len(projects)
        total_testcases = sum(p.total_testcase_count for p in projects)
        executed_testcases = sum(p.executed_testcase_count for p in projects)
        ok_testcases = sum(p.ok_testcase_count for p in projects)
        ng_testcases = sum(p.ng_testcase_count for p in projects)

        self.total_projects_card.set_value(total_projects)
        self.total_testcases_card.set_value(total_testcases)
        self.executed_testcases_card.set_value(executed_testcases)
        self.ok_testcases_card.set_value(ok_testcases)
        self.ng_testcases_card.set_value(ng_testcases)

    def _create_actions_widget(self, cell_data, row_index):
        _ = cell_data
        actions_widget = QWidget()
        layout = QHBoxLayout(actions_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        view_button = QPushButton("View")
        view_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        view_button.setObjectName("BlueButton")
        view_button.clicked.connect(partial(self._handle_project_selected, row_index))

        edit_button = QPushButton("Edit")
        edit_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        edit_button.setObjectName("GreenButton")
        edit_button.clicked.connect(partial(self._handle_project_edit, row_index))

        delete_button = QPushButton("Delete")
        delete_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        delete_button.setObjectName("RedButton")
        delete_button.clicked.connect(partial(self._handle_project_delete, row_index))

        layout.addWidget(view_button)
        layout.addWidget(edit_button)
        layout.addWidget(delete_button)
        return actions_widget

    def _create_ng_test_cases_widget(self, cell_data, row_index):
        label = QLabel(str(cell_data))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setProperty("class", "ngCount")
        has_ng = str(cell_data).isdigit() and int(cell_data) > 0
        label.setProperty("has_ng", "true" if has_ng else "false")
        return label

    def _create_clickable_project_name_widget(self, cell_data, row_index):
        label = QLabel(str(cell_data))
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        label.setProperty("class", "projectName")
        return label

    def _configure_table_columns(self):
        self.column_configs: List[BaseColumnConfig] = [
        #     SelectColumnConfig(
        #     header="Select",
        #     select_type=SelectType.SINGLE,
        #     default_width=0.04,
        #     min_width=40,
        # ),
            IndexColumnConfig(
                header="No.",
                editable=False,
                default_width=0.065,
                min_width=60,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            TextColumnConfig(
                header="Project Name",
                editable=True,
                min_width=200,
                default_width=0.286,
                alignment=Qt.AlignmentFlag.AlignCenter,
                default_value="New Project",
                widget_factory=self._create_clickable_project_name_widget,
            ),
            NumberColumnConfig(
                header="Total Cases",
                editable=False,
                default_width=0.130,
                min_width=100,
                alignment=Qt.AlignmentFlag.AlignCenter,
                calculation=NumberCalculation.SUM,
                decimal_places=0,
            ),
            NumberColumnConfig(
                header="Executed",
                editable=False,
                default_width=0.130,
                min_width=100,
                alignment=Qt.AlignmentFlag.AlignCenter,
                calculation=NumberCalculation.SUM,
                decimal_places=0,
            ),
            NumberColumnConfig(
                header="OK Test Cases",
                editable=False,
                default_width=0.109,
                min_width=80,
                alignment=Qt.AlignmentFlag.AlignCenter,
                calculation=NumberCalculation.SUM,
                decimal_places=0,
            ),
            NumberColumnConfig(
                header="NG Test Cases",
                editable=False,
                default_width=0.109,
                min_width=80,
                alignment=Qt.AlignmentFlag.AlignCenter,
                default_value=0,
                widget_factory=self._create_ng_test_cases_widget,
                calculation=NumberCalculation.SUM,
                decimal_places=0,
            ),
            ActionColumnConfig(
                header="Actions",
                editable=False,
                resizable=False,
                default_width=0.150,
                min_width=140,
                alignment=Qt.AlignmentFlag.AlignCenter,
                widget_factory=self._create_actions_widget,
            ),
        ]

    def _connect_signals(self):
        self.ui.searchLineEdit.setObjectName("SearchLineEdit")
        self.ui.searchLineEdit.textChanged.connect(self._handle_search)
        self.ui.newProjectButton.setObjectName("NewProjectButton")
        self.ui.newProjectButton.clicked.connect(self._handle_project_create)
        # self.table_widget.selection_changed.connect(self._handle_row_selection_changed)
        self.db.signals.project_edited.connect(self.refresh_data_async)

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

                    self._handle_search(self.ui.searchLineEdit.text())
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

                    self.ui.searchLineEdit.clear()
                    
                    self.all_projects.insert(0, new_project)
                    
                    self.populate_table(self.all_projects)
                    self._update_total_cards(self.all_projects)

                    # self.refresh_data()
                    # self.ui.searchLineEdit.clear()
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
