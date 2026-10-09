"""
Add/Edit Test Case Dialog

This dialog provides functionality to create new test cases or edit existing ones
using the API integration.
"""

from typing import Dict, Optional

from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import QDialog, QMessageBox

from models.database import DataManager
from services.logging_config import get_logger
from ui.build.ui_add_or_edit_testcase import Ui_ModernTestcaseForm

logger = get_logger("add_edit_testcase_dialog")


class TestCaseDialogWorker(QThread):
    """Worker thread for async test case operations in dialog."""

    operation_completed = Signal(str, object)  # operation_type, result
    operation_failed = Signal(str, str)  # operation_type, error_message

    def __init__(self, data_manager: DataManager, operation: str, **kwargs):
        super().__init__()
        self.data_manager = data_manager
        self.operation = operation
        self.kwargs = kwargs

    def run(self):
        try:
            import asyncio

            if self.operation == "create_test_case":
                result = asyncio.run(self._create_test_case())
            elif self.operation == "update_test_case":
                result = asyncio.run(self._update_test_case())
            else:
                raise ValueError(f"Unknown operation: {self.operation}")

            self.operation_completed.emit(self.operation, result)
        except Exception as e:
            logger.error("Dialog worker operation failed: %s", str(e))
            self.operation_failed.emit(self.operation, str(e))

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


