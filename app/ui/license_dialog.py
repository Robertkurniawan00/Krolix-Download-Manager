"""
Krolix Download Manager - License Registration Dialog
Clean macOS Modern dark modal for registering serial keys
and viewing product license details.
Supports Standard 20-digit Pattern (XXXXX-XXXXX-XXXXX-XXXXX), Advance Master Mode,
and Honeypot Keygen Detection.
"""

import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QFont

from ..core.license_manager import LicenseManager
from ..utils.helpers import apply_windows_dark_titlebar
from . import fluent_icons
from .fake_serial_dialog import FakeSerialDetectedDialog


class LicenseRegistrationDialog(QDialog):
    license_status_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.license_mgr = LicenseManager.get_instance()
        self.setWindowTitle("Registrasi Lisensi - Krolix Download Manager")
        self.setFixedWidth(540)
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
            QLineEdit {
                background-color: #0f172a;
                border: 1px solid #283548;
                border-radius: 6px;
                padding: 8px 12px;
                color: #f8fafc;
                font-size: 12px;
                font-family: 'Segoe UI', sans-serif;
            }
            QLineEdit:focus {
                border: 1px solid #10b981;
                background-color: #131d31;
            }
            QPushButton {
                font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
                border-radius: 6px;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: 600;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        info = self.license_mgr.get_license_display_info()

        # Header with Shield Icon & Title
        header = QHBoxLayout()
        header.setSpacing(12)

        lbl_icon = QLabel()
        shield_color = "#a855f7" if info["is_master"] else "#10b981" if info["is_full"] else "#ef4444" if info["is_fake"] else "#f59e0b"
        lbl_icon.setPixmap(fluent_icons.create_fluent_shield_icon(shield_color).pixmap(32, 32))
        header.addWidget(lbl_icon)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        
        lbl_title = QLabel()
        if info["is_full"]:
            lbl_title.setText("Informasi Lisensi Produk")
            self.lbl_subtitle = QLabel("Aplikasi telah terdaftar dengan lisensi resmi yang sah.")
            sub_color = "#c084fc" if info["is_master"] else "#10b981"
        else:
            lbl_title.setText("Aktivasi Lisensi Produk")
            self.lbl_subtitle = QLabel(f"Status saat ini: {info['status_title']}")
            sub_color = "#ef4444" if info["is_fake"] else "#f59e0b"
            
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc;")
        self.lbl_subtitle.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {sub_color};")
        title_vbox.addWidget(lbl_title)
        title_vbox.addWidget(self.lbl_subtitle)
        header.addLayout(title_vbox)
        header.addStretch()
        layout.addLayout(header)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #1e293b;")
        layout.addWidget(sep)

        # Content depending on whether registered
        if info["is_full"]:
            self._build_registered_view(layout, info)
        else:
            self._build_unregistered_view(layout, info)

    def _build_registered_view(self, layout: QVBoxLayout, info: dict):
        is_master = info.get("is_master", False)

        # Single elegant certificate frame
        card = QFrame()
        card_border = "#581c87" if is_master else "#1e293b"
        card_bg = "#120a22" if is_master else "#0d1322"
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {card_bg};
                border: 1px solid {card_border};
                border-radius: 8px;
            }}
        """)
        cvbox = QVBoxLayout(card)
        cvbox.setContentsMargins(18, 16, 18, 16)
        cvbox.setSpacing(14)

        # Top strip inside card: Badge + Verification Status
        top_strip = QHBoxLayout()
        top_strip.setSpacing(8)

        lbl_badge = QLabel()
        if is_master:
            lbl_badge.setText("★ ADVANCE MASTER MODE")
            lbl_badge.setStyleSheet("""
                QLabel {
                    background-color: #2e1065;
                    color: #c084fc;
                    border: 1px solid #7e22ce;
                    border-radius: 10px;
                    padding: 2px 10px;
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 0.5px;
                }
            """)
        else:
            lbl_badge.setText("✓ FULL VERSION (PERPETUAL)")
            lbl_badge.setStyleSheet("""
                QLabel {
                    background-color: #064e3b;
                    color: #34d399;
                    border: 1px solid #059669;
                    border-radius: 10px;
                    padding: 2px 10px;
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 0.5px;
                }
            """)
        top_strip.addWidget(lbl_badge)
        top_strip.addStretch()

        lbl_verified = QLabel("Terverifikasi Sah ✓")
        lbl_verified.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
        top_strip.addWidget(lbl_verified)
        cvbox.addLayout(top_strip)

        # Subtle separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #1e293b;")
        cvbox.addWidget(sep)

        # Clean 2-column key-value grid (no nested boxes!)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(9)

        def add_row(row_idx: int, label_text: str, value_widget: QLabel):
            lbl_key = QLabel(label_text)
            lbl_key.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
            lbl_key.setFixedWidth(130)
            grid.addWidget(lbl_key, row_idx, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value_widget, row_idx, 1)

        # 1. Registered Name
        lbl_name = QLabel(info.get("registered_name", "Licensed User"))
        lbl_name.setStyleSheet("color: #f8fafc; font-size: 12px; font-weight: 600;")
        add_row(0, "Pemilik Lisensi", lbl_name)

        # 2. Email
        lbl_email = QLabel(info.get("registered_email", "-"))
        lbl_email.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        add_row(1, "Email Terdaftar", lbl_email)

        # 3. Serial Key (Clean Consolas chip)
        lbl_serial = QLabel(info.get("serial_masked", "-"))
        lbl_serial.setStyleSheet("""
            QLabel {
                font-family: Consolas, monospace;
                font-size: 11px;
                font-weight: 700;
                color: #38bdf8;
                background-color: #131f37;
                border: 1px solid #1e3a5f;
                border-radius: 4px;
                padding: 2px 8px;
            }
        """)
        add_row(2, "Nomor Seri (Key)", lbl_serial)

        # 4. Hardware ID
        lbl_hwid = QLabel(info.get("hardware_id", "-"))
        lbl_hwid.setStyleSheet("font-family: Consolas, monospace; font-size: 11px; color: #94a3b8;")
        add_row(3, "Hardware ID (PC)", lbl_hwid)

        # 5. Segment Limit
        seg_limit_text = "64 Koneksi Simultan (Ultra Overdrive Turbo)" if is_master else "Hingga 32 Koneksi Simultan (Akselerasi Penuh)"
        seg_color = "#c084fc" if is_master else "#10b981"
        lbl_segs = QLabel(seg_limit_text)
        lbl_segs.setStyleSheet(f"color: {seg_color}; font-size: 11px; font-weight: 600;")
        add_row(4, "Koneksi Segmen", lbl_segs)

        # 6. Validity
        lbl_validity = QLabel("Lisensi Permanen (Lifetime - Tanpa Batas Kedaluwarsa)")
        lbl_validity.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        add_row(5, "Masa Berlaku", lbl_validity)

        cvbox.addLayout(grid)
        layout.addWidget(card)

        # Bottom Button Row (Clean & discrete)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)

        # Subtle deactivation link instead of big red button
        btn_unreg = QPushButton("Cabut Lisensi dari Perangkat Ini...")
        btn_unreg.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748b;
                border: none;
                font-size: 11px;
                text-decoration: underline;
                padding: 0;
            }
            QPushButton:hover {
                color: #f43f5e;
            }
        """)
        btn_unreg.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_unreg.setToolTip("Cabut aktivasi lisensi dari komputer ini jika ingin memindahkan ke komputer lain.")
        btn_unreg.clicked.connect(self._do_unregister)
        btn_row.addWidget(btn_unreg)

        btn_row.addStretch()

        btn_close = QPushButton("Tutup")
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 7px 24px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
            }
        """)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _build_unregistered_view(self, layout: QVBoxLayout, info: dict):
        if info["is_fake"]:
            info_text = f"Peringatan: {info['fake_reason'] or 'Serial number palsu terdeteksi.'} Fitur dibatasi maks 4 segmen."
            info_color = "#ef4444"
        elif info["is_trial"]:
            info_text = f"Anda sedang menggunakan masa evaluasi 30 hari ({info['days_left']} hari tersisa). Masukkan serial number untuk aktivasi permanen."
            info_color = "#f59e0b"
        else:
            info_text = "Masa uji coba telah berakhir. Fungsi dibatasi maks 4 koneksi. Masukkan serial number resmi."
            info_color = "#ef4444"

        lbl_notice = QLabel(info_text)
        lbl_notice.setWordWrap(True)
        lbl_notice.setStyleSheet(
            f"color: {info_color}; font-size: 11px; font-weight: 500; "
            f"background-color: #161a24; border: 1px solid #242c3d; border-radius: 6px; padding: 10px;"
        )
        layout.addWidget(lbl_notice)

        # Form Fields
        form_vbox = QVBoxLayout()
        form_vbox.setSpacing(8)

        # Names row
        names_row = QHBoxLayout()
        names_row.setSpacing(10)

        fn_vbox = QVBoxLayout()
        fn_vbox.setSpacing(3)
        lbl_fn = QLabel("Nama Depan (First Name):")
        lbl_fn.setStyleSheet("font-size: 11px; font-weight: 600; color: #94a3b8;")
        self.txt_first_name = QLineEdit()
        self.txt_first_name.setPlaceholderText("Nama Depan")
        fn_vbox.addWidget(lbl_fn)
        fn_vbox.addWidget(self.txt_first_name)
        names_row.addLayout(fn_vbox)

        ln_vbox = QVBoxLayout()
        ln_vbox.setSpacing(3)
        lbl_ln = QLabel("Nama Belakang (Last Name):")
        lbl_ln.setStyleSheet("font-size: 11px; font-weight: 600; color: #94a3b8;")
        self.txt_last_name = QLineEdit()
        self.txt_last_name.setPlaceholderText("Nama Belakang")
        ln_vbox.addWidget(lbl_ln)
        ln_vbox.addWidget(self.txt_last_name)
        names_row.addLayout(ln_vbox)

        form_vbox.addLayout(names_row)

        # Email
        email_vbox = QVBoxLayout()
        email_vbox.setSpacing(3)
        lbl_email = QLabel("Alamat Email:")
        lbl_email.setStyleSheet("font-size: 11px; font-weight: 600; color: #94a3b8;")
        self.txt_email = QLineEdit()
        self.txt_email.setPlaceholderText("nama@domain.com")
        email_vbox.addWidget(lbl_email)
        email_vbox.addWidget(self.txt_email)
        form_vbox.addLayout(email_vbox)

        # Serial Number Box (Pattern XXXXX-XXXXX-XXXXX-XXXXX)
        serial_vbox = QVBoxLayout()
        serial_vbox.setSpacing(3)

        serial_header = QHBoxLayout()
        lbl_serial = QLabel("Nomor Seri (Serial Number):")
        lbl_serial.setStyleSheet("font-size: 11px; font-weight: 600; color: #94a3b8;")
        serial_header.addWidget(lbl_serial)
        serial_header.addStretch()

        btn_paste = QPushButton("Tempel Papan Klip")
        btn_paste.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #38bdf8;
                border: none;
                font-size: 11px;
                text-decoration: underline;
                padding: 0;
            }
            QPushButton:hover {
                color: #7dd3fc;
            }
        """)
        btn_paste.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_paste.clicked.connect(self._paste_serial_from_clipboard)
        serial_header.addWidget(btn_paste)
        serial_vbox.addLayout(serial_header)

        self.txt_serial = QLineEdit()
        self.txt_serial.setPlaceholderText("XXXXX-XXXXX-XXXXX-XXXXX")
        self.txt_serial.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self.txt_serial.setMaxLength(23)
        self.txt_serial.textChanged.connect(self._on_serial_text_changed)
        serial_vbox.addWidget(self.txt_serial)

        form_vbox.addLayout(serial_vbox)
        layout.addLayout(form_vbox)

        # Actions Row
        actions = QHBoxLayout()
        actions.setSpacing(8)

        btn_cancel = QPushButton("Batal")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
            }
            QPushButton:hover {
                background-color: #334155;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        actions.addWidget(btn_cancel)

        btn_register = QPushButton("Daftar Sekarang (Register)")
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
        btn_register.clicked.connect(self._do_register)
        actions.addWidget(btn_register)

        layout.addLayout(actions)

    def _on_serial_text_changed(self, text: str):
        """Auto-formats serial with hyphens in 5-character blocks as the user types."""
        clean = text.replace("-", "").replace(" ", "").upper()
        if len(clean) > 20:
            clean = clean[:20]

        parts = [clean[i:i+5] for i in range(0, len(clean), 5) if clean[i:i+5]]
        formatted = "-".join(parts)

        if formatted != text:
            self.txt_serial.blockSignals(True)
            self.txt_serial.setText(formatted)
            self.txt_serial.setCursorPosition(len(formatted))
            self.txt_serial.blockSignals(False)

    def _paste_serial_from_clipboard(self):
        clip = QApplication.clipboard().text().strip()
        if clip:
            self.txt_serial.setText(clip)

    def _do_register(self):
        first = self.txt_first_name.text().strip()
        last = self.txt_last_name.text().strip()
        email = self.txt_email.text().strip()
        serial = self.txt_serial.text().strip()

        ok, msg, code = self.license_mgr.register(first, last, email, serial)
        if ok:
            if code == "VALID_MASTER":
                QMessageBox.information(
                    self,
                    "★ Advance Master Mode Diaktifkan ★",
                    "Selamat! Krolix Download Manager berhasil diaktifkan dalam ADVANCE MASTER MODE!\n\n"
                    "Fitur Khusus Aktif:\n"
                    "• 64 Segmen Koneksi Paralel (Ultra Overdrive)\n"
                    "• Akses penuh fitur Site Grabber & Penjadwal\n"
                    "• Prioritas alokasi thread kecepatan turbo"
                )
            else:
                QMessageBox.information(self, "Aktivasi Berhasil", msg)
            self.license_status_changed.emit()
            self.accept()
        else:
            if code.startswith("FAKE_SERIAL"):
                # Authentic Fake Serial Dialog Popup!
                dlg = FakeSerialDetectedDialog(reason=msg, serial_masked=serial, parent=self)
                dlg.exec()
            else:
                QMessageBox.warning(self, "Aktivasi Gagal", msg)

    def _do_unregister(self):
        reply = QMessageBox.question(
            self,
            "Konfirmasi Hapus Lisensi",
            "Apakah Anda yakin ingin menghapus data lisensi terdaftar untuk menguji fungsi terbatas?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.license_mgr.unregister()
            QMessageBox.information(
                self,
                "Lisensi Dihapus",
                "Aplikasi kini berada dalam status Tidak Berlisensi. Beberapa fungsi akan dibatasi."
            )
            self.license_status_changed.emit()
            self.accept()
