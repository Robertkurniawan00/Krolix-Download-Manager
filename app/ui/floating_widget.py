"""
Krolix Download Manager - Floating Drop Target Widget
Translucent always-on-top drop basket for dragging links with live speed HUD.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenu
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QCursor
from ..utils.helpers import format_speed

class FloatingDropWidget(QWidget):
    url_dropped = pyqtSignal(str)
    show_main_requested = pyqtSignal()
    restore_window_requested = show_main_requested

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setFixedSize(110, 85)

        self._drag_pos = QPoint()
        self.current_speed = 0.0
        self.active_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_lbl = QLabel("ZERO")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet("font-weight: 900; font-size: 13px; color: #10b981; letter-spacing: 1px;")
        layout.addWidget(self.title_lbl)

        self.speed_lbl = QLabel("0 KB/s")
        self.speed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_lbl.setStyleSheet("font-size: 11px; color: #f8fafc; font-weight: bold;")
        layout.addWidget(self.speed_lbl)

        self.info_lbl = QLabel("Drop Link")
        self.info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_lbl.setStyleSheet("font-size: 9px; color: #94a3b8;")
        layout.addWidget(self.info_lbl)

    def update_speed(self, speed_bps: float, active_count: int):
        self.current_speed = speed_bps
        self.active_count = active_count
        self.speed_lbl.setText(format_speed(speed_bps))
        if active_count > 0:
            self.info_lbl.setText(f"{active_count} aktif")
            self.info_lbl.setStyleSheet("font-size: 9px; color: #22c55e; font-weight: bold;")
        else:
            self.info_lbl.setText("Drop Link")
            self.info_lbl.setStyleSheet("font-size: 9px; color: #94a3b8;")
        self.update()

    def update_stats(self, active_count: int = 0, speed_bps: float = 0.0):
        self.update_speed(speed_bps=speed_bps, active_count=active_count)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw rounded dark card
        bg_color = QColor(24, 24, 27, 230) # #18181b with 90% opacity
        border_color = QColor(16, 185, 129, 180) if self.active_count > 0 else QColor(63, 63, 70, 180)

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.5))
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 12, 12)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.show_main_requested.emit()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        show_action = menu.addAction("Buka Jendela Utama")
        show_action.triggered.connect(self.show_main_requested.emit)
        menu.addSeparator()
        hide_action = menu.addAction("Sembunyikan Drop Target")
        hide_action.triggered.connect(self.hide)
        menu.exec(QCursor.pos())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        url = ""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                url = urls[0].toString()
        elif event.mimeData().hasText():
            url = event.mimeData().text().strip()

        if url and (url.startswith("http://") or url.startswith("https://") or url.startswith("ftp://")):
            self.url_dropped.emit(url)
            event.acceptProposedAction()
