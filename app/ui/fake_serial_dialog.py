"""
Krolix Download Manager - Fake Serial & Keygen Detection Dialog
Alert modal triggered when an unauthorized, keygen-generated,
blacklisted, or hosts-hijacked serial number is detected.
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from ..utils.helpers import apply_windows_dark_titlebar
from . import fluent_icons


class FakeSerialDetectedDialog(QDialog):
    def __init__(self, reason: str = "", serial_masked: str = "", parent=None):
        super().__init__(parent)
        self.reason = reason or "Serial Number dibuat menggunakan Keygen ilegal atau pola tidak sah."
        self.serial_masked = serial_masked
        self.setWindowTitle("Pemberitahuan Lisensi - Krolix Download Manager")
        self.setFixedWidth(540)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        apply_windows_dark_titlebar(self)

        logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "logo_32.png"))
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.setStyleSheet("""
            QDialog {
                background-color: #0b111a;
                border: 2px solid #ef4444;
                border-radius: 10px;
            }
            QLabel {
                font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
                color: #cbd5e1;
            }
            QPushButton {
                font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header with Red Warning Shield
        header = QHBoxLayout()
        header.setSpacing(14)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(fluent_icons.create_fluent_shield_icon("#ef4444").pixmap(38, 38))
        header.addWidget(lbl_icon)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        lbl_title = QLabel("Krolix Download Manager has been registered with a fake Serial Number!")
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #f87171;")
        title_vbox.addWidget(lbl_title)

        lbl_sub = QLabel("Serial Number palsu / buatan Keygen terdeteksi oleh sistem.")
        lbl_sub.setStyleSheet("font-size: 11px; color: #fca5a5; font-weight: 500;")
        title_vbox.addWidget(lbl_sub)
        header.addLayout(title_vbox)
        layout.addLayout(header)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #3b141e;")
        layout.addWidget(sep)

        # Alert Box containing detection reason
        alert_box = QFrame()
        alert_box.setStyleSheet("""
            QFrame {
                background-color: #241217;
                border: 1px solid #7f1d1d;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        ab_vbox = QVBoxLayout(alert_box)
        ab_vbox.setSpacing(6)

        lbl_diag = QLabel("⚠️ HASIL DETEKSI KEAMANAN:")
        lbl_diag.setStyleSheet("font-size: 11px; font-weight: 700; color: #f87171;")
        ab_vbox.addWidget(lbl_diag)

        lbl_reason = QLabel(self.reason)
        lbl_reason.setWordWrap(True)
        lbl_reason.setStyleSheet("font-size: 11px; color: #fecaca; line-height: 1.4;")
        ab_vbox.addWidget(lbl_reason)

        if self.serial_masked:
            lbl_serial = QLabel(f"Serial Key Terkait: <span style='font-family: Consolas; color: #cbd5e1;'>{self.serial_masked}</span>")
            lbl_serial.setTextFormat(Qt.TextFormat.RichText)
            lbl_serial.setStyleSheet("font-size: 11px; margin-top: 4px;")
            ab_vbox.addWidget(lbl_serial)

        layout.addWidget(alert_box)

        # Consequence message
        lbl_info = QLabel(
            "Untuk melindungi integritas aplikasi dan jaringan, seluruh fitur komersial telah dinonaktifkan.\n"
            "• Akselerasi segmen dibatasi maksimum 4 koneksi.\n"
            "• Site Grabber, Penjadwal, dan Batch Sniffer dinonaktifkan.\n\n"
            "Silakan beli lisensi resmi Krolix Download Manager atau masukkan serial key yang sah."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.4;")
        layout.addWidget(lbl_info)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_close = QPushButton("Tutup (Mode Dibatasi)")
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
            }
            QPushButton:hover {
                background-color: #283548;
                color: #f1f5f9;
            }
        """)
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        btn_row.addStretch()

        btn_register = QPushButton("Masukkan Serial Baru...")
        btn_register.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: #ffffff;
                border: none;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        btn_register.clicked.connect(self._open_registration)
        btn_row.addWidget(btn_register)

        layout.addLayout(btn_row)

    def _open_registration(self):
        from .license_dialog import LicenseRegistrationDialog
        dlg = LicenseRegistrationDialog(parent=self.parent())
        self.accept()
        dlg.exec()
