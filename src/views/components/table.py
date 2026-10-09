import sys
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QFrame,
    QSpacerItem,
    QLineEdit,
    QComboBox,
    QScrollArea,
    QCheckBox,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import (
    Qt,
    Signal,
    QRect,
    QTimer,
    QObject,
    QEvent,
    QModelIndex,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
)
from PySide6.QtGui import (
    QFont,
    QPalette,
    QColor,
    QFontDatabase,
    QCursor,
    QPainter,
    QPen,
)
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Protocol, Type, Union
from functools import partial
from enum import Enum
import statistics
from pathlib import Path

from views.components.add_choices_widget import MutableListWidget
from views.components.drop_down import ComboBox

# --- Color Palette (Based on the provided image) ---
COLOR_WHITE = "#FFFFFF"
COLOR_OFF_WHITE = "#ECF0F0"
COLOR_LIGHT_GRAY = "#D9D9D9"
COLOR_GREEN = "#56BB55"
COLOR_DARK_TEXT = "#203532"
COLOR_RED = "#F48080"
COLOR_BLUE = "#4A90E2"
COLOR_YELLOW = "#F9E79F"

class RowColor(Enum):
    """Enum to define available custom row background colors."""

    NONE = "none"  # Represents the default/no color state
    GREEN = "green"
    RED = "red"
    BLUE = "blue"
    WHITE = "white"
    OFF_WHITE = "off_white"
    YELLOW = "yellow"


class SelectType(Enum):
    """Enum for different selection types in a SelectColumn."""

    SINGLE = "single"
    MULTIPLE = "multiple"


class ColumnType(Enum):
    """Enum for different column types"""

    INDEX = "index"
    TEXT_DATA = "text_data"
    NUMBER_DATA = "number_data"
    LIST_DATA = "list_data"
    DROPDOWN = "dropdown"
    ACTIONS = "actions"


class NumberCalculation(Enum):
    """Enum for number calculation types"""

    NONE = "none"
    SUM = "sum"
    AVERAGE = "average"
    COUNT = "count"
    MIN = "min"
    MAX = "max"


class Stringable(Protocol):
    def __str__(self) -> str: ...
@dataclass
class BaseColumnConfig:
    """Base configuration for all column types."""

    header: str
    editable: bool = False
    is_pivot: bool = False
    resizable: bool = True
    min_width: int = 80
    default_width: float = 0.15  # Represents a proportion of the total width
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter
    default_value: Any = "-"
    widget_factory: Optional[Callable[[Any, int], QWidget]] = None


@dataclass
class IndexColumnConfig(BaseColumnConfig):
    """Configuration for an index column."""

    # Indexes are typically not editable or resizable by default
    editable: bool = False
    resizable: bool = False
    default_width: float = 0.05  # Usually smaller
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter


@dataclass
class TextColumnConfig(BaseColumnConfig):
    """Configuration for a standard text column."""

    pass  # No extra attributes needed


