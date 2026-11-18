"""
Krolix Download Manager - Tip of the Day Dialog
Displays practical tips and Krolix Power User features in an AMOLED Black aesthetic.
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from ..core.database import Database
from ..utils.helpers import apply_windows_dark_titlebar
from . import fluent_icons


DEFAULT_ZERO_TIPS = [
    # Krolix Power Tips
    "BitTorrent Real Seeding: Anda dapat melakukan seeding BitTorrent secara riil ke swarm peers! Buka menu Tasks -> BitTorrent Seeding Manager untuk memantau data terunggah, rasio bagi, dan durasi masa seeding.",
    "Unduh Video & Medsos (YT-DLP): Tekan Ctrl+Y kapan saja untuk mengunduh video dari YouTube, TikTok, Twitter/X, Instagram, dan ratusan situs lainnya dengan pilihan resolusi hingga 4K atau ekstrak audio MP3 secara instan.",
    "Integrasi Ekstensi Cerdas: Krolix mendukung integrasi peramban modern (Chrome, Edge, Firefox, Brave) melalui registrasi native messaging host berkecepatan tinggi.",
    "Akselerasi Multi-Segmen: Krolix membagi unduhan besar hingga 32 segmen simultan dan menulis langsung ke disk (direct-to-disk) untuk mencapai kecepatan unduh maksimum pada koneksi Anda.",
    "Desktop Floating Drop Target: Aktifkan 'Desktop Drop Target' dari menu View. Anda dapat menyeret link atau teks yang disalin langsung ke widget melayang di desktop untuk mengunduh seketika.",
    "Perbarui Alamat Unduhan (Refresh URL): Jika link direct-download kedaluwarsa saat unduhan terhenti, tekan Ctrl+U untuk memperbarui URL unduhan tanpa perlu mengunduh ulang dari awal.",
    "Verifikasi Checksum & Ekstrak Arsip: Klik kanan pada unduhan yang selesai untuk memverifikasi SHA-256 / MD5 atau langsung mengekstrak berkas ZIP/RAR/7Z tanpa membuka aplikasi eksternal.",
    "Pencarian Torrent DHT & BTDIG: Tekan Ctrl+D untuk mencari konten torrent langsung melalui jaringan terdesentralisasi DHT tanpa bergantung pada situs web torrent publik.",
    
    # Classic Productivity Tips (Adapted & Modernized)
    "Krolix mengambil alih unduhan dari peramban secara otomatis jika jenis berkas cocok dengan daftar ekstensi di 'Pengaturan -> Jenis Berkas & Pengecualian'.",
    "Jika server unduhan sibuk atau sering mengalami timeout, masukkan tugas ke antrean Scheduler. Krolix akan mencoba mengunduh ulang secara berkala secara otomatis.",
    "Anda dapat menahan tombol ALT pada keyboard saat mengeklik tautan di peramban untuk mencegah Krolix mengambil alih unduhan dan membiarkan peramban mengunduhnya langsung.",
    "Gunakan Site Grabber (Ctrl+G atau Toolbar) untuk menjelajahi seluruh situs web dan mengunduh semua berkas gambar, video, atau dokumen dengan kriteria filter tertentu.",
    "Gunakan fitur Batch Sniffer (Ctrl+Shift+B) untuk menyalin banyak link sekaligus dari halaman web atau dokumen dan memasukkannya ke antrean dalam satu langkah.",
    "Anda dapat menarik (drag and drop) berkas dari tabel unduhan Krolix langsung ke folder Manajer Berkas / Finder atau aplikasi pemutar media favorit Anda.",
    "Simpan kredensial server unduhan terproteksi (HTTP/FTP) di Pengaturan agar Anda tidak perlu memasukkan nama pengguna dan kata sandi berulang kali."
]


class TipDialog(QDialog):
    def __init__(self, parent=None, db=None):
        super().__init__(parent)
        self.db = db or Database.get_instance()
        self.setWindowTitle("Tip Hari Ini - Krolix Download Manager")
        self.setFixedSize(540, 360)
        apply_windows_dark_titlebar(self)

        self.tips = self._load_tips()
        self.current_index = int(self.db.get_setting("last_tip_index", "0")) % max(1, len(self.tips))

        self._init_ui()
        self._update_tip_display()

        # Keyboard shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self._prev_tip)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._next_tip)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close)

    def _load_tips(self) -> list:
        loaded = []
        # Try loading custom tips from asset file
        tips_path = os.path.join(os.path.dirname(__file__), "..", "assets", "tips.txt")
        if os.path.exists(tips_path):
            try:
                with open(tips_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            loaded.append(line)
            except Exception:
                pass

        # Fuse with Krolix Power Tips
        all_tips = list(DEFAULT_ZERO_TIPS)
        for t in loaded:
            if t not in all_tips:
                all_tips.append(t)
        return all_tips if all_tips else DEFAULT_ZERO_TIPS

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #070a0f;
                color: #f1f5f9;
                border: 1px solid #1e293b;
            }
            QLabel {
                color: #e2e8f0;
            }
            QPushButton {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 7px 18px;
                color: #f8fafc;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border-color: #3b82f6;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
            QPushButton#accentBtn {
                background-color: #2563eb;
                border-color: #3b82f6;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton#accentBtn:hover {
                background-color: #1d4ed8;
                border-color: #60a5fa;
            }
            QCheckBox {
                color: #94a3b8;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #334155;
                background-color: #0f172a;
            }
            QCheckBox::indicator:checked {
                background-color: #2563eb;
                border-color: #3b82f6;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header with Lightbulb icon & Title
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(fluent_icons.create_fluent_options_icon(color="#fbbf24").pixmap(32, 32))
        header_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        title_lbl = QLabel("Tahukah Anda?")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        title_vbox.addWidget(title_lbl)

        sub_lbl = QLabel("Kiat & Trik Pintar Krolix Download Manager")
        sub_lbl.setStyleSheet("font-size: 12px; color: #64748b;")
        title_vbox.addWidget(sub_lbl)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()

        self.lbl_counter = QLabel("Tip 1 dari 1")
        self.lbl_counter.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 600;")
        header_layout.addWidget(self.lbl_counter)

        layout.addLayout(header_layout)

        # Card container for Tip Content
        self.card = QFrame()
        self.card.setStyleSheet("""
            QFrame {
                background-color: #020408;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(16, 16, 16, 16)

        self.lbl_content = QLabel()
        self.lbl_content.setWordWrap(True)
        self.lbl_content.setStyleSheet("font-size: 13px; line-height: 1.5; color: #e2e8f0; background: transparent; border: none;")
        self.lbl_content.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        card_layout.addWidget(self.lbl_content)

        layout.addWidget(self.card, 1)

        # Bottom Controls
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        # Checkbox: Show tips on startup
        show_startup = self.db.get_setting("show_tips_on_startup", "true") == "true"
        self.chk_startup = QCheckBox("Tampilkan tip saat memulai")
        self.chk_startup.setChecked(show_startup)
        self.chk_startup.stateChanged.connect(self._on_startup_toggled)
        bottom_layout.addWidget(self.chk_startup)

        bottom_layout.addStretch()

        self.btn_prev = QPushButton("◄ Sebelumnya")
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.clicked.connect(self._prev_tip)
        bottom_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("Berikutnya ►")
        self.btn_next.setObjectName("accentBtn")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.clicked.connect(self._next_tip)
        bottom_layout.addWidget(self.btn_next)

        btn_close = QPushButton("Tutup")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.close)
        bottom_layout.addWidget(btn_close)

        layout.addLayout(bottom_layout)

    def _update_tip_display(self):
        if not self.tips:
            return
        total = len(self.tips)
        idx = self.current_index % total
        tip_text = self.tips[idx]
        self.lbl_content.setText(tip_text)
        self.lbl_counter.setText(f"Tip {idx + 1} dari {total}")
        self.db.set_setting("last_tip_index", str((idx + 1) % total))

    def _next_tip(self):
        self.current_index = (self.current_index + 1) % len(self.tips)
        self._update_tip_display()

    def _prev_tip(self):
        self.current_index = (self.current_index - 1 + len(self.tips)) % len(self.tips)
        self._update_tip_display()

    def _on_startup_toggled(self, state):
        is_checked = (state == Qt.CheckState.Checked.value or state == 2)
        self.db.set_setting("show_tips_on_startup", "true" if is_checked else "false")
