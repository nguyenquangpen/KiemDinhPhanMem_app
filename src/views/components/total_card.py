from ui.build.ui_total_widget import Ui_TotalWidget
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPainter, QPixmap, QColor, QBrush, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QGraphicsScene, QGraphicsPixmapItem, QGraphicsBlurEffect
)
from enum import Enum
import resources_rc
class DotColor(Enum):
    Gray = 0
    Black = 1
    Green = 2
    Red = 3

color_resource_map = {
    DotColor.Gray: u":/png/png/gray_circle.png",
    DotColor.Black: u":/png/png/black_circle.png",
    DotColor.Green: u":/png/png/green_circle.png",
    DotColor.Red: u":/png/png/red_circle.png"
}

class TotalCard(QWidget):
    def __init__(self, color:DotColor, name: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.ui = Ui_TotalWidget()
        self.ui.setupUi(self)
        self.ui.nameLabel.setText(name)
        self.ui.colorDotLabel.setPixmap(QPixmap(color_resource_map[color]))
    def set_value(self, value):
        if isinstance(value, str):
            self.ui.numberLabel.setText(value)
        else:
            text = str(value)
            self.ui.numberLabel.setText(text)