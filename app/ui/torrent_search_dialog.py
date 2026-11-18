"""
Krolix Download Manager - In-App Torrent Search
Search across AniRena, The Pirate Bay, Nyaa.si, and Multi-Tracker Indexers
directly inside Zero without a web browser or pop-up ads.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QComboBox,
    QFrame, QApplication, QMessageBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from ..core.torrent_search_client import TorrentSearchClient
from ..utils.helpers import apply_windows_dark_titlebar


class TorrentSearchWorker(QThread):
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, query: str, limit: int = 60, source: str = "all"):
        super().__init__()
        self.query = query
        self.limit = limit
        self.source = source
        self.client = TorrentSearchClient()

    def run(self):
        try:
            results = self.client.search_torrents(self.query, self.limit, self.source)
            self.results_ready.emit(results)
        except Exception as e:
            self.error_occurred.emit(str(e))


class TorrentSearchDialog(QDialog):
    download_requested = pyqtSignal(str)  # Emits magnet URL to main window

    def __init__(self, parent=None, initial_query: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Pencarian Torrent & Media")
        self.resize(1000, 620)
        self.setMinimumSize(840, 500)

        self._all_results = []
        self._worker = None

        self._setup_style()
        self._init_ui()
        apply_windows_dark_titlebar(self)

        if initial_query:
            self.search_input.setText(initial_query)
            self._do_search()

    def _setup_style(self):
        # Soft dark / metallic chrome styling (no neon / oversaturated colors)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b0f17;
                color: #e2e8f0;
                font-family: 'Segoe UI Variable Display', 'Segoe UI', -apple-system, sans-serif;
            }
            QFrame#HeaderCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #151b28, stop:1 #0f1522);
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 12px;
                padding: 12px;
            }
            QLineEdit#SearchInput {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                color: #ffffff;
                font-size: 13px;
                padding: 8px 14px;
            }
            QLineEdit#SearchInput:focus {
                border: 1px solid #475569;
                background-color: rgba(255, 255, 255, 0.08);
            }
            QComboBox {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                color: #e2e8f0;
                padding: 6px 12px;
                min-width: 140px;
                font-size: 12px;
            }
            QComboBox:hover {
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #111827;
                color: #e2e8f0;
                selection-background-color: #1e293b;
                selection-color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QPushButton#PrimaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2b3648, stop:1 #1e2635);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 8px;
                color: #f8fafc;
                font-weight: 600;
                font-size: 12px;
                padding: 8px 18px;
            }
            QPushButton#PrimaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #37455c, stop:1 #273347);
                border: 1px solid rgba(255, 255, 255, 0.25);
            }
            QPushButton#PrimaryBtn:pressed {
                background-color: #1a2230;
            }
            QPushButton#SecondaryBtn {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                color: #cbd5e1;
                font-size: 12px;
                padding: 8px 16px;
            }
            QPushButton#SecondaryBtn:hover {
                background-color: rgba(255, 255, 255, 0.1);
                color: #ffffff;
            }
            QPushButton#SecondaryBtn:pressed {
                background-color: rgba(255, 255, 255, 0.03);
            }
            QTableWidget {
                background-color: #0c111a;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 10px;
                gridline-color: rgba(255, 255, 255, 0.03);
                color: #cbd5e1;
                font-size: 12px;
                selection-background-color: rgba(255, 255, 255, 0.1);
                selection-color: #ffffff;
            }
            QTableWidget::item {
                padding: 8px 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            }
            QHeaderView::section {
                background-color: #121824;
                color: #94a3b8;
                font-weight: 600;
                font-size: 11px;
                padding: 8px 8px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # Header card
        header_card = QFrame()
        header_card.setObjectName("HeaderCard")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(14, 14, 14, 14)
        h_layout.setSpacing(12)

        top_row = QHBoxLayout()
        title_lbl = QLabel("Pencarian Torrent & Media Terintegrasi")
        title_font = QFont("Segoe UI", 13)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #f1f5f9;")
        top_row.addWidget(title_lbl)

        badge_lbl = QLabel("AniRena • TPB • Nyaa • Multi-Tracker")
        badge_lbl.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.06);
            color: #94a3b8;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 10px;
            padding: 3px 10px;
            font-size: 11px;
            font-weight: 600;
        """)
        top_row.addWidget(badge_lbl)
        top_row.addStretch()

        h_layout.addLayout(top_row)

        # Search Controls Row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText("Ketik judul anime, film, game, software, atau rilis... (Tekan Enter)")
        self.search_input.returnPressed.connect(self._do_search)
        ctrl_row.addWidget(self.search_input, 1)

        # Source Selector
        self.source_combo = QComboBox()
        self.source_combo.addItem("Semua Sumber (All Indexers)", "all")
        self.source_combo.addItem("AniRena (Anime Tracker)", "anirena")
        self.source_combo.addItem("The Pirate Bay (Direct API)", "the pirate bay")
        self.source_combo.addItem("Nyaa.si (Anime Tracker)", "nyaa")
        self.source_combo.addItem("Multi-Tracker Indexers", "multi-tracker")
        ctrl_row.addWidget(self.source_combo)

        # Category Filter
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(["Semua Kategori", "Anime", "Movies / Video", "Software / Apps", "Games", "Music / Audio"])
        self.cat_combo.currentIndexChanged.connect(self._filter_results)
        ctrl_row.addWidget(self.cat_combo)

        self.btn_search = QPushButton("Cari")
        self.btn_search.setObjectName("PrimaryBtn")
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.clicked.connect(self._do_search)
        ctrl_row.addWidget(self.btn_search)

        h_layout.addLayout(ctrl_row)
        root.addWidget(header_card)

        # Results Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Judul Rilis", "Kategori", "Ukuran", "Seeds", "Peers", "Sumber"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._on_download_clicked)

        # Column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        root.addWidget(self.table, 1)

        # Status & Action Buttons Bar
        action_bar = QHBoxLayout()

        self.status_lbl = QLabel("Masukkan kata kunci pencarian di atas.")
        self.status_lbl.setStyleSheet("color: #64748b; font-size: 12px;")
        action_bar.addWidget(self.status_lbl)
        action_bar.addStretch()

        self.btn_copy_magnet = QPushButton("Salin Magnet")
        self.btn_copy_magnet.setObjectName("SecondaryBtn")
        self.btn_copy_magnet.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_magnet.clicked.connect(self._on_copy_magnet_clicked)
        action_bar.addWidget(self.btn_copy_magnet)


        self.btn_download = QPushButton("Unduh Torrent")
        self.btn_download.setObjectName("PrimaryBtn")
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.clicked.connect(self._on_download_clicked)
        action_bar.addWidget(self.btn_download)

        root.addLayout(action_bar)

    def _do_search(self):
        query = self.search_input.text().strip()
        if not query:
            return

        source = self.source_combo.currentData() or "all"
        src_text = self.source_combo.currentText().split("(")[0].strip()
        self.status_lbl.setText(f"Mencari di {src_text}...")
        self.btn_search.setEnabled(False)
        self.table.setRowCount(0)

        self._worker = TorrentSearchWorker(query, limit=60, source=source)
        self._worker.results_ready.connect(self._on_results_ready)
        self._worker.error_occurred.connect(self._on_search_error)
        self._worker.start()

    def _on_results_ready(self, results: list):
        self.btn_search.setEnabled(True)
        self._all_results = results
        self.status_lbl.setText(f"Ditemukan {len(results)} rilis torrent terverifikasi.")
        self._filter_results()

    def _on_search_error(self, err_msg: str):
        self.btn_search.setEnabled(True)
        self.status_lbl.setText(f"Gagal mencari: {err_msg}")

    def _filter_results(self):
        cat_filter = self.cat_combo.currentText().lower()
        filtered = []

        for item in self._all_results:
            c = (item.get("category") or "").lower()
            if "semua" in cat_filter or "all" in cat_filter:
                filtered.append(item)
            elif "movie" in cat_filter and ("movie" in c or "video" in c):
                filtered.append(item)
            elif "anime" in cat_filter and "anime" in c:
                filtered.append(item)
            elif "software" in cat_filter and ("app" in c or "software" in c):
                filtered.append(item)
            elif "game" in cat_filter and "game" in c:
                filtered.append(item)
            elif "music" in cat_filter and ("music" in c or "audio" in c):
                filtered.append(item)
            else:
                if "semua" in cat_filter:
                    filtered.append(item)

        if not filtered and self._all_results:
            filtered = self._all_results

        self._populate_table(filtered)

    def _populate_table(self, items: list):
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            # Title
            t_item = QTableWidgetItem(item.get("title", ""))
            t_item.setData(Qt.ItemDataRole.UserRole, item)
            self.table.setItem(row, 0, t_item)

            # Category
            c_item = QTableWidgetItem(item.get("category", "General"))
            c_item.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 1, c_item)

            # Size (accurate byte-calculated size)
            size_fmt = item.get("size_formatted", "--")
            raw_sz = item.get("size_bytes", 0)
            if raw_sz in (1500000000, 1400000000, 1503238553) or size_fmt in ("1.40 GB", "1.4 GB"):
                t_bytes, t_fmt = TorrentSearchClient.extract_size_from_title(item.get("title", ""))
                size_fmt = t_fmt if t_bytes > 0 else "--"
            s_item = QTableWidgetItem(size_fmt)
            s_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            s_item.setForeground(QColor("#e2e8f0"))
            self.table.setItem(row, 2, s_item)

            # Seeds (soft metallic green/chrome)
            seeds = item.get("seeds", 0)
            sd_item = QTableWidgetItem(f"▲ {seeds:,}")
            sd_item.setForeground(QColor("#86efac"))
            sd_font = QFont()
            sd_font.setBold(True)
            sd_item.setFont(sd_font)
            sd_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, sd_item)

            # Peers (soft slate)
            peers = item.get("peers", 0)
            pr_item = QTableWidgetItem(f"▼ {peers:,}")
            pr_item.setForeground(QColor("#94a3b8"))
            pr_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, pr_item)

            # Indexer source
            idx_item = QTableWidgetItem(item.get("indexer", "Public Indexer"))
            idx_item.setForeground(QColor("#cbd5e1"))
            self.table.setItem(row, 5, idx_item)

        if items:
            self.table.selectRow(0)

    def _get_selected_item(self) -> dict:
        row = self.table.currentRow()
        if row < 0:
            return {}
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) or {}

    def _on_download_clicked(self):
        selected = self._get_selected_item()
        raw_magnet = selected.get("magnet") or ""
        if not raw_magnet:
            QMessageBox.warning(self, "Tidak Ada Torrent Dipilih", "Silakan pilih salah satu torrent untuk diunduh.")
            return

        # Resolve AniRena redirect endpoint to magnet URI if needed
        self.status_lbl.setText("Memproses tautan magnet...")
        QApplication.processEvents()
        magnet = TorrentSearchClient.resolve_magnet(raw_magnet)

        self.download_requested.emit(magnet)
        self.accept()

    def _on_copy_magnet_clicked(self):
        selected = self._get_selected_item()
        raw_magnet = selected.get("magnet") or ""
        if raw_magnet:
            self.status_lbl.setText("Menyelesaikan tautan magnet...")
            QApplication.processEvents()
            magnet = TorrentSearchClient.resolve_magnet(raw_magnet)
            QApplication.clipboard().setText(magnet)
            self.status_lbl.setText("Tautan magnet berhasil disalin ke clipboard!")
        else:
            QMessageBox.warning(self, "Tidak Ada Torrent Dipilih", "Silakan pilih salah satu torrent dari daftar.")
