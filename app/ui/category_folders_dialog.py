"""
Krolix Download Manager - Category Folders Customization Dialog
Allows users to configure specific destination directories for each file category
(Videos, Compressed, Programs, Music, Documents, Torrents).
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QFrame, QGridLayout
)
from ..core.database import Database
from ..utils.helpers import apply_windows_dark_titlebar, get_default_download_dir


class CategoryFoldersDialog(QDialog):
    CATEGORIES = [
        ("video", "Videos (Video & Film)", "Downloads/Videos"),
        ("compressed", "Compressed (Arsip .zip, .rar, .iso)", "Downloads/Compressed"),
        ("programs", "Programs (Aplikasi .exe, .msi, .apk)", "Downloads/Programs"),
        ("music", "Music (Musik & Audio)", "Downloads/Music"),
        ("documents", "Documents (Dokumen PDF, Office)", "Downloads/Documents"),
        ("torrents", "Torrents (File & Magnet BitTorrent)", "Downloads/Torrents"),
    ]

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db or Database.get_instance()
        self.setWindowTitle("Atur Jalur Folder Kategori")
        self.setFixedWidth(640)
        apply_windows_dark_titlebar(self)
        self._inputs = {}
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        self.setStyleSheet("""
            QDialog {
                background-color: #0b0f17;
                color: #e2e8f0;
            }
            QLabel {
                color: #cbd5e1;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #050811;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 6px 10px;
                color: #f1f5f9;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #10b981;
            }
            QPushButton {
                background-color: #0f1724;
                border: 1px solid #1b273d;
                border-radius: 5px;
                padding: 6px 14px;
                color: #e2e8f0;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #162235;
                border-color: #2563eb;
            }
            QPushButton#SaveBtn {
                background-color: #10b981;
                color: #020617;
                border: none;
                font-weight: 600;
            }
            QPushButton#SaveBtn:hover {
                background-color: #34d399;
            }
        """)

        # Header info
        lbl_head = QLabel("Konfigurasi Jalur Folder Otomatis")
        lbl_head.setStyleSheet("font-size: 14px; font-weight: 700; color: #10b981;")
        root.addWidget(lbl_head)

        lbl_desc = QLabel(
            "Tentukan folder penyimpanan khusus untuk setiap kategori unduhan. "
            "Jika dibiarkan kosong, unduhan akan otomatis masuk ke subfolder default."
        )
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        root.addWidget(lbl_desc)

        # Form grid
        grid_frame = QFrame()
        grid_frame.setStyleSheet("""
            QFrame {
                background-color: #070a0f;
                border: 1px solid #1b273d;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        grid = QGridLayout(grid_frame)
        grid.setSpacing(10)

        base_dir = self.db.get_setting("download_dir", "") or self.db.get_setting("default_save_path", get_default_download_dir())

        for row, (cat_id, label_text, default_rel) in enumerate(self.CATEGORIES):
            lbl = QLabel(label_text + ":")
            lbl.setStyleSheet("font-weight: 600; color: #cbd5e1;")
            grid.addWidget(lbl, row, 0)

            cat_key = f"category_dir_{cat_id}"
            current_val = self.db.get_setting(cat_key, "").strip()
            if not current_val:
                sub = "Videos" if cat_id == "video" else ("Compressed" if cat_id == "compressed" else cat_id.capitalize())
                current_val = os.path.join(base_dir, sub)

            txt = QLineEdit(current_val)
            self._inputs[cat_id] = txt
            grid.addWidget(txt, row, 1)

            btn_b = QPushButton("Browse...")
            btn_b.clicked.connect(lambda checked, c=cat_id: self._browse_cat(c))
            grid.addWidget(btn_b, row, 2)

        root.addWidget(grid_frame)

        # Bottom buttons
        btn_box = QHBoxLayout()
        btn_reset = QPushButton("Reset ke Default")
        btn_reset.clicked.connect(self._reset_defaults)
        btn_box.addWidget(btn_reset)
        btn_box.addStretch()

        btn_cancel = QPushButton("Batal")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("Simpan")
        btn_save.setObjectName("SaveBtn")
        btn_save.clicked.connect(self._save)
        btn_box.addWidget(btn_save)

        root.addLayout(btn_box)

    def _browse_cat(self, cat_id: str):
        txt = self._inputs.get(cat_id)
        if not txt:
            return
        initial = txt.text().strip()
        dir_selected = QFileDialog.getExistingDirectory(self, f"Pilih Folder {cat_id.capitalize()}", initial)
        if dir_selected:
            txt.setText(os.path.abspath(dir_selected))

    def _reset_defaults(self):
        base_dir = self.db.get_setting("download_dir", "") or self.db.get_setting("default_save_path", get_default_download_dir())
        for cat_id, _, _ in self.CATEGORIES:
            sub = "Videos" if cat_id == "video" else ("Compressed" if cat_id == "compressed" else cat_id.capitalize())
            target = os.path.join(base_dir, sub)
            if cat_id in self._inputs:
                self._inputs[cat_id].setText(target)

    def _save(self):
        for cat_id, txt in self._inputs.items():
            path_val = txt.text().strip()
            cat_key = f"category_dir_{cat_id}"
            if path_val:
                os.makedirs(path_val, exist_ok=True)
                self.db.set_setting(cat_key, path_val)
            else:
                self.db.set_setting(cat_key, "")
        self.accept()
