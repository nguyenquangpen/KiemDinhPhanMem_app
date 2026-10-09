from ui.build.ui_login_fail_widget import Ui_LoginFail
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPainter, QPixmap, QColor, QBrush, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QGraphicsScene, QGraphicsPixmapItem, QGraphicsBlurEffect
)

def blur_pixmap(pixmap, radius):
    """Applies a blur effect to a QPixmap."""
    if pixmap.isNull():
        return QPixmap()

    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(pixmap)
    blur_effect = QGraphicsBlurEffect()
    blur_effect.setBlurRadius(radius)
    item.setGraphicsEffect(blur_effect)
    scene.addItem(item)
    
    result_pixmap = QPixmap(pixmap.size())
    result_pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(result_pixmap)
    scene.render(painter, QRect(QPoint(0, 0), pixmap.size()), QRect(QPoint(0, 0), pixmap.size()))
    painter.end()
    
    return result_pixmap

class LoginFailWidget(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_LoginFail()
        self.ui.setupUi(self)
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.blur_radius = 15
        self.overlay_color = QColor(255, 255, 255, 50) 
        
        self._background_pixmap = QPixmap()

    def update_background(self):
        """
        Captures the parent widget's content and creates the blurred background.
        This should be called right before showing the overlay.
        """
        parent = self.parentWidget()
        if not parent:
            return

        self.setGeometry(parent.rect())
        background_pixmap = parent.grab()
        self._background_pixmap = blur_pixmap(background_pixmap, self.blur_radius)
        self.update()

    def paintEvent(self, event):
        """
        This is where the magic happens. We paint the pre-blurred background here.
        Qt will automatically paint the child widgets (from your UI file) on top of this.
        """
        if self._background_pixmap.isNull():
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        painter.drawPixmap(self.rect(), self._background_pixmap)
        
        painter.fillRect(self.rect(), self.overlay_color)

    def mousePressEvent(self, event: QMouseEvent):
        # When the overlay is clicked, emit the signal and close the widget
        self.clicked.emit()
        self.close() 
        super().mousePressEvent(event)

    def showEvent(self, event):
        """
        Override showEvent to ensure the background is updated when the widget becomes visible.
        """
        self.update_background()
        super().showEvent(event)
        
    def resizeEvent(self, event):
        if self.isVisible():
             self.update_background()
        super().resizeEvent(event)