from dataclasses import dataclass
from functools import partial
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from models.data_classes import Spec, Task, Viewpoint, ViewpointType

# Assuming the provided context files are in these locations
from models.database import DataManager
from services.element_picker import pick_elements
from services.field_locators import get_task_locators, save_task_locators
from services.logging_config import get_logger
from views.components.add_choices_widget import MutableListWidget
from views.components.input_card import InputCard, InputCardConfig, InputType
from views.components.table import (
    ActionColumnConfig,
    DataTableWidget,
    DropdownColumnConfig,
    ListDataColumnConfig,
    NumberColumnConfig,
    SelectColumnConfig,
    SelectType,
    TableModel,
    TextColumnConfig,
)

logger = get_logger(__name__)


class AddTaskDialog(QDialog):
    """A dialog window for creating a new task."""

    task_created = Signal(dict)

    def __init__(
        self,
        viewpoint_choices: List[str],
        viewpoint_name_to_id_map: Dict,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Create New Task")
        self.setMinimumWidth(500)
        self.viewpoint_name_to_id_map = viewpoint_name_to_id_map
        layout = QVBoxLayout(self)

        task_creation_configs = [
            InputCardConfig(
                label="Task Name",
                input_type=InputType.TEXT,
                placeholder="Enter a descriptive name for the task",
            ),
            InputCardConfig(
                label="Page Viewpoint",
                input_type=InputType.DROPDOWN,
                options=viewpoint_choices,
                default=viewpoint_choices[0] if viewpoint_choices else "Default",
            ),
            InputCardConfig(
                label="Test URL",
                input_type=InputType.TEXT,
                placeholder="https://example.com/page-to-test",
            ),
            InputCardConfig(
                label="Require Login", input_type=InputType.TRUE_FALSE, default=False
            ),
        ]

        self.input_card = InputCard(
            configs=task_creation_configs,
            save_button_text="Create Task",
        )
        self.input_card.save_requested.connect(self._on_save_requested)
        layout.addWidget(self.input_card)

    def _on_save_requested(self, form_data: dict):
        """Handle the save button click inside InputCard."""
        if not form_data.get("Task Name"):
            QMessageBox.warning(self, "Validation Error", "Task Name cannot be empty.")
            return

        new_task = {
            "url_test": form_data.get("Test URL"),
            "task_name": form_data.get("Task Name"),
            "viewpoint_id": self.viewpoint_name_to_id_map[
                form_data.get("Page Viewpoint")
            ],
            "request_login": form_data.get("Require Login", False),
            "items": [],
        }
        self.task_created.emit(new_task)
        self.accept()


@dataclass
class TaskCreationResult:
    success: bool
    task: Optional[Task] = None
    error_message: Optional[str] = None

class DbModificationWorker(QObject):
    """Generic worker for create, update, DB operations."""
    finished = Signal(bool, str)  # success, message

    def __init__(self, db_function, *args, **kwargs):
        super().__init__()
        self.db_function = partial(db_function, *args, **kwargs)

    def run(self):
        try:
            result = self.db_function()
            success = result is not None and result is not False
            self.finished.emit(success, "Operation completed successfully.")
        except Exception as e:
            logger.error(f"DB modification failed: {e}")
            self.finished.emit(False, str(e))


class ElementPickerWorker(QThread):
    """Mở trình duyệt cho người dùng click chọn từng field + nút Submit (blocking nên chạy ở thread riêng)."""
    finished_picking = Signal(object, str)  # list locator (cùng thứ tự labels), error message

    def __init__(self, url: str, labels: List[str]):
        super().__init__()
        self.url = url
        self.labels = labels

    def run(self):
        try:
            self.finished_picking.emit(pick_elements(self.url, self.labels), "")
        except Exception as e:
            logger.error(f"Element picking failed: {e}", exc_info=True)
            self.finished_picking.emit([], str(e))


class TaskCreatorWorker(QObject):
    finished = Signal(TaskCreationResult)

    def __init__(self, db: DataManager, task_data: dict):
        super().__init__()
        self.db = db
        self.task_data = task_data

    def run(self):
        try:
            project = self.db.current_project
            if not project or not project.project_id:
                self.finished.emit(
                    TaskCreationResult(
                        success=False, error_message="No active project selected."
                    )
                )
                return

            new_task = self.db.create_task_sync(self.task_data, project.project_id)
            if new_task:
                self.finished.emit(
                    TaskCreationResult(success=True, task=Task.from_dict(new_task))
                )
            else:
                self.finished.emit(
                    TaskCreationResult(
                        success=False, error_message="Database returned no new task."
                    )
                )
        except Exception as e:
            self.finished.emit(
                TaskCreationResult(
                    success=False, error_message=f"Error creating task: {e}"
                )
            )


@dataclass
class TestcaseGenerationResult:
    success: bool
    celery_task_id: Optional[str] = None
    error_message: Optional[str] = None


class TestcaseGenerationWorker(QObject):
    finished = Signal(TestcaseGenerationResult)
    progress_update = Signal(str)  # Status message

    def __init__(self, db: DataManager, task_id: str):
        super().__init__()
        self.db = db
        self.task_id = task_id

    def run(self):
        try:
            # Call the generate testcases API
            options = {"include_component_viewpoints": True, "force_regenerate": True}
            result = self.db.generate_testcases_sync(self.task_id, options)

            if result:
                celery_task_id = result.get("celery_task_id")
                if celery_task_id:
                    self.finished.emit(
                        TestcaseGenerationResult(
                            success=True, celery_task_id=celery_task_id
                        )
                    )
                else:
                    self.finished.emit(
                        TestcaseGenerationResult(
                            success=False, error_message="No Celery task ID returned."
                        )
                    )
            else:
                self.finished.emit(
                    TestcaseGenerationResult(
                        success=False,
                        error_message="Failed to start testcase generation.",
                    )
                )
        except Exception as e:
            self.finished.emit(
                TestcaseGenerationResult(
                    success=False, error_message=f"Error generating testcases: {e}"
                )
            )


class TestcaseGenerationProgressDialog(QDialog):
    """Dialog to show testcase generation progress with real-time monitoring."""

    def __init__(self, db: DataManager, task_id: str, task_name: str, parent=None):
        super().__init__(parent)
        self.db = db
        self.task_id = task_id
        self.celery_task_id = None
        self.setWindowTitle(f"Generating Testcases - {task_name}")
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        self.setModal(True)

        # Setup UI
        self._setup_ui()

        # Setup workers and monitoring
        self.generation_worker = None
        self.generation_thread = None
        self.monitoring_timer = QTimer()
        self.monitoring_timer.timeout.connect(self._check_progress)

        # Start generation
        self._start_generation()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Status label
        self.status_label = QLabel("Initializing testcase generation...")
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        layout.addWidget(self.progress_bar)

        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(200)
        layout.addWidget(self.log_output)

        # Button box
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _start_generation(self):
        self.generation_thread = QThread()
        self.generation_worker = TestcaseGenerationWorker(self.db, self.task_id)
        self.generation_worker.moveToThread(self.generation_thread)

        self.generation_thread.started.connect(self.generation_worker.run)
        self.generation_worker.finished.connect(self._on_generation_finished)
        self.generation_worker.progress_update.connect(self._update_status)
        self.generation_worker.finished.connect(self.generation_thread.quit)
        self.generation_worker.finished.connect(self.generation_worker.deleteLater)
        self.generation_thread.finished.connect(self.generation_thread.deleteLater)

        self.generation_thread.start()

    def _on_generation_finished(self, result: TestcaseGenerationResult):
        if result.success:
            self.celery_task_id = result.celery_task_id
            self._update_status("Generation started. Monitoring progress...")
            self._append_log(f"Celery task ID: {self.celery_task_id}")
            # Start monitoring
            self.monitoring_timer.start(2000)  # Check every 2 seconds
        else:
            self._update_status("Generation failed!")
            self._append_log(f"Error: {result.error_message}")
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
            self._update_buttons_for_completion()

    def _check_progress(self):
        """Check testcase generation progress with proper error handling."""
        if not self.celery_task_id:
            return

        try:
            self._check_generation_status()
            self._check_celery_status()
        except Exception as e:
            logger.error(f"Error checking progress: {e}")
            self._append_log(f"Error checking progress: {e}")

    def _check_generation_status(self):
        """Check generation status and handle completion states."""
        generation_status = self.db.get_generation_status_sync(self.task_id)
        if not generation_status:
            return

        status = generation_status.get("generation_status", "unknown")
        message = generation_status.get("message", "")

        # Handle completion states first (early returns)
        if status == "completed":
            self._handle_generation_completed(generation_status)
            return

        if status == "failed":
            self._handle_generation_failed(message)
            return

        # Handle running state
        if status == "in_progress":
            self._update_status("Generating testcases...")
            if message:
                self._append_log(message)

            # Handle progress information if available
            progress_info = generation_status.get("progress")
            if progress_info and isinstance(progress_info, dict):
                current = progress_info.get("current", 0)
                total = progress_info.get("total", 0)
                step_name = progress_info.get("step_name", "")
                details = progress_info.get("details", "")

                if step_name and details:
                    self._append_log(f"{step_name}: {details}")
                elif current and total:
                    progress_percent = int((current / total) * 100) if total > 0 else 0
                    self._append_log(
                        f"Progress: {current}/{total} ({progress_percent}%)"
                    )

    def _check_celery_status(self):
        """Check Celery background task status."""
        if not self.celery_task_id:
            return
        celery_status = self.db.get_background_task_status_sync(self.celery_task_id)
        if not celery_status:
            return

        celery_state = celery_status.get("status", "UNKNOWN")

        if celery_state == "SUCCESS":
            self._append_log("Background task completed successfully.")
            # Check if we haven't already completed via generation status
            if self.monitoring_timer.isActive():
                self._handle_celery_success(celery_status)
        elif celery_state == "FAILURE":
            self._handle_celery_failure(celery_status)
        elif celery_state == "PROGRESS":
            self._handle_celery_progress(celery_status)
        elif celery_state == "PENDING":
            self._append_log("Background task is pending...")
        elif celery_state == "STARTED":
            self._append_log("Background task has started execution.")
        elif celery_state == "RETRY":
            self._append_log("Background task is being retried.")

    def _handle_celery_success(self, celery_status):
        """Handle successful Celery task completion."""
        result = celery_status.get("result", {})
        if isinstance(result, dict):
            testcases_generated = result.get("testcases_generated", 0)
            if testcases_generated > 0:
                self._append_log(
                    f"Generated {testcases_generated} testcases successfully."
                )

            main_viewpoint = result.get("main_viewpoint", "")
            if main_viewpoint:
                self._append_log(f"Used main viewpoint: {main_viewpoint}")

    def _handle_generation_completed(self, generation_status):
        """Handle successful generation completion."""
        self._update_status("Testcase generation completed!")
        self._append_log("Generation completed successfully.")

        if generation_status.get("generated_count"):
            count = generation_status["generated_count"]
            self._append_log(f"Generated {count} testcases.")

        self._stop_monitoring_and_complete()

    def _handle_generation_failed(self, message):
        """Handle generation failure."""
        self._update_status("Testcase generation failed!")
        self._append_log(f"Generation failed: {message}")
        self._stop_monitoring_and_complete()

    def _handle_celery_failure(self, celery_status):
        """Handle Celery task failure."""
        error_info = celery_status.get("info", "")
        self._append_log(f"Background task failed: {error_info}")

    def _handle_celery_progress(self, celery_status):
        """Handle Celery task progress updates."""
        progress_info = celery_status.get("info", {})
        if isinstance(progress_info, dict) and "current" in progress_info:
            current_info = progress_info.get("current", "Processing...")
            self._append_log(f"Progress: {current_info}")

    def _stop_monitoring_and_complete(self):
        """Stop monitoring timer and update UI for completion."""
        self.monitoring_timer.stop()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self._update_buttons_for_completion()

    def _update_status(self, message: str):
        self.status_label.setText(message)

    def _append_log(self, message: str):
        import datetime

        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_output.append(f"[{current_time}] {message}")

    def _update_buttons_for_completion(self):
        self.button_box.clear()
        self.button_box.addButton(QDialogButtonBox.StandardButton.Ok)
        self.button_box.accepted.connect(self.accept)

    def closeEvent(self, event):
        if self.monitoring_timer.isActive():
            self.monitoring_timer.stop()
        event.accept()


def create_validation_widget(cell_data, _row_index):
    items = cell_data if isinstance(cell_data, list) else []
    validation_widget = MutableListWidget(title="", items=items)
    validation_widget.setMaximumHeight(100)
    validation_widget.setDisabled(True)
    return validation_widget


class TaskLoaderWorker(QObject):
    finished = Signal(list)

    def __init__(self, db: DataManager):
        super().__init__()
        self.db = db

    def run(self):
        tasks = []
        list_task = []
        try:
            project = self.db.get_current_project()
            if project and project.project_id:
                tasks = self.db.list_tasks_sync(project.project_id) or []
                list_task = [Task.from_dict(task) for task in tasks]

        except Exception as e:
            logger.error(f"Error loading tasks: {e}")
        self.finished.emit(list_task)


class TaskWidget(QWidget):
    def __init__(self, data_manager: DataManager, parent: Optional[QWidget] = None):
        super().__init__(parent=parent)
        self.db = data_manager
        self.setObjectName("PageWidget")

        # Remove local state - use DataManager's state instead
        self.page_viewpoint_choices = []
        self.component_viewpoint_choices = []
        self.viewpoint_name_to_id_map = {}
        self.viewpoint_id_to_name_map = {}
        self.viewpoint_name_to_object_map = {}

        self.current_tasks: List[Task] = []
        self._updating_selection = False
        self.is_specs_unsaved = False
        self.is_modifying = False
        # Connect to DataManager signals for state management
        self.db.signals.current_project_changed.connect(
            self._on_current_project_changed
        )
        self.db.signals.current_task_changed.connect(self._update_table_selection)
        self.db.signals.viewpoints_changed.connect(self._refresh_viewpoint_data)
        self.db.signals.current_user_changed.connect(self._on_user_changed)

        self._init_ui()
        
        # load data
        self._refresh_viewpoint_data()
        self._load_tasks_in_background()

        self.current_task_card.save_requested.connect(self._update_selected_task)
        self.is_creating_task = False

        # Remove these or set to None
        self.task_creator_thread: Optional[QThread] = None
        self.task_creator_worker: Optional[TaskCreatorWorker] = None

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_viewpoint_data()
    
    def _refresh_viewpoint_data(self):
        """Initialize viewpoint data from DataManager."""
        self.page_viewpoint_choices.clear()
        self.component_viewpoint_choices.clear()
        self.viewpoint_name_to_id_map.clear()
        self.viewpoint_id_to_name_map.clear()
        self.viewpoint_name_to_object_map.clear()
        current_project = self.db.get_current_project()
        if not current_project:
            logger.warning("No current project selected, cannot load viewpoints.")
            return

        viewpoints = self.db.get_viewpoints_sync(current_project.project_id) or []
        
        for vp_dict in viewpoints:
            vp = Viewpoint.from_dict(vp_dict)

            self.viewpoint_name_to_id_map[vp.name] = vp.viewpoint_id
            self.viewpoint_id_to_name_map[vp.viewpoint_id] = vp.name
            self.viewpoint_name_to_object_map[vp.name] = vp

            if vp.viewpoint_type == ViewpointType.PAGE:
                self.page_viewpoint_choices.append(vp.name)
            elif vp.viewpoint_type == ViewpointType.COMPONENT:
                self.component_viewpoint_choices.append(vp.name)

        self.page_viewpoint_choices.sort()
        self.component_viewpoint_choices.sort()

        self.current_task_card.update_dropdown_options(
            "Page Viewpoint", self.page_viewpoint_choices
        )
        logger.debug("Viewpoint data refreshed.")

    def _on_user_changed(self, user):
        if user:
            logger.info(f"User {user.username} logged in. Loading tasks...")
            self._load_tasks_in_background()
        else:
            self.current_tasks = []
            self.tasks_model.set_data([])
            self.db.set_current_task_sync(None)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title_label = QLabel("Task Management")
        title_label.setFont(QFont("Lexend", 18, QFont.Weight.Bold))
        title_label.setObjectName("TitleLabel")
        main_layout.addWidget(title_label)

        task_editing_configs = [
            InputCardConfig(
                label="Task Name",
                input_type=InputType.TEXT,
                placeholder="Select a task to edit its name",
            ),
            InputCardConfig(
                label="Page Viewpoint",
                input_type=InputType.DROPDOWN,
                options_factory=self._get_page_viewpoint_names,
            ),
            InputCardConfig(
                label="Test URL",
                input_type=InputType.TEXT,
                placeholder="Select a task to edit its URL",
            ),
            InputCardConfig(label="Require Login", input_type=InputType.TRUE_FALSE),
        ]

        self.current_task_card = InputCard(
            configs=task_editing_configs,
            save_button_text="Update Task",
            min_w=400,
            max_w=600,
        )
        # The card is disabled as no task can be selected.
        self.current_task_card.setEnabled(False)

        self._setup_tasks_table()

        top_section = QHBoxLayout()
        top_section.addWidget(self.current_task_card, stretch=1)
        top_section.addWidget(self.tasks_table_widget, stretch=2)
        main_layout.addLayout(top_section)

        specifications_title = QLabel("Task Specifications")
        specifications_title.setFont(QFont("Lexend", 14, QFont.Weight.Medium))
        main_layout.addWidget(
            specifications_title, alignment=Qt.AlignmentFlag.AlignLeft
        )

        self._setup_specifications_table()
        main_layout.addWidget(self.specifications_table_widget)
    
    def _run_db_modification_task(self, db_function, *args, **kwargs):
        """Runs a generic DB modification task in the background."""
        if self.is_modifying:
            QMessageBox.warning(self, "Busy", "An operation is already in progress.")
            return
        self.is_modifying = True
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.setEnabled(False)   
        self.modification_thread = QThread()
        self.modification_worker = DbModificationWorker(db_function, *args, **kwargs)
        self.modification_worker.moveToThread(self.modification_thread)

        self.modification_thread.started.connect(self.modification_worker.run)
        self.modification_worker.finished.connect(self._on_db_modification_finished)
        self.modification_worker.finished.connect(self.modification_thread.quit)
        self.modification_worker.finished.connect(self.modification_worker.deleteLater)
        self.modification_thread.finished.connect(self.modification_thread.deleteLater)

        self.modification_thread.start()

    def _on_db_modification_finished(self, success: bool, message: str):
        """Handles the result of the background DB modification."""
        self.is_modifying = False
        QApplication.restoreOverrideCursor()
        self.setEnabled(True)

        if success:
            QMessageBox.information(self, "Success", "Operation completed successfully.")
            self._load_tasks_in_background()  # Refresh data from source
        else:
            QMessageBox.critical(self, "Error", f"Operation failed: {message}")

    def _create_delete_button_widget(self, _cell_data, row_index):
        btn = QPushButton("Delete")
        btn.setFixedSize(60, 24)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setObjectName("RedButton")
        btn.clicked.connect(partial(self._delete_specification, row_index))
        return btn

    def _create_btn_task_spec_actions(self, cell_data, row_index):
        _ = cell_data
        actions_widget = QWidget()
        layout = QHBoxLayout(actions_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        delete_button = QPushButton("Delete")
        delete_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        delete_button.setObjectName("RedButton")
        delete_button.clicked.connect(partial(self._delete_specification, row_index))

        layout.addWidget(delete_button)
        return actions_widget

    def _create_btn_task_actions(self, cell_data, row_index):
        _ = cell_data
        actions_widget = QWidget()
        layout = QHBoxLayout(actions_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        gen_button = QPushButton("Generate testcase")
        gen_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        gen_button.setObjectName("GreenButton")
        gen_button.clicked.connect(partial(self._handle_generate_testcase, row_index))

        # Check if the task has a viewpoint selected
        if row_index < len(self.current_tasks):
            task = self.current_tasks[row_index]
            if not task or not task.viewpoint_id:
                gen_button.setEnabled(False)
                gen_button.setToolTip(
                    "Please select a Page Viewpoint for this task first"
                )
            else:
                gen_button.setToolTip("Generate testcases using AI analysis")

        delete_button = QPushButton("Delete")
        delete_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        delete_button.setObjectName("RedButton")
        delete_button.clicked.connect(partial(self._delete_task, row_index))

        pick_button = QPushButton("🎯 Chọn field")
        pick_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        pick_button.clicked.connect(partial(self._handle_pick_fields, row_index))
        if row_index < len(self.current_tasks) and self.current_tasks[row_index]:
            locators = get_task_locators(self.current_tasks[row_index].task_id)
            pick_button.setToolTip(
                f"Đã chọn {len(locators['fields'])} field - testcase sẽ chạy nhanh không cần agent"
                if locators
                else "Click chọn từng field trên trang để chạy testcase nhanh, chính xác hơn"
            )

        layout.addWidget(gen_button)
        layout.addWidget(pick_button)
        layout.addWidget(delete_button)
        return actions_widget

    def _handle_pick_fields(self, row_index):
        task = self.current_tasks[row_index] if row_index < len(self.current_tasks) else None
        if not task or not task.task_id:
            QMessageBox.warning(self, "Error", "Could not find task details.")
            return
        if not task.url_test:
            QMessageBox.warning(self, "Thiếu URL", "Task chưa có URL cần test.")
            return
        if not task.specs:
            QMessageBox.warning(self, "Chưa có field", "Hãy thêm specifications (field) cho task trước.")
            return

        labels = [f"{i}. {spec.name}" for i, spec in enumerate(task.specs, start=1)] + ["Nút Submit / Lưu"]
        QMessageBox.information(
            self,
            "Chọn field trên trang",
            "Trình duyệt sẽ mở trang cần test. Click lần lượt vào từng field theo thanh đỏ phía trên:\n\n"
            + "\n".join(labels)
            + "\n\n• F2: tạm tắt chế độ chọn (để đăng nhập / mở popup), nhấn lại để chọn tiếp"
            "\n• Esc: bỏ qua field hiện tại",
        )

        self._picker_worker = ElementPickerWorker(task.url_test, labels)
        self._picker_worker.finished_picking.connect(partial(self._on_fields_picked, task))
        self._picker_worker.start()

    def _on_fields_picked(self, task: Task, picked: list, error: str):
        if error:
            QMessageBox.critical(self, "Lỗi", f"Không chọn được field: {error}")
            return

        field_picks, submit = picked[:-1], picked[-1]
        fields = {spec.name: loc for spec, loc in zip(task.specs, field_picks) if loc}
        if not fields:
            QMessageBox.warning(self, "Chưa chọn", "Chưa chọn field nào, không lưu.")
            return
        save_task_locators(task.task_id, fields, submit)

        summary = [
            f"{i}. {spec.name}  →  {loc['desc'] if loc else '(bỏ qua)'}"
            for i, (spec, loc) in enumerate(zip(task.specs, field_picks), start=1)
        ]
        summary.append(f"Submit  →  {submit['desc'] if submit else '(bỏ qua)'}")
        QMessageBox.information(self, "Đã lưu field", "\n".join(summary))
        self._load_tasks_in_background()

    def _handle_generate_testcase(self, row_index):
        logger.info(f"Generate testcase for row {row_index}")

        # Get the task data from the table
        row_data = self.tasks_model.get_row(row_index)
        if not row_data:
            QMessageBox.warning(self, "Error", "Could not find task data.")
            return

        task_id, task_name = row_data[1], row_data[2]

        if not task_id:
            QMessageBox.warning(
                self, "Error", "Cannot generate testcases for a task with no ID."
            )
            return

        # Get the task details to check if viewpoint is selected
        current_task = None
        for task in self.current_tasks:
            if task and task.task_id == task_id:
                current_task = task
                break

        if not current_task:
            QMessageBox.warning(self, "Error", "Could not find task details.")
            return

        if not current_task.viewpoint_id:
            QMessageBox.warning(
                self,
                "No Viewpoint Selected",
                "Please select a Page Viewpoint for this task before generating testcases.",
            )
            return

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            "Generate Testcases",
            f"Do you want to generate testcases for task '{task_name}'?\n\n"
            "This process may take several minutes and will use AI to analyze "
            "the specified page and generate relevant test scenarios.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Open progress dialog
            progress_dialog = TestcaseGenerationProgressDialog(
                self.db, task_id, task_name, self
            )
            if progress_dialog.exec() == QDialog.DialogCode.Accepted:
                # Refresh tasks to show any updates
                self._load_tasks_in_background()
                QMessageBox.information(
                    self,
                    "Generation Complete",
                    f"Testcase generation for '{task_name}' has completed successfully!",
                )

    def _setup_specifications_table(self):

        self.save_specs_button = QPushButton("Save Specifications")
        self.save_specs_button.setObjectName("GreenButton")
        self.save_specs_button.setToolTip(
            "Saves all changes made to the specifications list"
        )
        self.save_specs_button.setEnabled(False)  # Initially disabled
        self.save_specs_button.clicked.connect(self._save_specifications)

        self.specifications_column_configs = [
            TextColumnConfig(
                header="Item name",
                editable=True,
                min_width=150,
                default_width=0.2,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            DropdownColumnConfig(
                header="Required",
                options=["True", "False"],
                min_width=80,
                default_width=0.1,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            NumberColumnConfig(
                header="Min",
                editable=True,
                min_width=50,
                default_width=0.05,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            NumberColumnConfig(
                header="Max",
                editable=True,
                min_width=50,
                default_width=0.05,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            TextColumnConfig(
                header="Specifications",
                editable=True,
                min_width=200,
                default_width=0.25,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            TextColumnConfig(
                header="Default values",
                editable=True,
                min_width=150,
                default_width=0.2,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
            ListDataColumnConfig(
                header="Validation type",
                min_width=300,
                default_width=0.3,
                alignment=Qt.AlignmentFlag.AlignCenter,
                items_factory=self._get_component_viewpoint_names,
            ),
            ActionColumnConfig(
                header="Actions",
                widget_factory=self._create_btn_task_spec_actions,
                min_width=70,
                default_width=0.07,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
        ]
        self.specifications_table_model = TableModel([])
        self.specifications_table_widget = DataTableWidget(
            column_configs=self.specifications_column_configs,
            model=self.specifications_table_model,
            items_per_page=5,
            item_height=110,
            header_height=40,
            show_add_button=True,
            highlight_selected_row=True,
            custom_buttons=[self.save_specs_button],
        )
        self.specifications_table_model.cell_changed.connect(self._on_spec_data_changed)
        self.specifications_table_widget.add_new_row_clicked.connect(
            self._add_new_specification
        )

    def _get_component_viewpoint_names(self) -> List[str]:
        # choices = []
        # for vp_dict in self.db.get_viewpoints_sync():
        #     vp = Viewpoint.from_dict(vp_dict)
        #     if vp.viewpoint_type == ViewpointType.COMPONENT:
        #         choices.append(vp.name)
        # return sorted(choices)
        return self.component_viewpoint_choices

    def _setup_tasks_table(self):
        # Removed SelectColumnConfig to disablef selection via checkboxes
        self.tasks_columns = [
            SelectColumnConfig(header="", select_type=SelectType.SINGLE),
            TextColumnConfig(header="Task ID", editable=False, default_width=0.2),
            TextColumnConfig(header="Task Name", editable=False, default_width=0.4),
            ActionColumnConfig(
                header="Actions",
                editable=False,
                widget_factory=self._create_btn_task_actions,
                default_width=0.25,
            ),
        ]
        self.tasks_model = TableModel([])
        self.tasks_table_widget = DataTableWidget(
            column_configs=self.tasks_columns,
            model=self.tasks_model,
            items_per_page=10,
            item_height=48,
            header_height=40,
            show_add_button=True,
            highlight_selected_row=True,
        )
        self.tasks_table_widget.selection_changed.connect(
            self._on_task_selection_changed
        )
        self.tasks_table_widget.add_new_row_clicked.connect(self._open_add_task_dialog)

    def _prompt_to_save_changes(self) -> bool:
        if not self.is_specs_unsaved:
            return True  # No changes, so proceed.

        previous_task = self.db.get_current_task()
        if not previous_task:
            return True  # No task was selected, nothing to save.

        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"You have unsaved changes for task '{previous_task.task_name}'.\n\nDo you want to save them?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Save:
            self._save_specifications()
            # Proceed only if save was successful (which resets the dirty flag)
            return not self.is_specs_unsaved
        elif reply == QMessageBox.StandardButton.Discard:
            self.is_specs_unsaved = False
            self.save_specs_button.setEnabled(False)
            return True  # Proceed
        else:  # Cancel
            return False  # Cancel the calling action

    def _create_task_actions_widget(self, _cell_data, row_index):
        btn = QPushButton("Delete")
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setFixedSize(70, 26)
        btn.setObjectName("RedButton")
        btn.clicked.connect(partial(self._delete_task, row_index))
        return btn

    def _load_tasks_in_background(self):
        self.task_thread = QThread()
        self.worker = TaskLoaderWorker(self.db)
        self.worker.moveToThread(self.task_thread)
        self.task_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_tasks_loaded)
        self.worker.finished.connect(self.task_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.task_thread.finished.connect(self.task_thread.deleteLater)
        self.task_thread.start()

    def _on_task_selection_changed(self, selected_indices: List[int]):
        if self._updating_selection:
            return

        current_task = self.db.get_current_task()
        new_task_id = None

        if selected_indices:
            # The table data is [None, task_id, task_name, None]
            row = self.tasks_model.get_row(selected_indices[0])
            new_task_id = row[1] if isinstance(row, List) else None
            if new_task_id is None:
                return

        # Only prompt if we are actually switching from a valid task to a different one
        is_switching_task = (
            current_task and new_task_id and new_task_id != current_task.task_id
        )
        is_clearing_selection = current_task and not selected_indices

        if is_switching_task or is_clearing_selection:
            if not self._prompt_to_save_changes():
                # User cancelled. Revert the selection in the table.
                self._updating_selection = True
                try:
                    previous_index = -1
                    for i, task in enumerate(self.current_tasks):
                        if (
                            current_task
                            and current_task.task_id
                            and task.task_id == current_task.task_id
                        ):
                            previous_index = i
                            break
                    if previous_index != -1:
                        self.tasks_table_widget.set_selection([previous_index])
                    else:
                        self.tasks_table_widget.clear_selection()
                finally:
                    self._updating_selection = False
                return  # Abort the selection change

        # --- Original logic for handling the new selection ---
        if not selected_indices:
            self.db.set_current_task_sync(None)
            return

        task = self.current_tasks[selected_indices[0]]
        if not task or not task.task_id:
            self.db.set_current_task_sync(None)
            return

        self.db.set_current_task_sync(task.task_id)

    def _update_table_selection(self, current_task: Optional[Task]):
        """Update table selection to match DataManager's current task."""
        if not current_task:
            current_task = self.db.get_current_task()
        self._updating_selection = True
        try:
            if not current_task or not current_task.task_id:
                self.tasks_table_widget.clear_selection()
                self._updating_selection = False
                return

            # Find the task in our current tasks list
            for index, task in enumerate(self.current_tasks):
                if task and task.task_id == current_task.task_id:
                    self.tasks_table_widget.set_selection([index])
                    break
            else:
                self.tasks_table_widget.clear_selection()
                self.tasks_table_widget.set_selection([])
        finally:

            if not current_task:
                self.current_task_card.clear_data()
                self.current_task_card.setEnabled(False)
                self._refresh_specifications_table(None)
                self._updating_selection = False
                return

            self.current_task_card.setEnabled(True)

            task_details_for_card = {
                "Task Name": current_task.task_name,
                "Test URL": current_task.url_test,
                "Page Viewpoint": self.viewpoint_id_to_name_map.get(
                    current_task.viewpoint_id, "Unknown"
                ),
                "Require Login": current_task.request_login,
            }
            self.current_task_card.set_data(task_details_for_card)
            self._refresh_specifications_table(current_task)
            self._updating_selection = False

    def _update_selected_task(self):
        current_task = self.db.get_current_task()
        if not current_task or not current_task.task_id:
            QMessageBox.warning(
                self, "No Task Selected", "Cannot update a task without a valid ID."
            )
            return

        form_data = self.current_task_card.get_data()

        # Update task properties
        current_task.task_name = form_data.get("Task Name", current_task.task_name)
        current_task.url_test = form_data.get("Test URL", current_task.url_test)
        current_task.viewpoint_id = self.viewpoint_name_to_id_map[
            form_data.get("Page Viewpoint", current_task.viewpoint_id)
        ]
        current_task.request_login = form_data.get(
            "Require Login", current_task.request_login
        )

        self._run_db_modification_task(
            self.db.update_task_sync, current_task.task_id, current_task.to_dict()
        )

    def _on_tasks_loaded(self, tasks: List[Task]):
        # Data format now matches the 3 columns in the new config
        table_data = [
            [
                None,  # Placeholder for SelectColumnConfig (Column 0)
                t.task_id,  # Data for TextColumnConfig "Task ID" (Column 1)
                t.task_name,  # Data for TextColumnConfig "Task Name" (Column 2)
                None,  # Placeholder for ActionColumnConfig (Column 3)
            ]
            for t in tasks
        ]

        self.tasks_model.set_data(table_data)
        self.current_tasks = tasks
        self._update_table_selection(None)

    def _open_add_task_dialog(self):
        if not self.page_viewpoint_choices:
            QMessageBox.warning(
                self,
                "No Page Viewpoint",
                "Please create a Page Viewpoint before creating a new task.",
            )
            return
        
        dialog = AddTaskDialog(
            self.page_viewpoint_choices, self.viewpoint_name_to_id_map, self
        )
        dialog.task_created.connect(self._start_task_creation_in_background)
        dialog.exec()

    def _start_task_creation_in_background(self, task_data: dict):
        # Simple flag check instead of thread state
        if self.is_creating_task:
            QMessageBox.warning(
                self, "Busy", "Please wait for the current task creation to complete."
            )
            return

        # Set flag to prevent multiple concurrent creations
        self.is_creating_task = True

        # Create new thread and worker each time
        self.task_creator_thread = QThread()
        self.task_creator_worker = TaskCreatorWorker(self.db, task_data)
        self.task_creator_worker.moveToThread(self.task_creator_thread)

        # Connect signals
        self.task_creator_thread.started.connect(self.task_creator_worker.run)
        self.task_creator_worker.finished.connect(self._on_task_creation_finished)
        self.task_creator_worker.finished.connect(self.task_creator_thread.quit)
        self.task_creator_worker.finished.connect(self.task_creator_worker.deleteLater)
        self.task_creator_thread.finished.connect(self.task_creator_thread.deleteLater)

        # Start the thread
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.setEnabled(False)
        self.task_creator_thread.start()

    def _on_task_creation_finished(self, result: TaskCreationResult):
        # Reset flag first
        self.is_creating_task = False

        QApplication.restoreOverrideCursor()
        self.setEnabled(True)

        if result.success:
            QMessageBox.information(
                self,
                "Success",
                f"Task '{result.task.task_name if result.task else ''}' created successfully.",
            )
            self._load_tasks_in_background()
            # Set the newly created task as current
            if result.task:
                self.db.set_current_task_sync(result.task.task_id)
        else:
            QMessageBox.critical(
                self, "Error", f"Failed to create the new task: {result.error_message}"
            )

    def _delete_task(self, row_index: int):
        # get_row will now return [task_id, task_name, None]
        row_data = self.tasks_model.get_row(row_index)
        if not row_data:
            return
        task_id, task_name = row_data[1], row_data[0]

        # MODIFICATION: Added check for task ID before proceeding
        if not task_id:
            QMessageBox.warning(self, "Error", "Cannot delete a task with no ID.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the task '{task_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_db_modification_task(self.db.delete_task_sync, task_id)

    def _get_page_viewpoint_names(self) -> List[str]:
        """Returns the current list of page viewpoint names. Used as a factory."""
        return self.page_viewpoint_choices

    def _on_current_project_changed(self, _project):
        """React to DataManager current project changes."""
        # Give the user a last chance to save changes before they are lost.
        self._refresh_viewpoint_data()
        if self.is_specs_unsaved:
            previous_task = self.db.get_current_task()
            if previous_task:
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    f"You have unsaved changes for task '{previous_task.task_name}'.\n\nSave them before switching projects?",
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard,
                    QMessageBox.StandardButton.Save,
                )
                if reply == QMessageBox.StandardButton.Save:
                    self._save_specifications()

        # Reset dirty flag as we are leaving the context for a new project.
        self.is_specs_unsaved = False
        self.save_specs_button.setEnabled(False)
        
        self._refresh_viewpoint_data()
        # Reload tasks for the new project
        self._load_tasks_in_background()
        # Clear current task selection
        self.db.set_current_task_sync(None)

    def _add_new_specification(self):
        current_task = self.db.get_current_task()
        if not current_task or not current_task.task_id:
            QMessageBox.warning(
                self,
                "No Task Selected",
                "Please select a valid task before adding a specification.",
            )
            return

        new_spec = Spec(
            name="New spec",
            required=False,
            min=0,
            max=0,
            specification="",
            default_value="",
            validation_types=[],
        )

        if current_task.specs is None:
            current_task.specs = []
        current_task.specs.append(new_spec)

        new_row_data = [
            new_spec.name,
            "False",
            new_spec.min,
            new_spec.max,
            new_spec.specification,
            new_spec.default_value,
            [],  
            None,
        ]

        insert_position = self.specifications_table_model.get_row_count()

        if hasattr(self.specifications_table_widget, 'set_auto_edit_row'):
             self.specifications_table_widget.set_auto_edit_row(insert_position)
        self.specifications_table_model.add_row(insert_position, new_row_data)
        # Instead of saving, just refresh the table and mark as dirty
        # self._refresh_specifications_table(task=current_task)
        self.is_specs_unsaved = True
        self.save_specs_button.setEnabled(True)

    def _refresh_specifications_table(self, task: Optional[Task]):
        # Reset dirty flag whenever the table is reloaded
        self.is_specs_unsaved = False
        self.save_specs_button.setEnabled(False)

        if task and task.specs:
            specs_data = []
            for spec in task.specs:
                validation_display_names = []
                if spec.validation_types:
                    for validation_item in spec.validation_types:
                        if isinstance(validation_item, dict):
                            validation_display_names.append(
                                validation_item.get("name", "")
                            )
                        elif isinstance(validation_item, str):
                            validation_display_names.append(validation_item)

                specs_data.append(
                    [
                        spec.name,
                        "True" if spec.required else "False",
                        spec.min,
                        spec.max,
                        spec.specification,
                        spec.default_value,
                        validation_display_names,
                        None,
                    ]
                )
            self.specifications_table_model.set_data(specs_data)
        else:
            self.specifications_table_model.set_data([])

    def _on_spec_data_changed(self, row: int, column: int, new_value: Any):
        import copy

        current_task = self.db.get_current_task()
        if not current_task or not current_task.specs or row >= len(current_task.specs):
            return

        try:
            spec_to_update = current_task.specs[row]
            header_name = self.specifications_column_configs[column].header

            if header_name == "Item name":
                spec_to_update.name = str(new_value)
            elif header_name == "Required":
                # Assuming the dropdown returns a string "True" or "False"
                spec_to_update.required = str(new_value).lower() == "true"
            elif header_name == "Min":
                spec_to_update.min = int(new_value)
            elif header_name == "Max":
                spec_to_update.max = int(new_value)
            elif header_name == "Specifications":
                spec_to_update.specification = str(new_value)
            elif header_name == "Default values":
                spec_to_update.default_value = str(new_value)
            elif header_name == "Validation type":
                if isinstance(new_value, list):
                    # Check if the number of selected items exceeds the limit
                    if len(new_value) > 5:
                        QMessageBox.warning(
                            self,
                            "Selection Limit Reached",
                            "You can select a maximum of 5 validation types. The selection has been truncated.",
                        )
                        new_value = new_value[:5]

                        spec_to_update.validation_types = new_value

                        def refresh_table_and_enable_save():
                            self._refresh_specifications_table(current_task)
                            self.is_specs_unsaved = True
                            self.save_specs_button.setEnabled(True)

                        QTimer.singleShot(0, refresh_table_and_enable_save)
                    else:
                        spec_to_update.validation_types = new_value

            # Mark as dirty and enable the save button
            self.is_specs_unsaved = True
            self.save_specs_button.setEnabled(True)

        except (ValueError, TypeError) as e:
            logger.error(f"Error processing spec change: {e}")
            QMessageBox.warning(self, "Invalid Input", f"Could not apply change: {e}")
            # Optionally, you could revert the change in the model here
            self._refresh_specifications_table(current_task)

    def _save_specifications(self):
        import json
        """Saves all specification changes for the current task to the database."""
        current_task = self.db.get_current_task()
        if not current_task or not current_task.task_id:
            QMessageBox.warning(self, "No Task", "No current task is selected.")
            return

        if not self.is_specs_unsaved:
            QMessageBox.information(
                self,
                "No Changes",
                "There are no unsaved changes to the specifications.",
            )
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            payload = current_task.to_dict()

            if "specs" in payload:
                payload["items"] = payload.pop("specs")

            for item in payload.get("items", []):
                if "name" in item:
                    item["item_name"] = item.pop("name")
                if "specification" in item:
                    item["spec"] = item.pop("specification")
                if "default_value" in item:
                    item["default"] = item.pop("default_value")

                item["required"] = str(item.get("required", "false")).lower() == "true"
                validation_types = item.get("validation_types")
                if not validation_types:
                    continue

                cleaned_validation_objects = []
                for element in validation_types:
                    if isinstance(element, str):
                        viewpoint_obj = self.viewpoint_name_to_object_map.get(element)
                        if viewpoint_obj:
                            cleaned_validation_objects.append(viewpoint_obj.to_dict())
                    elif isinstance(element, dict):
                        cleaned_validation_objects.append(element)

                item["validation_types"] = cleaned_validation_objects

            logger.debug(f"Payload for update_task_sync: {json.dumps(payload, indent=2)}")

            self._run_db_modification_task(
                self.db.update_task_sync, current_task.task_id, payload
            )

            self.is_specs_unsaved = False
            self.save_specs_button.setEnabled(False)

        except Exception as e:
            logger.error(f"Error preparing to save specifications: {e}")
            QMessageBox.critical(
                self, "Error", f"An unexpected error occurred while preparing to save: {e}"
            )
        finally:
            QApplication.restoreOverrideCursor()

    def _delete_specification(self, row_index: int):
        current_task = self.db.get_current_task()
        if not current_task or not current_task.task_id:
            return
        if current_task.specs and 0 <= row_index < len(current_task.specs):
            spec_name = current_task.specs[row_index].name
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete the specification '{spec_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

            current_task.specs.pop(row_index)
            self._refresh_specifications_table(current_task)
            self.is_specs_unsaved = True
            self.save_specs_button.setEnabled(True)
