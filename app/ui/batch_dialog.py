"""
Krolix Download Manager - Batch & Wildcard Pattern Downloader
Allows downloading lists of URLs or wildcard ranges like http://site.com/ep[01-24].mp4
"""

import os
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QFileDialog, QLineEdit, QMessageBox
)
from PyQt6.QtCore import Qt
from ..utils.helpers import get_category_from_ext, sanitize_filename

class BatchDialog(QDialog):
    def __init__(self, initial_urls=None, initial_items=None, default_save_dir=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unduh Massal / Batch & Pattern - Krolix Download Manager")
        self.resize(750, 520)
        self.generated_urls = []
        self.default_save_dir = default_save_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        self.init_ui()
        if initial_urls:
            urls_list = [u.strip() for u in initial_urls if u.strip()]
            self.input_text.setPlainText("\n".join(urls_list))
            self._parse_urls()
        elif initial_items:
            self._load_items(initial_items)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        info_lbl = QLabel(
            "<b>Masukkan daftar URL atau Pola Range Wildcard:</b><br>"
            "<span style='color: #94a3b8;'>Contoh Pola: <code>https://cdn.site.com/anime/ep_[01-12].mp4</code> atau beberapa baris URL.</span>"
        )
        layout.addWidget(info_lbl)

        self.input_text = QPlainTextEdit()
        self.input_text.setPlaceholderText("Tempel daftar URL atau masukkan URL dengan pola range [01-20] di sini...")
        self.input_text.setFixedHeight(110)
        layout.addWidget(self.input_text)

        parse_row = QHBoxLayout()
        parse_btn = QPushButton("Urai & Generate URL (Parse)")
        parse_btn.setObjectName("accentBtn")
        parse_btn.clicked.connect(self._parse_urls)
        parse_row.addWidget(parse_btn)
        parse_row.addStretch()

        self.sel_all_cb = QCheckBox("Pilih Semua")
        self.sel_all_cb.setChecked(True)
        self.sel_all_cb.toggled.connect(self._toggle_select_all)
        parse_row.addWidget(self.sel_all_cb)
        layout.addLayout(parse_row)

        # Table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Pilih", "Nama Berkas", "URL Asal"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 220)
        layout.addWidget(self.table)

        # Target dir
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Simpan ke:"))
        self.dir_input = QLineEdit(self.default_save_dir)
        browse_btn = QPushButton("Pilih...")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(self.dir_input, 1)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # Bottom buttons
        btn_row = QHBoxLayout()
        self.count_lbl = QLabel("0 item terdeteksi")
        btn_row.addWidget(self.count_lbl)
        btn_row.addStretch()

        cancel_btn = QPushButton("Batal")
        cancel_btn.clicked.connect(self.reject)

        self.start_btn = QPushButton("Mulai Unduh Semua")
        self.start_btn.setObjectName("accentBtn")
        self.start_btn.clicked.connect(self._accept_batch)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.start_btn)
        layout.addLayout(btn_row)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Pilih Folder Unduhan", self.dir_input.text())
        if d:
            self.dir_input.setText(d)

    def _parse_urls(self):
        raw = self.input_text.toPlainText().strip()
        if not raw:
            return

        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        expanded = []

        pattern_re = re.compile(r'\[(\d+)-(\d+)\]')

        for line in lines:
            match = pattern_re.search(line)
            if match:
                s_str, e_str = match.groups()
                start_num = int(s_str)
                end_num = int(e_str)
                pad_len = len(s_str) if s_str.startswith('0') else 0

                # Sane limit on range expansion (max 200 items per pattern to avoid freeze)
                if abs(end_num - start_num) > 200:
                    QMessageBox.warning(self, "Range Terlalu Besar", "Rentang pola maksimal adalah 200 item sekaligus.")
                    return

                step = 1 if end_num >= start_num else -1
                for n in range(start_num, end_num + step, step):
                    formatted_n = f"{n:0{pad_len}d}" if pad_len > 0 else str(n)
                    expanded_url = pattern_re.sub(formatted_n, line, count=1)
                    expanded.append(expanded_url)
            else:
                if line.startswith("http://") or line.startswith("https://") or line.startswith("ftp://"):
                    expanded.append(line)

        self.generated_urls = expanded
        self._populate_table()

    def _load_items(self, items: list):
        self.table.setRowCount(len(items))
        self.generated_urls = []
        for row, it in enumerate(items):
            url = it.get('url', '').strip() if isinstance(it, dict) else str(it).strip()
            fname = (it.get('filename') or it.get('description') or (url.split('/')[-1].split('?')[0] or f"item_{row+1}")) if isinstance(it, dict) else (url.split('/')[-1].split('?')[0] or f"item_{row+1}")
            clean_fname = sanitize_filename(fname)
            self.generated_urls.append(url)

            cb_item = QTableWidgetItem()
            cb_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            cb_item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, cb_item)
            self.table.setItem(row, 1, QTableWidgetItem(clean_fname))
            self.table.setItem(row, 2, QTableWidgetItem(url))

        self.count_lbl.setText(f"{len(items)} item terdeteksi")

    def _populate_table(self):
        self.table.setRowCount(len(self.generated_urls))
        for row, url in enumerate(self.generated_urls):
            # Checkbox item
            cb_item = QTableWidgetItem()
            cb_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            cb_item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, cb_item)

            # Filename
            raw_fname = url.split('/')[-1].split('?')[0] or f"item_{row+1}"
            clean_fname = sanitize_filename(raw_fname)
            self.table.setItem(row, 1, QTableWidgetItem(clean_fname))

            # URL
            self.table.setItem(row, 2, QTableWidgetItem(url))

        self.count_lbl.setText(f"{len(self.generated_urls)} item terdeteksi")

    def _toggle_select_all(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item:
                item.setCheckState(state)

    def _accept_batch(self):
        selected_items = self.get_selected_items()
        if not selected_items:
            QMessageBox.information(self, "Peringatan", "Pilih minimal 1 item untuk diunduh.")
            return
        self.accept()

    def get_selected_items(self) -> list:
        """Returns list of dicts: {'url': str, 'filename': str, 'save_path': str, 'category': str}"""
        base_dir = self.dir_input.text().strip() or os.path.join(os.path.expanduser("~"), "Downloads")
        items = []
        for r in range(self.table.rowCount()):
            cb_item = self.table.item(r, 0)
            if cb_item and cb_item.checkState() == Qt.CheckState.Checked:
                fname = self.table.item(r, 1).text().strip()
                url = self.table.item(r, 2).text().strip()
                cat = get_category_from_ext(fname)
                save_path = os.path.join(base_dir, fname)
                items.append({
                    'url': url,
                    'filename': fname,
                    'save_path': save_path,
                    'category': cat
                })
        return items
