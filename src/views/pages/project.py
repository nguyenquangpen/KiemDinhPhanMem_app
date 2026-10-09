from functools import partial
from typing import List, Optional

from PySide6.QtCore import Qt, Slot, QObject, QRunnable, Signal, QThreadPool
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.data_classes import Project, Task
from models.database import DataManager
from services.logging_config import get_logger

# Assuming components are in these locations
from views.components.input_card import InputCard, InputCardConfig, InputType
from views.components.table import (
    DataTableWidget,
    TableModel,
    BaseColumnConfig,
    IndexColumnConfig,
    TextColumnConfig,
    NumberColumnConfig,
    ActionColumnConfig,
    SelectColumnConfig,
    SelectType,
)

logger = get_logger("project")


class LoadTasksWorkerSignals(QObject):
    """Defines signals available from a running LoadTasksWorker thread."""

    finished = Signal(list)  # Emits list of Task objects on success
    error = Signal(str)  # Emits error message string on failure


class LoadTasksWorker(QRunnable):
    """
    Worker thread for fetching tasks from the DataManager.
    Inherits from QRunnable to handle worker thread setup, signals, and wrap the task function.
    """

    def __init__(self, data_manager: DataManager):
        super().__init__()
        self.db = data_manager
        self.signals = LoadTasksWorkerSignals()

    @Slot()
    def run(self):
        """The function that will be executed in the separate thread."""
        try:
            # A project must be selected to list its tasks
            if not self.db.get_current_project():
                self.signals.finished.emit([])
                return
            if self.db.current_project and self.db.current_project.project_id:
                tasks = (
                    self.db.list_tasks_sync(self.db.current_project.project_id) or []
                )
                list_task = [Task.from_dict(task) for task in tasks]
                self.signals.finished.emit(list_task)
        except Exception as e:
            logger.error(f"Error loading tasks in worker thread: {e}", exc_info=True)
            self.signals.error.emit(f"An unexpected error occurred: {e}")


