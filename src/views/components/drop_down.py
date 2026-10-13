from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox


class ComboBox(QComboBox):
    """
    QComboBox styled by the global stylesheet (asset/forms.qss).

    The old per-instance styling arguments (bg_color, border_radius, padding,
    item colours, arrow icons...) are still accepted so existing call sites keep
    working, but they are ignored: every combo box now shares one look.
    """

    # Custom signal emitted when the dropdown is about to be shown
    aboutToShow = Signal()

    def __init__(self, parent=None, items: list[str] | None = None, **_style_kwargs):
        super().__init__(parent)
        if items:
            self.addItems(items)
        self.setMinimumHeight(36)

    def showPopup(self):
        """Override showPopup to emit the aboutToShow signal before showing the dropdown."""
        self.aboutToShow.emit()
        super().showPopup()
