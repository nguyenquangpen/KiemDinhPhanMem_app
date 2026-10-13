from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional, Sequence, Union

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from views.components.drop_down import ComboBox


class InputType(Enum):
    TEXT = "text"
    DROPDOWN = "dropdown"
    TRUE_FALSE = "true_false"


@dataclass
class InputCardConfig:
    label: str
    input_type: InputType  # Enforced enum
    placeholder: Optional[str] = None
    default: Optional[Union[str, bool]] = None
    options: List[str] = field(default_factory=list)  # For dropdown
    options_factory: Optional[Callable[[], List[str]]] = None


class InputField(QWidget):
    def __init__(
        self,
        config: Union[InputCardConfig, dict],
        parent=None,
        input_font_size: int = 14,
        label_font_size: int = 8,
    ):
        super().__init__(parent)

        # Allow passing dict for convenience
        if isinstance(config, dict):
            config["input_type"] = InputType(
                config["input_type"]
            )  # Convert string to Enum
            config = InputCardConfig(**config)
        self.config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Label
        self.label = QLabel(config.label)
        self.label.setObjectName("InputFieldLabel")
        self.label.setAlignment(
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft
        )
        layout.addWidget(self.label)

        # Input widget based on type
        input_type = config.input_type
        if input_type == InputType.TEXT:
            self.input_widget = QLineEdit()
            self.input_widget.setObjectName("InputFieldText")
            self.input_widget.setPlaceholderText(config.placeholder or "")
            self.input_widget.setText(str(config.default or ""))

        elif input_type in [InputType.DROPDOWN, InputType.TRUE_FALSE]:
            self.input_widget = ComboBox()

            if input_type == InputType.DROPDOWN:
                dropdown_options = []
                if config.options and config.options_factory:
                    raise ValueError(
                        f"For '{config.label}', provide 'options' or 'options_factory', not both."
                    )

                if config.options_factory:
                    # Initial population
                    dropdown_options = config.options_factory()
                    # Connect to refresh options when dropdown is about to be shown
                    self.input_widget.aboutToShow.connect(
                        self._refresh_dropdown_options
                    )
                elif config.options:
                    dropdown_options = config.options

                self.input_widget.addItems(dropdown_options)
                if config.default in dropdown_options:
                    self.input_widget.setCurrentText(str(config.default))

            else:
                self.input_widget.addItems(["True", "False"])
                default_value = (
                    "True" if config.default in [True, "True", "true", 1] else "False"
                )
                self.input_widget.setCurrentText(default_value)

        else:
            raise ValueError(f"Unsupported input_type: {input_type}")

        layout.addWidget(self.input_widget)

    def _refresh_dropdown_options(self):
        """Refresh dropdown options by calling the factory function"""
        if (
            self.config.input_type == InputType.DROPDOWN
            and self.config.options_factory
            and isinstance(self.input_widget, QComboBox)
        ):

            # Store current selection
            current_text = self.input_widget.currentText()

            # Clear and repopulate
            self.input_widget.clear()
            new_options = self.config.options_factory()
            self.input_widget.addItems(new_options)

            # Restore selection if it still exists
            if current_text in new_options:
                self.input_widget.setCurrentText(current_text)

    def get_value(self):
        t = self.config.input_type
        if t == InputType.TEXT:
            if isinstance(self.input_widget, QLineEdit):
                return self.input_widget.text()
        elif t == InputType.DROPDOWN:
            if isinstance(self.input_widget, QComboBox):
                return self.input_widget.currentText()
        elif t == InputType.TRUE_FALSE:
            if isinstance(self.input_widget, QComboBox):
                return self.input_widget.currentText() == "True"