class ProjectWidget(QWidget):
    task_selected = Signal()
    edit_task_requested = Signal(Task)
    view_testcases_requested = Signal(Task)
    add_task_requested = Signal()

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)

        self.setObjectName("PageWidget")
        self.db = data_manager
        self.thread_pool = QThreadPool.globalInstance()

        # Store task objects for selection mapping
        self.current_tasks: List[Task] = []
        # Flag to prevent infinite selection loops
        self._updating_selection = False

        # Connect to DataManager signals for state management
        self.db.signals.current_project_changed.connect(
            self._on_current_project_changed
        )
        self.db.signals.current_task_changed.connect(self._on_current_task_changed)

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 20, 30, 20)
        main_layout.setSpacing(20)

        # --- Top Section (Details + Add Task) ---
        top_layout = QHBoxLayout()
        top_layout.setSpacing(30)

        # --- Bottom Section (Tasks Table) ---
        bottom_layout = QVBoxLayout()
        bottom_layout.setSpacing(10)

        main_layout.addLayout(top_layout)
        main_layout.addLayout(bottom_layout)

        # --- Populate Sections ---
        self.project_details_card = self._setup_project_details()
        self.tasks_table_widget = self._setup_tasks_table()

        top_layout.addWidget(self.project_details_card, 1)

        tasks_title = QLabel("Tasks")
        tasks_title.setObjectName("TasksTitleLabel")

        bottom_layout.addWidget(tasks_title)
        bottom_layout.addWidget(self.tasks_table_widget)

        # --- Load Initial Data ---
        self._load_project_data()

    def _setup_project_details(self) -> QWidget:
        """Creates the 'Project Details' card widget."""
        container = QWidget()
        container.setObjectName("CardWidget")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("Project Details")
        title.setObjectName("CardTitleLabel")
        layout.addWidget(title)

        configs = [
            InputCardConfig(
                label="Project Name",
                input_type=InputType.TEXT,
                placeholder="Project Alpha",
            ),
            InputCardConfig(
                label="URL Login",
                input_type=InputType.TEXT,
                placeholder="https://example.com/login",
            ),
            InputCardConfig(
                label="Login ID", input_type=InputType.TEXT, placeholder="BobAbc"
            ),
            InputCardConfig(
                label="Password", input_type=InputType.TEXT, placeholder="password123"
            ),
        ]
        self.project_input_card = InputCard(configs=configs, save_button_text="Save")
        self.project_input_card.save_requested.connect(self._handle_save_project)
        layout.addWidget(self.project_input_card)

        return container

    def _create_form_field(self, label_text: str, input_widget: QWidget) -> QWidget:
        """Helper to create a label-input pair."""
        field_container = QWidget()
        field_layout = QVBoxLayout(field_container)
        field_layout.setContentsMargins(0, 0, 0, 0)
        field_layout.setSpacing(5)
        field_layout.addWidget(QLabel(label_text))
        field_layout.addWidget(input_widget)
        return field_container

    def _setup_tasks_table(self) -> DataTableWidget:
        """Creates and configures the tasks table with an empty model."""
        column_configs: List[BaseColumnConfig] = [
            SelectColumnConfig(header="Select", select_type=SelectType.SINGLE),
            IndexColumnConfig(header="No", default_width=0.05, resizable=False),
            TextColumnConfig(
                header="Task Name",
                default_width=0.25,
                alignment=Qt.AlignmentFlag.AlignCenter,
                editable=True,
            ),
            NumberColumnConfig(
                header="Test Cases",
                default_width=0.12,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            NumberColumnConfig(
                header="Executed",
                default_width=0.15,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            NumberColumnConfig(
                header="OK",
                default_width=0.13,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            NumberColumnConfig(
                header="NG",
                default_width=0.15,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            ActionColumnConfig(
                header="Actions",
                widget_factory=self._create_task_actions,
                default_width=0.15,
            ),
        ]

        add_task_button = QPushButton("Add task")
        add_task_button.setObjectName("GreenButton")

        add_task_button.clicked.connect(self._handle_add_task_request)

        # Start with empty data - will be populated by async loading
        self.table_model = TableModel(data=[])
        table = DataTableWidget(
            column_configs, self.table_model, highlight_selected_row=True,
            custom_buttons=[add_task_button]
        )

        # Connect selection changes to update DataManager state
        table.selection_changed.connect(self._on_task_selection_changed)
        table.delete_requested.connect(self._delete_task)
        return table

    def _create_task_actions(self, cell_data, row_index) -> QWidget:
        """Factory function to create custom action buttons for tasks."""
        _ = cell_data
        action_widget = QWidget()
        layout = QHBoxLayout(action_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        edit_btn = QPushButton("Edit")
        edit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        edit_btn.setObjectName("BlueButton")

        testcases_btn = QPushButton("Test Cases")
        testcases_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        testcases_btn.setObjectName("GreenButton")  # Use a different style if needed

        delete_btn = QPushButton("Delete")
        delete_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        delete_btn.setObjectName("RedButton")

        # Connect buttons to new handlers that emit signals
        edit_btn.clicked.connect(partial(self._handle_edit_task_request, row_index))
        testcases_btn.clicked.connect(
            partial(self._handle_view_testcases_request, row_index)
        )
        delete_btn.clicked.connect(partial(self._delete_task, row_index))

        layout.addWidget(edit_btn)
        layout.addWidget(testcases_btn)
        layout.addWidget(delete_btn)

        return action_widget

    def _edit_task(self, row_index: int):
        """Handle edit button click by setting the task as current."""
        # Validate row index bounds
        if not (0 <= row_index < len(self.current_tasks)):
            logger.warning(f"Edit task called with invalid row index: {row_index}")
            return

        task = self.current_tasks[row_index]

        # Validate task has valid ID
        if not task or not task.task_id:
            logger.warning("Cannot edit task without valid task_id")
            QMessageBox.warning(
                self, "Invalid Task", "Cannot edit a task without a valid ID."
            )
            return

        self.db.set_current_task_sync(task.task_id)
        self.task_selected.emit()
        logger.info(f"Set current task to: {task.task_name}")

    def _delete_task(self, row_index: int):
        """Handle delete button click."""
        # Validate row index bounds
        if not (0 <= row_index < len(self.current_tasks)):
            logger.warning(f"Delete task called with invalid row index: {row_index}")
            return

        task = self.current_tasks[row_index]

        # Validate task has valid ID
        if not task or not task.task_id:
            logger.warning("Cannot delete task without valid task_id")
            QMessageBox.warning(
                self, "Invalid Task", "Cannot delete a task without a valid ID."
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the task '{task.task_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self.db.delete_task_sync(task.task_id):
                    # Clear current task if it was the one being deleted
                    current_task = self.db.get_current_task()
                    if current_task and current_task.task_id == task.task_id:
                        self.db.set_current_task_sync(None)

                    # Reload tasks
                    self._load_tasks_async()
                    logger.info(f"Deleted task: {task.task_name}")
                else:
                    QMessageBox.critical(self, "Error", "Failed to delete the task.")
            except Exception as e:
                logger.error(f"Error deleting task: {e}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Error",
                    f"An error occurred while deleting the task: {str(e)}",
                )

    def _handle_edit_task_request(self, row_index: int):
        """Handle 'Edit' button click by emitting a signal with the task."""
        if not (0 <= row_index < len(self.current_tasks)):
            logger.warning(f"Edit task request with invalid row index: {row_index}")
            return

        task = self.current_tasks[row_index]
        if not task or not task.task_id:
            logger.warning("Cannot edit task without a valid task_id")
            QMessageBox.warning(
                self, "Invalid Task", "Cannot edit a task without a valid ID."
            )
            return

        self.db.set_current_task_sync(task.task_id)
        logger.info(f"Emitting edit_task_requested for task: {task.task_name}")
        self.edit_task_requested.emit(task)
    
    def _handle_add_task_request(self):
        """Handle 'Add task' button click by emitting a signal."""
        logger.info("Emitting add_task_requested to switch to the task page.")
        self.add_task_requested.emit()

    def _handle_view_testcases_request(self, row_index: int):
        """Handle 'Test Cases' button click by emitting a signal with the task."""
        if not (0 <= row_index < len(self.current_tasks)):
            logger.warning(
                f"View test cases request with invalid row index: {row_index}"
            )
            return

        task = self.current_tasks[row_index]
        if not task or not task.task_id:
            logger.warning("Cannot view test cases for task without a valid task_id")
            QMessageBox.warning(
                self,
                "Invalid Task",
                "Cannot view test cases for a task without a valid ID.",
            )
            return

        self.db.set_current_task_sync(task.task_id)
        logger.info(f"Emitting view_testcases_requested for task: {task.task_name}")
        self.view_testcases_requested.emit(task)

    def _on_task_selection_changed(self, selected_indices: List[int]):
        """Handle table selection changes and update DataManager state."""
        # Prevent infinite selection loops
        if self._updating_selection:
            return

        logger.debug(f"Task selection changed: {selected_indices}")

        # Handle no selection
        if not selected_indices:
            self.db.set_current_task_sync(None)
            return

        row_index = selected_indices[0]  # Single selection

        # Validate row index bounds
        if not (0 <= row_index < len(self.current_tasks)):
            logger.warning(f"Selection changed with invalid row index: {row_index}")
            self.db.set_current_task_sync(None)
            return

        task = self.current_tasks[row_index]

        # Validate task has valid ID
        if not task or not task.task_id:
            logger.warning("Selected task has no valid task_id")
            self.db.set_current_task_sync(None)
            return

        # Update DataManager state
        self.db.set_current_task_sync(task.task_id)
        self.task_selected.emit()
        logger.debug(f"Selected task: {task.task_name} (ID: {task.task_id})")

    def _load_tasks_async(self):
        """Loads tasks for the current project in a separate thread."""
        logger.info("Starting worker to load tasks...")
        self.tasks_table_widget.setEnabled(False)  # Disable table during load

        worker = LoadTasksWorker(self.db)
        worker.signals.finished.connect(self._on_tasks_loaded)
        worker.signals.error.connect(self._on_tasks_load_error)
        self.thread_pool.start(worker)

    @Slot(list)
    def _on_tasks_loaded(self, tasks: List[Task]):
        """Slot to handle the successful loading of tasks from the worker."""
        logger.info(f"Successfully loaded {len(tasks)} tasks.")

        # Store tasks for selection mapping
        self.current_tasks = tasks

        # Build table data
        table_data = []
        for task in tasks:
            table_data.append(
                [
                    None,  # Placeholder for SelectColumn
                    None,  # Placeholder for IndexColumn (table generates the number)
                    task.task_name,
                    getattr(task, "total_testcase_count", 0),
                    (
                        getattr(task, "ok_testcase_count", 0)
                        + getattr(task, "ng_testcase_count", 0)
                    ),
                    getattr(task, "ok_testcase_count", 0),
                    getattr(task, "ng_testcase_count", 0),
                    None,  # Placeholder for ActionColumn
                ]
            )

        # Update table model
        if hasattr(self.table_model, "set_data"):
            self.table_model.set_data(table_data)
        else:
            # Fallback if set_data doesn't exist
            logger.warning(
                "TableModel does not have a 'set_data' method. Re-creating model."
            )
            self.table_model = TableModel(data=table_data)
            self.tasks_table_widget.model = self.table_model

        self.tasks_table_widget.setEnabled(True)  # Re-enable table

        # Update selection to match current task from DataManager
        self._update_table_selection()

    def _update_table_selection(self):
        """Update table selection to match DataManager's current task."""
        current_task = self.db.get_current_task()

        # Prevent selection loops
        self._updating_selection = True

        try:
            if not current_task or not current_task.task_id:
                self.tasks_table_widget.clear_selection()
                return

            # Find the task in our current tasks list
            for index, task in enumerate(self.current_tasks):
                if task and task.task_id == current_task.task_id:
                    self.tasks_table_widget.set_selection([index])
                    logger.debug(
                        f"Updated table selection to row {index} for task: {task.task_name}"
                    )
                    break
            else:
                # Current task not found in table, clear selection
                logger.warning(
                    f"Current task {current_task.task_id} not found in loaded tasks"
                )
                if hasattr(self.tasks_table_widget, "clear_selection"):
                    self.tasks_table_widget.clear_selection()
                elif hasattr(self.tasks_table_widget, "set_selection"):
                    self.tasks_table_widget.set_selection([])
        finally:
            self._updating_selection = False

    @Slot(str)
    def _on_tasks_load_error(self, error_message: str):
        """Slot to handle errors from the task loading worker."""
        logger.error(f"Failed to load tasks: {error_message}")
        QMessageBox.critical(self, "Task Loading Error", error_message)
        self.tasks_table_widget.setEnabled(True)  # Re-enable table even on error
        self.current_tasks = []  # Clear tasks on error

        # Clear table data on error
        if hasattr(self.table_model, "set_data"):
            self.table_model.set_data([])

    def _load_project_data(self):
        """Fetches current project data and triggers asynchronous task loading."""
        current_project = self.db.get_current_project()

        if current_project:
            logger.info("Loading project data for: %s", current_project.name)
            project_data = {
                "Project Name": current_project.name,
                "URL Login": current_project.url,
                "Description": getattr(current_project, "description", ""),
                "Login ID": getattr(current_project, "login_id", ""),
                "Password": getattr(current_project, "password", ""),
            }
            self.project_input_card.set_data(project_data)
            self.project_input_card.setEnabled(True)
            logger.debug("Project data loaded successfully")
            self._load_tasks_async()  # Trigger async task loading
        else:
            logger.warning("ProjectWidget: No current project found to load.")
            self.project_input_card.clear_data()
            self.project_input_card.setEnabled(False)
            # Clear the tasks table as well if no project is selected
            self.current_tasks = []
            if hasattr(self.table_model, "set_data"):
                self.table_model.set_data([])
            else:
                self.table_model = TableModel(data=[])
                self.tasks_table_widget.model = self.table_model

    def _on_current_project_changed(self, project: Optional[Project]):
        """React to DataManager current project changes."""
        logger.debug("Current project changed, refreshing project data")
        self._load_project_data()
        # Clear current task when project changes
        self.db.set_current_task_sync(None)

    def _on_current_task_changed(self, task: Optional[Task]):
        """React to DataManager current task changes."""
        logger.debug(f"Current task changed: {task.task_name if task else 'None'}")
        # Update table selection to reflect the current task
        self._update_table_selection()

    def refresh_project_data(self):
        """Public method to refresh project data when project selection changes."""
        logger.debug("Refreshing project data display")
        self._load_project_data()

    def set_current_project(self, project: Project):
        """Set the current project and refresh the display."""
        logger.info(
            "Setting current project: %s (ID: %s)", project.name, project.project_id
        )
        if project.project_id is not None:
            self.db.set_current_project_sync(project.project_id)
        else:
            logger.warning("Cannot set project with None project_id")

    @Slot(dict)
    def _handle_save_project(self, data: dict):
        """Handle saving project data when Save button is clicked."""
        current_project = self.db.get_current_project()
        if not current_project:
            QMessageBox.warning(
                self, "No Project", "There is no project selected to save."
            )
            return

        try:
            logger.info("Saving project data for: %s", current_project.name)

            # Update project data
            current_project.name = data.get("Project Name", "")
            current_project.url = data.get("URL Login", "")
            if hasattr(current_project, "description"):
                current_project.description = data.get("Description", "")
            if hasattr(current_project, "login_id"):
                current_project.login_id = data.get("Login ID", "")
            if hasattr(current_project, "password"):
                current_project.password = data.get("Password", "")

            logger.debug(
                "Updated project data: %s",
                {
                    "name": current_project.name,
                    "url": current_project.url,
                    "login_id": getattr(current_project, "login_id", ""),
                },
            )

            payload = [
                {"name": current_project.name},
                {"description": getattr(current_project, "description", "")},
                {"url": current_project.url},
            ]

            project_id = (
                current_project.project_id
                if current_project.project_id is not None
                else ""
            )

            if not project_id:
                logger.error("Cannot save project without valid project_id")
                QMessageBox.critical(
                    self, "Error", "Cannot save project without a valid ID."
                )
                return

            if self.db.update_project_specifications_sync(project_id, payload):
                logger.info("Project '%s' saved successfully", current_project.name)
                QMessageBox.information(
                    self,
                    "Success",
                    f"Project '{current_project.name}' has been saved successfully.",
                )
                # Update the current project in DataManager to trigger signals
                if self.db.get_current_project().project_id != str(project_id):
                    self.db.set_current_project_sync(project_id)
                else: self.db.signals.current_project_changed.emit(self.db.current_project)
            else:
                logger.error("Failed to save project: project not found in database")
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to save the project (project not found in database).",
                )
        except Exception as e:
            logger.error("Error saving project: %s", e, exc_info=True)
            QMessageBox.critical(
                self, "Error", f"An error occurred while saving the project: {str(e)}"
            )
