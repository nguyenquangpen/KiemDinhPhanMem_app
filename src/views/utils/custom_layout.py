from PySide6.QtWidgets import (QApplication, QWidget, QLayout, QLayoutItem,
                                QPushButton, QMainWindow, QVBoxLayout, QLabel, QStyle)
from PySide6.QtCore import Qt, QRect, QSize, QPoint
import sys


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, h_spacing=-1, v_spacing=-1):
        super().__init__(parent)

        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)

        self._item_list: list[QLayoutItem] = []
        self._h_space = h_spacing
        self._v_space = v_spacing

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item: QLayoutItem) -> None:
        """Add an item to the layout."""
        self._item_list.append(item)

    def count(self) -> int:
        """Return the number of items in the layout."""
        return len(self._item_list)

    def itemAt(self, index: int) -> QLayoutItem | None:
        """Return the item at the given index."""
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        """Remove and return the item at the given index."""
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        """Return which directions this layout can expand."""
        return Qt.Orientation(0)  # No expanding directions

    def hasHeightForWidth(self) -> bool:
        """Return True if this layout's preferred height depends on its width."""
        return True

    def heightForWidth(self, width: int) -> int:
        """Return the preferred height for the given width."""
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect: QRect) -> None:
        """Set the geometry of the layout."""
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        """Return the preferred size of the layout."""
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        """Return the minimum size of the layout."""
        size = QSize()

        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())

        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """Perform the layout calculation."""
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(),
                                     -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._item_list:
            widget = item.widget()
            space_x = self._horizontal_spacing()
            space_y = self._vertical_spacing()

            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + margins.bottom()

    def _horizontal_spacing(self) -> int:
        """Return the horizontal spacing between items."""
        if self._h_space >= 0:
            return self._h_space
        else:
            return self._smart_spacing(QStyle.PixelMetric.PM_LayoutHorizontalSpacing)

    def _vertical_spacing(self) -> int:
        """Return the vertical spacing between items."""
        if self._v_space >= 0:
            return self._v_space
        else:
            return self._smart_spacing(QStyle.PixelMetric.PM_LayoutVerticalSpacing)

    def _smart_spacing(self, pm: QStyle.PixelMetric) -> int:
        """Get spacing from the parent widget's style."""
        parent = self.parent()
        if not parent:
            return -1
        elif parent.isWidgetType():
            return parent.style().pixelMetric(pm, None, parent) # type: ignore
        else:
            return parent.spacing() # type: ignore