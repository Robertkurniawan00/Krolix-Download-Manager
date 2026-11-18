from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QHeaderView, QAbstractItemView, QCheckBox, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

from ..core.torrent_downloader import TorrentWorker
from ..utils.helpers import apply_windows_dark_titlebar

class TorrentInfoWorker(QThread):
    files_ready = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, source: str):
        super().__init__()
        self.source = source

    def run(self):
        try:
            # Assuming get_file_list is a static method that parses `aria2c --show-files`
            files = TorrentWorker.get_file_list(self.source)
            self.files_ready.emit(files)
        except Exception as e:
            self.error.emit(str(e))

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

class TorrentFileSelectorDialog(QDialog):
    files_selected = pyqtSignal(list)

    def __init__(self, torrent_source: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pilih File dalam Torrent")
        self.resize(800, 500)
        apply_windows_dark_titlebar(self)
        
        self.torrent_source = torrent_source
        self.all_files = []
        
        self._setup_style()
        self._init_ui()
        self._load_files()

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0b0f17;
                color: #e2e8f0;
                font-family: 'Segoe UI Variable Display', 'Segoe UI', -apple-system, sans-serif;
            }
            QTableWidget {
                background-color: #0f1522;
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 8px;
                gridline-color: rgba(255, 255, 255, 0.04);
                color: #e2e8f0;
                font-size: 13px;
                selection-background-color: rgba(255, 255, 255, 0.08);
                selection-color: #ffffff;
            }
            QTableWidget::item {
                padding: 4px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            }
            QHeaderView::section {
                background-color: #151b28;
                color: #94a3b8;
                font-weight: 600;
                font-size: 12px;
                padding: 8px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            QPushButton#FilterBtn {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                color: #cbd5e1;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton#FilterBtn:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QPushButton#PrimaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2b3648, stop:1 #1e2635);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 8px;
                color: #f8fafc;
                font-weight: 600;
                font-size: 13px;
                padding: 8px 18px;
            }
            QPushButton#PrimaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #37455c, stop:1 #273347);
                border: 1px solid rgba(255, 255, 255, 0.25);
            }
            QPushButton#SecondaryBtn {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                color: #cbd5e1;
                font-size: 13px;
                padding: 8px 16px;
            }
            QPushButton#SecondaryBtn:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QLabel#InfoLabel {
                color: #94a3b8;
                font-size: 13px;
            }
            QLabel#FooterLabel {
                color: #e2e8f0;
                font-weight: 600;
                font-size: 13px;
            }
        """)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Info Header
        self.lbl_info = QLabel("Memuat daftar file...")
        self.lbl_info.setObjectName("InfoLabel")
        root.addWidget(self.lbl_info)

        # Filters
        filter_row = QHBoxLayout()
        btn_sel_all = QPushButton("Pilih Semua")
        btn_sel_all.setObjectName("FilterBtn")
        btn_sel_all.clicked.connect(lambda: self._set_all_checked(True))
        
        btn_sel_none = QPushButton("Batalkan Semua")
        btn_sel_none.setObjectName("FilterBtn")
        btn_sel_none.clicked.connect(lambda: self._set_all_checked(False))
        
        btn_sel_vid = QPushButton("Video Saja")
        btn_sel_vid.setObjectName("FilterBtn")
        btn_sel_vid.clicked.connect(self._select_video_only)
        
        btn_sel_aud = QPushButton("Audio Saja")
        btn_sel_aud.setObjectName("FilterBtn")
        btn_sel_aud.clicked.connect(self._select_audio_only)

        filter_row.addWidget(btn_sel_all)
        filter_row.addWidget(btn_sel_none)
        filter_row.addWidget(btn_sel_vid)
        filter_row.addWidget(btn_sel_aud)
        filter_row.addStretch()
        root.addLayout(filter_row)

        # Table
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
        self.table.setColumnWidth(0, 40)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        root.addWidget(self.table, 1)

        # Footer & Actions
        footer_row = QHBoxLayout()
        self.lbl_footer = QLabel("Dipilih: 0 file (0 B dari 0 B total)")
        self.lbl_footer.setObjectName("FooterLabel")
        footer_row.addWidget(self.lbl_footer)
        footer_row.addStretch()

        btn_cancel = QPushButton("Batal")
        btn_cancel.setObjectName("SecondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_download = QPushButton("▶ Mulai Download")
        self.btn_download.setObjectName("PrimaryBtn")
        self.btn_download.clicked.connect(self._on_download_clicked)
        self.btn_download.setEnabled(False)

        footer_row.addWidget(btn_cancel)
        footer_row.addWidget(self.btn_download)
        root.addLayout(footer_row)

    def _load_files(self):
        self._worker = TorrentInfoWorker(self.torrent_source)
        self._worker.files_ready.connect(self._on_files_ready)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_files_ready(self, files: list):
        self.all_files = files
        self.lbl_info.setText(f"Menampilkan {len(files)} file.")
        
        self.table.setRowCount(len(files))
        for row, f in enumerate(files):
            # Checkbox
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setContentsMargins(10, 0, 0, 0)
            chk_box = QCheckBox()
            chk_box.setChecked(True)
            chk_box.stateChanged.connect(self._update_footer)
            chk_layout.addWidget(chk_box)
            chk_widget.chk_box = chk_box  # Store reference
            self.table.setCellWidget(row, 0, chk_widget)

            # Name
            name_item = QTableWidgetItem(f.get("name", ""))
            name_item.setData(Qt.ItemDataRole.UserRole, f)
            self.table.setItem(row, 1, name_item)

            # Size
            size = f.get("size", 0)
            size_item = QTableWidgetItem(format_size(size))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, size_item)

            # Path
            path_item = QTableWidgetItem(f.get("path", ""))
            path_item.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 3, path_item)

        self.btn_download.setEnabled(True)
        self._update_footer()

    def _on_error(self, msg: str):
        self.lbl_info.setText(f"Gagal memuat file: {msg}")
        self.lbl_info.setStyleSheet("color: #ef4444;")

    def _set_all_checked(self, state: bool):
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if w and hasattr(w, 'chk_box'):
                w.chk_box.setChecked(state)
        self._update_footer()

    def _select_video_only(self):
        vid_exts = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.ts'}
        self._filter_by_ext(vid_exts)

    def _select_audio_only(self):
        aud_exts = {'.mp3', '.flac', '.wav', '.aac', '.m4a', '.ogg', '.wma'}
        self._filter_by_ext(aud_exts)

    def _filter_by_ext(self, exts: set):
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            item = self.table.item(row, 1)
            if w and hasattr(w, 'chk_box') and item:
                f_data = item.data(Qt.ItemDataRole.UserRole)
                ext = f_data.get("ext", "").lower()
                # Check if it has the extension
                # Alternatively check name ending
                name = f_data.get("name", "").lower()
                is_match = any(name.endswith(e) for e in exts)
                w.chk_box.setChecked(is_match)
        self._update_footer()

    def _update_footer(self):
        selected_count = 0
        selected_size = 0
        total_size = 0

        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if not item: continue
            f_data = item.data(Qt.ItemDataRole.UserRole)
            size = f_data.get("size", 0)
            total_size += size
            
            w = self.table.cellWidget(row, 0)
            if w and hasattr(w, 'chk_box') and w.chk_box.isChecked():
                selected_count += 1
                selected_size += size

        self.lbl_footer.setText(f"Dipilih: {selected_count} file ({format_size(selected_size)} dari {format_size(total_size)} total)")
        self.btn_download.setEnabled(selected_count > 0)

    def _on_download_clicked(self):
        selected_indices = []
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            item = self.table.item(row, 1)
            if w and hasattr(w, 'chk_box') and w.chk_box.isChecked() and item:
                f_data = item.data(Qt.ItemDataRole.UserRole)
                if "index" in f_data:
                    selected_indices.append(f_data["index"])
        
        self.selected_indices = selected_indices
        self.files_selected.emit(selected_indices)
        self.accept()

    def get_selected_indices(self) -> list:
        return getattr(self, "selected_indices", [])

