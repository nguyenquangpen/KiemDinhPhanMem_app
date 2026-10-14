import asyncio
import logging
import os
import sys

if getattr(sys, 'frozen', False):
    browsers_path = os.path.join(sys._MEIPASS, 'ms-playwright')
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from models.database import DataManager
from services.logging_config import get_logger, setup_logging_with_env
from services.session import session_manager
from settings.config import API_ENDPOINT, DEMO_PASSWORD, DEMO_USERNAME
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
            use_api=True
        )
        self.script_dir = os.path.dirname(__file__)
        self.icon_path = os.path.join(self.script_dir, "theme", "icon", "favicon.ico")
        self.main_window = None

    def run(self) -> bool:
        """Không có màn hình đăng nhập: tự đăng nhập server bằng tài khoản demo rồi mở thẳng màn hình chính."""
        logger.info("Running TestAgent application")
        if not asyncio.run(self.db.auto_login(DEMO_USERNAME, DEMO_PASSWORD)):
            reply = QMessageBox.question(
                None,
                "Không kết nối được server",
                f"Không đăng nhập được vào server tại {API_ENDPOINT}.\n"
                "Hãy kiểm tra server đã chạy (python main.py trong KiemDinhPhanMem_server) "
                "và MongoDB đang bật.\n\n"
                "Mở app ở chế độ offline để xem dữ liệu cục bộ?\n"
                "(Sinh testcase, chạy testcase và đồng bộ cần server.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
            # Dữ liệu cục bộ gắn với user theo tên, không cần token
            logger.warning("Server unavailable, starting in offline mode as '%s'", DEMO_USERNAME)
            self.db._get_local_user(DEMO_USERNAME)

        self.main_window = MainWindow(self.db)
        if os.path.exists(self.icon_path):
            self.main_window.setWindowIcon(QIcon(self.icon_path))
        else:
            logger.warning("Window icon file not found at: %s", self.icon_path)
        self.main_window.set_user_info(session_manager.get_user_info() or {"username": DEMO_USERNAME})
        self.main_window.show()
        return True


if __name__ == "__main__":
    logger.info(
        "Logger initialized with level: %s",
        logging.getLevelName(logger.getEffectiveLevel()),
    )
    logger.info("Starting TestAgent Tool application")
    app = QApplication(sys.argv)
    asset.apply_style(app)

    controller = ApplicationController()
    if not controller.run():
        sys.exit(1)

    logger.info("Application started successfully")
    sys.exit(app.exec())
