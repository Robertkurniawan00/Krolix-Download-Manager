"""
Krolix Download Manager - Dedicated BitTorrent & Magnet Add Dialog
Allows adding downloads from .torrent files or Magnet links with full file inspection,
selective download checkboxes, and custom destination folder selection.
"""

import os
from typing import Optional, List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QCheckBox, QWidget, QFrame,
    QMessageBox, QApplication, QSpinBox
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ..core.downloader import DownloadEngine
from ..core.torrent_downloader import TorrentWorker
from ..utils.helpers import format_bytes, sanitize_filename, apply_windows_dark_titlebar, get_app_icon


class TorrentMetaWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, source: str, headers: Optional[dict] = None):
        super().__init__()
        self.source = source
        self.headers = headers or {}

    def run(self):
        try:
            info = TorrentWorker.get_torrent_info(self.source, headers=self.headers)
            self.finished.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class TorrentAddDialog(QDialog):
    """
    Dedicated BitTorrent Add Dialog.
    Styling matches Windows 11 Fluent Dark UI:
    - Glowing emerald top rim line
    - BitTorrent / Magnet source input with Browse / Paste buttons
    - Editable torrent name & destination folder
    - Live selective file table with filter pills (Video, Audio, Select All)
    - Action buttons: 'Download Now', 'Download Later', 'Cancel'
    """
    def __init__(
        self,
        engine: DownloadEngine,
        initial_source: str = "",
        is_magnet: bool = False,
        is_magnet_mode: bool = False,
        default_save_dir: str = "",
        parent=None,
        headers: Optional[dict] = None,
        **kwargs
    ):
        super().__init__(parent)
        self.engine = engine
        self.source = initial_source.strip()
        self.headers = dict(headers or kwargs.get("headers") or {})
        self.is_magnet_mode = is_magnet or is_magnet_mode or kwargs.get("is_magnet", False) or self.source.startswith("magnet:")
        self.default_save_dir = default_save_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        
        # Auto subfolder for Torrents
        auto_subfolders = self.engine.db.get_setting("category_subfolders", "true") == "true"
        if auto_subfolders:
            self.default_save_dir = os.path.join(self.default_save_dir, "Torrents")
        os.makedirs(self.default_save_dir, exist_ok=True)

        self.result_task = None
        self.start_immediately = True
        self.all_files = []
        self.selected_indices = None
        self.total_bytes = -1

        title = "Tambah Magnet Link" if self.is_magnet_mode else "Tambah File BitTorrent (.torrent)"
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(760, 520)
        self.setMinimumSize(640, 420)
        apply_windows_dark_titlebar(self)

        app_icon = get_app_icon()
        if app_icon:
            self.setWindowIcon(app_icon)

        self._setup_style()
        self._init_ui()

        if self.source:
            self._load_torrent_metadata()

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #070a0f;
                border: 1px solid #1b273d;
                border-radius: 8px;
            }
            QLabel {
                color: #cbd5e1;
                font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #0b0f17;
                border: 1px solid #1b273d;
                border-radius: 6px;
                padding: 7px 10px;
                color: #f1f5f9;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #10b981;
                background-color: #0d1320;
            }
            QTableWidget {
                background-color: #0b0f17;
                border: 1px solid #1b273d;
                border-radius: 6px;
                gridline-color: rgba(255, 255, 255, 0.04);
                color: #e2e8f0;
                font-size: 12px;
                selection-background-color: rgba(16, 185, 129, 0.15);
                selection-color: #ffffff;
            }
            QTableWidget::item {
                padding: 4px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            }
            QHeaderView::section {
                background-color: #0d1117;
                color: #94a3b8;
                font-weight: 600;
                font-size: 11px;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #1b273d;
            }
            QPushButton#FilterBtn {
                background-color: #0f1724;
                border: 1px solid #1b273d;
                border-radius: 4px;
                color: #94a3b8;
                font-size: 11px;
                padding: 4px 10px;
            }
            QPushButton#FilterBtn:hover {
                background-color: #151f30;
                color: #f1f5f9;
                border-color: #2563eb;
            }
            QPushButton#BrowseBtn {
                background-color: #0f1724;
                border: 1px solid #1b273d;
                border-radius: 5px;
                color: #cbd5e1;
                font-size: 11px;
                font-weight: 600;
                padding: 6px 12px;
            }
            QPushButton#BrowseBtn:hover {
                background-color: #151f30;
                color: #ffffff;
                border-color: #2563eb;
            }
            QPushButton#PrimaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #059669);
                border: none;
                border-radius: 6px;
                color: #ffffff;
                font-weight: 600;
                font-size: 12px;
                padding: 8px 22px;
            }
            QPushButton#PrimaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34d399, stop:1 #10b981);
            }
            QPushButton#SecondaryBtn {
                background-color: #0f1724;
                border: 1px solid #1b273d;
                border-radius: 6px;
                color: #e2e8f0;
                font-size: 12px;
                padding: 8px 16px;
            }
            QPushButton#SecondaryBtn:hover {
                background-color: #1b273d;
            }
        """)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 16)
        root.setSpacing(0)

        # 1. Glowing Emerald Top Rim Line
        rim_line = QFrame()
        rim_line.setFixedHeight(2)
        rim_line.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 transparent,
                stop:0.25 rgba(16, 185, 129, 0.4),
                stop:0.5 #10b981,
                stop:0.75 rgba(16, 185, 129, 0.4),
                stop:1 transparent);
            border: none;
        """)
        root.addWidget(rim_line)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 0)
        layout.setSpacing(12)
        root.addWidget(content, 1)

        # Header Title
        header_row = QHBoxLayout()
        lbl_head = QLabel("Unduhan BitTorrent / Magnet" if self.is_magnet_mode else "Unduhan File BitTorrent (.torrent)")
        lbl_head.setStyleSheet("font-size: 14px; font-weight: 700; color: #10b981;")
        header_row.addWidget(lbl_head)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Source input row
        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        lbl_src = QLabel("Sumber:" if not self.is_magnet_mode else "Magnet URL:")
        lbl_src.setFixedWidth(80)
        lbl_src.setStyleSheet("font-weight: 600; color: #94a3b8;")
        source_row.addWidget(lbl_src)

        self.txt_source = QLineEdit(self.source)
        if self.is_magnet_mode:
            self.txt_source.setPlaceholderText("magnet:?xt=urn:btih:... atau URL .torrent")
        else:
            self.txt_source.setPlaceholderText("Pilih file .torrent lokal atau URL .torrent...")
        self.txt_source.textChanged.connect(self._on_source_text_changed)
        source_row.addWidget(self.txt_source, 1)

        if not self.is_magnet_mode:
            btn_browse_file = QPushButton("Pilih File...")
            btn_browse_file.setObjectName("BrowseBtn")
            btn_browse_file.clicked.connect(self._browse_torrent_file)
            source_row.addWidget(btn_browse_file)
        else:
            btn_paste = QPushButton("Tempel")
            btn_paste.setObjectName("BrowseBtn")
            btn_paste.clicked.connect(self._paste_magnet)
            source_row.addWidget(btn_paste)

        layout.addLayout(source_row)

        # Name row
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        lbl_nm = QLabel("Nama Paket:")
        lbl_nm.setFixedWidth(80)
        lbl_nm.setStyleSheet("font-weight: 600; color: #94a3b8;")
        name_row.addWidget(lbl_nm)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Nama folder / file unduhan...")
        name_row.addWidget(self.txt_name, 1)
        layout.addLayout(name_row)

        # Save to row
        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        lbl_save = QLabel("Simpan Ke:")
        lbl_save.setFixedWidth(80)
        lbl_save.setStyleSheet("font-weight: 600; color: #94a3b8;")
        save_row.addWidget(lbl_save)

        self.txt_save_path = QLineEdit(self.default_save_dir)
        save_row.addWidget(self.txt_save_path, 1)

        btn_browse_folder = QPushButton("Folder...")
        btn_browse_folder.setObjectName("BrowseBtn")
        btn_browse_folder.clicked.connect(self._browse_folder)
        save_row.addWidget(btn_browse_folder)
        layout.addLayout(save_row)

        # Masa Seeding row (1-31 Hari)
        seed_row = QHBoxLayout()
        seed_row.setSpacing(8)
        lbl_seed = QLabel("Masa Seeding:")
        lbl_seed.setFixedWidth(80)
        lbl_seed.setStyleSheet("font-weight: 600; color: #94a3b8;")
        seed_row.addWidget(lbl_seed)

        self.spn_seed_days = QSpinBox()
        self.spn_seed_days.setRange(1, 31)
        self.spn_seed_days.setValue(3)
        self.spn_seed_days.setSuffix(" Hari")
        self.spn_seed_days.setFixedWidth(110)
        self.spn_seed_days.setStyleSheet("""
            QSpinBox {
                background-color: #0b0f17;
                border: 1px solid #1b273d;
                border-radius: 6px;
                padding: 6px 10px;
                color: #10b981;
                font-size: 12px;
                font-weight: 600;
            }
        """)
        seed_row.addWidget(self.spn_seed_days)

        lbl_seed_desc = QLabel("(Jika rasio tercapai sebelum masa seeding habis, upload di-throttle ke 0 B/s)")
        lbl_seed_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        seed_row.addWidget(lbl_seed_desc)
        seed_row.addStretch()
        layout.addLayout(seed_row)

        # Telemetry info card
        self.info_card = QFrame()
        self.info_card.setStyleSheet("""
            QFrame {
                background-color: #0b0f17;
                border: 1px solid #151f30;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        info_layout = QHBoxLayout(self.info_card)
        info_layout.setContentsMargins(10, 6, 10, 6)
        info_layout.setSpacing(14)

        self.lbl_status = QLabel("● Memeriksa info torrent...")
        self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        info_layout.addWidget(self.lbl_status)
        info_layout.addStretch()

        self.lbl_size = QLabel("Total: --")
        self.lbl_size.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        info_layout.addWidget(self.lbl_size)

        self.lbl_selected_size = QLabel("Dipilih: --")
        self.lbl_selected_size.setStyleSheet("color: #34d399; font-size: 11px; font-weight: 600;")
        info_layout.addWidget(self.lbl_selected_size)
        layout.addWidget(self.info_card)

        # Filter buttons row (for multi-file torrents)
        self.filter_container = QWidget()
        filter_layout = QHBoxLayout(self.filter_container)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(6)

        btn_sel_all = QPushButton("Pilih Semua")
        btn_sel_all.setObjectName("FilterBtn")
        btn_sel_all.clicked.connect(lambda: self._set_all_checked(True))
        filter_layout.addWidget(btn_sel_all)

        btn_sel_none = QPushButton("Batalkan Semua")
        btn_sel_none.setObjectName("FilterBtn")
        btn_sel_none.clicked.connect(lambda: self._set_all_checked(False))
        filter_layout.addWidget(btn_sel_none)

        btn_sel_vid = QPushButton("Video Saja")
        btn_sel_vid.setObjectName("FilterBtn")
        btn_sel_vid.clicked.connect(self._select_video_only)
        filter_layout.addWidget(btn_sel_vid)

        btn_sel_aud = QPushButton("Audio Saja")
        btn_sel_aud.setObjectName("FilterBtn")
        btn_sel_aud.clicked.connect(self._select_audio_only)
        filter_layout.addWidget(btn_sel_aud)

        filter_layout.addStretch()
        layout.addWidget(self.filter_container)

        # File List Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Pilih", "Nama File", "Ukuran", "Path"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 36)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.table, 1)

        # Action Buttons Footer
        footer = QHBoxLayout()
        footer.setContentsMargins(20, 10, 20, 0)
        footer.setSpacing(10)

        self.btn_cancel = QPushButton("Batal")
        self.btn_cancel.setObjectName("SecondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        footer.addWidget(self.btn_cancel)

        footer.addStretch()

        self.btn_download_later = QPushButton("Download Nanti")
        self.btn_download_later.setObjectName("SecondaryBtn")
        self.btn_download_later.clicked.connect(lambda: self._create_and_finish(start_now=False))
        footer.addWidget(self.btn_download_later)

        self.btn_download_now = QPushButton("▶ Mulai Download")
        self.btn_download_now.setObjectName("PrimaryBtn")
        self.btn_download_now.clicked.connect(lambda: self._create_and_finish(start_now=True))
        footer.addWidget(self.btn_download_now)

        root.addLayout(footer)

    def _browse_torrent_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Pilih File BitTorrent", "", "Torrent Files (*.torrent);;All Files (*.*)"
        )
        if file_path:
            self.txt_source.setText(file_path)
            self._load_torrent_metadata()

    def _paste_magnet(self):
        text = QApplication.clipboard().text().strip()
        if text:
            self.txt_source.setText(text)
            self._load_torrent_metadata()

    def _browse_folder(self):
        cur = self.txt_save_path.text() or self.default_save_dir
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Tujuan", cur)
        if folder:
            self.txt_save_path.setText(folder)

    def _on_source_text_changed(self):
        txt = self.txt_source.text().strip()
        if txt.startswith("magnet:") or txt.lower().endswith(".torrent") or (os.path.isfile(txt) and txt.lower().endswith(".torrent")):
            self._load_torrent_metadata()

    def _load_torrent_metadata(self):
        src = self.txt_source.text().strip()
        if not src:
            return

        self.lbl_status.setText("● Memeriksa paket BitTorrent...")
        self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.btn_download_now.setEnabled(False)
        self.btn_download_later.setEnabled(False)

        self.worker = TorrentMetaWorker(src, headers=self.headers)
        self.worker.finished.connect(self._on_meta_ready)
        self.worker.error.connect(self._on_meta_error)
        self.worker.start()

    def _on_meta_ready(self, info: dict):
        name = info.get("name") or "torrent_download"
        if not self.txt_name.text().strip() or self.txt_name.text() == "torrent_download":
            self.txt_name.setText(name)

        tot_bytes = info.get("total_bytes", -1)
        self.total_bytes = tot_bytes
        self.lbl_size.setText(f"Total: <b>{format_bytes(tot_bytes) if tot_bytes > 0 else 'Swarm Metadata'}</b>")

        files = info.get("files", [])
        self.all_files = files

        if files:
            self.filter_container.setVisible(True)
            self.table.setVisible(True)
            self.table.setRowCount(len(files))
            for row, f in enumerate(files):
                chk_widget = QWidget()
                chk_layout = QHBoxLayout(chk_widget)
                chk_layout.setContentsMargins(8, 0, 0, 0)
                chk_box = QCheckBox()
                chk_box.setChecked(True)
                chk_box.stateChanged.connect(self._update_selection_stats)
                chk_layout.addWidget(chk_box)
                chk_widget.chk_box = chk_box
                self.table.setCellWidget(row, 0, chk_widget)

                name_item = QTableWidgetItem(f.get("name", ""))
                name_item.setData(Qt.ItemDataRole.UserRole, f)
                self.table.setItem(row, 1, name_item)

                size_val = f.get("size", 0)
                sz_item = QTableWidgetItem(format_bytes(size_val))
                sz_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, 2, sz_item)

                path_item = QTableWidgetItem(f.get("path", ""))
                path_item.setForeground(QColor("#94a3b8"))
                self.table.setItem(row, 3, path_item)

            self.lbl_status.setText(f"● Siap mengunduh ({len(files)} file terdeteksi)")
            self.lbl_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
            self._update_selection_stats()
        else:
            self.filter_container.setVisible(False)
            self.table.setVisible(False)
            self.lbl_status.setText("● Magnet Swarm siap terhubung")
            self.lbl_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
            self.lbl_selected_size.setText("Mode: Unduh Seluruh Isi Swarm")

        self.btn_download_now.setEnabled(True)
        self.btn_download_later.setEnabled(True)

    def _on_meta_error(self, err_msg: str):
        self.lbl_status.setText(f"● Gagal membaca torrent: {err_msg}")
        self.lbl_status.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: 600;")
        self.btn_download_now.setEnabled(True)
        self.btn_download_later.setEnabled(True)

    def _set_all_checked(self, checked: bool):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if w and hasattr(w, "chk_box"):
                w.chk_box.setChecked(checked)
        self._update_selection_stats()

    def _select_video_only(self):
        exts = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts"}
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            item = self.table.item(r, 1)
            if w and hasattr(w, "chk_box") and item:
                f_data = item.data(Qt.ItemDataRole.UserRole)
                name = (f_data.get("name") or "").lower()
                w.chk_box.setChecked(any(name.endswith(e) for e in exts))
        self._update_selection_stats()

    def _select_audio_only(self):
        exts = {".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".wma"}
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            item = self.table.item(r, 1)
            if w and hasattr(w, "chk_box") and item:
                f_data = item.data(Qt.ItemDataRole.UserRole)
                name = (f_data.get("name") or "").lower()
                w.chk_box.setChecked(any(name.endswith(e) for e in exts))
        self._update_selection_stats()

    def _update_selection_stats(self):
        sel_count = 0
        sel_bytes = 0
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if w and hasattr(w, "chk_box") and w.chk_box.isChecked():
                item = self.table.item(r, 1)
                if item:
                    f_data = item.data(Qt.ItemDataRole.UserRole)
                    sel_bytes += f_data.get("size", 0)
                sel_count += 1
        self.lbl_selected_size.setText(f"Dipilih: <b>{sel_count} file</b> ({format_bytes(sel_bytes)})")
        self.btn_download_now.setEnabled(sel_count > 0 or not self.all_files)
        self.btn_download_later.setEnabled(sel_count > 0 or not self.all_files)

    def _create_and_finish(self, start_now: bool):
        source = self.txt_source.text().strip()
        if not source:
            QMessageBox.warning(self, "Input Kosong", "Silakan masukkan file .torrent atau tautan magnet.")
            return

        if not self.engine.db.is_torrent_enabled():
            QMessageBox.warning(
                self,
                "BitTorrent Dinonaktifkan",
                "Fitur BitTorrent dinonaktifkan dalam Pengaturan Krolix Download Manager.\n\n"
                "Untuk mengunduh, buka menu Options dan beri centang pada 'Aktifkan Dukungan BitTorrent / Magnet'."
            )
            return

        save_dir = self.txt_save_path.text().strip() or self.default_save_dir
        os.makedirs(save_dir, exist_ok=True)

        filename = self.txt_name.text().strip() or "torrent_download"
        filename = sanitize_filename(filename)

        headers = dict(self.headers)
        headers["seed_duration_days"] = self.spn_seed_days.value()
        # Collect selected files if multi-file
        selected = []
        if self.all_files:
            for r in range(self.table.rowCount()):
                w = self.table.cellWidget(r, 0)
                if w and hasattr(w, "chk_box") and w.chk_box.isChecked():
                    item = self.table.item(r, 1)
                    if item:
                        f_data = item.data(Qt.ItemDataRole.UserRole)
                        if "index" in f_data:
                            selected.append(f_data["index"])
            if selected and len(selected) < len(self.all_files):
                headers["selected_files"] = selected

        self.start_immediately = start_now
        tb = self.total_bytes if self.total_bytes > 0 else None

        from ..core.database import Database as _DB
        zero_log = str(_DB.get_instance().get_setting("zero_log_mode", "false")).lower() in ("true", "1", "yes")

        try:
            self.result_task = self.engine.create_task(
                url=source,
                save_dir=save_dir,
                filename=filename,
                connections=8,
                headers=headers,
                total_bytes=tb,
                resumable=True,
                zero_log=zero_log
            )
            self.result_task.category = "Torrents"
            if hasattr(self.engine, "db") and not zero_log:
                self.engine.db.save_task(self.result_task)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Gagal Menambahkan Unduhan", f"Terjadi kesalahan:\n{e}")

    def closeEvent(self, event):
        if hasattr(self, "_meta_worker") and self._meta_worker and self._meta_worker.isRunning():
            self._meta_worker.quit()
            self._meta_worker.wait(1500)
        super().closeEvent(event)
