"""
Test Progress Dialog

A dialog that shows test execution progress with real-time updates.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class TestProgressDialog(QDialog):
    """Dialog to show test execution progress"""

    def __init__(self, test_count: int, parent=None):
        super().__init__(parent)
        self.test_count = test_count
        self.current_test = 0
        self.setup_ui()
        self.setup_timer()

    def setup_ui(self):
        """Setup the dialog UI"""
        self.setWindowTitle("Test Execution Progress")
        self.setModal(True)
        self.setMinimumSize(500, 400)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Title
        title_label = QLabel("🧪 Executing Test Cases")
        title_label.setStyleSheet(
            """
            QLabel {
                font-size: 18pt;
                font-weight: bold;
                color: #203532;
                padding: 10px;
                text-align: center;
            }
        """
        )
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(self.test_count)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                border: 2px solid #CCCCCC;
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
                background-color: #F5F5F5;
            }
            QProgressBar::chunk {
                background-color: #4A90E2;
                border-radius: 3px;
            }
        """
        )
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Preparing to run tests...")
        self.status_label.setStyleSheet(
            """
            QLabel {
                font-size: 12pt;
                color: #666666;
                padding: 5px;
            }
        """
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Log output
        log_label = QLabel("Execution Log:")
        log_label.setStyleSheet("font-weight: bold; color: #203532;")
        layout.addWidget(log_label)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(150)
        self.log_output.setStyleSheet(
            """
            QTextEdit {
                background-color: #F8F8F8;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                font-family: 'Consolas', monospace;
                font-size: 10pt;
            }
        """
        )
        layout.addWidget(self.log_output)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet(
            """
            QPushButton {
                background-color: #F48080;
                color: white;
                font-weight: bold;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #E66B6B;
            }
        """
        )
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.close_button = QPushButton("Close")
        self.close_button.setStyleSheet(
            """
            QPushButton {
                background-color: #4A90E2;
                color: white;
                font-weight: bold;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #357ABD;
            }
        """
        )
        self.close_button.clicked.connect(self.accept)
        self.close_button.setVisible(False)  # Hide until tests complete
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

        # Set dialog style
        self.setStyleSheet(
            """
            QDialog {
                background-color: #ECF0F0;
                font-family: 'Lexend';
            }
        """
        )

    def setup_timer(self):
        """Setup timer for progress updates"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)

    def start_execution(self):
        """Start the test execution display"""
        self.status_label.setText("Initializing browser...")
        self.add_log("🚀 Starting test execution")
        self.add_log(f"📋 {self.test_count} test cases to execute")

    def update_test_progress(self, test_name: str, status: str):
        """Update progress for current test"""
        if status == "started":
            self.current_test += 1
            self.progress_bar.setValue(self.current_test)
            self.status_label.setText(f"Running: {test_name}")
            self.add_log(f"▶️  Test {self.current_test}/{self.test_count}: {test_name}")
        elif status == "completed":
            self.add_log(f"✅ Completed: {test_name}")
        elif status == "failed":
            self.add_log(f"❌ Failed: {test_name}")
        elif status == "error":
            self.add_log(f"🚫 Error: {test_name}")

    def execution_completed(self, success: bool, message: str = ""):
        """Handle execution completion"""
        if success:
            self.status_label.setText("✅ All tests completed successfully!")
            self.add_log("🎉 Test execution completed successfully")
        else:
            self.status_label.setText("❌ Test execution failed")
            self.add_log(f"💥 Test execution failed: {message}")

        self.progress_bar.setValue(self.test_count)
        self.cancel_button.setVisible(False)
        self.close_button.setVisible(True)

    def add_log(self, message: str):
        """Add a message to the log"""
        from datetime import datetime

        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_output.append(log_entry)

        # Auto-scroll to bottom
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def update_progress(self):
        """Update progress animation"""
        # This can be used for animated progress updates
        pass
