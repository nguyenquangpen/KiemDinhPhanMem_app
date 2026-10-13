"""
TestCase Management Window with API Integration

This window provides comprehensive test case management functionality
with full API integration and modern UI components.
"""

import asyncio
import base64
import os
import re
import sys
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
    QProgressDialog,
)

from asset import tokens
from models.data_classes import Project
from views.components import icons, ui_kit
from models.database import DataManager
from services.logging_config import get_logger
from services.field_locators import get_task_locators
from services.quick_runner import run_quick_testcase
from services.session import session_manager
from settings.config import API_ENDPOINT, WS_ENDPOINT

# from ui.build.ui_screenshot_viewer import Ui_ScreenshotViewer
from views.components.screenshot_gallery_widget import ScreenshotGalleryWidget
from views.components.screenshot_viewer import ScreenshotViewerDialog
from views.components.table import (
    ActionColumnConfig,
    ColumnConfig,
    RowColor,
    DataTableWidget,
    SelectColumnConfig,
    SelectType,
    TableModel,
    TextColumnConfig,
)

# Import and use the existing AddEditTestCaseDialog
from .add_edit_testcase_dialog import AddEditTestCaseDialog

logger = get_logger("testcases_main")

from services.websocket_agent_runner import (
    EnhancedAgentTestRunnerService as TestRunnerService,
)

# Custom UI setup for widget (not using ui_testcases which is for QMainWindow)

logger = get_logger("testcases_main")


class TestCaseMainWorker(QThread):
    """Worker thread for async test case operations in main window."""

    operation_completed = Signal(str, object)  # operation_type, result
    operation_failed = Signal(str, str)  # operation_type, error_message
    test_progress = Signal(str, str, str)  # test_id, test_name, status
    ui_test_update = Signal(str, str)  # update_type, data

    def __init__(self, data_manager: DataManager, operation: str, **kwargs):
        super().__init__()
        self.data_manager = data_manager
        self.operation = operation
        self.kwargs = kwargs
        self.cancellation_requests = set()
        self.current_test_id = None
        self.current_task = None
        self.results = []
        self._loop = None
        self._is_stopping = False

    def run(self):
        try:
            if self.operation == "load_test_cases":
                result = asyncio.run(self._load_test_cases())
            elif self.operation == "delete_test_case":
                test_case_id = self.kwargs.get("test_case_id")
                delete_success = asyncio.run(self._delete_test_case())
                result = {"success": delete_success, "test_case_id": test_case_id}
            elif self.operation == "run_test_cases":
                result = asyncio.run(self._run_test_cases())
            elif self.operation == "save_execution_results_batch":
                result = asyncio.run(self._save_execution_results_batch())
            elif self.operation == "get_execution_history":
                result = asyncio.run(self._get_execution_history())
            else:
                raise ValueError(f"Unknown operation: {self.operation}")

            self.operation_completed.emit(self.operation, result)

        except asyncio.CancelledError:
            logger.info("Test execution was successfully cancelled by the user.")
            self.operation_completed.emit(self.operation, self.results)
            pass

        except Exception as e:
            failed_id = (
                self.kwargs.get("test_case_id")
                if self.operation == "delete_test_case"
                else None
            )
            error_message = (
                f"Operation '{self.operation}' failed for ID '{failed_id}': {e}"
                if failed_id
                else str(e)
            )
            logger.error("Main worker operation failed: %s", error_message)
            self.operation_failed.emit(self.operation, error_message)

    async def _save_execution_results_batch(self):
        """Save multiple execution results to database in batch"""
        execution_results = self.kwargs.get("execution_results")
        if not execution_results:
            raise ValueError("Execution results data is required")

        saved_count = 0
        failed_count = 0

        for execution_result in execution_results:
            try:
                await self.data_manager.save_test_execution_result(execution_result)
                saved_count += 1
                logger.debug(
                    "Saved execution result for test: %s",
                    execution_result.get("test_name", "unknown"),
                )
            except Exception as e:
                failed_count += 1
                logger.error(
                    "Failed to save execution result for test %s: %s",
                    execution_result.get("test_name", "unknown"),
                    str(e),
                )

        return {"saved": saved_count, "failed": failed_count}

    async def _load_test_cases(self):
        project_id = self.kwargs.get("project_id")
        task_id = self.kwargs.get("task_id")
        if not project_id:
            raise ValueError("Project ID is required for loading test cases")
        return await self.data_manager.get_test_cases(project_id, task_id)

    async def _delete_test_case(self):
        test_case_id = self.kwargs.get("test_case_id")
        if not test_case_id:
            raise ValueError("Test case ID is required for deletion")
        return await self.data_manager.delete_test_case(test_case_id)

    async def _stop_test_cases(self):
        """Stop ongoing test case executions."""
        test_case_id = self.kwargs.get("test_case_id")
        if not test_case_id:
            raise ValueError("Test case ID is required for stopping execution")

    async def _run_test_cases(self):
        """Execute test cases using Enhanced Agent Runner with WebSocket capability"""
        self._loop = asyncio.get_event_loop()
        test_cases = self.kwargs.get("test_cases", [])
        project_id = self.kwargs.get("project_id")
        headless_mode = self.kwargs.get(
            "headless", False
        )  # Default to headed mode for visibility
        use_websocket = self.kwargs.get(
            "use_websocket", True
        )  # Default to WebSocket mode

        if not TestRunnerService:
            raise RuntimeError("No test runner service available")

        self.runner_service = TestRunnerService(
            headless=headless_mode,
            use_websocket=use_websocket,
            websocket_url=WS_ENDPOINT,
            auth_token=session_manager.get_access_token(),
            project_id=project_id,
        )
        logger.info(
            "Initialized Enhanced Agent Test Runner (WebSocket: %s)", use_websocket
        )

        self.results = []

        for test_case in test_cases:
            test_id = str(test_case.get("uuid", "unknown"))
            test_name = test_case.get("test_case", "Unknown Test")

            if test_id in self.cancellation_requests:
                logger.info(f"Skip canceled test case: {test_name} ({test_id})")
                self.test_progress.emit(test_id, test_name, "cancelled")
                self.results.append(
                    {
                        "test_id": test_id,
                        "test_name": test_name,
                        "status": "cancelled",
                        "error_message": "Test execution cancelled by user",
                    }
                )
                continue
            self.current_test_id = test_id

            # Emit progress update
            self.test_progress.emit(test_id, test_name, "running")

            try:
                project_data = None
                if project_id:
                    project_obj = await self.data_manager.get_project_by_id(
                        project_id, self.data_manager.current_local_user_id
                    )
                    if project_obj:
                        project_data = project_obj.to_dict()

                task_data = None
                task_uuid = test_case.get("task_uuid") or test_case.get("task_id")
                if task_uuid:
                    task_data = await self.data_manager.get_task(task_uuid)

                checkpoint_data = self.kwargs.get("checkpoint_data", None)
                
                clean_test_case = test_case.copy()

                if "checkpoint_data" in clean_test_case:
                    del clean_test_case["checkpoint_data"]
                
                if "test_result_details" in clean_test_case:
                    del clean_test_case["test_result_details"]

                full_context = {
                    "test_case": clean_test_case,
                    "project": project_data,
                    "task": task_data,
                    "checkpoint_data": checkpoint_data,
                }

                # Task đã chọn field trên trang -> chạy runner cố định (không cần agent LLM duyệt DOM)
                locators = get_task_locators(task_uuid) if task_uuid else None
                if locators and task_data:
                    logger.info("Quick run (picked fields) for test case: %s", test_name)
                    self.current_task = asyncio.create_task(
                        run_quick_testcase(
                            clean_test_case,
                            task_data,
                            locators,
                            API_ENDPOINT,
                            session_manager.get_access_token(),
                            headless=headless_mode,
                        )
                    )
                else:
                    self.current_task = asyncio.create_task(
                        self.runner_service.execute_single_test(
                            full_context, on_step_update=self._on_step_change
                        )
                    )
                result = await self.current_task

                # Enhanced status handling for WebSocket communication
                if result:
                    status = result.get("status", "unknown")
                    if status in ["passed", "completed"]:
                        self.test_progress.emit(test_id, test_name, "passed")
                    elif status == "failed":
                        self.test_progress.emit(test_id, test_name, "failed")
                    else:
                        self.test_progress.emit(test_id, test_name, "error")
                else:
                    self.test_progress.emit(test_id, test_name, "error")

                # Enhance result with additional data for database storage
                if result:
                    result.update(
                        {
                            "test_id": test_id,
                            "testcase_id": test_case.get("id") or test_case.get("uuid"),
                            "test_name": test_name,
                            "project_id": project_id,
                            "end_time": result.get("end_time")
                            or datetime.now().isoformat(),
                            "execution_id": f"{test_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                            "checkpoint_data": result.get("checkpoint_data"),
                        }
                    )

                self.results.append(result)

            except asyncio.CancelledError:
                logger.info(f"Task cancelled: {test_name}")
                self.test_progress.emit(test_id, test_name, "cancelled")
                self.results.append(
                    {
                        "test_id": test_id,
                        "test_name": test_name,
                        "status": "cancelled",
                        "error_message": "Task was cancelled",
                    }
                )

            except Exception as e:
                logger.error("Test case %s execution failed: %s", test_name, str(e))
                self.test_progress.emit(test_id, test_name, "error")
                self.results.append(
                    {
                        "test_id": test_id,
                        "test_name": test_name,
                        "status": "error",
                        "error": str(e),
                        "websocket_communication": False,
                    }
                )

            finally:
                self.current_test_id = None
                self.current_task = None
                self.runner_service = None

        if hasattr(self, "runner_service") and self.runner_service:
            await self.runner_service.cleanup()
        self._loop = None

        return self.results

    async def _save_execution_result(self):
        """Save execution result to database"""
        execution_result = self.kwargs.get("execution_result")
        if not execution_result:
            raise ValueError("Execution result data is required")
        return await self.data_manager.save_test_execution_result(execution_result)

    async def _get_execution_history(self):
        """Get execution history for a project"""
        project_id = self.kwargs.get("project_id")
        if not project_id:
            raise ValueError("Project ID is required for execution history")
        return await self.data_manager.get_test_execution_results(project_id)

    def _on_step_change(self, step_val):
        if self.current_test_id:
            self.ui_test_update.emit(self.current_test_id, str(step_val))

    def stop(self):
        """Signals the worker to stop the test execution."""
        logger.info(
            "Stop signal received. Attempting to gracefully stop test execution."
        )
        self.is_stopping = True

    def request_cancellation(self, test_id: set):
        self.cancellation_requests.update(test_id)
        logger.info(f"receive stop request from ID: {test_id}")
        if self.current_test_id and self.current_test_id in self.cancellation_requests:
            logger.info(f"Performing graceful stop for test ID: {self.current_test_id}")
            asyncio.run_coroutine_threadsafe(self._perform_graceful_stop(), self._loop)
        else:
            logger.warning("Runner service does not support graceful_stop!")

    async def _perform_graceful_stop(self):
        """Perform graceful stop of the current test execution."""
        try:
            await self.runner_service.runner.graceful_stop()
            if self.current_task:
                await asyncio.wait_for(self.current_task, timeout=20)
        except asyncio.TimeoutError:
            logger.warning("Server took too long to stop. Force killing...")
            if self.current_task:
                self.current_task.cancel()
        except Exception as e:
            logger.error(f"Error during graceful stop: {e}")
            if self.current_task:
                self.current_task.cancel()


