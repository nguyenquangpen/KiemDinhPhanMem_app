"""
A reusable widget for displaying screenshots in a grid layout with pagination
and fullscreen viewing capabilities. Uses manual UI construction to avoid
issues with generated UI files.
"""

import os
from typing import List

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.logging_config import get_logger

from views.components import ui_kit

logger = get_logger("screenshot_gallery")


class ScreenshotGalleryWidget(QWidget):
    """
    A reusable widget for displaying screenshots in a grid layout.

    Features:
    - Grid display of up to 4 screenshots per page
    - Pagination navigation
    - Click to view fullscreen
    - Refresh functionality
    - Automatic image loading and scaling
    """

    # Signals
    screenshot_clicked = Signal(str)  # Emitted when a screenshot is clicked
    refresh_requested = Signal()  # Emitted when refresh is clicked

    def __init__(self, parent=None):
        super().__init__(parent)

        # Initialize state
        self.screenshots: List[str] = []
        self.current_page = 0
        self.images_per_page = 4

        # Setup UI manually to avoid generated UI file issues
        self._create_ui()
        self._setup_connections()

    def _create_ui(self):
        """Create the UI layout manually."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # Title section
        title_layout = QHBoxLayout()

        self.titleLabel = QLabel("Screenshots")
        self.titleLabel.setObjectName("CardTitle")
        title_layout.addWidget(self.titleLabel)

        title_layout.addStretch()

        self.main_layout.addLayout(title_layout)

        # Gallery grid (2x2)
        self.gallery_widget = QWidget()
        gallery_layout = QGridLayout(self.gallery_widget)
        gallery_layout.setSpacing(15)

        # Create 4 screenshot display areas
        self.display_labels = []

        for row in range(2):
            for col in range(2):
                # Container for each screenshot
                container = QWidget()
                container_layout = QVBoxLayout(container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(5)

                # Image display label
                label = QLabel()
                label.setObjectName("ScreenshotPreviewLabel")
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                label.setMinimumSize(250, 200)
                label.setMaximumSize(350, 280)
                label.setScaledContents(False)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)

                container_layout.addWidget(label)
                gallery_layout.addWidget(container, row, col)
                self.display_labels.append(label)

        self.main_layout.addWidget(self.gallery_widget)

        # Navigation section
        nav_layout = QHBoxLayout()

        self.prevButton = ui_kit.button("Previous", "neutral", "chevron-left")

        nav_layout.addWidget(self.prevButton)

        # Page info
        self.pageInfoLabel = QLabel("Page 1 of 1")
        self.pageInfoLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pageInfoLabel.setObjectName("PaginationInfo")
        nav_layout.addStretch()
        nav_layout.addWidget(self.pageInfoLabel)
        nav_layout.addStretch()

        self.nextButton = ui_kit.button("Next", "neutral", "chevron-right", icon_right=True)

        nav_layout.addWidget(self.nextButton)

        self.main_layout.addLayout(nav_layout)

    def _setup_connections(self):
        """Setup signal connections."""
        # Navigation
        self.prevButton.clicked.connect(self.previous_page)
        self.nextButton.clicked.connect(self.next_page)

        # Click on images for fullscreen
        for i, label in enumerate(self.display_labels):

            def create_click_handler(index):
                def handler(event):
                    if (
                        hasattr(event, "button")
                        and event.button() == Qt.MouseButton.LeftButton
                    ):
                        self._on_screenshot_clicked(index)
                    QLabel.mousePressEvent(label, event)

                return handler

            label.mousePressEvent = create_click_handler(i)

    def set_screenshots(self, screenshots: List[str], title: str = "Screenshots"):
        """Set the list of screenshots to display."""
        self.screenshots = screenshots or []
        self.current_page = 0
        self.titleLabel.setText(title)
        self._update_display()

    def refresh_screenshots(self):
        """Refresh the current display."""
        self._update_display()

    def previous_page(self):
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_display()

    def next_page(self):
        """Go to next page."""
        total_pages = self._get_total_pages()
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._update_display()

    def _get_total_pages(self) -> int:
        """Calculate total number of pages."""
        if not self.screenshots:
            return 1
        return (len(self.screenshots) - 1) // self.images_per_page + 1

    def _update_display(self):
        """Update the display with current page screenshots."""
        try:
            # Update navigation buttons
            total_pages = self._get_total_pages()
            self.prevButton.setEnabled(self.current_page > 0)
            self.nextButton.setEnabled(self.current_page < total_pages - 1)

            # Update page info
            if self.screenshots:
                self.pageInfoLabel.setText(
                    f"Page {self.current_page + 1} of {total_pages}"
                )
            else:
                self.pageInfoLabel.setText("No screenshots")

            # Update screenshots
            start_idx = self.current_page * self.images_per_page

            for i in range(self.images_per_page):
                label = self.display_labels[i]
                screenshot_idx = start_idx + i

                if screenshot_idx < len(self.screenshots):
                    screenshot_path = self.screenshots[screenshot_idx]

                    if os.path.exists(screenshot_path):
                        # Load and display image
                        pixmap = QPixmap(screenshot_path)
                        if not pixmap.isNull():
                            # Scale image to fit label
                            scaled_pixmap = pixmap.scaled(
                                label.size() - QSize(20, 20),  # Account for padding
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                            label.setPixmap(scaled_pixmap)
                            label.setText("")
                        else:
                            label.clear()
                            label.setText(
                                f"Invalid image\\n{os.path.basename(screenshot_path)}"
                            )
                    else:
                        label.clear()
                        label.setText(
                            f"File not found\\n{os.path.basename(screenshot_path)}"
                        )

                    label.show()
                else:
                    # Hide unused slots
                    label.clear()
                    label.setText("")
                    label.hide()

        except Exception as e:
            logger.error(f"Error updating gallery display: {e}")
            for label in self.display_labels:
                label.setText("Error loading screenshots")

    def _on_screenshot_clicked(self, index: int):
        """Handle screenshot click (image or view button)."""
        start_idx = self.current_page * self.images_per_page
        screenshot_idx = start_idx + index

        if screenshot_idx < len(self.screenshots):
            screenshot_path = self.screenshots[screenshot_idx]

            # Emit signal for external handling
            self.screenshot_clicked.emit(screenshot_path)

            # Also show fullscreen directly
            self._show_fullscreen(screenshot_path)

    def _show_fullscreen(self, screenshot_path: str):
        """Show screenshot in fullscreen dialog."""
        try:
            if not os.path.exists(screenshot_path):
                QMessageBox.warning(
                    self,
                    "File Not Found",
                    f"Screenshot file not found:\\n{screenshot_path}",
                )
                return

            # Create fullscreen dialog
            fullscreen_dialog = QDialog(self)
            fullscreen_dialog.setObjectName("FullscreenViewer")
            fullscreen_dialog.setWindowTitle("Screenshot Viewer")
            fullscreen_dialog.setWindowState(Qt.WindowState.WindowMaximized)

            layout = QVBoxLayout(fullscreen_dialog)
            layout.setContentsMargins(20, 20, 20, 20)

            # Image label
            image_label = QLabel()
            pixmap = QPixmap(screenshot_path)
            if not pixmap.isNull():
                # Scale to fit screen
                screen_geom = fullscreen_dialog.screen().availableGeometry()
                target_size = QSize(
                    int(screen_geom.width() * 0.9), int(screen_geom.height() * 0.9)
                )
                scaled_pixmap = pixmap.scaled(
                    target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                image_label.setPixmap(scaled_pixmap)
            else:
                image_label.setText("Unable to load image")

            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(image_label)

            # Close button
            close_btn = ui_kit.button("Close (Esc)", "neutral", "x")
            close_btn.clicked.connect(fullscreen_dialog.close)

            # ESC key handling
            def handle_key_press(event):
                if event.key() == Qt.Key.Key_Escape:
                    fullscreen_dialog.close()
                else:
                    QDialog.keyPressEvent(fullscreen_dialog, event)

            fullscreen_dialog.keyPressEvent = handle_key_press

            layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)
            fullscreen_dialog.exec()

        except Exception as e:
            logger.error(f"Error showing fullscreen: {e}")
            QMessageBox.critical(
                self, "Error", f"Failed to display screenshot:\\n{str(e)}"
            )
