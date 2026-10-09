"""
Fixed Screenshot Viewer Dialog

This provides a working replacement for the problematic ScreenshotViewerDialog
that was crashing due to UI file issues.
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from services.logging_config import get_logger

logger = get_logger("screenshot_viewer")


class ScreenshotViewerDialog(QDialog):
    """
    A working replacement for ScreenshotViewerDialog that doesn't rely on the problematic UI file.

    This dialog provides the same functionality as the original but uses manual UI construction
    instead of the generated UI file that was causing crashes.
    """

    def __init__(self, test_case_name, screenshots_list, parent=None):
        super().__init__(parent)

        self.setWindowTitle(f"Screenshots: {test_case_name}")
        self.setModal(True)
        self.resize(1000, 600)

        # Validate input
        if not screenshots_list:
            print("Warning: No screenshots provided")
            screenshots_list = []

        self.screenshots = screenshots_list
        self.current_start_index = 0
        self.images_per_page = 3

        self.screenshot_labels = []
        self.fullscreen_buttons = []

        self.setup_ui()
        self.setup_connections()
        self.update_display()

        logger.info(
            f"ScreenshotViewerDialog created with {len(self.screenshots)} screenshots"
        )

    def setup_ui(self):
        """Setup UI manually without using problematic .ui file"""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # Header
        header_layout = QHBoxLayout()

        self.title_label = QLabel(f"Screenshots: {len(self.screenshots)} images")
        self.title_label.setStyleSheet(
            """
            QLabel {
                font-size: 18pt;
                font-weight: bold;
                color: #203532;
                padding: 10px;
            }
        """
        )
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        self.image_count_label = QLabel("0 images")
        self.image_count_label.setStyleSheet(
            """
            QLabel {
                font-size: 14pt;
                color: #666666;
                padding: 5px;
            }
        """
        )
        header_layout.addWidget(self.image_count_label)

        main_layout.addLayout(header_layout)

        # Screenshots area
        screenshots_layout = QHBoxLayout()
        screenshots_layout.setSpacing(15)

        for i in range(3):
            # Container for each screenshot and its button
            screenshot_container = QVBoxLayout()

            # Screenshot label
            label = QLabel("No Image")
            label.setMinimumSize(400, 300)
            label.setMaximumSize(450, 350)
            label.setStyleSheet(
                """
                QLabel {
                    background-color: #FFFFFF;
                    border: 2px solid #CCCCCC;
                    border-radius: 8px;
                    color: #666666;
                    font-size: 12pt;
                }
                QLabel:hover {
                    border: 2px solid #4A90E2;
                }
            """
            )
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setScaledContents(False)
            self.screenshot_labels.append(label)

            screenshot_container.addWidget(label)
            screenshots_layout.addLayout(screenshot_container)

        main_layout.addLayout(screenshots_layout)

        # Navigation and controls
        nav_layout = QHBoxLayout()

        self.prev_button = QPushButton("← Previous")
        self.prev_button.setStyleSheet(
            """
            QPushButton {
                background-color: #28A745;
                color: white;
                font-size: 14pt;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px 20px;
                border: none;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1E7E34;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
        """
        )

        self.next_button = QPushButton("Next →")
        self.next_button.setStyleSheet(
            """
            QPushButton {
                background-color: #28A745;
                color: white;
                font-size: 14pt;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px 20px;
                border: none;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1E7E34;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
        """
        )

        nav_layout.addWidget(self.prev_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_button)

        main_layout.addLayout(nav_layout)

        # Set main dialog styling
        self.setStyleSheet(
            """
            QDialog {
                background-color: #ECF0F0;
                font-family: Arial, sans-serif;
            }
        """
        )

    def setup_connections(self):
        """Setup signal connections"""
        self.prev_button.clicked.connect(self.prev_page)
        self.next_button.clicked.connect(self.next_page)

        # Click on image to show fullscreen - proper event handling
        for i, label in enumerate(self.screenshot_labels):
            # Create a proper mouse press event handler
            def create_mouse_handler(index):
                def mouse_handler(event):
                    if (
                        hasattr(event, "button")
                        and event.button() == Qt.MouseButton.LeftButton
                    ):
                        self.show_fullscreen(index)
                    # Call the original mousePressEvent if it exists
                    QLabel.mousePressEvent(label, event)

                return mouse_handler

            label.mousePressEvent = create_mouse_handler(i)

    def prev_page(self):
        """Navigate to previous page"""
        try:
            if self.current_start_index >= self.images_per_page:
                self.current_start_index -= self.images_per_page
                self.update_display()
        except Exception as e:
            print(f"Error in prev_page: {e}")

    def next_page(self):
        """Navigate to next page"""
        try:
            if self.current_start_index + self.images_per_page < len(self.screenshots):
                self.current_start_index += self.images_per_page
                self.update_display()
        except Exception as e:
            print(f"Error in next_page: {e}")

    def update_display(self):
        """Update the display with current screenshots and pagination state"""
        try:
            # Update navigation buttons
            self.prev_button.setEnabled(self.current_start_index > 0)
            self.next_button.setEnabled(
                self.current_start_index + self.images_per_page < len(self.screenshots)
            )

            # Hide navigation buttons if total images <= 3
            if len(self.screenshots) <= 3:
                self.prev_button.hide()
                self.next_button.hide()
            else:
                self.prev_button.show()
                self.next_button.show()

            # Update counter
            if len(self.screenshots) > 0:
                start = self.current_start_index + 1
                end = min(
                    self.current_start_index + self.images_per_page,
                    len(self.screenshots),
                )
                total = len(self.screenshots)
                self.image_count_label.setText(f"{start}-{end} of {total} images")
            else:
                self.image_count_label.setText("No images")

            # Update screenshots
            for i, label in enumerate(self.screenshot_labels):
                screenshot_index = self.current_start_index + i
                if screenshot_index < len(self.screenshots):
                    screenshot_path = self.screenshots[screenshot_index]
                    self._load_screenshot_into_label(
                        label, screenshot_path, screenshot_index
                    )
                    label.show()
                else:
                    # Hide if no image
                    label.hide()

        except Exception as e:
            print(f"Error in update_display: {e}")
            # Set error state
            for label in self.screenshot_labels:
                label.setText("Error loading screenshots")
                label.show()

    def _load_screenshot_into_label(
        self, label: QLabel, screenshot_path: str, index: int
    ):
        """Load a screenshot into a label widget"""
        try:
            if not os.path.exists(screenshot_path):
                label.clear()
                label.setText(
                    f"Screenshot {index + 1}\nFile not found:\n{os.path.basename(screenshot_path)}"
                )
                label.setStyleSheet(
                    label.styleSheet()
                    + "\nQLabel { color: red; background-color: #FFE6E6; }"
                )
                return

            pixmap = QPixmap(screenshot_path)
            if not pixmap.isNull():
                # Scale pixmap to fit label while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(
                    label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                label.setPixmap(scaled_pixmap)
                label.setText("")  # Clear any text
                # Reset styling to remove error states
                label.setStyleSheet(
                    """
                    QLabel {
                        background-color: #FFFFFF;
                        border: 2px solid #CCCCCC;
                        border-radius: 8px;
                        color: #666666;
                        font-size: 12pt;
                    }
                    QLabel:hover {
                        border: 2px solid #4A90E2;
                    }
                """
                )
            else:
                label.clear()
                label.setText(f"Screenshot {index + 1}\nInvalid image format")
                label.setStyleSheet(
                    label.styleSheet()
                    + "\nQLabel { color: red; background-color: #FFE6E6; }"
                )

        except Exception as e:
            logger.error(f"Error loading screenshot {screenshot_path}: {e}")
            label.clear()
            label.setText(f"Screenshot {index + 1}\nError loading image")
            label.setStyleSheet(
                label.styleSheet()
                + "\nQLabel { color: red; background-color: #FFE6E6; }"
            )

    def show_fullscreen(self, index: int):
        """Show fullscreen view of a screenshot"""
        try:
            screenshot_index = self.current_start_index + index
            if screenshot_index >= len(self.screenshots):
                return

            screenshot_path = self.screenshots[screenshot_index]

            if not os.path.exists(screenshot_path):
                QMessageBox.warning(
                    self,
                    "File Not Found",
                    f"Screenshot file not found:\n{screenshot_path}",
                )
                return

            # Create fullscreen dialog
            fullscreen_dialog = QDialog(self)
            fullscreen_dialog.setWindowTitle(
                f"Fullscreen: {os.path.basename(screenshot_path)}"
            )
            fullscreen_dialog.setWindowState(Qt.WindowState.WindowMaximized)

            layout = QVBoxLayout(fullscreen_dialog)
            layout.setContentsMargins(20, 20, 20, 20)

            # Image label
            image_label = QLabel()
            pixmap = QPixmap(screenshot_path)

            if not pixmap.isNull():
                # Scale to fit screen while maintaining aspect ratio
                screen_geom = fullscreen_dialog.screen().availableGeometry()
                target_size = screen_geom.size() * 0.9
                scaled_pixmap = pixmap.scaled(
                    target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                image_label.setPixmap(scaled_pixmap)
            else:
                image_label.setText("Unable to load image")
                image_label.setStyleSheet("color: red; font-size: 18pt;")

            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(image_label)

            # Close button
            close_btn = QPushButton("✖ Close (ESC)")
            close_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #DC3545;
                    color: white;
                    font-size: 14pt;
                    font-weight: bold;
                    border-radius: 6px;
                    padding: 10px 20px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #C82333;
                }
            """
            )
            close_btn.clicked.connect(fullscreen_dialog.close)

            # ESC key handler
            def handle_key_press(event):
                if event.key() == Qt.Key.Key_Escape:
                    fullscreen_dialog.close()
                else:
                    QDialog.keyPressEvent(fullscreen_dialog, event)

            fullscreen_dialog.keyPressEvent = handle_key_press

            layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)
            fullscreen_dialog.exec()

        except Exception as e:
            print(f"Error in show_fullscreen: {e}")
            QMessageBox.warning(self, "Error", f"Failed to display screenshot: {e}")