@dataclass
class NumberColumnConfig(BaseColumnConfig):
    """Configuration for a numeric data column."""

    alignment: Qt.AlignmentFlag = (
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    calculation: NumberCalculation = NumberCalculation.NONE
    decimal_places: int = 2


@dataclass
class DropdownColumnConfig(BaseColumnConfig):
    """Configuration for a column with a dropdown/combobox."""

    options: List[str] = field(
        default_factory=lambda: ["Default"]
    )  # Use default_factory
    # Dropdowns are inherently editable if you want the user to change the value
    editable: bool = True


@dataclass
class ListDataColumnConfig(BaseColumnConfig):
    """Configuration for the mutable list"""

    data: List[Stringable] = field(default_factory=lambda: [])
    editable: bool = True

    all_available_items: List[str] = field(default_factory=list)
    items_factory: Optional[Callable[[], List[str]]] = None


@dataclass
class ActionColumnConfig(BaseColumnConfig):
    """Configuration for a column containing action buttons."""

    editable: bool = False
    resizable: bool = False
    default_width: float = 0.1


@dataclass
class SelectColumnConfig(BaseColumnConfig):
    """Configuration for a column with a checkbox for selection."""

    editable: bool = False
    resizable: bool = False
    default_width: float = 0.05
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter

    select_type: SelectType = SelectType.SINGLE
    header: str = ""


# This type alias is useful for type hinting lists of configs
ColumnConfig = Union[
    IndexColumnConfig,
    TextColumnConfig,
    NumberColumnConfig,
    DropdownColumnConfig,
    ActionColumnConfig,
    ListDataColumnConfig,
    SelectColumnConfig,
    BaseColumnConfig,
]


@dataclass
class RowContext:
    """Context information for row operations"""

    data_index: int
    group_value: str
    group_position: int


class NumberCalculator:
    """Utility class for performing calculations on number data"""

    @staticmethod
    def calculate(
        values: List[Any], calculation: NumberCalculation, decimal_places: int = 2
    ) -> str:
        if calculation == NumberCalculation.NONE:
            return ""
        numeric_values = []
        for val in values:
            try:
                if val is not None and str(val).strip() not in ["", "-"]:
                    numeric_values.append(float(val))
            except (ValueError, TypeError):
                continue
        if not numeric_values:
            return "N/A"
        try:
            if calculation == NumberCalculation.SUM:
                result = sum(numeric_values)
            elif calculation == NumberCalculation.AVERAGE:
                result = statistics.mean(numeric_values)
            elif calculation == NumberCalculation.COUNT:
                return str(len(numeric_values))
            elif calculation == NumberCalculation.MIN:
                result = min(numeric_values)
            elif calculation == NumberCalculation.MAX:
                result = max(numeric_values)
            else:
                return "N/A"
            return (
                f"{result:.{decimal_places}f}"
                if decimal_places > 0
                else str(int(result))
            )
        except Exception:
            return "Error"


class TableModel(QObject):
    """Data model to hold and manage table data, separate from the view."""

    data_changed = Signal()
    rowsInserted = Signal(QModelIndex, int, int)
    rowsRemoved = Signal(QModelIndex, int, int)
    row_added = Signal(int)
    row_removed = Signal(int)
    cell_changed = Signal(int, int, object)

    def __init__(self, data: List[List[Any]], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._data = data

    def set_data(self, data: List[List[Any]]):
        self._data = data
        self.data_changed.emit()

    def get_row_count(self) -> int:
        return len(self._data)

    def get_page_data(self, page: int, items_per_page: int) -> List[List[Any]]:
        start_index = (page - 1) * items_per_page
        end_index = start_index + items_per_page
        return self._data[start_index:end_index]

    def get_row(self, index: int) -> Optional[List[Any]]:
        return self._data[index] if 0 <= index < len(self._data) else None

    def get_column_data(self, column_index: int) -> List[Any]:
        return [row[column_index] for row in self._data if column_index < len(row)]

    def update_cell(self, row_index: int, col_index: int, value: Any):
        if 0 <= row_index < len(self._data) and 0 <= col_index < len(
            self._data[row_index]
        ):
            self._data[row_index][col_index] = value
            self.data_changed.emit()
            self.cell_changed.emit(row_index, col_index, value)

    def add_row(self, index: int, row_data: List[Any]):
        if 0 <= index <= len(self._data):
            self._data.insert(index, row_data)
            self.data_changed.emit()
            self.row_added.emit(index)

    def remove_row(self, index: int):
        if 0 <= index < len(self._data):
            del self._data[index]
            self.data_changed.emit()
            self.row_removed.emit(index)


class AddRowWidget(QWidget):
    """A widget that shows an add button when hovered and a green line when not hovered."""

    add_row_requested = Signal(RowContext)

    def __init__(self, row_context: RowContext, parent=None):
        super().__init__(parent)
        self.row_context = row_context
        # self.setFixedHeight(5)  # Initially small height when not hovered
        self.setMouseTracking(
            True
        )  # Ensure mouse events are tracked even when no button is pressed

        self.is_hovered = False

        self.initial_height = 10
        self.hover_height = 30
        self.setMinimumHeight(self.initial_height)

        self.add_button = QPushButton("+ Add Row", self)
        self.add_button.setFixedSize(80, 24)
        self.add_button.setObjectName("GreenButton")
        self.add_button.clicked.connect(self._handle_add_click)

        self.opacity_effect = QGraphicsOpacityEffect(self.add_button)
        self.add_button.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)
        self.add_button.hide()

        self.height_animation = QPropertyAnimation(self, b"minimumHeight")
        self.height_animation.setDuration(200)
        self.height_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.height_animation.valueChanged.connect(self._force_layout_update)

        self.opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_animation.setDuration(150)
        self.opacity_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.opacity_animation.finished.connect(self._on_fade_out_finished)

        self._collapse_on_click_animation = self._create_collapse_animation()
        self._collapse_on_click_animation.finished.connect(self._emit_add_request)

    def _create_collapse_animation(self) -> QParallelAnimationGroup:
        group = QParallelAnimationGroup(self)

        height_anim = QPropertyAnimation(self, b"minimumHeight")
        height_anim.setDuration(150)
        height_anim.setEndValue(self.initial_height)
        height_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        opacity_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        opacity_anim.setDuration(150)
        opacity_anim.setEndValue(0.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        group.addAnimation(height_anim)
        group.addAnimation(opacity_anim)
        return group

    def _handle_add_click(self):
        self.add_row_requested.emit(self.row_context)
        self.leaveEvent(None)

    def _emit_add_request(self):
        self.add_row_requested.emit(self.row_context)

    def _force_layout_update(self):
        if self.parentWidget() and self.parentWidget().layout():
            self.parentWidget().layout().activate()

    def _on_fade_out_finished(self):
        if self.opacity_effect.opacity() == 0.0:
            self.add_button.hide()

    def enterEvent(self, event):
        if (
            self.is_hovered
            or self._collapse_on_click_animation.state()
            == QPropertyAnimation.State.Running
        ):
            return
        self.is_hovered = True
        self.update()
        self.height_animation.stop()
        self.opacity_animation.stop()
        self._position_add_button()
        self.add_button.show()
        self.opacity_animation.setStartValue(self.opacity_effect.opacity())
        self.opacity_animation.setEndValue(1.0)
        self.opacity_animation.start()
        self.height_animation.setStartValue(self.height())
        self.height_animation.setEndValue(self.hover_height)
        self.height_animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.is_hovered:
            return
        self.is_hovered = False
        self.update()
        self.height_animation.stop()
        self.opacity_animation.stop()
        self.opacity_animation.setStartValue(self.opacity_effect.opacity())
        self.opacity_animation.setEndValue(0.0)
        self.opacity_animation.start()
        self.height_animation.setStartValue(self.height())
        self.height_animation.setEndValue(self.initial_height)
        self.height_animation.start()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        self._position_add_button()
        super().resizeEvent(event)

    def _position_add_button(self):
        btn_x = (self.width() - self.add_button.width()) // 2
        btn_y = (self.hover_height - self.add_button.height()) // 2
        self.add_button.move(btn_x, btn_y)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.is_hovered:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            line_color = QColor(COLOR_GREEN)
            line_thickness = 2
            pen = QPen(line_color, line_thickness)
            painter.setPen(pen)

            line_y = self.initial_height // 2
            painter.drawLine(0, line_y, self.width(), line_y)
            painter.end()


class EditableCell(QWidget):
    """A cell that can be edited by double-clicking."""

    value_changed = Signal(str)
    clicked = Signal()

    def __init__(
        self,
        initial_text,
        row,
        editable=True,
        alignment=Qt.AlignmentFlag.AlignLeft,
        is_number=False,
    ):
        super().__init__()
        self.editable, self.is_editing, self.is_number, self.row = (
            editable,
            False,
            is_number,
            row,
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(initial_text)
        self.label.setFont(QFont(self.font().family(), 10))
        self.label.setAlignment(alignment)
        self.label.setWordWrap(True)
        self.line_edit = QLineEdit(initial_text)
        self.line_edit.setFont(QFont(self.font().family(), 10))
        self.line_edit.setAlignment(alignment)
        self.line_edit.hide()
        self.line_edit.editingFinished.connect(self._finish_editing)
        layout.addWidget(self.label)
        layout.addWidget(self.line_edit)

    def mouseDoubleClickEvent(self, event):
        if self.editable:
            self._start_editing()
        super().mouseDoubleClickEvent(event)

    def _start_editing(self):
        self.is_editing = True
        self.label.hide()
        self.line_edit.show()
        self.line_edit.setObjectName("EditingCellLineEdit")  # form.qss
        self.line_edit.style().unpolish(self.line_edit)
        self.line_edit.style().polish(self.line_edit)
        self.line_edit.setFocus()
        self.line_edit.selectAll()

    def _finish_editing(self):
        if self.is_editing:
            new_text = self.line_edit.text()
            if self.is_number and new_text.strip():
                try:
                    float(new_text)
                except ValueError:
                    self.line_edit.setText(
                        self.label.text()
                    )  # Revert if not a valid number
                    self.is_editing = False
                    self.line_edit.hide()
                    self.label.show()
                    return
            self.label.setText(new_text)
            self.value_changed.emit(new_text)
            self.is_editing = False
            self.line_edit.hide()
            self.label.show()

    def mousePressEvent(self, event):
        self.clicked.emit()  # Emit signal for row click
        super().mousePressEvent(event)


class CalculationWidget(QWidget):
    """Widget to display column calculations"""

    def __init__(
        self,
        config: NumberColumnConfig,
        model: TableModel,
        column_index: int,
        parent=None,
    ):
        super().__init__(parent)
        self.config, self.model, self.column_index = config, model, column_index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        # No need to check config type here, it's guaranteed by the `__init__` signature
        self.calc_label = QLabel()
        self.calc_label.setObjectName("CalculationLabel")
        self.calc_label.setAlignment(config.alignment)
        layout.addWidget(self.calc_label)
        self.model.data_changed.connect(self.update_calculation)
        self.update_calculation()
        self.setObjectName("CalculationWidget")

    def update_calculation(self):
        if hasattr(self, "calc_label"):
            # We can now directly access calculation and decimal_places without error
            result = NumberCalculator.calculate(
                self.model.get_column_data(self.column_index),
                self.config.calculation,
                self.config.decimal_places,
            )
            self.calc_label.setText(
                f"{self.config.calculation.value.title()}: {result}"
            )


class ResizeHandle(QWidget):
    drag_started = Signal(int)
    dragged = Signal(int, int)
    drag_finished = Signal()

    def __init__(self, parent, column_index, min_height: int):
        super().__init__(parent)
        self.column_index = column_index
        self.setFixedWidth(5)
        self.setMinimumHeight(min_height)
        self.setCursor(Qt.CursorShape.SplitHCursor)
        self.is_dragging = False
        self.mouse_press_pos = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center_x, padding = self.width() // 2, 8
        if self.height() > padding * 2:
            line_rect = QRect(center_x - 1, padding, 2, self.height() - 2 * padding)
            painter.setBrush(QColor(COLOR_OFF_WHITE))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(line_rect, 1, 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.mouse_press_pos = event.globalPosition()
            self.drag_started.emit(self.column_index)
            event.accept()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            delta = event.globalPosition().x() - self.mouse_press_pos.x()  # type: ignore
            self.dragged.emit(self.column_index, int(delta))
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.drag_finished.emit()
            event.accept()


class HeaderWidget(QWidget):
    """A fixed widget for displaying the table header and resize handles."""

    drag_started = Signal(int)
    dragged = Signal(int, int)
    drag_finished = Signal()

    def __init__(
        self,
        column_configs: List[ColumnConfig],
        column_widths: List[float],
        header_height: int,
        parent=None,
    ):
        super().__init__(parent)
        self.column_configs, self.column_widths, self.header_height = (
            column_configs,
            column_widths,
            header_height,
        )
        self.setFixedHeight(self.header_height)
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(0)
        self._build_header()

    def _build_header(self):
        for i, config in enumerate(self.column_configs):
            label = QLabel(config.header)
            label.setFont(QFont(self.font().family(), 10, QFont.Weight.DemiBold))
            label.setMinimumHeight(self.header_height)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if i == 0:
                label.setObjectName("TableHeaderFirst")
            elif i == len(self.column_configs) - 1:
                label.setObjectName("TableHeaderLast")
            else:
                label.setObjectName("TableHeader")

            self.grid_layout.addWidget(label, 0, i * 2)

            # Add resize handle between columns, except for the last one
            if i < len(self.column_configs) - 1 and config.resizable:
                handle = ResizeHandle(self, i, self.header_height)
                handle.drag_started.connect(self.drag_started)
                handle.dragged.connect(self.dragged)
                handle.drag_finished.connect(self.drag_finished)
                self.grid_layout.addWidget(handle, 0, i * 2 + 1)
                self.grid_layout.setColumnStretch(
                    i * 2 + 1, 0
                )  # Ensure handle doesn't take up space

        # Set column stretches based on configured widths
        stretch_multiplier = 1000
        for i, width_percentage in enumerate(self.column_widths):
            self.grid_layout.setColumnStretch(
                i * 2, int(width_percentage * stretch_multiplier)
            )
            self.grid_layout.setColumnMinimumWidth(
                i * 2, self.column_configs[i].min_width
            )

        # Add a stretch item at the end to push columns to the left
        self.grid_layout.setColumnStretch(len(self.column_configs) * 2, 1)

    def set_column_stretch(self, column_index: int, stretch: int):
        # Apply stretch to the actual data column (every other column in the grid layout)
        self.grid_layout.setColumnStretch(column_index * 2, stretch)


class SelectCell(QWidget):
    """A cell widget with a selectable radio button or checkbox."""

    toggled = Signal(int, bool)

    def __init__(
        self, row_index: int, is_selected: bool, select_type: SelectType, parent=None
    ):
        super().__init__(parent)
        self.row_index = row_index
        self._is_selected = is_selected
        self.select_type = select_type
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(24, 24)
        self.setMaximumSize(48, 48)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggled.emit(self.row_index, not self._is_selected)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect_size = 16
        x, y = (self.width() - rect_size) // 2, (self.height() - rect_size) // 2
        checkbox_rect = QRect(x, y, rect_size, rect_size)
        if self.select_type == SelectType.SINGLE:
            if self._is_selected:
                painter.setBrush(QColor(COLOR_BLUE))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(checkbox_rect)
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(COLOR_LIGHT_GRAY), 2))
                painter.drawEllipse(checkbox_rect)
        else:
            if self._is_selected:
                painter.setBrush(QColor(COLOR_BLUE))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(checkbox_rect, 4, 4)
                pen = QPen(QColor(COLOR_WHITE), 2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(
                    checkbox_rect.left() + 4,
                    checkbox_rect.center().y(),
                    checkbox_rect.center().x(),
                    checkbox_rect.bottom() - 4,
                )
                painter.drawLine(
                    checkbox_rect.center().x(),
                    checkbox_rect.bottom() - 4,
                    checkbox_rect.right() - 4,
                    checkbox_rect.top() + 5,
                )
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(COLOR_LIGHT_GRAY), 2))
                painter.drawRoundedRect(checkbox_rect, 4, 4)


class DataTableWidget(QWidget):
    """
    A highly configurable and performant data table widget.

    Features:
    - Fixed header with resizable columns.
    - Pagination for handling large datasets.
    - Grouping of rows based on a 'pivot' column.
    - Support for various column types (text, number, dropdown, actions, etc.).
    - Optional row selection (single or multiple).
    - Optional calculation footers for numeric columns.
    - Animated "Add Row" functionality within groups.

    Signals:
    - selection_changed(list[int]): Emitted when the set of selected rows changes.
                                     Provides a list of absolute row indices.
    - add_row_requested(RowContext): Emitted when the user clicks the animated '+'
                                     button to add a row within a group.
    - add_new_row_clicked(): Emitted when the main 'Add' button in the footer is clicked.
    - delete_requested(int): Emitted when a delete action is triggered for a row.
                             Provides the absolute row index.
    - cell_changed(int, int, Any): Emitted when a cell's value is changed by the user.
                                   Provides (row_index, col_index, new_value).
    - page_changed(int): Emitted when the user navigates to a different page.
    """

    selection_changed = Signal(list)
    add_row_requested = Signal(RowContext)
    add_new_row_clicked = Signal()
    delete_requested = Signal(int)
    cell_changed = Signal(int, int, object)
    page_changed = Signal(int)

    def __init__(
        self,
        column_configs: List[ColumnConfig],
        model: TableModel,
        items_per_page: int = 50,
        item_height: int = 40,
        header_height: int = 60,
        show_calculations: bool = False,
        show_add_button: bool = False,
        show_animated_add_row: bool = False,
        highlight_selected_row: bool = False,
        parent: Optional[QWidget] = None,
        custom_buttons: List[QPushButton] = [],
    ):
        super().__init__(parent)
        self.column_configs = column_configs
        self.model = model
        self.items_per_page = items_per_page
        self.item_height = item_height
        self.header_height = header_height
        self.show_calculations = show_calculations
        self.show_add_button = show_add_button
        self.show_animated_add_row = show_animated_add_row
        self.highlight_selected_row = highlight_selected_row
        self.custom_buttons = custom_buttons

        # --- State ---
        self.row_colors: Dict[int, RowColor] = {}
        self.current_page = 1
        self.total_pages = 1
        self.drag_start_percentages: Optional[List[float]] = None
        self.auto_edit_row_index = -1
        self.selected_row_index = -1  # For single selection
        self.selected_row_indices: set[int] = set()  # For multiple selection

        # --- Configuration derived from column_configs ---
        self._configure_from_configs()

        # --- Widget Factories ---
        self._cell_widget_factories: Dict[Type[BaseColumnConfig], Callable] = {
            SelectColumnConfig: self._create_select_cell,
            IndexColumnConfig: self._create_index_cell,
            TextColumnConfig: self._create_text_cell,
            NumberColumnConfig: self._create_number_cell,
            DropdownColumnConfig: self._create_dropdown_cell,
            ListDataColumnConfig: self._create_list_data_cell,
            ActionColumnConfig: self._create_action_cell,
            BaseColumnConfig: self._create_base_cell,
        }

        # --- UI Initialization ---
        self._init_ui()
        self.model.data_changed.connect(self._on_model_data_changed)
        self._on_model_data_changed()  # Initial build

    def _configure_from_configs(self):
        """Sets up internal configuration based on the provided column configs."""
        # Selection mode
        self.select_column_config = next(
            (c for c in self.column_configs if isinstance(c, SelectColumnConfig)), None
        )
        self.selection_mode = (
            self.select_column_config.select_type
            if self.select_column_config
            else SelectType.SINGLE
        )

        # Pivot column index
        self.pivot_column_index = next(
            (i for i, cfg in enumerate(self.column_configs) if cfg.is_pivot), None
        )

        # Calculate initial column widths, ensuring they sum to 1
        total_percentage = sum(c.default_width for c in self.column_configs)
        self.column_widths = [
            (
                (c.default_width / total_percentage)
                if total_percentage > 0
                else (1.0 / len(self.column_configs))
            )
            for c in self.column_configs
        ]

    # --- Public API ---

    def get_selected_row_indices(self) -> List[int]:
        """Returns a sorted list of absolute indices of the selected rows."""
        if self.selection_mode == SelectType.SINGLE:
            return [self.selected_row_index] if self.selected_row_index != -1 else []
        return sorted(list(self.selected_row_indices))

    def clear_selection(self):
        """Clears all row selections."""
        self.selected_row_index = -1
        self.selected_row_indices.clear()
        self.selection_changed.emit([])
        self._rebuild_table()

    def set_selection(self, row_indices: List[int]):
        """Programmatically sets the selected rows."""
        if not self.highlight_selected_row or not self.select_column_config:
            return

        self.clear_selection()
        max_index = self.model.get_row_count() - 1
        valid_indices = {idx for idx in row_indices if 0 <= idx <= max_index}

        if not valid_indices:
            return

        if self.selection_mode == SelectType.SINGLE:
            self.selected_row_index = next(iter(valid_indices))
        else:
            self.selected_row_indices = valid_indices

        self.selection_changed.emit(self.get_selected_row_indices())
        self._rebuild_table()

    def set_row_color(self, row_index: int, color: RowColor):
        """
        Sets a custom background color for a specific row.
        """
        if color != RowColor.NONE:
            # If a specific color is provided, add or update it.
            self.row_colors[row_index] = color
        elif row_index in self.row_colors:
            # If the color is RowColor.NONE, remove the entry.
            del self.row_colors[row_index]

        # Trigger a rebuild to apply the visual change.
        self._rebuild_table()

    def set_auto_edit_row(self, row_index: int):
        """
        Sets a row to enter edit mode automatically on the next table rebuild.
        Useful after adding a new row.
        """
        self.auto_edit_row_index = row_index

    # --- UI Initialization ---

    def _init_ui(self):
        """Initializes the main layout and sub-widgets."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        self.header_widget = HeaderWidget(
            self.column_configs, self.column_widths, self.header_height
        )
        self.header_widget.drag_started.connect(self._on_drag_start)
        self.header_widget.dragged.connect(self._on_column_resized)
        self.header_widget.drag_finished.connect(self._on_drag_finished)

        # Scroll Area for Data
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.data_container = QWidget()
        self.data_grid_layout = QGridLayout(self.data_container)
        self.data_grid_layout.setContentsMargins(0, 0, 0, 0)
        self.data_grid_layout.setSpacing(0)
        self.data_grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.data_container)

        # Pagination Footer
        self.pagination_container = QWidget()
        self.pagination_container.setObjectName("pagination-container")
        self.pagination_layout = QHBoxLayout(self.pagination_container)
        self.pagination_layout.setContentsMargins(20, 20, 20, 20)
        self._setup_pagination_controls()

        main_layout.addWidget(self.header_widget)
        main_layout.addWidget(self.scroll_area)
        main_layout.addWidget(self.pagination_container)

    # --- Table Rebuilding Logic ---

    def _on_model_data_changed(self):
        """Responds to changes in the data model."""
        count = self.model.get_row_count()
        self.total_pages = (
            (count + self.items_per_page - 1) // self.items_per_page if count > 0 else 1
        )
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages
        self._rebuild_table()
        self._update_pagination_display()

    def _rebuild_table(self):
        """Coordinates the process of clearing and repopulating the data grid."""
        self._clear_grid_layout()

        start_index = (self.current_page - 1) * self.items_per_page
        page_data = self.model.get_page_data(self.current_page, self.items_per_page)
        grouped_data = self._group_data_by_pivot(page_data, start_index)

        self._build_rows(grouped_data)
        if self.show_calculations:
            self._build_calculation_footer()

        self._update_grid_stretch()
        # Add a final spacer to push all content up
        spacer = QSpacerItem(
            10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.data_grid_layout.addItem(spacer)

    def _clear_grid_layout(self):
        """Removes all widgets from the data grid layout."""
        while self.data_grid_layout.count():
            item = self.data_grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build_rows(self, grouped_data):
        """Populates the grid layout with rows of data."""
        grid_row_idx = 0
        for group_value, group_rows in grouped_data:
            group_size = len(group_rows)
            for row_in_group_idx, (abs_row_idx, row_data) in enumerate(group_rows):
                self._create_and_add_row_widgets(
                    grid_row_idx, abs_row_idx, row_data, row_in_group_idx, group_size
                )

            grid_row_idx += group_size
            if self.pivot_column_index is not None and self.show_animated_add_row:
                last_row_in_group_abs_idx = group_rows[-1][0]
                row_context = RowContext(
                    last_row_in_group_abs_idx, str(group_value), row_in_group_idx
                )
                add_widget = AddRowWidget(row_context)
                add_widget.add_row_requested.connect(self.add_row_requested)
                self.data_grid_layout.addWidget(
                    add_widget, grid_row_idx, 0, 1, len(self.column_configs)
                )
                grid_row_idx += 1

    def _create_and_add_row_widgets(
        self, grid_row_idx, abs_row_idx, row_data, row_in_group_idx, group_size
    ):
        """Creates all cell widgets for a single row and adds them to the grid."""
        is_selected = self._is_row_selected(abs_row_idx)

        for col_idx, config in enumerate(self.column_configs):
            if config.is_pivot and row_in_group_idx > 0:
                continue

            cell_data = (
                row_data[col_idx] if col_idx < len(row_data) else config.default_value
            )
            content_widget = self._create_cell_widget(
                config, cell_data, abs_row_idx, col_idx
            )

            # Auto-enter edit mode if requested
            if abs_row_idx == self.auto_edit_row_index and isinstance(
                content_widget, EditableCell
            ):
                QTimer.singleShot(0, content_widget._start_editing)

            container = self._create_cell_container(
                content_widget, is_selected, grid_row_idx, abs_row_idx
            )
            row_span = group_size if config.is_pivot and row_in_group_idx == 0 else 1

            self.data_grid_layout.addWidget(
                container, grid_row_idx + row_in_group_idx, col_idx, row_span, 1
            )

        if abs_row_idx == self.auto_edit_row_index:
            self.auto_edit_row_index = -1

    def _create_cell_container(
        self,
        content_widget: QWidget,
        is_selected: bool,
        visual_row_idx: int,
        abs_row_idx: int,
    ) -> QWidget:
        """Wraps a content widget in a styled container for the grid."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 2, 5, 2)

        # Special handling for list widgets to align top
        if isinstance(content_widget, MutableListWidget):
            layout.addWidget(content_widget, 1, Qt.AlignmentFlag.AlignTop)
        else:
            layout.addWidget(content_widget)

        container.setMinimumHeight(self.item_height)

        custom_color_enum = self.row_colors.get(abs_row_idx)

        # Check if a custom color is set and is not the default.
        if custom_color_enum and custom_color_enum != RowColor.NONE:
            container.setObjectName(f"RowColor_{custom_color_enum.value}")
        elif self.highlight_selected_row and is_selected:
            container.setObjectName("SelectedRow")
        else:
            container.setObjectName("RowEven" if visual_row_idx % 2 == 0 else "RowOdd")
        # Force stylesheet re-evaluation
        container.style().unpolish(container)
        container.style().polish(container)

        return container

    def _build_calculation_footer(self):
        """Adds the calculation summary row to the bottom of the grid."""
        footer_row = self.data_grid_layout.rowCount()
        for i, config in enumerate(self.column_configs):
            if (
                isinstance(config, NumberColumnConfig)
                and config.calculation != NumberCalculation.NONE
            ):
                calc_widget = CalculationWidget(config, self.model, i)
                self.data_grid_layout.addWidget(calc_widget, footer_row, i)

    def _update_grid_stretch(self):
        """Applies the current column widths and minimums to the grid layout."""
        stretch_multiplier = 1000
        for i, (width_percentage, config) in enumerate(
            zip(self.column_widths, self.column_configs)
        ):
            stretch = int(width_percentage * stretch_multiplier)
            self.data_grid_layout.setColumnStretch(i, stretch)
            self.data_grid_layout.setColumnMinimumWidth(i, config.min_width)

    # --- Cell Widget Factory Methods ---

    def _create_cell_widget(
        self, config: ColumnConfig, data: Any, row_idx: int, col_idx: int
    ) -> QWidget:
        """Creates a cell widget based on the column configuration."""
        if config.widget_factory:
            widget = config.widget_factory(data, row_idx)
            if not isinstance(widget, QWidget):
                raise TypeError("widget_factory must return a QWidget")
            return widget

        factory_method = self._cell_widget_factories.get(
            type(config), self._create_base_cell
        )
        return factory_method(config, data, row_idx, col_idx)

    def _create_base_cell(
        self, config: BaseColumnConfig, data: Any, row_idx: int, col_idx: int
    ) -> QWidget:
        cell = QLabel(str(data))
        cell.setAlignment(config.alignment)
        cell.setWordWrap(True)
        return cell

    def _create_select_cell(
        self, config: SelectColumnConfig, data: Any, row_idx: int, col_idx: int
    ) -> QWidget:
        is_selected = self._is_row_selected(row_idx)
        cell = SelectCell(row_idx, is_selected, config.select_type)
        cell.toggled.connect(self._on_select_toggled)
        return cell

    def _create_index_cell(
        self, config: IndexColumnConfig, data: Any, row_idx: int, col_idx: int
    ) -> QWidget:
        # Index cell always shows the absolute row index + 1, not the data from the model.
        return EditableCell(
            str(row_idx + 1), row_idx, editable=False, alignment=config.alignment
        )

    def _create_text_cell(
        self, config: TextColumnConfig, data: Any, row_idx: int, col_idx: int
    ) -> QWidget:
        cell = EditableCell(
            str(data), row_idx, editable=config.editable, alignment=config.alignment
        )
        if config.editable:
            cell.value_changed.connect(
                lambda value: self.model.update_cell(row_idx, col_idx, value)
            )
            cell.value_changed.connect(
                lambda value: self.cell_changed.emit(row_idx, col_idx, value)
            )
        return cell

    def _create_number_cell(
        self, config: NumberColumnConfig, data: Any, row_idx: int, col_idx: int
    ) -> QWidget:
        cell = EditableCell(
            str(data),
            row_idx,
            editable=config.editable,
            alignment=config.alignment,
            is_number=True,
        )
        if config.editable:
            cell.value_changed.connect(
                lambda value: self.model.update_cell(row_idx, col_idx, value)
            )
            cell.value_changed.connect(
                lambda value: self.cell_changed.emit(row_idx, col_idx, value)
            )
        # Style based on value
        try:
            num_val = float(data) if data not in [None, "", "-"] else 0
            if num_val < 0:
                cell.label.setObjectName("NumberNegative")
            elif num_val > 0:
                cell.label.setObjectName("NumberPositive")
        except (ValueError, TypeError):
            pass
        return cell

    def _create_dropdown_cell(
        self, config: DropdownColumnConfig, data: Any, row_idx: int, col_idx: int
    ) -> QWidget:
        if not config.editable:
            return self._create_base_cell(config, data, row_idx, col_idx)

        combo = ComboBox(
            items=config.options
        )  # Assuming ComboBox has sensible defaults
        combo.setMinimumHeight(28)
        combo.blockSignals(True)
        combo.setCurrentText(str(data))
        combo.blockSignals(False)
        combo.currentTextChanged.connect(
            lambda text: self.model.update_cell(row_idx, col_idx, text)
        )
        return combo

    def _create_list_data_cell(
        self, config: ListDataColumnConfig, data: Any, row_idx: int, col_idx: int
    ) -> QWidget:
        items = data if isinstance(data, list) else []
        list_widget = MutableListWidget(
            items=items,
            editable=config.editable,
            all_available_items=config.all_available_items,
            items_factory=config.items_factory,
        )
        if config.editable:
            list_widget.items_changed.connect(
                lambda new_items: self.model.update_cell(row_idx, col_idx, new_items)
            )
        return list_widget

    def _create_action_cell(
        self, config: ActionColumnConfig, data: Any, row_idx: int, col_idx: int
    ) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        delete_btn = QPushButton("Delete")
        delete_btn.setObjectName("RedButton")
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(row_idx))
        layout.addWidget(delete_btn)
        return container

    # --- Data Grouping ---

    def _group_data_by_pivot(self, data, start_index=0):
        """Groups rows based on the pivot column if one is defined."""
        if self.pivot_column_index is None:
            return [(None, [(start_index + i, row) for i, row in enumerate(data)])]

        groups = []
        current_group = []
        current_pivot_value = None

        for i, row in enumerate(data):
            absolute_index = start_index + i
            pivot_value = row[self.pivot_column_index]
            if pivot_value != current_pivot_value:
                if current_group:
                    groups.append((current_pivot_value, current_group))
                current_pivot_value = pivot_value
                current_group = []
            current_group.append((absolute_index, row))

        if current_group:
            groups.append((current_pivot_value, current_group))
        return groups

    # --- Event Handlers & Slots ---

    def _on_select_toggled(self, row_index: int, is_checked: bool):
        """Handles clicks on selection cells (checkboxes/radio buttons)."""
        if not self.highlight_selected_row or not self.select_column_config:
            return

        if self.selection_mode == SelectType.SINGLE:
            self.selected_row_index = row_index if is_checked else -1
        else:  # MULTIPLE
            if is_checked:
                self.selected_row_indices.add(row_index)
            else:
                self.selected_row_indices.discard(row_index)

        self.selection_changed.emit(self.get_selected_row_indices())
        self._rebuild_table()

    def _is_row_selected(self, row_index: int) -> bool:
        """Checks if a given row index is currently selected."""
        if self.selection_mode == SelectType.SINGLE:
            return row_index == self.selected_row_index
        return row_index in self.selected_row_indices

    # --- Column Resizing ---

    def _on_drag_start(self, index: int):
        self.drag_start_percentages = list(self.column_widths)

    def _on_drag_finished(self):
        self.drag_start_percentages = None

    def _on_column_resized(self, index: int, dx: int):
        if self.drag_start_percentages is None:
            return

        table_width = self.data_container.width()
        if table_width <= 0:
            return

        left_col, right_col = index, index + 1
        if right_col >= len(self.column_configs):
            return

        left_min_px = self.column_configs[left_col].min_width
        right_min_px = self.column_configs[right_col].min_width
        left_min_perc, right_min_perc = (
            left_min_px / table_width,
            right_min_px / table_width,
        )

        delta_perc = dx / table_width
        new_left = self.drag_start_percentages[left_col] + delta_perc
        new_right = self.drag_start_percentages[right_col] - delta_perc

        # Enforce minimum widths
        if new_left < left_min_perc:
            new_right -= left_min_perc - new_left
            new_left = left_min_perc
        elif new_right < right_min_perc:
            new_left -= right_min_perc - new_right
            new_right = right_min_perc

        # Prevent columns from collapsing completely
        if new_left < 0 or new_right < 0:
            return

        self.column_widths[left_col], self.column_widths[right_col] = (
            new_left,
            new_right,
        )

        stretch_multiplier = 1000
        left_stretch = int(new_left * stretch_multiplier)
        right_stretch = int(new_right * stretch_multiplier)

        self.header_widget.set_column_stretch(left_col, left_stretch)
        self.header_widget.set_column_stretch(right_col, right_stretch)
        self.data_grid_layout.setColumnStretch(left_col, left_stretch)
        self.data_grid_layout.setColumnStretch(right_col, right_stretch)

    # --- Pagination ---

    def _setup_pagination_controls(self):
        if self.show_add_button:
            self.add_button = QPushButton("Add")
            self.add_button.setObjectName("GreenButton")
            self.add_button.clicked.connect(self.add_new_row_clicked)
            self.pagination_layout.addWidget(self.add_button)
        
        if self.custom_buttons:
            for button in self.custom_buttons:
                self.pagination_layout.addWidget(button)

        self.prev_button = QPushButton("← Previous")
        self.prev_button.setObjectName("PageNavButton")
        self.prev_button.clicked.connect(self._prev_page)

        self.next_button = QPushButton("Next →")
        self.next_button.setObjectName("PageNavButton")
        self.next_button.clicked.connect(self._next_page)

        self.page_buttons_widget = QWidget()
        self.page_buttons_layout = QHBoxLayout(self.page_buttons_widget)
        self.page_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.page_buttons_layout.setSpacing(5)

        self.pagination_layout.addStretch(1)
        self.pagination_layout.addWidget(self.prev_button)
        self.pagination_layout.addWidget(self.page_buttons_widget)
        self.pagination_layout.addWidget(self.next_button)

    def _update_pagination_display(self):
        while self.page_buttons_layout.count():
            child = self.page_buttons_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for page in self._generate_page_list():
            if isinstance(page, int):
                btn_name = (
                    "ActivePageButton" if page == self.current_page else "PageButton"
                )
                btn = QPushButton(str(page))
                btn.setObjectName(btn_name)
                btn.setFixedSize(32, 32)
                if page != self.current_page:
                    btn.clicked.connect(partial(self._go_to_page, page))
                self.page_buttons_layout.addWidget(btn)
            else:
                self.page_buttons_layout.addWidget(QLabel("..."))

        self.prev_button.setEnabled(self.current_page > 1)
        self.next_button.setEnabled(self.current_page < self.total_pages)

    def _generate_page_list(self):
        t, c = self.total_pages, self.current_page
        if t <= 7:
            return list(range(1, t + 1))
        if c < 5:
            return [1, 2, 3, 4, 5, "...", t]
        if c > t - 4:
            return [1, "...", t - 4, t - 3, t - 2, t - 1, t]
        return [1, "...", c - 1, c, c + 1, "...", t]

    def _go_to_page(self, page_num):
        self.current_page = page_num
        self.page_changed.emit(self.current_page)
        self._rebuild_table()
        self._update_pagination_display()

    def _next_page(self):
        if self.current_page < self.total_pages:
            self._go_to_page(self.current_page + 1)

    def _prev_page(self):
        if self.current_page > 1:
            self._go_to_page(self.current_page - 1)
