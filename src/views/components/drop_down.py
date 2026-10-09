from PySide6.QtWidgets import QComboBox
from PySide6.QtCore import Qt, Signal


class ComboBox(QComboBox):
    """
    A reusable and customizable QComboBox with modern styling.

    This component encapsulates the complex stylesheet and setup logic,
    allowing for easy customization through constructor parameters.
    """

    # Custom signal emitted when the dropdown is about to be shown
    aboutToShow = Signal()

    def __init__(
        self,
        parent=None,
        items: list[str] | None = None,
        # --- Style Customization ---
        bg_color: str = "#FFFFFF",
        border_radius: int = 10,
        border_color: str = "transparent",
        border_width: int = 0,
        padding: int = 10,
        text_color: str = "#000000",
        item_bg_color: str = "#FFFFFF",
        item_selected_bg_color: str = "#56BB55",
        item_text_color: str = "#000000",
        item_selected_text_color: str = "#000000",
        down_arrow_icon: str = ":/png/png/down.png",
        up_arrow_icon: str = ":/png/png/up.png",
    ):
        """
        Initializes the StyledComboBox.

        Args:
            parent: The parent widget.
            items: A list of strings to populate the combo box initially.
            bg_color: Background color of the combo box itself.
            border_radius: Corner radius for the combo box and its dropdown view.
            padding: Left and right padding inside the combo box.
            text_color: Color of the displayed text in the combo box.
            item_bg_color: Background color of items in the dropdown list.
            item_selected_bg_color: Background color of a selected/hovered item.
            item_text_color: Text color of items in the dropdown list.
            item_selected_text_color: Text color of a selected/hovered item.
            down_arrow_icon: Path to the resource for the 'down' arrow.
            up_arrow_icon: Path to the resource for the 'up' arrow (when dropdown is open).
        """
        super().__init__(parent)

        if items:
            self.addItems(items)

        # Apply modern popup view settings
        self.view().window().setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.view().window().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Generate and set the stylesheet
        stylesheet = self._create_stylesheet(
            bg_color,
            border_radius,
            padding,
            text_color,
            item_bg_color,
            item_selected_bg_color,
            item_text_color,
            item_selected_text_color,
            down_arrow_icon,
            up_arrow_icon,
            border_color,
            border_width,
        )
        self.setStyleSheet(stylesheet)

        # Set minimum height for better visual appearance
        self.setMinimumHeight(20 + padding)

    def showPopup(self):
        """Override showPopup to emit the aboutToShow signal before showing the dropdown."""
        self.aboutToShow.emit()
        super().showPopup()

    def _create_stylesheet(
        self,
        bg_color,
        border_radius,
        padding,
        text_color,
        item_bg_color,
        item_selected_bg_color,
        item_text_color,
        item_selected_text_color,
        down_arrow_icon,
        up_arrow_icon,
        border_color,
        border_width,
    ) -> str:
        """Dynamically generates the stylesheet based on input parameters."""
        return f"""
            QComboBox {{
                background: {bg_color};
                color: {text_color};
                border-radius: {border_radius}px;
                border: {border_width}px solid {border_color};
                padding: 0px {padding}px 0px {padding}px;
            }}
            QComboBox::drop-down {{
                border-top-right-radius: {border_radius}px;
                border-bottom-right-radius: {border_radius}px;
            }}
            QComboBox::down-arrow {{
                margin-right: {padding}px;
                image: url({down_arrow_icon});
            }}
            QComboBox::down-arrow:on {{
                margin-right: {padding}px;
                image: url({up_arrow_icon});
            }}
            QComboBox QAbstractItemView {{
                background: {item_bg_color};
                border: none;
                outline: 0px;
                border-radius: {border_radius}px;
                color: {item_text_color};
            }}
            QComboBox QAbstractItemView::item {{
                background: {item_bg_color};
                color: {item_text_color};
                border: 1px solid transparent; /* for spacing */
                border-radius: {border_radius}px;
                padding: 5px {padding}px; /* Add some vertical padding */
            }}
            QComboBox QAbstractItemView::item:selected, 
            QComboBox QAbstractItemView::item:hover {{
                background: {item_selected_bg_color};
                color: {item_selected_text_color};
                border-radius: {border_radius}px;
            }}
        """
