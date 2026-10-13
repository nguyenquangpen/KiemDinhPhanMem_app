from functools import partial
from typing import List, Optional

from PySide6.QtCore import Qt, Slot, QObject, QRunnable, Signal, QThreadPool
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from asset import tokens
from views.components import ui_kit
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
    open_viewpoints_requested = Signal()

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

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # --- Main Layout: header, then main column + side column ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 28, 32, 28)
        main_layout.setSpacing(24)

        self.header = ui_kit.page_header(
            "Project", "Project settings and the tasks that generate its test cases."
        )
        main_layout.addWidget(self.header)

        body = QHBoxLayout()
        body.setSpacing(24)
        main_layout.addLayout(body, 1)

        main_col = QVBoxLayout()
        main_col.setSpacing(24)
        body.addLayout(main_col, 1)

        # --- Populate Sections ---
        self.project_details_card = self._setup_project_details()
        self.tasks_table_widget = self._setup_tasks_table()

        main_col.addWidget(self.project_details_card)
        tasks_title = QLabel("Tasks")
        tasks_title.setObjectName("CardTitle")
        main_col.addWidget(tasks_title)
        main_col.addWidget(self.tasks_table_widget, 1)
        main_col.setSpacing(12)

        side = QWidget()
        side.setFixedWidth(280)
        side_col = QVBoxLayout(side)
        side_col.setContentsMargins(0, 0, 0, 0)
        side_col.setSpacing(24)
        side_col.addWidget(self._setup_selected_task_card())
        side_col.addStretch(1)
        body.addWidget(side)

        # --- Load Initial Data ---
        self._load_project_data()

    def _setup_project_details(self) -> QWidget:
        """Creates the 'Project Details' card widget."""
        container = ui_kit.Card(padding=0, spacing=0)
        split = QHBoxLayout()
        split.setSpacing(0)
        container.body.addLayout(split)
        form_section = ui_kit.CardSection(padding=(0, 18, 0, 4), spacing=0, line="right")
        split.addWidget(form_section, 1)
        layout = form_section.body
        intro = QVBoxLayout()
        intro.setContentsMargins(24, 0, 24, 0)
        intro.setSpacing(2)
        intro.addWidget(ui_kit.label("Login details", "CardEyebrow"))
        intro.addWidget(ui_kit.label("Used by the AI agent to log in before each run.", "MutedText", wrap=True))
        layout.addLayout(intro)

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
        self.project_input_card = InputCard(
            configs=configs, save_button_text="Save changes", field_spacing=8, field_height=60
        )
        # The card already draws the frame; keep the form flat inside it.
        self.project_input_card.box.setObjectName("Section")
        for input_field in self.project_input_card.fields:
            if input_field.config.label == "Password" and isinstance(input_field.input_widget, QLineEdit):
                input_field.input_widget.setEchoMode(QLineEdit.EchoMode.Password)
        self.project_input_card.save_requested.connect(self._handle_save_project)
        layout.addWidget(self.project_input_card)

        split.addWidget(self._setup_coverage_section(), 1)
        return container

    def _setup_coverage_section(self) -> QWidget:
        section = ui_kit.CardSection(padding=(28, 18, 28, 20), spacing=8)
        center = Qt.AlignmentFlag.AlignHCenter
        section.body.addWidget(ui_kit.label("Coverage", "CardEyebrow", align=center))
        section.body.addWidget(ui_kit.label("Executed cases in this project", "MutedText", align=center))
        self.coverage_box = ui_kit.label("0 / 0", "ValueBox", align=Qt.AlignmentFlag.AlignCenter)
        section.body.addWidget(self.coverage_box)
        self.coverage_bar = ui_kit.progress(0)
        section.body.addWidget(self.coverage_bar)
        section.body.addSpacing(8)
        self.coverage_ok = ui_kit.StatRow("OK", "0", "ok")
        self.coverage_ng = ui_kit.StatRow("NG", "0", "ng")
        section.body.addWidget(self.coverage_ok)
        section.body.addWidget(self.coverage_ng)
        section.body.addStretch(1)
        section.body.addWidget(ui_kit.label("Reusable checks live in the viewpoint library.", "BodyText", wrap=True, align=center))
        open_vp = ui_kit.button("Open viewpoints", "secondary", small=True)
        open_vp.clicked.connect(self.open_viewpoints_requested)
        section.body.addWidget(open_vp, 0, center)
        return section

    def _setup_selected_task_card(self) -> QWidget:
        card = ui_kit.Card(padding=0, spacing=0)
        self.selected_head = ui_kit.centered_header("Selected task", "", "", line=False)
        card.body.addWidget(self.selected_head)

        actions = ui_kit.CardSection(padding=(24, 0, 24, 20))
        self.open_testcases_button = ui_kit.button("Open test cases", "primary", "arrow-right", icon_right=True)
        self.open_testcases_button.clicked.connect(self._open_selected_task_testcases)
        actions.body.addWidget(self.open_testcases_button)
        card.body.addWidget(actions)

        self.selected_details = QWidget()
        details_layout = QVBoxLayout(self.selected_details)
        details_layout.setContentsMargins(24, 0, 24, 24)
        details_layout.setSpacing(16)
        details_layout.addWidget(ui_kit.divider(dotted=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        self.selected_values = {}
        for row, key in enumerate(["Test URL", "Login", "Fields", "Executed"]):
            grid.addWidget(ui_kit.label(key, "MutedText"), row, 0)
            value = ui_kit.label("—", "BodyText", wrap=True)
            grid.addWidget(value, row, 1)
            self.selected_values[key] = value
        details_layout.addLayout(grid)
        card.body.addWidget(self.selected_details)
        self._refresh_selected_task_card()
        return card

    def _selected_task(self) -> Optional[Task]:
        current = self.db.get_current_task()
        if not current or not current.task_id:
            return None
        for task in self.current_tasks:
            if task and task.task_id == current.task_id:
                return task
        return current

    def _refresh_selected_task_card(self):
        task = self._selected_task()
        head = self.selected_head
        if not task:
            head.big_label.setVisible(False)
            head.caption_label.setText("Select a task in the table to see its details.")
            head.caption_label.setVisible(True)
            self.open_testcases_button.setVisible(False)
            self.selected_details.setVisible(False)
            return
        total = getattr(task, "total_testcase_count", 0) or 0
        ok = getattr(task, "ok_testcase_count", 0) or 0
        ng = getattr(task, "ng_testcase_count", 0) or 0
        head.big_label.setText(task.task_name or "Untitled task")
        head.big_label.setVisible(True)
        head.caption_label.setText(f"{total} test cases · {ng} NG" if ng else f"{total} test cases")
        head.caption_label.setVisible(True)
        self.open_testcases_button.setVisible(True)
        self.selected_details.setVisible(True)
        self.selected_values["Test URL"].setText(task.url_test or "—")
        self.selected_values["Login"].setText("Required" if task.request_login else "Not required")
        self.selected_values["Fields"].setText(f"{len(task.specs or [])} specified")
        self.selected_values["Executed"].setText(f"{ok + ng} of {total}")

    def _open_selected_task_testcases(self):
        task = self._selected_task()
        if task:
            self.view_testcases_requested.emit(task)

    def _update_coverage(self):
        total = sum(getattr(t, "total_testcase_count", 0) or 0 for t in self.current_tasks)
        ok = sum(getattr(t, "ok_testcase_count", 0) or 0 for t in self.current_tasks)
        ng = sum(getattr(t, "ng_testcase_count", 0) or 0 for t in self.current_tasks)
        executed = ok + ng
        self.coverage_box.setText(f"{executed} / {total}")
        self.coverage_bar.setValue(round(executed / total * 100) if total else 0)
        self.coverage_ok.set_value(ok)
        self.coverage_ng.set_value(ng)

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
            SelectColumnConfig(header="", select_type=SelectType.SINGLE, min_width=44),
            IndexColumnConfig(header="No", default_width=0.05, resizable=False, min_width=44),
            TextColumnConfig(
                header="Task",
                default_width=0.27,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                editable=True,
            ),
            NumberColumnConfig(
                header="Cases",
                default_width=0.09,
                min_width=60,
            ),
            NumberColumnConfig(
                header="Executed",
                default_width=0.1,
                min_width=70,
            ),
            NumberColumnConfig(
                header="OK",
                default_width=0.08,
                min_width=50,
            ),
            NumberColumnConfig(
                header="NG",
                default_width=0.08,
                min_width=50,
                widget_factory=self._create_ng_cell,
            ),
            ActionColumnConfig(
                header="Actions",
                widget_factory=self._create_task_actions,
                default_width=0.22,
                min_width=180,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            ),
        ]

        add_task_button = ui_kit.button("Add task", "primary", "plus", small=True)

        add_task_button.clicked.connect(self._handle_add_task_request)

        # Start with empty data - will be populated by async loading
        self.table_model = TableModel(data=[])
        table = DataTableWidget(
            column_configs, self.table_model, highlight_selected_row=True,
            custom_buttons=[add_task_button], item_height=48, header_height=44,
            items_per_page=10,
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
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        testcases_btn = ui_kit.button("Test cases", "secondary", small=True)
        edit_btn = ui_kit.icon_button("edit", "Edit task")
        delete_btn = ui_kit.icon_button("trash", "Delete task", danger=True)

        # Connect buttons to new handlers that emit signals
        edit_btn.clicked.connect(partial(self._handle_edit_task_request, row_index))
        testcases_btn.clicked.connect(
            partial(self._handle_view_testcases_request, row_index)
        )
        delete_btn.clicked.connect(partial(self._delete_task, row_index))

        layout.addWidget(testcases_btn)
        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)

        return action_widget

    def _create_ng_cell(self, cell_data, row_index) -> QWidget:
        _ = row_index
        value = int(cell_data or 0) if str(cell_data or 0).isdigit() else 0
        if value:
            return ui_kit.badge(f"{value} NG", "ng")
        lbl = ui_kit.label("0", "CellText", align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return lbl

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
        self._update_coverage()
        self._refresh_selected_task_card()

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
            self.header.title_label.setText(current_project.name)
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
        self._refresh_selected_task_card()

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
