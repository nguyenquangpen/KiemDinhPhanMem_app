from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from . import tokens
from .style_manager import StyleManager

STYLE_DIR = Path(__file__).parent.resolve()
FONT_DIR = STYLE_DIR / "fonts"

style_manager = StyleManager(STYLE_DIR)


def load_fonts() -> None:
    """Register the bundled Poppins / Noto Serif fonts (falls back to Segoe UI if missing)."""
    for font_file in sorted(FONT_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(font_file))


def apply_style(app: QApplication):
    load_fonts()
    base_font = QFont(tokens.FONT_UI)
    base_font.setFamilies([tokens.FONT_UI, "Segoe UI", "Arial"])
    base_font.setPixelSize(13)
    app.setFont(base_font)

    full_stylesheet = style_manager.get_full_stylesheet()
    app.setStyleSheet(full_stylesheet)
