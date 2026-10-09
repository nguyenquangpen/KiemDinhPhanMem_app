"""
TestCase Widget for Test Case Management

This widget provides functionality to manage test cases within a project,
including creating, viewing, updating, and deleting test cases via API.
"""

import asyncio
from typing import Dict, List, Optional

from PySide6.QtCore import QThread, QTimer, Signal, Slot, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QWidget,
)

from models.data_classes import Project, TestcaseStatus
from models.database import DataManager
from services.logging_config import get_logger
from ui.build.ui_task import Ui_TestcaseWidget
from views.pages.add_edit_testcase_dialog import AddEditTestCaseDialog
from pathlib import Path

logger = get_logger("testcases_widget")


class TestCaseWorker(QThread):
    """Worker thread for async test case operations."""

    operation_completed = Signal(str, object)  # operation_type, result
    operation_failed = Signal(str, str)  # operation_type, error_message

    def __init__(self, data_manager: DataManager, operation: str, **kwargs):
        super().__init__()
        self.data_manager = data_manager
        self.operation = operation
        self.kwargs = kwargs

    def run(self):
        try:
            if self.operation == "load_test_cases":
                result = asyncio.run(self._load_test_cases())
            elif self.operation == "create_test_case":
                result = asyncio.run(self._create_test_case())
            elif self.operation == "update_test_case":
                result = asyncio.run(self._update_test_case())
            elif self.operation == "delete_test_case":
                result = asyncio.run(self._delete_test_case())
            else:
                raise ValueError(f"Unknown operation: {self.operation}")

            self.operation_completed.emit(self.operation, result)
        except Exception as e:
            logger.error("Worker operation failed: %s", str(e))
            self.operation_failed.emit(self.operation, str(e))

    async def _load_test_cases(self):
        project_id = self.kwargs.get("project_id")
        if not project_id:
            raise ValueError("Project ID is required for loading test cases")
        return await self.data_manager.get_test_cases(project_id)

    async def _create_test_case(self):
        test_case_data = self.kwargs.get("test_case_data")
        if not test_case_data:
            raise ValueError("Test case data is required for creation")
        return await self.data_manager.create_test_case(test_case_data)

    async def _update_test_case(self):
        test_case_id = self.kwargs.get("test_case_id")
        test_case_data = self.kwargs.get("test_case_data")
        if not test_case_id or not test_case_data:
            raise ValueError("Test case ID and data are required for update")
        return await self.data_manager.update_test_case(test_case_id, test_case_data)

    async def _delete_test_case(self):
        test_case_id = self.kwargs.get("test_case_id")
        if not test_case_id:
            raise ValueError("Test case ID is required for deletion")
        return await self.data_manager.delete_test_case(test_case_id)


