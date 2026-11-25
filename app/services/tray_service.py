from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor
from PyQt6.QtCore import QObject, pyqtSignal

class TrayService(QObject):
    show_window_requested = pyqtSignal()
    hide_window_requested = pyqtSignal()
    add_url_requested = pyqtSignal()
    pause_all_requested = pyqtSignal()
    resume_all_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tray_icon = QSystemTrayIcon(parent)
        self.icon = self._create_icon()
        self.tray_icon.setIcon(self.icon)
        self.tray_icon.setToolTip("Krolix Download Manager - Background Worker Aktif (Port 9666)")

        self._build_menu()
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _create_icon(self) -> QIcon:
        try:
            from ..utils.helpers import get_app_icon
            app_icon = get_app_icon()
            if app_icon and not app_icon.isNull():
                return app_icon
        except Exception:
            pass

        import os
        logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "logo_32.png"))
        if os.path.exists(logo_path):
            return QIcon(logo_path)
        pix = QPixmap(32, 32)
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#0EA5E9"))
        p.setPen(QColor("#0284C7"))
        p.drawRoundedRect(2, 2, 28, 28, 6, 6)
        p.end()
        return QIcon(pix)

    def _build_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #070a0f;
                color: #f1f5f9;
                border: 1px solid #1e293b;
                padding: 4px;
                border-radius: 8px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #0ea5e9;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #1e293b;
                margin: 4px 6px;
            }
        """)

        status_act = QAction("Background Worker: Aktif (Port 9666)", menu)
        status_act.setEnabled(False)
        menu.addAction(status_act)

        menu.addSeparator()

        show_act = QAction("Buka Krolix Download Manager", menu)
        show_act.triggered.connect(self.show_window_requested.emit)
        menu.addAction(show_act)

        hide_act = QAction("Sembunyikan Jendela ke Tray", menu)
        hide_act.triggered.connect(self.hide_window_requested.emit)
        menu.addAction(hide_act)

        add_act = QAction("Tambah Unduhan Baru...", menu)
        add_act.triggered.connect(self.add_url_requested.emit)
        menu.addAction(add_act)

        menu.addSeparator()

        pause_all_act = QAction("Jeda Semua Unduhan", menu)
        pause_all_act.triggered.connect(self.pause_all_requested.emit)
        menu.addAction(pause_all_act)

        resume_all_act = QAction("Lanjutkan Semua Unduhan", menu)
        resume_all_act.triggered.connect(self.resume_all_requested.emit)
        menu.addAction(resume_all_act)

        menu.addSeparator()

        exit_act = QAction("Keluar & Matikan Worker...", menu)
        exit_act.triggered.connect(self.exit_requested.emit)
        menu.addAction(exit_act)

        self.tray_icon.setContextMenu(menu)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick, QSystemTrayIcon.ActivationReason.Trigger):
            self.show_window_requested.emit()

    def show_notification(self, title: str, message: str):
        self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def show_message(self, title: str, message: str):
        self.show_notification(title, message)
