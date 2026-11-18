"""
Krolix Download Manager - Trial Expired & Restricted Feature Nag Dialog
Informs the user about locked features and provides an easy path to register.
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from ..core.license_manager import LicenseManager
from ..utils.helpers import apply_windows_dark_titlebar
from . import fluent_icons


class TrialExpiredNagDialog(QDialog):
    def __init__(self, locked_feature_name: str = "", parent=None):
        super().__init__(parent)
        self.license_mgr = LicenseManager.get_instance()
        self.locked_feature_name = locked_feature_name
        self.setWindowTitle("Pemberitahuan Lisensi - Krolix Download Manager")
        self.setFixedWidth(500)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        apply_windows_dark_titlebar(self)

        logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "logo_32.png"))
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.setStyleSheet("""
            QDialog {
                background-color: #0b111a;
                border: 1px solid #1e293b;
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

        # Header
        header = QHBoxLayout()
        header.setSpacing(12)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(fluent_icons.create_fluent_shield_icon("#ef4444").pixmap(32, 32))
        header.addWidget(lbl_icon)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        lbl_title = QLabel("Masa Uji Coba Berakhir (Versi Terbatas)")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc;")
        title_vbox.addWidget(lbl_title)

        lbl_sub = QLabel("Beberapa fitur komersial dinonaktifkan.")
        lbl_sub.setStyleSheet("font-size: 11px; color: #f87171; font-weight: 500;")
        title_vbox.addWidget(lbl_sub)
        header.addLayout(title_vbox)
        header.addStretch()
        layout.addLayout(header)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #1e293b;")
        layout.addWidget(sep)

        # Feature locked alert box if specific feature triggered it
        if self.locked_feature_name:
            feature_box = QFrame()
            feature_box.setStyleSheet("""
                QFrame {
                    background-color: #27141b;
                    border: 1px solid #5c1d2e;
                    border-radius: 8px;
                    padding: 10px 12px;
                }
            """)
            fb_layout = QHBoxLayout(feature_box)
            fb_layout.setContentsMargins(8, 6, 8, 6)
            fb_lbl = QLabel(f"🔒 <b>Fitur Terkunci:</b> {self.locked_feature_name} hanya tersedia pada <b>Full Version</b>.")
            fb_lbl.setStyleSheet("color: #fca5a5; font-size: 11px;")
            fb_lbl.setTextFormat(Qt.TextFormat.RichText)
            fb_layout.addWidget(fb_lbl)
            layout.addWidget(feature_box)

        # Comparison Card
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #0d1626;
                border: 1px solid #1b273d;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        cvbox = QVBoxLayout(card)
        cvbox.setSpacing(8)

        lbl_comp_title = QLabel("Perbedaan Fitur Full Version vs Versi Terbatas:")
        lbl_comp_title.setStyleSheet("color: #e2e8f0; font-weight: 700; font-size: 11px;")
        cvbox.addWidget(lbl_comp_title)

        comp_text = (
            "<table width='100%' cellpadding='4' style='font-size: 11px;'>"
            "<tr><th align='left' style='color: #94a3b8;'>Fungsi</th><th align='left' style='color: #f87171;'>Versi Terbatas</th><th align='left' style='color: #10b981;'>Full Version</th></tr>"
            "<tr><td style='color: #cbd5e1;'>Koneksi Segmen</td><td style='color: #fca5a5;'>Maks 4 Koneksi</td><td style='color: #86efac;'>Hingga 32 Koneksi</td></tr>"
            "<tr><td style='color: #cbd5e1;'>Unduhan Bersamaan</td><td style='color: #fca5a5;'>Maks 2 Unduhan</td><td style='color: #86efac;'>Tanpa Batas</td></tr>"
            "<tr><td style='color: #cbd5e1;'>Site Grabber</td><td style='color: #fca5a5;'>Dinonaktifkan ❌</td><td style='color: #86efac;'>Aktif Penuh ✔</td></tr>"
            "<tr><td style='color: #cbd5e1;'>Penjadwal Antrean</td><td style='color: #fca5a5;'>Dinonaktifkan ❌</td><td style='color: #86efac;'>Aktif Penuh ✔</td></tr>"
            "<tr><td style='color: #cbd5e1;'>Batch Sniffer</td><td style='color: #fca5a5;'>Dinonaktifkan ❌</td><td style='color: #86efac;'>Aktif Penuh ✔</td></tr>"
            "</table>"
        )
        lbl_comp = QLabel(comp_text)
        lbl_comp.setTextFormat(Qt.TextFormat.RichText)
        cvbox.addWidget(lbl_comp)

        layout.addWidget(card)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_continue = QPushButton("Lanjutkan Mode Terbatas")
        btn_continue.setStyleSheet("""
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
        btn_continue.clicked.connect(self.reject)
        btn_row.addWidget(btn_continue)

        btn_row.addStretch()

        btn_register = QPushButton("Daftarkan Lisensi Sekarang...")
        btn_register.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #022c22;
                border: none;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #34d399;
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