class TestCaseWidget(QWidget):
    """Widget for managing test cases within a project."""

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self.setObjectName("PageWidget")
        self.db = data_manager
        self.current_project: Optional[Project] = None
        self.test_cases: List[Dict] = []
        self.worker: Optional[TestCaseWorker] = None

        # Setup UI
        self.ui = Ui_TestcaseWidget()
        self.ui.setupUi(self)

        self._setup_ui_components()
        self._connect_signals()
        self._setup_timer()

        logger.info("TestCaseWidget initialized")

    def _setup_ui_components(self):
        """Setup and configure UI components."""
        # Configure labels
        self.ui.label_9.setText("Project Name")
        self.ui.label_11.setText("Search Test Cases")
        self.ui.label_12.setText("Status Filter")
        self.ui.label.setText("Priority Filter")

        # Configure input fields
        self.ui.lineEdit_2.setPlaceholderText("Current project name")
        self.ui.lineEdit_2.setReadOnly(True)
        self.ui.lineEdit.setPlaceholderText("Search by title or description...")

        # Configure combo boxes
        self._setup_status_filter()
        self._setup_priority_filter()

        # Add "Add Test Case" button to the sidebar
        self._add_create_button()

        # Configure table
        self._setup_table()

        logger.debug("UI components configured")

    def _add_create_button(self):
        """Add 'Add Test Case' button to the sidebar."""
        # Create the button
        self.add_test_case_btn = QPushButton("➕ Add Test Case")
        self.add_test_case_btn.setObjectName("GreenButton")
        self.add_test_case_btn.clicked.connect(self._show_add_test_case_dialog)

        # Add button to the sidebar layout after the last combo box
        self.ui.verticalLayout_9.insertWidget(
            self.ui.verticalLayout_9.count() - 1, self.add_test_case_btn
        )

    def _setup_status_filter(self):
        """Setup status filter combo box."""
        self.ui.comboBox_2.clear()
        self.ui.comboBox_2.addItem("All Statuses", "")
        for status in TestcaseStatus:
            self.ui.comboBox_2.addItem(status.value, status.value)

    def _setup_priority_filter(self):
        """Setup priority filter combo box."""
        self.ui.comboBox.clear()
        priorities = ["All Priorities", "High", "Medium", "Low"]
        for priority in priorities:
            value = "" if priority == "All Priorities" else priority
            self.ui.comboBox.addItem(priority, value)

    def _setup_table(self):
        """Setup the test cases table."""
        table = self.ui.testcaseTableWidget

        # Set column headers
        headers = [
            "ID",
            "Title",
            "Description",
            "Status",
            "Priority",
            "Created",
            "Actions",
        ]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        # Configure table properties
        table.setSelectionBehavior(table.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)

        # Resize columns
        header = table.horizontalHeader()
        header.setStretchLastSection(True)

        logger.debug("Table configured with headers: %s", headers)

    def _connect_signals(self):
        """Connect UI signals to slots."""
        # Search functionality
        self.ui.lineEdit.textChanged.connect(self._on_search_changed)
        self.ui.comboBox_2.currentTextChanged.connect(self._filter_test_cases)
        self.ui.comboBox.currentTextChanged.connect(self._filter_test_cases)

        # Table interactions
        self.ui.testcaseTableWidget.cellDoubleClicked.connect(
            self._on_table_double_click
        )

        logger.debug("Signals connected")

    def _setup_timer(self):
        """Setup timer for delayed search operations."""
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._filter_test_cases)

    @Slot()
    def refresh_test_cases(self):
        """Refresh test cases data from API."""
        if not self.current_project:
            logger.warning("No current project set for refreshing test cases")
            return

        logger.info("Refreshing test cases for project: %s", self.current_project.name)
        self._load_test_cases_async(self.current_project.project_id)

    def refresh_project_data(self):
        """Refresh project data and test cases."""
        current_project = self.db.get_current_project()
        if current_project:
            self.set_current_project(current_project)
        else:
            logger.warning("No current project available")
            self._show_no_project_message()

    def set_current_project(self, project: Project):
        """Set the current project and load its test cases."""
        if not project:
            logger.warning("Attempted to set None as current project")
            return

        self.current_project = project
        self.ui.lineEdit_2.setText(project.name)

        # Enable the Add Test Case button when a project is selected
        if hasattr(self, "add_test_case_btn"):
            self.add_test_case_btn.setEnabled(True)

        logger.info(
            "Current project set to: %s (ID: %s)", project.name, project.project_id
        )
        self.refresh_test_cases()

    def _load_test_cases_async(self, project_id: int):
        """Load test cases asynchronously."""
        if self.worker and self.worker.isRunning():
            logger.debug("Worker already running, skipping test case load")
            return

        self.worker = TestCaseWorker(self.db, "load_test_cases", project_id=project_id)
        self.worker.operation_completed.connect(self._on_test_cases_loaded)
        self.worker.operation_failed.connect(self._on_operation_failed)
        self.worker.start()

    @Slot(str, object)
    def _on_test_cases_loaded(self, operation: str, result):
        """Handle successful test cases loading."""
        if operation == "load_test_cases":
            if result and isinstance(result, list):
                self.test_cases = result
                logger.info("Loaded %d test cases", len(self.test_cases))
                self._populate_table(self.test_cases)
            else:
                self.test_cases = []
                logger.info("No test cases found for current project")
                self._populate_table([])

    @Slot(str, str)
    def _on_operation_failed(self, operation: str, error_message: str):
        """Handle failed operations."""
        logger.error("Operation %s failed: %s", operation, error_message)

        if operation == "load_test_cases":
            QMessageBox.warning(
                self, "Load Failed", f"Failed to load test cases: {error_message}"
            )
        elif operation == "create_test_case":
            QMessageBox.warning(
                self, "Create Failed", f"Failed to create test case: {error_message}"
            )
        elif operation == "update_test_case":
            QMessageBox.warning(
                self, "Update Failed", f"Failed to update test case: {error_message}"
            )
        elif operation == "delete_test_case":
            QMessageBox.warning(
                self, "Delete Failed", f"Failed to delete test case: {error_message}"
            )

    def _populate_table(self, test_cases: List[Dict]):
        """Populate the table with test case data."""
        table = self.ui.testcaseTableWidget
        table.setRowCount(len(test_cases))

        for row, test_case in enumerate(test_cases):
            # ID
            table.setItem(row, 0, QTableWidgetItem(str(test_case.get("id", ""))))

            # Title
            table.setItem(row, 1, QTableWidgetItem(test_case.get("title", "")))

            # Description
            description = test_case.get("description", "")
            # Truncate long descriptions
            if len(description) > 50:
                description = description[:47] + "..."
            table.setItem(row, 2, QTableWidgetItem(description))

            # Status
            table.setItem(row, 3, QTableWidgetItem(test_case.get("status", "")))

            # Priority
            table.setItem(row, 4, QTableWidgetItem(test_case.get("priority", "Medium")))

            # Created date
            created_date = test_case.get("created_at", "")
            if created_date:
                # Format date if needed
                created_date = (
                    created_date.split("T")[0] if "T" in created_date else created_date
                )
            table.setItem(row, 5, QTableWidgetItem(created_date))

            # Actions - Create action buttons
            actions_widget = self._create_action_buttons(test_case)
            table.setCellWidget(row, 6, actions_widget)

        # Resize columns to content
        table.resizeColumnsToContents()
        logger.debug("Table populated with %d test cases", len(test_cases))

    def _create_action_buttons(self, test_case: Dict) -> QWidget:
        """Create action buttons for each test case row."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Edit button
        edit_btn = QPushButton("Edit")
        edit_btn.setFixedSize(50, 25)
        edit_btn.setObjectName("GreenButton")
        edit_btn.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        edit_btn.clicked.connect(lambda: self._edit_test_case(test_case))
        layout.addWidget(edit_btn)

        # Delete button
        delete_btn = QPushButton("Delete")
        delete_btn.setFixedSize(50, 25)
        delete_btn.setObjectName("RedButton")
        delete_btn.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        delete_btn.clicked.connect(lambda: self._delete_test_case(test_case))
        layout.addWidget(delete_btn)

        return widget

    @Slot()
    def _on_search_changed(self):
        """Handle search text changes with debouncing."""
        self.search_timer.stop()
        self.search_timer.start(300)  # 300ms delay

    @Slot()
    def _filter_test_cases(self):
        """Filter test cases based on search criteria."""
        search_text = self.ui.lineEdit.text().lower()
        status_filter = self.ui.comboBox_2.currentData()
        priority_filter = self.ui.comboBox.currentData()

        filtered_cases = []
        for test_case in self.test_cases:
            # Text search
            if (
                search_text
                and search_text not in test_case.get("title", "").lower()
                and search_text not in test_case.get("description", "").lower()
            ):
                continue

            # Status filter
            if status_filter and test_case.get("status", "") != status_filter:
                continue

            # Priority filter
            if (
                priority_filter
                and test_case.get("priority", "Medium") != priority_filter
            ):
                continue

            filtered_cases.append(test_case)

        self._populate_table(filtered_cases)
        logger.debug(
            "Filtered %d test cases from %d total",
            len(filtered_cases),
            len(self.test_cases),
        )

    @Slot(int, int)
    def _on_table_double_click(self, row: int, column: int):
        """Handle table double-click to view test case details."""
        if row < len(self.test_cases):
            test_case = self.test_cases[row]
            self._view_test_case_details(test_case)

    def _view_test_case_details(self, test_case: Dict):
        """Show detailed view of a test case."""
        # For now, show a simple message box with details
        # This could be expanded to a dedicated dialog
        details = f"""
