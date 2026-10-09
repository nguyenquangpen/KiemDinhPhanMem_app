from pathlib import Path
from PySide6.QtWidgets import QApplication
from .style_manager import StyleManager 

STYLE_DIR = Path(__file__).parent.resolve()

style_manager = StyleManager(STYLE_DIR)


def apply_style(app: QApplication):
    full_stylesheet = style_manager.get_full_stylesheet()

    app.setStyleSheet(full_stylesheet)
    