class AddEditTestCaseDialog(QDialog):
    """Dialog for adding or editing test cases."""

    test_case_saved = Signal(dict)  # Emitted when test case is successfully saved

    def __init__(
        self,
        data_manager: DataManager,
        project_id: int,
        test_case: Optional[Dict] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.db = data_manager
        self.project_id = project_id
        self.test_case = test_case  # None for new test case, Dict for editing
        self.worker: Optional[TestCaseDialogWorker] = None
        # Setup UI
        try:
            self.ui = Ui_ModernTestcaseForm()
            self.ui.setupUi(self)
        except Exception as e:
            import traceback

            traceback.print_exc()

        self._setup_dialog()
        self._connect_signals()
        self._populate_form()
        logger.info(
            "AddEditTestCaseDialog initialized for %s",
            "editing" if test_case else "creating new",
        )

    def _setup_dialog(self):
        """Setup dialog properties."""
        if self.test_case:
            self.setWindowTitle("Edit Test Case")
            self.ui.titleLabel.setText("Edit Test Case")
            test_case_id = self.test_case.get("id") or self.test_case.get("uuid", "N/A")
            self.ui.subtitleLabel.setText(f"ID: {test_case_id}")
            self.ui.saveButton.setText("💾 Update Test Case")
        else:
            self.setWindowTitle("Add New Test Case")
            self.ui.titleLabel.setText("Add New Test Case")
            self.ui.subtitleLabel.setText("Create a new test case")
            self.ui.saveButton.setText("💾 Create Test Case")

        # Set dialog properties
        self.setModal(True)
        self.resize(720, 600)

    def _connect_signals(self):
        """Connect UI signals to slots."""
        self.ui.saveButton.clicked.connect(self._save_test_case)

    def _populate_form(self):
        """Populate form fields if editing existing test case."""
        if self.test_case:
            # Map API response fields to form fields
            self.ui.fieldInput.setText(self.test_case.get("test_field", ""))
            self.ui.typeInput.setText(self.test_case.get("test_type", ""))
            self.ui.expectInput.setText(self.test_case.get("test_expect", ""))
            self.ui.testcaseInput.setText(self.test_case.get("test_case", ""))
            self.ui.referTextEdit.setPlainText(self.test_case.get("test_reference", ""))

    def _get_form_data(self) -> Dict:
        """Extract data from form fields."""
        return {
            "project_id": str(self.project_id),
            "test_field": self.ui.fieldInput.text().strip(),
            "test_type": self.ui.typeInput.text().strip(),
            "test_case": self.ui.testcaseInput.text().strip(),
            "test_reference": self.ui.referTextEdit.toPlainText().strip(),
            "test_expect": self.ui.expectInput.text().strip(),
        }

    def _validate_form(self) -> bool:
        """Validate form data."""
        data = self._get_form_data()

        # Check required fields
        if not data["test_field"]:
            QMessageBox.warning(self, "Validation Error", "Field name is required.")
            self.ui.fieldInput.setFocus()
            return False

        if not data["test_type"]:
            QMessageBox.warning(self, "Validation Error", "Test type is required.")
            self.ui.typeInput.setFocus()
            return False

        if not data["test_expect"]:
            QMessageBox.warning(self, "Validation Error", "expect type is required.")
            self.ui.expectInput.setFocus()
            return False

        if not data["test_case"]:
            QMessageBox.warning(
                self, "Validation Error", "Test case description is required."
            )
            self.ui.testcaseInput.setFocus()
            return False

        return True

    @Slot()
    def _save_test_case(self):
        """Save test case (create or update)."""
        if not self._validate_form():
            return

        # Disable save button during operation
        self.ui.saveButton.setEnabled(False)
        self.ui.saveButton.setText("💾 Saving...")

        test_case_data = self._get_form_data()

        if self.test_case:
            # Update existing test case
            test_case_id = self.test_case.get("id") or self.test_case.get("uuid")
            if not test_case_id:
                QMessageBox.critical(
                    self, "Error", "Cannot update test case: missing ID."
                )
                self._reset_save_button()
                return

            logger.info("Updating test case with ID: %s", test_case_id)
            self._start_worker("update_test_case", test_case_id, test_case_data)
        else:
            # Create new test case
            logger.info("Creating new test case for project: %s", self.project_id)
            self._start_worker("create_test_case", test_case_data)

    def _start_worker(self, operation: str, *args):
        """Start worker thread for async operations."""
        if self.worker and self.worker.isRunning():
            logger.debug("Worker already running, ignoring new operation")
            return

        kwargs = {}
        if operation == "create_test_case":
            kwargs["test_case_data"] = args[0]
        elif operation == "update_test_case":
            kwargs["test_case_id"] = args[0]
            kwargs["test_case_data"] = args[1]

        self.worker = TestCaseDialogWorker(self.db, operation, **kwargs)
        self.worker.operation_completed.connect(self._on_operation_completed)
        self.worker.operation_failed.connect(self._on_operation_failed)
        self.worker.start()

    @Slot(str, object)
    def _on_operation_completed(self, operation: str, result):
        """Handle successful operations."""
        logger.info("Operation %s completed successfully", operation)

        if operation == "create_test_case" and result:
            QMessageBox.information(self, "Success", "Test case created successfully!")
            self.test_case_saved.emit(result)
            self.accept()
        elif operation == "update_test_case" and result:
            QMessageBox.information(self, "Success", "Test case updated successfully!")
            # Emit updated test case data
            updated_data = self._get_form_data()
            updated_data["id"] = self.test_case.get("id")
            self.test_case_saved.emit(updated_data)
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Warning",
                f"Operation {operation} completed but no result returned.",
            )
            self._reset_save_button()

    @Slot(str, str)
    def _on_operation_failed(self, operation: str, error_message: str):
        """Handle failed operations."""
        logger.error("Operation %s failed: %s", operation, error_message)

        if operation == "create_test_case":
            QMessageBox.critical(
                self, "Create Failed", f"Failed to create test case: {error_message}"
            )
        elif operation == "update_test_case":
            QMessageBox.critical(
                self, "Update Failed", f"Failed to update test case: {error_message}"
            )

        self._reset_save_button()

    def _reset_save_button(self):
        """Reset save button to original state."""
        self.ui.saveButton.setEnabled(True)
        if self.test_case:
            self.ui.saveButton.setText("💾 Update Test Case")
        else:
            self.ui.saveButton.setText("💾 Create Test Case")

    def closeEvent(self, event):
        """Handle dialog close event."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        event.accept()