Test Case: {test_case.get('title', 'N/A')}

Description: {test_case.get('description', 'N/A')}

Status: {test_case.get('status', 'N/A')}
Priority: {test_case.get('priority', 'N/A')}

Steps: {', '.join(test_case.get('steps', []))}
Expected Result: {test_case.get('expected_result', 'N/A')}
        """

        QMessageBox.information(self, "Test Case Details", details.strip())

    def _edit_test_case(self, test_case: Dict):
        """Edit an existing test case."""
        if not self.current_project:
            QMessageBox.warning(self, "No Project", "Please select a project first.")
            return

        logger.info(
            "Opening edit dialog for test case: %s", test_case.get("title", "N/A")
        )

        dialog = AddEditTestCaseDialog(
            self.db, self.current_project.project_id, test_case, parent=self
        )
        dialog.test_case_saved.connect(self._on_test_case_saved)
        dialog.exec()

    @Slot()
    def _show_add_test_case_dialog(self):
        """Show dialog to add a new test case."""
        if not self.current_project:
            QMessageBox.warning(self, "No Project", "Please select a project first.")
            return

        logger.info(
            "Opening add test case dialog for project: %s", self.current_project.name
        )

        dialog = AddEditTestCaseDialog(
            self.db, self.current_project.project_id, parent=self
        )
        dialog.test_case_saved.connect(self._on_test_case_saved)
        dialog.exec()

    @Slot(dict)
    def _on_test_case_saved(self, test_case_data: Dict):
        """Handle when a test case is saved (created or updated)."""
        logger.info("Test case saved, refreshing test cases list")
        self.refresh_test_cases()

    def _delete_test_case(self, test_case: Dict):
        """Delete a test case after confirmation."""
        test_case_id = test_case.get("id")
        test_case_title = test_case.get("title", "Unknown")

        if not test_case_id:
            QMessageBox.warning(self, "Delete Error", "Test case ID not found.")
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete test case '{test_case_title}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info(
                "Deleting test case: %s (ID: %s)", test_case_title, test_case_id
            )
            self._delete_test_case_async(test_case_id)

    def _delete_test_case_async(self, test_case_id: int):
        """Delete test case asynchronously."""
        if self.worker and self.worker.isRunning():
            logger.debug("Worker already running, skipping test case deletion")
            return

        self.worker = TestCaseWorker(
            self.db, "delete_test_case", test_case_id=test_case_id
        )
        self.worker.operation_completed.connect(self._on_test_case_deleted)
        self.worker.operation_failed.connect(self._on_operation_failed)
        self.worker.start()

    @Slot(str, object)
    def _on_test_case_deleted(self, operation: str, result):
        """Handle successful test case deletion."""
        if operation == "delete_test_case" and result:
            logger.info("Test case deleted successfully")
            QMessageBox.information(self, "Success", "Test case deleted successfully.")
            # Refresh the test cases list
            self.refresh_test_cases()

    def _show_no_project_message(self):
        """Show message when no project is selected."""
        self.ui.lineEdit_2.setText("No project selected")
        self.ui.testcaseTableWidget.setRowCount(0)

        # Disable the Add Test Case button when no project is selected
        if hasattr(self, "add_test_case_btn"):
            self.add_test_case_btn.setEnabled(False)

        logger.info("No project selected - cleared test cases table")
