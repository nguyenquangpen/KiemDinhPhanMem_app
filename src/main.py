import logging
import os
import sys

if getattr(sys, 'frozen', False):
    browsers_path = os.path.join(sys._MEIPASS, 'ms-playwright')
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_path

from PySide6.QtCore import Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from models.data_classes import User
from models.database import DataManager
from services.logging_config import get_logger, setup_logging_with_env
from services.session import session_manager
from settings.config import API_ENDPOINT, API_CW_ENDPOINT
from views.pages.auth import LoginWindow
from views.pages.home import MainWindow
import asset

# Initialize logging system with environment configuration
setup_logging_with_env()
logger = get_logger("testagent")


class ApplicationController:
    def __init__(self):
        logger.info("Initializing TestAgent application")
        self.db = DataManager(
            "agent_local_storage.db", 
            API_ENDPOINT, 
            API_CW_ENDPOINT,
            use_api=True
        )

        self.script_dir = os.path.dirname(__file__)
        self.icon_path = os.path.join(self.script_dir, "theme", "icon", "favicon.ico")
        # Check if user is already authenticated via session
        if session_manager.is_authenticated():
            user_info = session_manager.get_user_info()
            if user_info:
                logger.info("User already logged in: %s", user_info.get("username"))
                self.main_window = MainWindow(self.db)
                if os.path.exists(self.icon_path):
                    window_icon = QIcon(self.icon_path)
                    self.main_window.setWindowIcon(window_icon)
                    logger.info("Window icon set from: %s", self.icon_path)
                else:
                    logger.warning("Window icon file not found at: %s", self.icon_path)
                self.main_window.set_user_info(user_info)
                self.main_window.show()
                self.login_window = None
                return
        logger.info("Login window initialized")

        # User is not authenticated, show login window
        self.login_window = LoginWindow(self.db)
        self.main_window = MainWindow(self.db)
        self.login_window.login_success.connect(self.show_main_window)

    def run(self):
        logger.info("Running TestAgent application")
        if self.login_window is not None:
            if os.path.exists(self.icon_path):
                window_icon = QIcon(self.icon_path)
                self.login_window.setWindowIcon(window_icon)
                logger.info("Window icon set from: %s", self.icon_path)
            else:
                logger.warning("Window icon file not found at: %s", self.icon_path)
            self.login_window.show()

    @Slot(User)
    def show_main_window(self, user: User):
        logger.info(
            "Login successful for user: '%s'. Showing main window.",
            user.get("username"),
        )

        self.main_window.set_user_info(user)
        if os.path.exists(self.icon_path):
            window_icon = QIcon(self.icon_path)
            self.main_window.setWindowIcon(window_icon)
            logger.info("Window icon set from: %s", self.icon_path)
        else:
            logger.warning("Window icon file not found at: %s", self.icon_path)
        self.main_window.show()
        if self.login_window:
            self.login_window.close()


if __name__ == "__main__":
    logger.info(
        "Logger initialized with level: %s",
        logging.getLevelName(logger.getEffectiveLevel()),
    )
    logger.info("Starting TestAgent Tool application")
    app = QApplication(sys.argv)
    asset.apply_style(app)

    controller = ApplicationController()
    controller.run()

    logger.info("Application started successfully")
    sys.exit(app.exec())
