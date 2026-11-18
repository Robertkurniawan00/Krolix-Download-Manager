from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QComboBox,
    QFrame, QApplication, QMessageBox, QAbstractItemView, QListWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

from ..core.dht_crawler import TorrentSearchEngine
from ..utils.helpers import apply_windows_dark_titlebar


class DHTSearchWorker(QThread):
    results_ready = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, query: str):
        super().__init__()
        self.query = query

    def run(self):
        try:
            engine = TorrentSearchEngine()
            results = engine.search(self.query)
            self.results_ready.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class MetadataResolveWorker(QThread):
    resolved = pyqtSignal(dict)
    failed = pyqtSignal()

    def __init__(self, info_hash: str):
        super().__init__()
        self.info_hash = info_hash

    def run(self):
        try:
            engine = TorrentSearchEngine()
            meta = engine.resolve(self.info_hash)
            if meta:
                self.resolved.emit(meta)
            else:
                self.failed.emit()
        except Exception:
            self.failed.emit()


class DHTSearchDialog(QDialog):
    download_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cari Torrent (DHT & BTDIG)")
        self.resize(900, 600)
        self.setMinimumSize(800, 500)
        
        apply_windows_dark_titlebar(self)

        self._search_worker = None
        self._resolve_worker = None
        self._all_results = []
        self._current_selected = None

        self._setup_style()
        self._init_ui()

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0b0f17;
                color: #e2e8f0;
                font-family: 'Segoe UI Variable Display', 'Segoe UI', -apple-system, sans-serif;
            }
            QLineEdit, QComboBox {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                color: #ffffff;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #475569;
                background-color: rgba(255, 255, 255, 0.08);
            }
            QTableWidget, QListWidget {
                background-color: #0f1522;
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 8px;
                gridline-color: rgba(255, 255, 255, 0.04);
                color: #e2e8f0;
                font-size: 13px;
                selection-background-color: rgba(255, 255, 255, 0.08);
                selection-color: #ffffff;
            }
            QTableWidget::item, QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QHeaderView::section {
                background-color: #151b28;
                color: #94a3b8;
                font-weight: 600;
                padding: 6px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            QFrame#FileInfoPanel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #151b28, stop:1 #0f1522);
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 8px;
                padding: 10px;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                color: #cbd5e1;
                font-size: 12px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QPushButton#PrimaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2b3648, stop:1 #1e2635);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 8px;
                color: #f8fafc;
                font-weight: 600;
            }
            QPushButton#PrimaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #37455c, stop:1 #273347);
                border: 1px solid rgba(255, 255, 255, 0.25);
            }
            QPushButton#BlueBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #334155, stop:1 #1e293b);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 8px;
                color: #f8fafc;
                font-weight: 600;
            }
            QPushButton#BlueBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #475569, stop:1 #334155);
                border: 1px solid rgba(255, 255, 255, 0.25);
            }
        """)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # 1. Search Bar
        search_row = QHBoxLayout()
        self.inp_search = QLineEdit()
        self.inp_search.setPlaceholderText("Cari judul, nama file, atau hash info...")
        self.inp_search.returnPressed.connect(self._do_search)
        
        self.combo_source = QComboBox()
        self.combo_source.addItems(["Semua Sumber", "BTDIG Only", "DHT Only"])
        
        self.btn_search = QPushButton("Cari")
        self.btn_search.setObjectName("PrimaryBtn")
        self.btn_search.clicked.connect(self._do_search)

        search_row.addWidget(self.inp_search, 1)
        search_row.addWidget(self.combo_source)
        search_row.addWidget(self.btn_search)
        root.addLayout(search_row)

        # 2. Results Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Nama", "Ukuran", "Seeds", "Sumber", "Hash"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        root.addWidget(self.table, 1)

        # 3. File Info Panel (Hidden initially)
        self.file_panel = QFrame()
        self.file_panel.setObjectName("FileInfoPanel")
        self.file_panel.setVisible(False)
        fp_layout = QVBoxLayout(self.file_panel)
        fp_layout.setContentsMargins(10, 10, 10, 10)
        
        fp_top = QHBoxLayout()
        fp_top.addWidget(QLabel("Metadata File:"))
        fp_top.addStretch()
        self.btn_resolve = QPushButton("Resolve Metadata")
        self.btn_resolve.clicked.connect(self._on_resolve_clicked)
        fp_top.addWidget(self.btn_resolve)
        fp_layout.addLayout(fp_top)
        
        self.file_list = QListWidget()
        fp_layout.addWidget(self.file_list)
        root.addWidget(self.file_panel)

        # 4. Action Buttons Bottom
        bottom_row = QHBoxLayout()
        self.lbl_status = QLabel("Siap.")
        self.lbl_status.setStyleSheet("color: #94a3b8;")
        bottom_row.addWidget(self.lbl_status)
        bottom_row.addStretch()
        
        self.btn_copy = QPushButton("Salin Magnet")
        self.btn_copy.clicked.connect(self._on_copy_clicked)
        
        self.btn_select_file = QPushButton("Pilih File...")
        self.btn_select_file.setObjectName("BlueBtn")
        self.btn_select_file.clicked.connect(self._on_select_file_clicked)
        
        self.btn_download = QPushButton("Download")
        self.btn_download.setObjectName("PrimaryBtn")
        self.btn_download.clicked.connect(self._on_download_clicked)
        
        self.btn_close = QPushButton("Tutup")
        self.btn_close.clicked.connect(self.accept)

        bottom_row.addWidget(self.btn_copy)
        bottom_row.addWidget(self.btn_select_file)
        bottom_row.addWidget(self.btn_download)
        bottom_row.addWidget(self.btn_close)
        root.addLayout(bottom_row)

    def _do_search(self):
        query = self.inp_search.text().strip()
        if not query:
            return

        self.btn_search.setEnabled(False)
        self.lbl_status.setText("Mencari...")
        self.table.setRowCount(0)
        self.file_panel.setVisible(False)

        self._search_worker = DHTSearchWorker(query)
        self._search_worker.results_ready.connect(self._on_search_done)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.start()

    def _on_search_done(self, results):
        self.btn_search.setEnabled(True)
        self._all_results = results
        self.lbl_status.setText(f"Ditemukan {len(results)} hasil.")
        self._populate_table(results)

    def _on_search_error(self, err_msg):
        self.btn_search.setEnabled(True)
        self.lbl_status.setText(f"Error: {err_msg}")

    def _populate_table(self, items):
        source_filter = self.combo_source.currentText()
        filtered = []
        for it in items:
            src = it.get('source', '')
            if source_filter == "BTDIG Only" and src != "BTDIG":
                continue
            if source_filter == "DHT Only" and src != "DHT":
                continue
            filtered.append(it)

        self.table.setRowCount(len(filtered))
        for row, item in enumerate(filtered):
            # Nama
            n_item = QTableWidgetItem(item.get("name", "Unknown"))
            n_item.setData(Qt.ItemDataRole.UserRole, item)
            self.table.setItem(row, 0, n_item)

            # Ukuran
            s_item = QTableWidgetItem(item.get("size_formatted", "--"))
            self.table.setItem(row, 1, s_item)

            # Seeds
            sd_item = QTableWidgetItem(f"▲ {item.get('seeds', 0):,}")
            sd_item.setForeground(QColor("#86efac"))
            self.table.setItem(row, 2, sd_item)

            # Sumber
            src_item = QTableWidgetItem(item.get("source", "DHT"))
            self.table.setItem(row, 3, src_item)
            
            # Hash
            h_item = QTableWidgetItem(item.get("info_hash", "")[:12] + "...")
            h_item.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 4, h_item)

    def _on_selection_changed(self):
        row = self.table.currentRow()
        if row < 0:
            self._current_selected = None
            self.file_panel.setVisible(False)
            return
        
        self._current_selected = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _on_row_double_clicked(self):
        self._on_selection_changed()
        if self._current_selected:
            self.file_panel.setVisible(True)
            self.file_list.clear()
            
            files = self._current_selected.get('files', [])
            if files:
                for f in files:
                    self.file_list.addItem(f"{f.get('name')} ({f.get('size_formatted', '')})")
                self.btn_resolve.setEnabled(False)
            else:
                self.file_list.addItem("Metadata belum tersedia. Klik Resolve Metadata.")
                self.btn_resolve.setEnabled(True)

    def _on_resolve_clicked(self):
        if not self._current_selected:
            return
            
        hash_val = self._current_selected.get('info_hash')
        if not hash_val:
            return

        self.btn_resolve.setEnabled(False)
        self.file_list.clear()
        self.file_list.addItem("Resolving metadata... (bisa memakan waktu beberapa saat)")
        
        self._resolve_worker = MetadataResolveWorker(hash_val)
        self._resolve_worker.resolved.connect(self._on_resolved)
        self._resolve_worker.failed.connect(self._on_resolve_failed)
        self._resolve_worker.start()

    def _on_resolved(self, meta):
        self.file_list.clear()
        files = meta.get('files', [])
        if files:
            for f in files:
                self.file_list.addItem(f"{f.get('name')} ({f.get('size_formatted', '')})")
        else:
            self.file_list.addItem("Tidak ada file ditemukan dalam metadata.")
            
        # Update current selected item cache
        if self._current_selected:
            self._current_selected['files'] = files

    def _on_resolve_failed(self):
        self.btn_resolve.setEnabled(True)
        self.file_list.clear()
        self.file_list.addItem("Gagal mendapatkan metadata.")

    def _get_magnet(self) -> str:
        if not self._current_selected:
            return ""
        magnet = self._current_selected.get('magnet', '')
        if not magnet:
            hash_val = self._current_selected.get('info_hash', '')
            name = self._current_selected.get('name', 'Unknown')
            if hash_val:
                magnet = f"magnet:?xt=urn:btih:{hash_val}&dn={name}"
        return magnet

    def _on_copy_clicked(self):
        magnet = self._get_magnet()
        if magnet:
            QApplication.clipboard().setText(magnet)
            self.lbl_status.setText("Magnet tersalin ke clipboard.")

    def _on_select_file_clicked(self):
        # Placeholder for TorrentFileSelectorDialog idea
        QMessageBox.information(self, "Pilih File", "Fitur pilih file akan diimplementasikan pada TorrentFileSelectorDialog.")

    def _on_download_clicked(self):
        magnet = self._get_magnet()
        if not magnet:
            QMessageBox.warning(self, "Peringatan", "Pilih torrent terlebih dahulu.")
            return
            
        self.download_requested.emit(magnet)
        self.accept()
