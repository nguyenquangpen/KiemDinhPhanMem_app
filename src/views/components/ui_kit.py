"""Small building blocks for the redesigned UI (cards, headers, buttons, badges).

All colours come from ``asset/*.qss`` through object names; this module only
creates widgets and sets object names / properties.
"""

from typing import Callable, Iterable, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from asset import tokens
from views.components import icons

# Button variants -> (objectName, icon colour)
_BUTTON_VARIANTS = {
    "primary": ("PrimaryButton", "#FFFFFF"),
    "secondary": ("SecondaryButton", tokens.SECONDARY_TEXT),
    "neutral": ("NeutralButton", tokens.TEXT),
    "danger": ("DangerButton", tokens.DANGER_TEXT),
    "ghost-danger": ("GhostDangerButton", tokens.DANGER_TEXT),
}


def repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after changing an object name or dynamic property."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def button(
    text: str,
    variant: str = "neutral",
    icon_name: Optional[str] = None,
    icon_right: bool = False,
    small: bool = False,
    on_click: Optional[Callable] = None,
    parent: Optional[QWidget] = None,
) -> QPushButton:
    object_name, icon_color = _BUTTON_VARIANTS[variant]
    btn = QPushButton(text, parent)
    btn.setObjectName(object_name)
    btn.setProperty("size", "small" if small else "normal")
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    if icon_name:
        btn.setIcon(icons.icon(icon_name, icon_color, 16, 2))
        btn.setIconSize(QSize(14 if small else 16, 14 if small else 16))
        if icon_right:
            btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