class TestCaseMainWindow(QWidget):
    """Main test case management window with full API integration."""

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self.setObjectName("PageWidget")
        self.db = data_manager
        self.current_project: Optional[Project] = None
        self.current_task: Optional[Dict] = None
        self.test_cases: List[Dict] = []
        self.deletion_queue: List[str] = []
        self.deletion_states: List[int] = []
        self.worker: Optional[TestCaseMainWorker] = None

        # Create custom UI layout for widget
        self.setup_ui()
        self._setup_datatable()
        self.setup_connections()
        self.refresh_project_data()

        # Set window properties
        self.setWindowTitle("Test Case Management System")
        self.setMinimumSize(1000, 600)

        logger.info("TestCaseMainWindow initialized")

    # -----------------------
    # Internal utilities
    # -----------------------
    def _project_root(self) -> str:
        """Return absolute path to project root (one level above src)."""
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))

    def _slugify(self, value: str) -> str:
        """Create a filesystem-safe, ASCII-only slug from a name."""
        if not value:
            return "screenshot"
        # Remove accents, keep ASCII, then replace non-alnum with underscores
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
        return value or "screenshot"

    def _format_run_timestamp(self, iso_str: Optional[str]) -> str:
        """Format an ISO datetime string to folder-friendly 'YYYYmmdd_HHMMSS'."""
        dt: datetime
        try:
            dt = datetime.fromisoformat(iso_str) if iso_str else datetime.now()
        except Exception:
            dt = datetime.now()
        return dt.strftime("%Y%m%d_%H%M%S")

    def _save_test_execution_results_to_database(
        self, results: List[Dict], screenshot_paths: Dict[str, List[str]]
    ):
        """Save test execution results to database with screenshot file paths."""
        if not self.current_project:
            logger.warning("No current project for saving test results")
            return

        logger.info("Saving %d test execution results to database", len(results))
        execution_results = []

        for result in results or []:
            try:
                test_id = str(result.get("test_id", "unknown"))
                status = result.get("status", "unknown")
                is_success = status in ["passed", "completed"]
                final_step = 0 if is_success else result.get("step_number", 0)
                final_checkpoint = None if is_success else result.get("checkpoint_data")
                execution_result = {
                    "execution_id": result.get("execution_id"),
                    "testcase_id": result.get("testcase_id") or result.get("test_id"),
                    "test_name": result.get("test_name", "Unknown Test"),
                    "project_id": self.current_project.project_id,
                    "status": result.get("status", "unknown"),
                    "start_time": result.get("start_time", datetime.now().isoformat()),
                    "end_time": result.get("end_time", datetime.now().isoformat()),
                    "error_message": result.get("error_message", ""),
                    "error_log": result.get("error_log", ""),
                    "screenshots": screenshot_paths.get(
                        test_id, []
                    ),  # File paths instead of base64
                    "screenshots_count": len(screenshot_paths.get(test_id, [])),
                    "execution_duration": self._calculate_duration(
                        result.get("start_time"), result.get("end_time")
                    ),
                    "executed_by_user_id": None,  # TODO: Get current user ID
                    "created_at": datetime.now().isoformat(),
                    "checkpoint_data": final_checkpoint,
                    "step_number": final_step,
                }
                execution_results.append(execution_result)

            except Exception as e:
                logger.error(
                    "Failed to prepare execution result for test %s: %s",
                    result.get("test_name", "unknown"),
                    str(e),
                )
        # Save all results in a single batch operation using one worker
        if execution_results:
            self._save_execution_results_batch(execution_results)

    def _save_execution_results_batch(self, execution_results: List[Dict]):
        """Save multiple execution results to database using a single worker thread."""
        try:
            # Create single worker for batch database save operation
            self._save_worker = TestCaseMainWorker(
                self.db,
                "save_execution_results_batch",
                execution_results=execution_results,
            )
            # Ensure any existing save worker is properly cleaned up
            if hasattr(self, "_save_worker") and self._save_worker.isRunning():
                logger.debug(
                    "Previous save worker still running, waiting for completion..."
                )
                self._save_worker.wait(4000)  # Wait up to 5 seconds

            self._save_worker.operation_completed.connect(
                self._on_execution_results_batch_saved
            )
            self._save_worker.operation_failed.connect(
                self._on_execution_results_batch_save_failed
            )
            self._save_worker.start()

        except Exception as e:
            logger.error(
                "Failed to start execution results batch save worker: %s", str(e)
            )

    @Slot(str, object)
    def _on_execution_results_batch_saved(self, operation: str, result):
        """Handle successful batch execution results save."""
        if operation == "save_execution_results_batch":
            saved_count = result.get("saved", 0)
            failed_count = result.get("failed", 0)
            logger.info(
                "Batch execution results saved: %d successful, %d failed",
                saved_count,
                failed_count,
            )
            if failed_count > 0:
                logger.warning("Some execution results failed to save to database")

    @Slot(str, str)
    def _on_execution_results_batch_save_failed(self, operation: str, error_msg: str):
        """Handle failed batch execution results save."""
        if operation == "save_execution_results_batch":
            logger.error("Failed to save execution results batch: %s", error_msg)

    def _save_test_run_screenshots(self, results: List[Dict]) -> Dict[str, List[str]]:
        """Decode and save screenshots for each test result.
        Returns a mapping of test_id -> list of saved file paths.
        """
        saved: Dict[str, List[str]] = {}
        base_dir = os.path.join(self._project_root(), "screenshots")
        os.makedirs(base_dir, exist_ok=True)

        for result in results or []:
            test_id = str(result.get("test_id", "unknown"))
            test_name = result.get("test_name", "test")
            # Prefer end_time, fallback to start_time, then now
            run_folder = self._format_run_timestamp(
                result.get("end_time") or result.get("start_time")
            )
            target_dir = os.path.join(base_dir, test_id, run_folder)
            os.makedirs(target_dir, exist_ok=True)

            screenshots = result.get("screenshots") or []
            pad = max(2, len(str(len(screenshots) or 0)))
            saved_paths: List[str] = []

            for idx, img in enumerate(screenshots, start=1):
                if not img:
                    continue

                # If it's already a path to an existing file, just reuse it
                if isinstance(img, str) and os.path.exists(img):
                    saved_paths.append(img)
                    continue

                # Handle base64 string, with optional data URL prefix
                data_str = img if isinstance(img, str) else ""
                if data_str.startswith("data:image"):
                    data_str = data_str.split(",", 1)[1] if "," in data_str else ""

                try:
                    png_bytes = base64.b64decode(data_str)
                except Exception as e:
                    logger.warning(
                        "Invalid screenshot data for %s #%d: %s", test_name, idx, str(e)
                    )
                    continue

                filename = f"{self._slugify(test_name)}_{str(idx).zfill(pad)}.png"
                out_path = os.path.join(target_dir, filename)
                try:
                    with open(out_path, "wb") as f:
                        f.write(png_bytes)
                    saved_paths.append(out_path)
                    logger.info("Saved screenshot: %s", out_path)
                except Exception as e:
                    logger.error("Failed to write screenshot %s: %s", out_path, str(e))

            saved[test_id] = saved_paths

        return saved

    def _find_latest_screenshots_for_test(
        self, test_case: Dict
    ) -> tuple[List[str], Optional[str]]:
        """Find the latest run's screenshots for a given test case.

        Returns (paths, run_dir) where run_dir is the directory of the latest run or None.
        """
        test_uuid = str(test_case.get("uuid") or "").strip()
        fallback_id = str(test_case.get("id") or "").strip()
        base_dir = os.path.join(self._project_root(), "screenshots")

        def list_images_in(dir_path: str) -> List[str]:
            exts = {".png", ".jpg", ".jpeg"}
            try:
                names = sorted(os.listdir(dir_path))
            except Exception:
                return []
            return [
                os.path.join(dir_path, n)
                for n in names
                if os.path.splitext(n)[1].lower() in exts
            ]

        # Prefer UUID folder
        for folder_name in (test_uuid, fallback_id):
            if not folder_name:
                continue
            test_dir = os.path.join(base_dir, folder_name)
            if not os.path.isdir(test_dir):
                continue
            try:
                run_dirs = [
                    os.path.join(test_dir, d)
                    for d in os.listdir(test_dir)
                    if os.path.isdir(os.path.join(test_dir, d))
                ]
                # Sort by folder name desc (YYYYmmdd_HHMMSS sorts lexicographically)
                run_dirs.sort(reverse=True)
            except Exception:
                run_dirs = []

            if not run_dirs:
                # Maybe images directly inside test_dir
                imgs = list_images_in(test_dir)
                if imgs:
                    return imgs, test_dir
                continue

            latest_dir = run_dirs[0]
            imgs = list_images_in(latest_dir)
            if imgs:
                return imgs, latest_dir

        return [], None

    def setup_ui(self):
        """Setup UI components for the widget"""
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 28, 32, 28)
        main_layout.setSpacing(20)

        # Header: title + main actions
        self.addButton = ui_kit.button("Add test case", "neutral", "plus")
        self.stopButton = ui_kit.button("Stop", "danger", "stop")
        self.stopButton.setToolTip("Stop the selected test cases")
        self.runButton = ui_kit.button("Run selected", "primary", "play")
        self.header = ui_kit.page_header(
            "Test cases", "", [self.addButton, self.stopButton, self.runButton]
        )
        main_layout.addWidget(self.header)

        # Summary + bulk actions above the table
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.summary_badges = {
            "all": ui_kit.badge("All 0", "info"),
            "ok": ui_kit.badge("OK 0", "ok"),
            "ng": ui_kit.badge("NG 0", "ng"),
            "run": ui_kit.badge("Running 0", "run"),
            "none": ui_kit.badge("Not run 0", "none"),
        }
        for badge in self.summary_badges.values():
            toolbar.addWidget(badge)
        toolbar.addStretch(1)
        self.deleteButton = ui_kit.button("Delete selected", "ghost-danger", "trash", small=True)
        toolbar.addWidget(self.deleteButton)
        main_layout.addLayout(toolbar)

        self.table_container = QWidget()
        main_layout.addWidget(self.table_container, 1)

    @staticmethod
    def _result_tone(text: str) -> str:
        t = str(text or "").strip().lower()
        if t in ("passed", "completed", "ok", "success"):
            return "ok"
        if t in ("failed", "error", "ng"):
            return "ng"
        if t.startswith("running") or t in ("cancelled", "stopping"):
            return "run"
        return "none"

    def _create_result_cell(self, cell_data, row_index):
        _ = row_index
        text = str(cell_data or "Pending")
        return ui_kit.badge(text, self._result_tone(text))

    def _create_field_cell(self, cell_data, row_index):
        _ = row_index
        return ui_kit.label(str(cell_data or ""), "CellStrong", wrap=True)

    def _create_muted_cell(self, cell_data, row_index):
        _ = row_index
        return ui_kit.label(str(cell_data or ""), "MutedText", wrap=True)

    def _update_summary(self):
        """Refresh the OK / NG / running counters above the table."""
        counts = {"ok": 0, "ng": 0, "run": 0, "none": 0}
        for i in range(self.table_model.get_row_count()):
            row = self.table_model.get_row(i) or []
            counts[self._result_tone(row[5] if len(row) > 5 else "")] += 1
        total = sum(counts.values())
        ui_kit.set_badge(self.summary_badges["all"], f"All {total}", "info")
        ui_kit.set_badge(self.summary_badges["ok"], f"OK {counts['ok']}", "ok")
        ui_kit.set_badge(self.summary_badges["ng"], f"NG {counts['ng']}", "ng")
        ui_kit.set_badge(self.summary_badges["run"], f"Running {counts['run']}", "run")
        ui_kit.set_badge(self.summary_badges["none"], f"Not run {counts['none']}", "none")
        self.summary_badges["run"].setVisible(counts["run"] > 0)

        task_name = getattr(self.current_task, "task_name", "") if self.current_task else ""
        noun = "case" if total == 1 else "cases"
        subtitle = f"Task \u201c{task_name}\u201d \u00b7 {total} {noun}" if task_name else f"{total} {noun}"
        self.header.subtitle_label.setText(subtitle)
        self.header.subtitle_label.setVisible(True)

    def _setup_datatable(self):
        """Setup the DataTableWidget with consistent project styling."""
        left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        column_configs: List[ColumnConfig] = [
            SelectColumnConfig(
                header="",
                default_width=0.04,
                min_width=40,
                resizable=True,
                select_type=SelectType.MULTIPLE,
            ),
            TextColumnConfig(header="Field", default_width=0.11, resizable=True, alignment=left,
                             widget_factory=self._create_field_cell),
            TextColumnConfig(header="Type", default_width=0.10, alignment=left,
                             widget_factory=self._create_muted_cell),
            TextColumnConfig(
                header="Test case",
                default_width=0.33,
                alignment=left,
            ),
            TextColumnConfig(header="Steps", default_width=0.05, min_width=56),
            TextColumnConfig(header="Result", default_width=0.09, min_width=90, alignment=left,
                             widget_factory=self._create_result_cell),
            TextColumnConfig(header="Run status", default_width=0.09, min_width=90, alignment=left,
                             widget_factory=self._create_muted_cell),
            TextColumnConfig(header="Updated", default_width=0.09, min_width=90, alignment=left,
                             widget_factory=self._create_muted_cell),
            ActionColumnConfig(
                header="",
                default_width=0.12,
                min_width=120,
                resizable=True,
                widget_factory=self._create_action_buttons_widget,
            ),
        ]

        self.table_model = TableModel([])
        self.table_widget = DataTableWidget(
            column_configs=column_configs,
            model=self.table_model,
            item_height=52,
            header_height=44,
            items_per_page=15,
            highlight_selected_row=True,
        )
        self.table_model.data_changed.connect(self._update_summary)

        # Thêm table widget vào container
        table_layout = QVBoxLayout(self.table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(self.table_widget)

    def setup_connections(self):
        """Setup button connections"""
        self.runButton.clicked.connect(self.run_tests)
        self.deleteButton.clicked.connect(self.delete_selected)
        self.addButton.clicked.connect(self.add_test_case)
        self.stopButton.clicked.connect(self.stop_selected)

    def refresh_project_data(self):
        """Refresh project data and load test cases for current project."""
        current_project = self.db.get_current_project()
        current_task = self.db.get_current_task()
        self.current_task = current_task

        if current_project:
            self.current_project = current_project
            logger.info("Loading test cases for project: %s", current_project.name)
            self.load_test_cases()
        else:
            logger.warning("No current project available")
            self.current_project = None
            self.test_cases = []
            self.table_model.set_data([])

    def load_test_cases(self):
        """Load test cases from API using worker thread"""
        if not self.current_project:
            logger.warning("No current project set for loading test cases")
            return

        if self.worker and self.worker.isRunning():
            logger.debug("Worker already running, skipping test case load")
            return

        logger.info(
            "Loading test cases for project ID: %s", self.current_project.project_id
        )
        self.worker = TestCaseMainWorker(
            self.db,
            "load_test_cases",
            project_id=self.current_project.project_id,
            task_id=self.current_task.task_id if self.current_task else None,
        )
        self.worker.operation_completed.connect(self.on_test_cases_loaded)
        self.worker.operation_failed.connect(self.on_operation_failed)
        self.worker.start()

    @Slot(str, object)
    def on_test_cases_loaded(self, operation: str, result):
        """Handle loaded test cases"""
        logger.info("Operation %s completed successfully", operation)
        if operation == "load_test_cases":
            self.test_cases = result or []
            model_data = self._format_data_for_model(self.test_cases)
            self.table_model.set_data(model_data)

    def _format_data_for_model(self, test_cases: List[Dict]) -> List[List]:
        """Formats the API data into a list of lists for the TableModel."""
        formatted_data = []
        for tc in test_cases:
            updated_at = (
                tc.get("updated_at", "").split("T")[0]
                if "T" in tc.get("updated_at", "")
                else "N/A"
            )
            test_result = tc.get("test_result", "Pending")
            run_status = tc.get("last_run_status", "Not Run")

            if tc.get("test_result_details"):
                details_data = tc["test_result_details"]
                details_dict = None

                if isinstance(details_data, list) and details_data:
                    details_dict = details_data[0]
                elif isinstance(details_data, dict):
                    details_dict = details_data

                if details_dict and isinstance(details_dict, dict):
                    test_result = details_dict.get("status", test_result).title()

                tc["saved_step"] = tc.get("step_number", 0)
                tc["checkpoint_data"] = tc.get("checkpoint_data", {})

            row = [
                None,
                tc.get("test_field", "Component"),
                tc.get("test_type", "Functional"),
                tc.get("test_case", "Unnamed Test"),
                tc.get("step_number", 0),
                test_result,
                run_status,
                updated_at,
                tc,
            ]
            formatted_data.append(row)
        return formatted_data

    @Slot(str, str)
    def on_operation_failed(self, operation: str, error_msg: str):
        """Handle operation failures"""
        logger.error("Operation %s failed: %s", operation, error_msg)
        if operation == "load_test_cases":
            QMessageBox.warning(
                self, "Load Error", f"Failed to load test cases: {error_msg}"
            )
        elif operation == "delete_test_case":
            QMessageBox.warning(
                self, "Delete Error", f"Failed to delete test case: {error_msg}"
            )
            self._process_next_deletion()
        elif operation == "run_test_cases":
            QMessageBox.critical(
                self, "Test Execution Error", f"Test execution failed: {error_msg}"
            )
        elif operation == "stop_test_cases":
            QMessageBox.warning(
                self, "Stop Error", f"Failed to stop test cases: {error_msg}"
            )

    def on_test_execution_completed(self, operation: str, results):
        """Handle test execution completion"""
        if operation == "run_test_cases":
            logger.info("Test execution completed with %d results", len(results))

            # Count results
            passed = sum(1 for r in results if r and r.get("status") == "passed")
            failed = sum(1 for r in results if r and r.get("status") == "failed")
            errors = sum(1 for r in results if r and r.get("status") == "error")

            # Save screenshots for all results and get file paths
            saved_map = self._save_test_run_screenshots(results)
            total_saved = sum(len(v) for v in saved_map.values())

            # Save test execution results to database
            self._save_test_execution_results_to_database(results, saved_map)

            for result in results:
                if not result: continue
                status = result.get("status")
                if status in ["passed", "completed"]:
                    test_id = str(result.get("test_id"))
                    for i, tc in enumerate(self.test_cases):
                        if str(tc.get("uuid")) == test_id:
                            self.table_model.update_cell(i, 4, "0")
                            self.test_cases[i]["step_number"] = 0
                            break

            # Show summary
            message = "Test execution completed!\n\n"
            message += f"Passed: {passed}\n"
            message += f"Failed: {failed}\n"
            message += f"Errors: {errors}\n"
            message += f"Total: {len(results)}"

            if total_saved:
                # Show where screenshots were stored; for the first non-empty, show its folder
                try:
                    base_dir = os.path.join(self._project_root(), "screenshots")
                    first_dir = None
                    for test_id, paths in saved_map.items():
                        if paths:
                            # Compute the run folder from first path: screenshots/<id>/<run>/<file>
                            parts = os.path.normpath(paths[0]).split(os.sep)
                            if len(parts) >= 3:
                                # Find index of 'screenshots'
                                if "screenshots" in parts:
                                    i = parts.index("screenshots")
                                    if i + 2 < len(parts):
                                        first_dir = os.path.join(*parts[: i + 3])
                            break
                    message += "\n\n"
                    message += f"Saved {total_saved} screenshot(s) under: {base_dir}"
                    if first_dir:
                        message += f"\nLatest run folder: {first_dir}"
                except Exception as e:
                    logger.error("Error saving screenshots: %s", str(e))

            message += "\n\nResults saved to database for future reference."
            QMessageBox.information(self, "Test Execution Complete", message)


    def _save_single_execution_result(self, execution_result: Dict):
        """Save a single execution result to database using worker thread."""
        try:
            # Create worker for database save operation
            worker = TestCaseMainWorker(
                self.db, "save_execution_result", execution_result=execution_result
            )
            worker.operation_completed.connect(self._on_execution_result_saved)
            worker.operation_failed.connect(self._on_execution_result_save_failed)
            worker.start()
        except Exception as e:
            logger.error("Failed to start execution result save worker: %s", str(e))

    @Slot(str, object)
    def _on_execution_result_saved(self, operation: str, result):
        """Handle successful execution result save."""
        if operation == "save_execution_result":
            logger.debug("Execution result saved successfully")

    @Slot(str, str)
    def _on_execution_result_save_failed(self, operation: str, error_msg: str):
        """Handle failed execution result save."""
        if operation == "save_execution_result":
            logger.error("Failed to save execution result: %s", error_msg)

    def _calculate_duration(self, start_time: str, end_time: str) -> Optional[float]:
        """Calculate execution duration in seconds."""
        try:
            if not start_time or not end_time:
                return None
            start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            return (end - start).total_seconds()
        except Exception as e:
            logger.warning("Failed to calculate duration: %s", str(e))
            return None

    def on_test_progress(self, test_id: str, test_name: str, status: str):
        """Handle test progress updates"""
        logger.info("Test progress: %s (%s) - %s", test_name, test_id, status)

        # Find the test case in the table and update its visual status
        row_index = -1
        for i, tc in enumerate(self.test_cases):
            if str(tc.get("uuid")) == test_id:
                row_index = i
                break

        if row_index != -1:
            result_text = "Pending"
            status_text = status.capitalize()

            if status == "running":
                result_text = "Running..."
                # Set the row color to blue to indicate it's active
                self.table_widget.set_row_color(row_index, RowColor.YELLOW)

            elif status in ["passed", "completed"]:
                result_text = "Passed"
                # The test is finished, so remove the custom color
                self.table_widget.set_row_color(row_index, RowColor.GREEN)

            elif status == "failed":
                result_text = "Failed"
                # The test is finished, so remove the custom color
                self.table_widget.set_row_color(row_index, RowColor.RED)

            elif status == "error":
                result_text = "Error"
                # The test is finished, so remove the custom color
                self.table_widget.set_row_color(row_index, RowColor.RED)

            elif status == "cancelled":
                result_text = "Cancelled"
                self.table_widget.set_row_color(row_index, RowColor.OFF_WHITE)

            # Update the text in the table cells
            self.table_model.update_cell(row_index, 5, result_text)
            self.table_model.update_cell(row_index, 6, status_text)

        else:
            logger.warning(
                "Could not find test case with ID %s to update progress.", test_id
            )

    def _create_action_buttons_widget(self, cell_data, row_index):
        """Create action buttons for each row"""
        test_case = cell_data  # cell_data is the full dictionary for the test case
        action_widget = QWidget()
        layout = QHBoxLayout(action_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        view_btn = ui_kit.icon_button("eye", "View details")
        view_btn.clicked.connect(lambda checked, tc=test_case: self.view_test_case(tc))

        edit_btn = ui_kit.icon_button("edit", "Edit test case")
        edit_btn.clicked.connect(lambda checked, tc=test_case: self.edit_test_case(tc))

        history_btn = ui_kit.icon_button("history", "Execution history")
        history_btn.clicked.connect(
            lambda checked, tc=test_case: self.view_execution_history(tc)
        )

        layout.addWidget(view_btn)
        layout.addWidget(edit_btn)
        layout.addWidget(history_btn)

        return action_widget

    def view_test_case(self, test_case):
        """Show a test case: result up top, details and screenshots below."""
        try:
            from PySide6.QtWidgets import QGridLayout

            test_case_name = test_case.get("test_case", "Unknown Test Case")
            screenshots, latest_dir = self._find_latest_screenshots_for_test(test_case)

            dialog = QDialog(self)
            dialog.setWindowTitle("Test Case Details")
            dialog.setModal(True)
            dialog.setMinimumWidth(560)
            dialog.setMaximumSize(820, 760)

            outer = QVBoxLayout(dialog)
            outer.setContentsMargins(20, 20, 20, 20)
            outer.setSpacing(16)

            card = ui_kit.Card(padding=0, spacing=0)
            outer.addWidget(card)

            # Header: field / type, result, test case text
            result_text = self._latest_result_text(test_case)
            tone = self._result_tone(result_text)
            head = ui_kit.centered_header(
                " \u00b7 ".join(
                    p for p in [test_case.get("test_field", ""), test_case.get("test_type", "")] if p
                ) or "Test case",
                result_text,
                test_case_name,
            )
            head.big_label.setProperty("tone", tone)
            ui_kit.repolish(head.big_label)
            card.body.addWidget(head)

            # Details
            details = ui_kit.CardSection(padding=(24, 18, 24, 18), spacing=10)
            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(10)
            grid.setColumnStretch(1, 1)

            def add_row(row, key, value):
                grid.addWidget(ui_kit.label(key, "FieldLabel"), row, 0, Qt.AlignmentFlag.AlignTop)
                shown = str(value) if value not in [None, "", "N/A"] else "Not specified"
                value_lbl = ui_kit.label(shown, "BodyText" if shown != "Not specified" else "MutedText", wrap=True)
                value_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(value_lbl, row, 1)

            add_row(0, "Expected result", test_case.get("test_expect", ""))
            add_row(1, "Reference data", test_case.get("test_reference", ""))
            add_row(2, "Steps", test_case.get("step_number", 0))
            details.body.addLayout(grid)
            card.body.addWidget(details)

            dotted = QHBoxLayout()
            dotted.setContentsMargins(24, 0, 24, 0)
            dotted.addWidget(ui_kit.divider(dotted=True))
            card.body.addLayout(dotted)

            # Screenshots
            shots = ui_kit.CardSection(padding=(24, 16, 24, 18), spacing=6)
            if screenshots and latest_dir:
                folder = os.path.join(
                    os.path.basename(os.path.dirname(latest_dir)), os.path.basename(latest_dir)
                )
                shots.body.addWidget(ui_kit.StatRow(f"{len(screenshots)} screenshot(s) from the last run", "", "ok"))
                shots.body.addWidget(ui_kit.label(folder, "MutedText", wrap=True))
            else:
                shots.body.addWidget(ui_kit.StatRow("No screenshots yet", "", "none"))
                shots.body.addWidget(ui_kit.label("Run this test case to capture screenshots.", "MutedText", wrap=True))
            card.body.addWidget(shots)

            # Technical details (small, muted)
            def fmt(ts):
                try:
                    return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
                except Exception:  # noqa: BLE001 - display only
                    return ts or "\u2014"

            case_id = test_case.get("uuid") or test_case.get("id") or "\u2014"
            tech = ui_kit.label(
                f"ID {case_id}  \u00b7  "
                f"created {fmt(test_case.get('created_at'))}  \u00b7  updated {fmt(test_case.get('updated_at'))}",
                "MutedText",
                wrap=True,
            )
            tech.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            outer.addWidget(tech)

            # Buttons
            buttons_layout = QHBoxLayout()
            buttons_layout.setSpacing(8)
            gallery_btn = ui_kit.button("Gallery", "secondary", "images")
            gallery_btn.setEnabled(bool(screenshots))
            gallery_btn.setToolTip("Browse screenshots in gallery mode")
            open_btn = ui_kit.button("View screenshots", "primary", "arrow-right", icon_right=True)
            open_btn.setEnabled(bool(screenshots))
            open_btn.setToolTip("Open screenshot viewer for detailed examination")
            close_btn = ui_kit.button("Close", "neutral")

            def open_screenshots():
                try:
                    viewer = ScreenshotViewerDialog(test_case_name, screenshots, parent=self)
                    logger.info(f"Opening screenshot viewer with {len(screenshots)} screenshots")
                    viewer.exec()
                except Exception as e:
                    logger.error("Error opening screenshots: %s", str(e))
                    QMessageBox.critical(
                        self, "Screenshot Viewer Error", f"Failed to open screenshot viewer:\n{str(e)}"
                    )

            def open_gallery_view():
                try:
                    self.open_screenshot_gallery(test_case_name, screenshots)
                except Exception as e:
                    logger.error("Error opening gallery view: %s", str(e))
                    QMessageBox.critical(self, "Gallery Error", f"Failed to open gallery view:\n{str(e)}")

            open_btn.clicked.connect(open_screenshots)
            gallery_btn.clicked.connect(open_gallery_view)
            close_btn.clicked.connect(dialog.accept)

            buttons_layout.addWidget(close_btn)
            buttons_layout.addStretch()
            buttons_layout.addWidget(gallery_btn)
            buttons_layout.addWidget(open_btn)
            outer.addLayout(buttons_layout)

            dialog.exec()

        except Exception as e:
            logger.error("Error viewing test case: %s", str(e))
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")

    def _latest_result_text(self, test_case: Dict) -> str:
        """The result shown in the table for this test case (falls back to the API field)."""
        for i, tc in enumerate(self.test_cases):
            if tc is test_case or (tc.get("uuid") and tc.get("uuid") == test_case.get("uuid")):
                row = self.table_model.get_row(i)
                if row and len(row) > 5 and row[5]:
                    return str(row[5])
        return str(test_case.get("test_result") or "Pending")

    def open_screenshot_gallery(self, test_case_name: str, screenshots: List[str]):
        """
        Open a new dialog with the ScreenshotGalleryWidget.

        This demonstrates how to use the reusable ScreenshotGalleryWidget component.
        """
        try:
            # Create a dialog to contain the gallery widget
            gallery_dialog = QDialog(self)
            gallery_dialog.setWindowTitle(f"Gallery: {test_case_name}")
            gallery_dialog.setModal(True)
            gallery_dialog.resize(900, 600)

            # Create layout for the dialog
            dialog_layout = QVBoxLayout(gallery_dialog)
            dialog_layout.setContentsMargins(20, 20, 20, 20)
            dialog_layout.setSpacing(12)

            # Create and configure the gallery widget
            gallery_widget = ScreenshotGalleryWidget(parent=gallery_dialog)
            gallery_widget.set_screenshots(
                screenshots, f"Screenshots: {test_case_name}"
            )

            # Connect gallery signals for external handling if needed
            def on_screenshot_clicked(screenshot_path: str):
                logger.info(f"Screenshot clicked: {screenshot_path}")
                # You can add custom handling here

            def on_refresh_requested():
                # Reload screenshots from the file system
                screenshots, latest_dir = self._find_latest_screenshots_for_test(
                    {"test_case": test_case_name}
                )
                gallery_widget.set_screenshots(
                    screenshots, f"Screenshots: {test_case_name}"
                )
                logger.info(f"Gallery refreshed with {len(screenshots)} screenshots")

            gallery_widget.screenshot_clicked.connect(on_screenshot_clicked)
            gallery_widget.refresh_requested.connect(on_refresh_requested)

            # Add widget to dialog
            dialog_layout.addWidget(gallery_widget)

            # Add dialog control buttons
            button_layout = QHBoxLayout()

            close_btn = ui_kit.button("Close", "neutral")
            close_btn.clicked.connect(gallery_dialog.accept)

            button_layout.addStretch()
            button_layout.addWidget(close_btn)

            dialog_layout.addLayout(button_layout)

            # Show the dialog
            gallery_dialog.exec()

        except Exception as e:
            logger.error(f"Error opening screenshot gallery: {e}")
            QMessageBox.critical(
                self, "Gallery Error", f"Failed to open screenshot gallery:\n{str(e)}"
            )

    def view_execution_history(self, test_case: Dict):
        try:
            from PySide6.QtWidgets import (
                QGroupBox,
                QSizePolicy,
            )

            test_case_name = test_case.get("test_case", "Unknown Test Case")
            test_id = test_case.get("id") or test_case.get("uuid")

            dialog = QDialog(self)
            dialog.setWindowTitle(f"Execution History: {test_case_name}")
            dialog.setModal(True)
            dialog.setMinimumSize(950, 650)

            main_layout = QVBoxLayout(dialog)
            main_layout.setContentsMargins(24, 24, 24, 20)
            main_layout.setSpacing(12)

            title_label = ui_kit.label("Execution history", "PageTitle")
            subtitle_label = ui_kit.label(f"{test_case_name}", "PageSubtitle", wrap=True)

            main_layout.addWidget(title_label)
            main_layout.addWidget(subtitle_label)

            history_groupbox = ui_kit.Card(padding=16, spacing=8)

            history_groupbox.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            groupbox_layout = history_groupbox.body

            loading_label = ui_kit.label("Loading history, please wait...", "MutedText")
            loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            groupbox_layout.addWidget(loading_label)

            history_table = self._setup_history_table()
            history_table.setVisible(False)
            groupbox_layout.addWidget(history_table)
            main_layout.addWidget(history_groupbox)

            close_btn = ui_kit.button("Close", "neutral")
            close_btn.clicked.connect(dialog.accept)

            button_layout = QHBoxLayout()
            button_layout.addStretch()
            button_layout.addWidget(close_btn)
            main_layout.addLayout(button_layout)

            def on_history_loaded(operation: str, results):
                logger.info(results)
                if operation == "get_execution_history":
                    loading_label.hide()
                    history_table.setVisible(True)
                    self._populate_history_table(history_table, results, test_id)

            def on_history_failed(operation: str, error_msg: str):
                if operation == "get_execution_history":
                    loading_label.setText(f"Failed to load history: {error_msg}")
                    loading_label.setObjectName("WarningText")
                    ui_kit.repolish(loading_label)

            if self.current_project:
                worker = TestCaseMainWorker(
                    self.db,
                    "get_execution_history",
                    project_id=self.current_project.project_id,
                )
                worker.operation_completed.connect(on_history_loaded)
                worker.operation_failed.connect(on_history_failed)
                worker.start()
            else:
                loading_label.setText("No project selected.")

            dialog.exec()

        except Exception as e:
            logger.error("Error while viewing execution history: %s", str(e))
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")

    def _setup_history_table(self) -> QTableView:
        from PySide6.QtWidgets import QHeaderView, QTableView

        table_view = QTableView()
        table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table_view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        table_view.setAlternatingRowColors(True)
        table_view.setShowGrid(False)
        table_view.verticalHeader().hide()
        table_view.setSortingEnabled(True)

        header = table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        return table_view

    def _populate_history_table(
        self, table: QTableView, results: List[Dict], test_id: str
    ):
        import json

        from PySide6.QtCore import Qt
        from PySide6.QtGui import QStandardItem, QStandardItemModel

        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(
            ["Status", "Time", "Duration (seconds)", "Error", "Screenshots", "Action"]
        )

        if not results:
            table.setModel(model)
            return

        test_results = [
            r for r in results if str(r.get("testcase_id", "")) == str(test_id)
        ]
        if not test_results:
            table.setModel(model)
            return

        test_results.sort(key=lambda x: x.get("end_time", ""), reverse=True)

        for result in test_results:
            status = result.get("status", "unknown").title()
            status_item = QStandardItem(status)
            from PySide6.QtGui import QColor

            color_map = {
                "Passed": QColor(tokens.PRIMARY_TEXT),
                "Completed": QColor(tokens.PRIMARY_TEXT),
                "Failed": QColor(tokens.DANGER_TEXT),
                "Error": QColor(tokens.DANGER_TEXT),
            }
            status_item.setForeground(color_map.get(status, Qt.GlobalColor.black))
            status_font = status_item.font()
            status_font.setFamily(tokens.FONT_UI)
            status_font.setBold(True)
            status_item.setFont(status_font)

            timestamp_str = result.get("end_time") or result.get("start_time", "N/A")
            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                time_item = QStandardItem(dt.strftime("%Y-%m-%d %H:%M:%S"))
            except Exception as e:
                time_item = QStandardItem(timestamp_str)
                logger.error("Error parsing timestamp: %s", str(e), exc_info=True)

            duration = result.get("execution_duration")
            duration_item = QStandardItem(
                f"{duration:.2f}" if duration is not None else "N/A"
            )
            duration_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            error_msg = result.get("error_message", "")
            error_item = QStandardItem(
                error_msg.splitlines()[0] if error_msg else "None"
            )
            if error_msg:
                error_item.setToolTip(error_msg)

            count = result.get("screenshots_count", 0)
            screenshots_item = QStandardItem(f"{count}")
            screenshots_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            screenshots_data = result.get("screenshots", [])
            screenshots_list = []
            if isinstance(screenshots_data, str) and screenshots_data.startswith("["):
                try:
                    screenshots_list = json.loads(screenshots_data)
                except json.JSONDecodeError:
                    pass
            elif isinstance(screenshots_data, list):
                screenshots_list = screenshots_data

            model.appendRow(
                [
                    status_item,
                    time_item,
                    duration_item,
                    error_item,
                    screenshots_item,
                    QStandardItem(""),
                ]
            )

            if count > 0:
                row_index = model.rowCount() - 1
                view_btn = ui_kit.button("View screenshots", "secondary", small=True)
                view_btn.clicked.connect(
                    lambda checked=False, s=screenshots_list, name=result.get(
                        "test_name"
                    ): self.open_screenshot_viewer(name, s)
                )
                table.setIndexWidget(model.index(row_index, 5), view_btn)

        table.setModel(model)

    def open_screenshot_viewer(self, test_case_name: str, screenshots: List[str]):
        try:
            viewer = ScreenshotViewerDialog(test_case_name, screenshots, parent=self)
            viewer.exec()
        except Exception as e:
            logger.error("Error opening screenshot viewer: %s", str(e))
            QMessageBox.critical(
                self, "Error", f"Could not open screenshot viewer:\n{str(e)}"
            )

    def edit_test_case(self, test_case):
        """Edit test case using the existing dialog"""
        try:
            if not self.current_project:
                QMessageBox.warning(
                    self, "No Project", "Please select a project first."
                )
                return

            # Import and use the existing AddEditTestCaseDialog
            from .add_edit_testcase_dialog import AddEditTestCaseDialog

            dialog = AddEditTestCaseDialog(
                self.db, self.current_project.project_id, test_case, parent=self
            )
            dialog.test_case_saved.connect(self.on_test_case_saved)
            dialog.exec()
        except Exception as e:
            logger.error("Error editing test case: %s", str(e))
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")

    @Slot(dict)
    def on_test_case_saved(self, test_case_data):
        """Handle when a test case is saved (created or updated)"""
        logger.info("Test case saved, refreshing test cases list")
        QTimer.singleShot(300, self.load_test_cases)
        self.load_test_cases()

    def add_test_case(self):
        """Add new test case using the existing dialog"""
        try:
            if not self.current_project:
                QMessageBox.warning(
                    self, "No Project", "Please select a project first."
                )
                return
            dialog = AddEditTestCaseDialog(
                self.db, self.current_project.project_id, parent=self
            )
            dialog.test_case_saved.connect(self.on_test_case_saved)
            dialog.exec()
        except Exception as e:
            logger.error("Error adding test case: %s", str(e))
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")

    def run_tests(self):
        """Run selected tests in headed mode"""
        selected_test_cases = self.get_selected_test_cases()

        if not selected_test_cases:
            QMessageBox.warning(
                self, "No Selection", "Please select at least one test case to run"
            )
            return

        if not TestRunnerService:
            QMessageBox.critical(
                self,
                "Test Runner Unavailable",
                "No test runner service is available. Please check your installation.",
            )
            return

        headless_mode = False
        use_websocket = True
        skip_general_confirm = False
        tc = selected_test_cases[0]
        checkpoint_data = tc.get("checkpoint_data")

        if len(selected_test_cases) == 1:
            if tc.get("saved_step", 0) > 0 and checkpoint_data is not None:
                reply = QMessageBox.question(
                    self,
                    "Resume from Checkpoint?",
                    f"Test case '<b>{tc.get('test_case')}</b>' stopped at <b>Step {tc.get('saved_step')}</b>.<br><br>"
                    "<b>Yes</b>: Resume from the last checkpoint.<br>"
                    "<b>No</b>: Start a fresh execution from the beginning.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    skip_general_confirm = True

        if not skip_general_confirm:
            test_names = [tc.get("test_case", "Unknown") for tc in selected_test_cases]
            message = f"Do you want to run the following {len(selected_test_cases)} selected test cases in a headed browser?\n\n"
            # Show a preview of the test cases to be run
            message += "\n".join([f"• {name}" for name in test_names[:10]])
            if len(test_names) > 10:
                message += f"\n... and {len(test_names) - 10} more"

            checkpoint_data = None

            # Ask for user confirmation before running the tests
            reply = QMessageBox.question(
                self,
                "Confirm Test Execution",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # Start test execution in a worker thread
        self.worker = TestCaseMainWorker(
            self.db,
            "run_test_cases",
            test_cases=selected_test_cases,
            project_id=(
                self.current_project.project_id if self.current_project else None
            ),
            headless=headless_mode,
            use_websocket=use_websocket,
            checkpoint_data=checkpoint_data,
        )
        self.worker.operation_completed.connect(self.on_test_execution_completed)
        self.worker.operation_failed.connect(self.on_operation_failed)
        self.worker.test_progress.connect(self.on_test_progress)
        self.worker.ui_test_update.connect(self.update_step_number_ui)
        self.worker.start()

        # Show a status message to the user
        QMessageBox.information(
            self,
            "Test Execution Started",
            "Test execution has started in a headed browser.\n"
            "Check the logs for progress and status.",
        )

    @Slot(str, str)
    def update_step_number_ui(self, test_id: str, step_number: int):
        for i, tc in enumerate(self.test_cases):
            if str(tc.get("uuid")) == test_id:
                self.table_model.update_cell(i, 4, str(step_number))
                self.test_cases[i]["current_step"] = step_number
                break

    def delete_selected(self):
        """Delete selected test cases"""
        selected_test_cases = self.get_selected_test_cases()

        if selected_test_cases:
            test_names = [tc.get("test_case", "Unknown") for tc in selected_test_cases]
            message = (
                f"Are you sure you want to delete {len(selected_test_cases)} "
                f"test case(s)?\n\n"
            )
            message += "\n".join(
                [f"• {name}" for name in test_names[:5]]
            )  # Show first 5
            if len(test_names) > 5:
                message += f"\n... and {len(test_names) - 5} more"

            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Delete test cases one by one
                self.delete_test_cases(selected_test_cases)
        else:
            QMessageBox.warning(
                self, "No Selection", "Please select at least one test case to delete"
            )

    def stop_selected(self):
        selected_to_stop = self.get_selected_test_cases()
        if not selected_to_stop:
            QMessageBox.warning(
                self, "Not selected", "Please select at least one test case to stop."
            )
            return
        if (
            self.worker
            and self.worker.isRunning()
            and self.worker.operation == "run_test_cases"
        ):
            ids_to_stop = {tc.get("uuid") for tc in selected_to_stop if tc.get("uuid")}
        else:
            QMessageBox.information(
                self,
                "No tests running",
                "There are currently no test cases being executed.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirm Stop",
            "Stopping will finish the current step and download all checkpoints before exiting.\n"
            "This may take a few seconds. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._perform_graceful_stop_ui()
            self.worker.request_cancellation(ids_to_stop)

    def _perform_graceful_stop_ui(self):
        self.stop_dialog = QProgressDialog(
            "Sending stop signal to server...\nWaiting for final checkpoints...",
            None,
            0,
            0,
            self,
        )
        self.stop_dialog.setWindowTitle("Stopping Gracefully")
        self.stop_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.stop_dialog.setCancelButton(None)
        self.stop_dialog.setMinimumDuration(0)

        self.stop_dialog.show()
        self.worker.finished.connect(self._on_worker_finished_gracefully)

    def _on_worker_finished_gracefully(self):
        if hasattr(self, "stop_dialog") and self.stop_dialog:
            self.stop_dialog.close()
        try:
            self.worker.finished.disconnect(self._on_worker_finished_gracefully)
        except:
            pass
        self.stopButton.setEnabled(True)
        self.runButton.setEnabled(True)
        self.deleteButton.setEnabled(True)
        QMessageBox.information(
            self,
            "Stopped",
            "Test execution stopped successfully.\nAll checkpoints received.",
        )

    def get_selected_test_cases(self) -> List[Dict]:
        """Get selected test cases from the table"""
        selected_indices = self.table_widget.get_selected_row_indices()

        return [
            self.test_cases[i] for i in selected_indices if i < len(self.test_cases)
        ]

    def delete_test_cases(self, test_cases_to_delete: List[Dict]):
        """Populates the deletion queue and starts the sequential deletion process."""
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(
                self, "Busy", "Another operation is already in progress."
            )
            return

        # The walrus operator (:=) assigns the value to test_id, then the `if` checks it.
        # This makes the type narrowing explicit in one line.
        self.deletion_queue = [
            test_id
            for tc in test_cases_to_delete
            if (test_id := (tc.get("id") or tc.get("uuid"))) is not None
        ]

        if not self.deletion_queue:
            logger.warning("No valid test case IDs found for deletion.")
            QMessageBox.warning(
                self, "No Selection", "No valid test cases were selected for deletion."
            )
            return

        # Start processing the first item in the queue
        self._process_next_deletion()

    @Slot(str, object)
    def on_test_case_deleted(self, operation: str, result):
        """Handles a single successful deletion and triggers the next one."""
        if operation == "delete_test_case":
            deleted_id = result.get("test_case_id")
            if not deleted_id:
                logger.warning("Delete operation succeeded but returned no ID.")
                self._process_next_deletion()
                return

            # Find the index of the item to remove from our local data
            index_to_remove = -1
            for i, tc in enumerate(self.test_cases):
                # Check both 'id' and 'uuid' for robustness
                if str(tc.get("id")) == str(deleted_id) or str(tc.get("uuid")) == str(
                    deleted_id
                ):
                    index_to_remove = i
                    break

            if index_to_remove != -1:
                logger.info(
                    f"Removing test case {deleted_id} from UI at index {index_to_remove}."
                )
                # Remove from our master list first
                del self.test_cases[index_to_remove]
                # Then tell the table model to remove the row, which updates the view
                self.table_model.remove_row(index_to_remove)
            else:
                logger.warning(
                    f"Could not find deleted test case {deleted_id} in the UI."
                )

            self._process_next_deletion()

    def closeEvent(self, event):
        """Handle window close event"""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        event.accept()

    def _process_next_deletion(self):
        """Processes the next test case ID from the deletion queue."""
        if not self.deletion_queue:
            # Queue is empty, all deletions are done
            logger.info("All selected test cases have been deleted.")

            QTimer.singleShot(10, self.load_test_cases)  # Refresh the list

            self.table_widget.set_selection([])
            QMessageBox.information(
                self, "Success", "All selected test cases were deleted successfully."
            )
            return

        # Get the next ID from the front of the queue
        test_case_id_to_delete = self.deletion_queue.pop(0)

        logger.info(
            f"Deleting test case ID: {test_case_id_to_delete}. Remaining: {len(self.deletion_queue)}"
        )

        self.worker = TestCaseMainWorker(
            self.db, "delete_test_case", test_case_id=test_case_id_to_delete
        )
        # Make sure to connect to the correct slots
        self.worker.operation_completed.connect(self.on_test_case_deleted)
        self.worker.operation_failed.connect(self.on_operation_failed)
        self.worker.start()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Set application properties
    app.setApplicationName("Test Case Management System")
    app.setApplicationVersion("1.0")

    window = TestCaseMainWindow()
    window.show()

    sys.exit(app.exec())
