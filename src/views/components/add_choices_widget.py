from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QLineEdit,
    QDialog,
    QLayoutItem,
    QListWidget,
    QDialogButtonBox,
    QAbstractItemView,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPalette, QFont, QColor
from typing import List, Optional, Callable  # Import Callable
from views.utils.custom_layout import (
    FlowLayout,
)


class PillWidget(QWidget):
    """A styled widget containing text and an optional remove button."""

    remove_clicked = Signal(str)

    def __init__(self, text: str, removable: bool = True, parent=None):
        super().__init__(parent)
        self.text = text
        self.removable = removable
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(5)

        self.label = QLabel(self.text)
        self.label.setFont(QFont(self.font().family(), 9))
        layout.addWidget(self.label)

        if self.removable:
            self.remove_btn = QPushButton("×")
            self.remove_btn.setFixedSize(16, 16)
            self.remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.remove_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #E0E0E0; color: #555555;
                    border: none; border-radius: 8px; font-weight: bold;
                }
                QPushButton:hover { background-color: #F48080; color: white; }
            """
            )
            self.remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self.text))
            layout.addWidget(self.remove_btn)

        self.setLayout(layout)
        self.setAutoFillBackground(True)
        self.setPalette(QPalette(QColor("#E9E9E9")))
        self.setStyleSheet("border-radius: 10px;")


class AddButton(QPushButton):
    """A styled add button."""

    def __init__(self, parent=None):
        super().__init__("+", parent)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: #56BB55; color: white;
                border: none; border-radius: 11px;
                font-size: 16px; font-weight: bold;
                padding-bottom: 2px;
            }}
            QPushButton:hover {{ background-color: #4CAF50; }}
        """
        )


class AddItemDialog(QDialog):
    """A dialog for searching and selecting items to add."""

    def __init__(self, existing_items: List[str], items: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Validation Types")
        self.setMinimumWidth(300)

        self.existing_items = set(existing_items)
        self.full_item_list = []

        layout = QVBoxLayout(self)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search for items to add...")
        self.search_input.textChanged.connect(self._update_filter)
        layout.addWidget(self.search_input)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        layout.addWidget(self.list_widget)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._populate_list(items)

    def _populate_list(self, items):
        """Populates the list widget with available, non-existing items."""
        self.full_item_list = items
        # Filter out items that are already in the main widget
        available_items = [
            item for item in self.full_item_list if item not in self.existing_items
        ]
        self.list_widget.addItems(sorted(available_items))

    def _update_filter(self, text: str):
        """Hides or shows items in the list based on the search text."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            # Hide the item if its text doesn't contain the search query (case-insensitive)
            item.setHidden(text.lower() not in item.text().lower())

    def get_selected_items(self) -> List[str]:
        """Returns the text of the selected items in the list."""
        return [item.text() for item in self.list_widget.selectedItems()]


class MutableListWidget(QWidget):
    """
    A widget that displays a list of strings as "pills" that can be
    added or removed via a user-friendly interface.
    """

    select_dialog_open = Signal(list)
    items_changed = Signal(list)

    def __init__(
        self,
        title: str = "",
        items: Optional[List[str]] = None,
        all_available_items: Optional[List[str]] = None,
        items_factory: Optional[Callable[[], List[str]]] = None,
        editable: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.title = title
        # Use a set for faster lookups when adding, but keep a list for order
        self._items = items or []
        self._item_set = set(self._items)
        self.all_available_items = all_available_items or []
        self.items_factory = items_factory
        self.editable = editable
        self._pill_widgets = {}  # Use a dict for faster pill lookup on removal

        self.add_btn = None

        self._init_ui()
        self._populate_items()

    def _init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)

        if self.title:
            main_layout.addWidget(QLabel(self.title))

        self.flow_widget = QWidget()
        self.flow_layout = FlowLayout()
        self.flow_layout.setSpacing(4)
        self.flow_widget.setLayout(self.flow_layout)

        main_layout.addWidget(self.flow_widget)
        self.setLayout(main_layout)

    def _populate_items(self):
        """Re-draws all pill widgets from the internal item list."""
        self._clear_pills()
        for item in self._items:
            self._add_pill_widget(item)

        if self.editable:
            self._ensure_plus_button()

    def _clear_pills(self):
        """Removes all pill widgets from the layout."""
        for pill in self._pill_widgets.values():
            pill.deleteLater()
        self._pill_widgets.clear()

    def _add_pill_widget(self, text: str):
        """Creates and adds a single pill widget to the layout."""
        if text in self._pill_widgets:
            return  # Avoid duplicates

        pill = PillWidget(text, removable=self.editable)
        if self.editable:
            pill.remove_clicked.connect(self._remove_item)

        self.flow_layout.addWidget(pill)
        self._pill_widgets[text] = pill

    def _ensure_plus_button(self):
        """Ensures the add button is created and correctly positioned."""
        if self.add_btn is None:
            self.add_btn = AddButton()
            self.add_btn.clicked.connect(self._show_add_dialog)
            self.flow_layout.addWidget(self.add_btn)
        else:
            # Ensure the button is at the end of the layout
            self.flow_layout.removeWidget(self.add_btn)
            self.flow_layout.addWidget(self.add_btn)
        self.add_btn.setVisible(True)

    def _show_add_dialog(self):
        """Shows the dialog to add new items, fetching them if necessary."""
        # Determine the source for available items, prioritizing the factory
        if self.items_factory:
            # Call the factory to get a fresh list of items
            available_items = self.items_factory()
        else:
            # Fallback to the pre-supplied static list
            available_items = self.all_available_items

        self.select_dialog_open.emit(available_items)
        dialog = AddItemDialog(self._items, available_items, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_items = dialog.get_selected_items()
            if new_items:
                self.add_items(new_items)

    def _remove_item(self, text: str):
        """Removes an item by its text."""
        if text in self._item_set:
            self._items.remove(text)
            self._item_set.remove(text)

            # Remove the specific widget instead of rebuilding everything
            pill_to_remove = self._pill_widgets.pop(text, None)
            if pill_to_remove:
                pill_to_remove.deleteLater()

            self.items_changed.emit(self.get_items())

    def add_item(self, text: str):
        """Adds a single item to the widget."""
        self.add_items([text])

    def add_items(self, texts: List[str]):
        """Adds multiple items to the widget."""
        added_any = False
        for text in texts:
            if text and text not in self._item_set:
                self._items.append(text)
                self._item_set.add(text)
                self._add_pill_widget(text)
                added_any = True

        if added_any:
            if self.editable and self.add_btn:
                # Ensure plus button is always last
                self._ensure_plus_button()
            self.items_changed.emit(self.get_items())

    def get_items(self) -> List[str]:
        """Returns the current list of items."""
        return self._items.copy()

    def set_editable(self, editable: bool):
        """Sets the editable state of the widget."""
        if self.editable == editable:
            return

        self.editable = editable
        self._populate_items()  # Re-draw all pills to show/hide remove buttons
        if not self.editable and self.add_btn:
            self.add_btn.setVisible(False)