class FixedSizeButton(QPushButton):
    """QPushButton that keeps its fixed size even when QSS sets min-height: 0."""

    def __init__(self, size: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._size = QSize(size, size)
        self.setFixedSize(self._size)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return self._size

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return self._size


def icon_button(
    icon_name: str,
    tooltip: str,
    danger: bool = False,
    on_click: Optional[Callable] = None,
    parent: Optional[QWidget] = None,
) -> QPushButton:
    """32x32 square button used for row actions (edit, delete, history...)."""
    btn = FixedSizeButton(32, parent)
    btn.setObjectName("IconButton")
    btn.setProperty("danger", "true" if danger else "false")
    btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    color = tokens.DANGER_ICON if danger else tokens.TEXT_MUTED
    btn.setIcon(icons.icon(icon_name, color, 16))
    btn.setIconSize(QSize(16, 16))
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def label(text: str = "", role: str = "BodyText", wrap: bool = False, align=None) -> QLabel:
    """A QLabel whose look comes from QSS via its object name.

    Roles: PageTitle, PageSubtitle, CardTitle, CardEyebrow, HeroNumber, BigName,
    BodyText, MutedText, FieldLabel, SectionLabel, StatValue.
    """
    lbl = QLabel(text)
    lbl.setObjectName(role)
    lbl.setWordWrap(wrap)
    if align is not None:
        lbl.setAlignment(align)
    return lbl


def badge(text: str, tone: str = "none") -> QLabel:
    """Pill-shaped status label. tone: ok | ng | run | none | info."""
    lbl = QLabel(text)
    lbl.setObjectName("Badge")
    lbl.setProperty("tone", tone)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return lbl


def set_badge(lbl: QLabel, text: str, tone: str) -> None:
    lbl.setText(text)
    lbl.setProperty("tone", tone)
    repolish(lbl)


def divider(dotted: bool = False) -> QFrame:
    line = QFrame()
    line.setObjectName("DottedDivider" if dotted else "Divider")
    line.setFixedHeight(2 if dotted else 1)
    return line


def progress(value: int = 0, tone: str = "ok") -> QProgressBar:
    bar = QProgressBar()
    bar.setObjectName("MiniProgress")
    bar.setProperty("tone", tone)
    bar.setTextVisible(False)
    bar.setRange(0, 100)
    bar.setValue(value)
    bar.setFixedHeight(6)
    return bar


class Card(QFrame):
    """White card with a thin border. Use ``body`` (a QVBoxLayout) to add content."""

    def __init__(self, parent: Optional[QWidget] = None, padding: int = 24, spacing: int = 12, subtle: bool = False):
        super().__init__(parent)
        self.setObjectName("SubtleCard" if subtle else "Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(spacing)


class CardSection(QWidget):
    """A padded block inside a Card. ``line`` draws a bottom (or right) border."""

    def __init__(self, padding=(24, 24, 24, 24), spacing: int = 8, line: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        names = {"bottom": "SectionBottomLine", "right": "SectionRightLine"}
        self.setObjectName(names.get(line or "", "Section"))
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*padding)
        self.body.setSpacing(spacing)


class StatRow(QWidget):
    """Icon + label on the left, value on the right (the checklist rows of the design)."""

    def __init__(self, text: str, value: str = "", status: str = "ok", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        self.text_label = label(text, "BodyText")
        self.value_label = label(value, "StatValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label, 1)
        layout.addWidget(self.value_label)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        self.icon_label.setPixmap(
            icons.pixmap(icons.status_icon_name(status), icons.status_color(status), 18)
        )

    def set_value(self, value) -> None:
        self.value_label.setText(str(value))

    def set_text(self, text: str) -> None:
        self.text_label.setText(text)


def page_header(title: str, subtitle: str = "", actions: Iterable[QWidget] = ()) -> QWidget:
    """Title + subtitle on the left, action buttons on the right."""
    header = QWidget()
    row = QHBoxLayout(header)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(12)
    text_col = QVBoxLayout()
    text_col.setSpacing(2)
    title_lbl = label(title, "PageTitle")
    text_col.addWidget(title_lbl)
    header.title_label = title_lbl  # type: ignore[attr-defined]
    sub_lbl = label(subtitle, "PageSubtitle", wrap=True)
    sub_lbl.setVisible(bool(subtitle))
    text_col.addWidget(sub_lbl)
    header.subtitle_label = sub_lbl  # type: ignore[attr-defined]
    row.addLayout(text_col, 1)
    for w in actions:
        row.addWidget(w, 0, Qt.AlignmentFlag.AlignBottom)
    return header


def card_header(title: str, subtitle: str = "", actions: Iterable[QWidget] = ()) -> CardSection:
    """Left-aligned header strip for table cards (title + optional actions, bottom line)."""
    section = CardSection(padding=(20, 16, 20, 16), spacing=2, line="bottom")
    row = QHBoxLayout()
    row.setSpacing(8)
    text_col = QVBoxLayout()
    text_col.setSpacing(2)
    title_lbl = label(title, "CardTitle")
    text_col.addWidget(title_lbl)
    sub_lbl = label(subtitle, "MutedText", wrap=True)
    sub_lbl.setVisible(bool(subtitle))
    text_col.addWidget(sub_lbl)
    row.addLayout(text_col, 1)
    for w in actions:
        row.addWidget(w)
    section.body.addLayout(row)
    section.title_label = title_lbl  # type: ignore[attr-defined]
    section.subtitle_label = sub_lbl  # type: ignore[attr-defined]
    return section


def centered_header(eyebrow: str, big: str = "", caption: str = "", line: bool = True, big_role: str = "BigName") -> CardSection:
    """Centered card header like the reference: small label, big value, caption."""
    section = CardSection(padding=(24, 24, 24, 20), spacing=2, line="bottom" if line else None)
    center = Qt.AlignmentFlag.AlignHCenter
    eyebrow_lbl = label(eyebrow, "CardEyebrow", align=center)
    big_lbl = label(big, big_role, align=center)
    caption_lbl = label(caption, "MutedText", wrap=True, align=center)
    section.body.addWidget(eyebrow_lbl)
    section.body.addWidget(big_lbl)
    section.body.addWidget(caption_lbl)
    big_lbl.setVisible(bool(big))
    caption_lbl.setVisible(bool(caption))
    section.eyebrow_label = eyebrow_lbl  # type: ignore[attr-defined]
    section.big_label = big_lbl  # type: ignore[attr-defined]
    section.caption_label = caption_lbl  # type: ignore[attr-defined]
    return section


def field(label_text: str, widget: QWidget) -> QWidget:
    """Label stacked above an input."""
    box = QWidget()
    col = QVBoxLayout(box)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(6)
    col.addWidget(label(label_text, "FieldLabel"))
    col.addWidget(widget)
    return box


def hbox(*widgets, spacing: int = 8, margins=(0, 0, 0, 0), stretch_first: bool = False) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(*margins)
    row.setSpacing(spacing)
    for i, w in enumerate(widgets):
        if w is None:
            row.addStretch(1)
        elif isinstance(w, QLayout):
            row.addLayout(w)
        else:
            row.addWidget(w, 1 if (stretch_first and i == 0) else 0)
    return row


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())
