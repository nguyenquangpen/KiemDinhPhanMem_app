import asyncio

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QMainWindow

from models.data_classes import User
from models.database import DataManager
from services.logging_config import get_ui_logger
from ui.build.ui_login import Ui_LoginWindow
from views.components.login_failed import LoginFailWidget

logger = get_ui_logger()


class LoginWorker(QThread):
    """Worker thread to handle async authentication"""

    login_result = Signal(bool, object)  # success, user_object

    def __init__(self, db_manager, username, password):
        super().__init__()
        self.db_manager = db_manager
        self.username = username
        self.password = password
        logger.debug("LoginWorker initialized with username: %s", self.username)

    def run(self):
        """Run the async authentication in a new event loop"""
        try:
            logger.debug("Starting authentication for user: %s", self.username)
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Run the async authentication
            success = loop.run_until_complete(
                self.db_manager.authenticate_user(self.username, self.password)
            )
            # success = loop.run_until_complete(
            #     self.db_manager.hybrid_authenticate(self.username, self.password)
            # )

            if success:
                logger.info("Authentication successful for user: %s", self.username)
                self.login_result.emit(
                    True, {"username": self.username, "authenticated": True}
                )
            else:
                logger.warning("Authentication failed for user: %s", self.username)
                self.login_result.emit(False, None)

        except Exception as e:
            logger.error("Login error for user %s: %s", self.username, e, exc_info=True)
            self.login_result.emit(False, None)
        finally:
            loop.close()


class LoginWindow(QMainWindow):
    login_success = Signal(User)

    def __init__(self, data_manager: DataManager):
        super().__init__()
        self.db = data_manager
        self.login_worker = None

        self.ui = Ui_LoginWindow()
        self.ui.setupUi(self)
        self.setWindowTitle("Login")
        self.ui.loginButton.clicked.connect(self.handle_login_click)
        self.ui.passwordEdit.returnPressed.connect(self.handle_login_click)

        self.fail_widget = LoginFailWidget(self)
        self.fail_widget.hide()  # Also hidden initially

        # 3. Connect the click signal to hide the message
        self.fail_widget.clicked.connect(self.hide_login_fail)
        logger.info("LoginWindow initialized with DataManager")

    def handle_login_click(self):
        """Handle login button click by starting worker thread."""
        username = self.ui.usernameEdit.text()
        password = self.ui.passwordEdit.text()
        logger.debug("Login button clicked with username: %s", username)
        # Disable UI while processing
        self.ui.loginButton.setEnabled(False)
        self.ui.loginButton.setText("Logging in...")

        # Create and start worker thread
        self.login_worker = LoginWorker(self.db, username, password)
        self.login_worker.login_result.connect(self.handle_login_result)
        self.login_worker.start()

    def handle_login_result(self, success: bool, user: User):
        """Handle the result from the login worker thread."""
        # Re-enable UI
        self.ui.loginButton.setEnabled(True)
        self.ui.loginButton.setText("Login")

        if success and user:
            self.login_success.emit(user)
            logger.info("Login successful for user: %s", user.get("username"))
            self.close()
        else:
            logger.warning("Login failed - showing error message")
            # Instead of a QMessageBox, show our custom widget
            self.show_login_fail()
            # Clear password and re-focus username
            self.ui.passwordEdit.clear()
            self.ui.usernameEdit.setFocus()
            self.ui.usernameEdit.selectAll()

        # Clean up worker
        if self.login_worker:
            self.login_worker.deleteLater()
            self.login_worker = None
            logger.debug("LoginWorker cleaned up after use")

    def show_login_fail(self):
        """Makes the fail widget visible and centers them."""
        self.fail_widget.show()
        self.fail_widget.raise_()
        self.center_fail_widget()
        logger.debug("Login fail widget shown and raised")

    def hide_login_fail(self):
        """Hides the the fail widget."""
        self.fail_widget.hide()
        logger.debug("Login fail widget hidden")

    def center_fail_widget(self):
        """Helper function to position the fail widget in the center of the window."""
        parent_rect = self.rect()
        widget_size = self.fail_widget.size()
        x = (parent_rect.width() - widget_size.width()) // 2
        y = (parent_rect.height() - widget_size.height()) // 2
        self.fail_widget.move(x, y)
        logger.debug("Centered fail widget at position: (%d, %d)", x, y)

    def resizeEvent(self, event):
        """
        Overrides the resize event to keep the filling the window and
        the fail widget centered.
        """
        # Let the parent class handle the event first
        super().resizeEvent(event)
        logger.debug("LoginWindow resized to: %s", self.size())
        # If the fail widget is visible, re-center it
        if self.fail_widget.isVisible():
            self.center_fail_widget()