class InputCard(QWidget):
    data_changed = Signal(dict)
    save_requested = Signal(dict)

    def __init__(
        self,
        configs: Sequence[Union[InputCardConfig, dict]],
        parent: Optional[QWidget] = None,
        save_button_text="Save",
        field_spacing: int = 14,
        field_height: Optional[int] = 64,
        input_font_size: int = 10,
        label_font_size: int = 8,
        min_w: Optional[int] = None,
        max_w: Optional[int] = None,
        min_h: Optional[int] = None,
        max_h: Optional[int] = None,
    ):
        super().__init__(parent)
        self.save_button_text = save_button_text

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # 👉 Inner styled box container
        self.box = QWidget()
        self.box.setObjectName("InputCardBox")
        self.box_layout = QVBoxLayout(self.box)
        self.box_layout.setContentsMargins(10, 10, 10, 10)
        self.box_layout.setSpacing(field_spacing)

        self.fields: List[InputField] = []

        for config in configs:
            field = InputField(
                config, input_font_size=input_font_size, label_font_size=label_font_size
            )
            self.fields.append(field)
            self.box_layout.addWidget(field)
            if field_height is not None:
                field.setFixedHeight(field_height)
            # Signal connections
            if field.config.input_type == InputType.TEXT and isinstance(
                field.input_widget, QLineEdit
            ):
                field.input_widget.textChanged.connect(self._emit_data_changed)
            elif field.config.input_type in [
                InputType.DROPDOWN,
                InputType.TRUE_FALSE,
            ] and isinstance(field.input_widget, QComboBox):
                field.input_widget.currentTextChanged.connect(self._emit_data_changed)

        # Save button layout
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addStretch()

        self.SaveButton = QPushButton(self.save_button_text)
        self.SaveButton.setMinimumSize(QSize(120, 38))
        self.SaveButton.setObjectName("PrimaryButton")
        self.SaveButton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.SaveButton.clicked.connect(self._on_save_clicked)

        button_layout.addWidget(self.SaveButton)
        self.box_layout.addLayout(button_layout)

        # Add styled box to outer layout
        outer_layout.addWidget(self.box)

        # Apply size constraints to the InputCard widget itself
        if min_w is not None:
            self.setMinimumWidth(min_w)
        if max_w is not None:
            self.setMaximumWidth(max_w)
        if min_h is not None:
            self.setMinimumHeight(min_h)
        if max_h is not None:
            self.setMaximumHeight(max_h)

    def _emit_data_changed(self):
        self.data_changed.emit(self.get_data())

    def _on_save_clicked(self):
        self.save_requested.emit(self.get_data())

    def get_data(self) -> dict:
        return {
            input_field.config.label: input_field.get_value()
            for input_field in self.fields
        }

    def set_data(self, data: dict):
        for input_field in self.fields:
            label = input_field.config.label
            if label in data:
                val = data[label]
                if input_field.config.input_type == InputType.TEXT and isinstance(
                    input_field.input_widget, QLineEdit
                ):
                    input_field.input_widget.setText(str(val))
                elif input_field.config.input_type == InputType.DROPDOWN and isinstance(
                    input_field.input_widget, QComboBox
                ):
                    input_field.input_widget.setCurrentText(str(val))
                elif (
                    input_field.config.input_type == InputType.TRUE_FALSE
                    and isinstance(input_field.input_widget, QComboBox)
                ):
                    input_field.input_widget.setCurrentText("True" if val else "False")

    def clear_data(self):
        for input_field in self.fields:
            if input_field.config.input_type == InputType.TEXT and isinstance(
                input_field.input_widget, QLineEdit
            ):
                input_field.input_widget.clear()
            elif input_field.config.input_type in [
                InputType.DROPDOWN,
                InputType.TRUE_FALSE,
            ] and isinstance(input_field.input_widget, QComboBox):
                input_field.input_widget.setCurrentIndex(-1)

    def update_dropdown_options(self, label: str, new_options: List[str]):
        for field in self.fields:
            if field.config.label == label:
                if isinstance(field.input_widget, QComboBox):
                    current_value = field.input_widget.currentText()

                    field.input_widget.clear()
                    field.input_widget.addItems(new_options)

                    index = field.input_widget.findText(current_value)
                    if index != -1:
                        field.input_widget.setCurrentIndex(index)
                    elif new_options:
                        field.input_widget.setCurrentIndex(0)
                    break