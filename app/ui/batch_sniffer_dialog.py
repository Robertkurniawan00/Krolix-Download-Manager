"""
Krolix Download Manager - Bulk Link Sniffer & Multi-Link Extractor Dialog
Scans, extracts, categorizes, and batch-enqueues downloadable links from clipboard, HTML, or raw text.
"""

import os
import re
import urllib.parse
from typing import List, Dict

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QPlainTextEdit,
    QFileDialog, QMessageBox, QFrame, QButtonGroup, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from ..utils.helpers import apply_windows_dark_titlebar, sanitize_filename, get_default_download_dir


class BatchSnifferDialog(QDialog):
    links_submitted = pyqtSignal(list, str, bool)  # (items, save_dir, start_now)

    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        self.raw_items: List[Dict] = []
        self.filtered_items: List[Dict] = []
        self.current_category = "all"

        self.setWindowTitle("Sniff & Ekstrak Link Massal (Bulk Link Sniffer)")
        self.resize(850, 640)
        apply_windows_dark_titlebar(self)

        self.setStyleSheet("""
            QDialog {
                background-color: #070a0f;
                color: #e2e8f0;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel {
                color: #cbd5e1;
                font-size: 12px;
            }
            QLineEdit, QPlainTextEdit {
                background-color: #0d1117;
                border: 1px solid #1b273d;
                border-radius: 6px;
                padding: 7px 10px;
                color: #f1f5f9;
                font-size: 12px;
            }
            QLineEdit:focus, QPlainTextEdit:focus {
                border: 1px solid #06b6d4;
                background-color: #111827;
            }
            QTableWidget {
                background-color: #0d1117;
                border: 1px solid #1b273d;
                border-radius: 6px;
                gridline-color: #162032;
                color: #e2e8f0;
                font-size: 12px;
                selection-background-color: #1e293b;
            }
            QHeaderView::section {
                background-color: #0a0e17;
                color: #94a3b8;
                border: none;
                border-bottom: 1px solid #1b273d;
                padding: 6px 8px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton {
                background-color: #161e2e;
                color: #cbd5e1;
                border: 1px solid #23314d;
                border-radius: 6px;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1e293b;
                color: #f8fafc;
                border-color: #38bdf8;
            }
            QPushButton#PrimaryBtn {
                background-color: #0284c7;
                color: #ffffff;
                border: 1px solid #0ea5e9;
                font-weight: 600;
            }
            QPushButton#PrimaryBtn:hover {
                background-color: #0ea5e9;
            }
            QPushButton#FilterBtn {
                background-color: #0d1117;
                border: 1px solid #1b273d;
                color: #94a3b8;
                padding: 5px 12px;
                border-radius: 12px;
                font-size: 11px;
            }
            QPushButton#FilterBtn:checked {
                background-color: #0369a1;
                border-color: #38bdf8;
                color: #ffffff;
                font-weight: 600;
            }
        """)

        self._init_ui()

        # Pre-fill from argument or clipboard
        clip_text = initial_text or QApplication.clipboard().text()
        if clip_text and any(s in clip_text.lower() for s in ["http://", "https://", "magnet:", "ftp://"]):
            self.txt_raw.setPlainText(clip_text)
            self._scan_links()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Header Title
        title_box = QHBoxLayout()
        lbl_title = QLabel("Sniff & Ekstrak Link Massal")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        title_box.addWidget(lbl_title)
        title_box.addStretch()

        lbl_desc = QLabel("Ekstraksi link otomatis dari teks, HTML, atau clipboard ke antrean unduhan")
        lbl_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        title_box.addWidget(lbl_desc)
        main_layout.addLayout(title_box)

        # Raw Text Input Box
        box_input = QFrame()
        box_input.setStyleSheet("background-color: #0b0f17; border: 1px solid #1b273d; border-radius: 8px; padding: 8px;")
        layout_input = QVBoxLayout(box_input)
        layout_input.setSpacing(8)

        row_tools = QHBoxLayout()
        lbl_inst = QLabel("Tempel teks mentah, kode sumber HTML, atau daftar link di bawah:")
        lbl_inst.setStyleSheet("color: #94a3b8; font-size: 11px;")
        row_tools.addWidget(lbl_inst)
        row_tools.addStretch()

        btn_paste_clip = QPushButton("Tempel dari Clipboard")
        btn_paste_clip.clicked.connect(self._paste_clipboard)
        btn_scan = QPushButton("Pindai Ulang")
        btn_scan.setObjectName("PrimaryBtn")
        btn_scan.clicked.connect(self._scan_links)

        row_tools.addWidget(btn_paste_clip)
        row_tools.addWidget(btn_scan)
        layout_input.addLayout(row_tools)

        self.txt_raw = QPlainTextEdit()
        self.txt_raw.setPlaceholderText("Tempel teks di sini (misal daftar URL, link download, atau teks dari halaman web)...")
        self.txt_raw.setFixedHeight(80)
        layout_input.addWidget(self.txt_raw)
        main_layout.addWidget(box_input)

        # Category Filter Pills
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(6)
        self.btn_filter_group = QButtonGroup(self)
        self.btn_filter_group.setExclusive(True)

        self.btn_f_all = QPushButton("Semua (0)")
        self.btn_f_video = QPushButton("Video (0)")
        self.btn_f_audio = QPushButton("Audio (0)")
        self.btn_f_docs = QPushButton("Arsip & Berkas (0)")
        self.btn_f_torrent = QPushButton("Torrent & Magnet (0)")

        for idx, (btn, cat) in enumerate([
            (self.btn_f_all, "all"),
            (self.btn_f_video, "video"),
            (self.btn_f_audio, "audio"),
            (self.btn_f_docs, "docs"),
            (self.btn_f_torrent, "torrent"),
        ]):
            btn.setObjectName("FilterBtn")
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            self.btn_filter_group.addButton(btn)
            btn.clicked.connect(lambda _, c=cat: self._filter_by_category(c))
            filter_bar.addWidget(btn)

        filter_bar.addStretch()

        btn_select_all = QPushButton("Pilih Semua")
        btn_select_all.clicked.connect(lambda: self._set_all_checks(True))
        btn_unselect_all = QPushButton("Batalkan Semua")
        btn_unselect_all.clicked.connect(lambda: self._set_all_checks(False))
        filter_bar.addWidget(btn_select_all)
        filter_bar.addWidget(btn_unselect_all)
        main_layout.addLayout(filter_bar)

        # Results Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Pilih", "Nama File", "Kategori", "Domain / Host", "URL Lengkap"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 230)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 90)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 140)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        main_layout.addWidget(self.table)

        # Destination & Options
        row_dest = QHBoxLayout()
        lbl_dest = QLabel("Folder Simpan:")
        lbl_dest.setFixedWidth(85)
        self.txt_dest = QLineEdit(get_default_download_dir())
        btn_dest = QPushButton("Jelajahi...")
        btn_dest.clicked.connect(self._browse_dest)
        row_dest.addWidget(lbl_dest)
        row_dest.addWidget(self.txt_dest)
        row_dest.addWidget(btn_dest)
        main_layout.addLayout(row_dest)

        # Footer Actions
        footer = QHBoxLayout()
        self.chk_start_now = QCheckBox("Mulai unduhan sekarang")
        self.chk_start_now.setChecked(True)
        self.chk_start_now.setStyleSheet("color: #cbd5e1; font-weight: 500;")
        footer.addWidget(self.chk_start_now)

        self.lbl_selected_summary = QLabel("0 link dipilih dari total 0")
        self.lbl_selected_summary.setStyleSheet("color: #94a3b8; font-size: 11px;")
        footer.addSpacing(15)
        footer.addWidget(self.lbl_selected_summary)
        footer.addStretch()

        btn_export = QPushButton("Simpan Daftar (.txt)")
        btn_export.clicked.connect(self._export_to_txt)
        footer.addWidget(btn_export)

        btn_cancel = QPushButton("Batal")
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        self.btn_submit = QPushButton("Tambahkan ke Unduhan")
        self.btn_submit.setObjectName("PrimaryBtn")
        self.btn_submit.clicked.connect(self._submit_links)
        footer.addWidget(self.btn_submit)

        main_layout.addLayout(footer)

    def _paste_clipboard(self):
        text = QApplication.clipboard().text()
        if text:
            self.txt_raw.setPlainText(text)
            self._scan_links()

    def _browse_dest(self):
        d = QFileDialog.getExistingDirectory(self, "Pilih Folder Simpan", self.txt_dest.text())
        if d:
            self.txt_dest.setText(d)

    def _classify_url(self, url: str) -> tuple:
        """Returns (filename, category, domain)"""
        clean_url = url.split("?")[0].split("#")[0]
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc or "Torrent/Magnet"

        if url.startswith("magnet:"):
            # Extract dn
            m = re.search(r"dn=([^&]+)", url)
            fn = urllib.parse.unquote(m.group(1)) if m else "Magnet Download"
            return sanitize_filename(fn), "torrent", "BitTorrent"

        path_fn = os.path.basename(clean_url) or "download.bin"
        ext = os.path.splitext(path_fn)[1].lower()

        video_exts = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".ts", ".m3u8", ".mpd", ".m4v"}
        audio_exts = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma"}
        doc_exts = {".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".exe", ".msi", ".apk", ".pdf", ".docx", ".epub"}

        if ext in video_exts or any(d in domain for d in ["youtube.com", "youtu.be", "vimeo.com", "tiktok.com"]):
            cat = "video"
        elif ext in audio_exts:
            cat = "audio"
        elif ext in doc_exts:
            cat = "docs"
        elif ext == ".torrent":
            cat = "torrent"
        else:
            cat = "docs"

        fn = sanitize_filename(urllib.parse.unquote(path_fn))
        return fn, cat, domain

    def _scan_links(self):
        text = self.txt_raw.toPlainText()
        if not text or not text.strip():
            self.raw_items = []
            self._update_counts()
            self._filter_by_category(self.current_category)
            return

        # Regex for standard URLs & Magnets
        url_pattern = re.compile(r'((?:https?|ftp)://[^\s"\'<>]+|magnet:\?[^\s"\'<>]+)', re.IGNORECASE)
        matches = url_pattern.findall(text)

        seen = set()
        self.raw_items = []

        for raw_u in matches:
            u = raw_u.strip(").,;\"'")
            if not u or u in seen:
                continue
            seen.add(u)
            fn, cat, dom = self._classify_url(u)
            self.raw_items.append({
                "url": u,
                "filename": fn,
                "category": cat,
                "domain": dom,
                "checked": True
            })

        self._update_counts()
        self._filter_by_category(self.current_category)

    def _update_counts(self):
        c_all = len(self.raw_items)
        c_vid = sum(1 for x in self.raw_items if x["category"] == "video")
        c_aud = sum(1 for x in self.raw_items if x["category"] == "audio")
        c_doc = sum(1 for x in self.raw_items if x["category"] == "docs")
        c_tor = sum(1 for x in self.raw_items if x["category"] == "torrent")

        self.btn_f_all.setText(f"Semua ({c_all})")
        self.btn_f_video.setText(f"Video ({c_vid})")
        self.btn_f_audio.setText(f"Audio ({c_aud})")
        self.btn_f_docs.setText(f"Arsip & Berkas ({c_doc})")
        self.btn_f_torrent.setText(f"Torrent & Magnet ({c_tor})")

    def _filter_by_category(self, cat: str):
        self.current_category = cat
        if cat == "all":
            self.filtered_items = self.raw_items
        else:
            self.filtered_items = [x for x in self.raw_items if x["category"] == cat]
        self._populate_table()

    def _populate_table(self):
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.filtered_items))

        for row, item in enumerate(self.filtered_items):
            # Checkbox
            chk = QCheckBox()
            chk.setChecked(item.get("checked", True))
            chk.toggled.connect(lambda c, it=item: self._on_item_check_changed(it, c))
            cell_w = QWidget()
            layout_c = QHBoxLayout(cell_w)
            layout_c.setContentsMargins(0, 0, 0, 0)
            layout_c.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout_c.addWidget(chk)
            self.table.setCellWidget(row, 0, cell_w)

            # Filename
            item_fn = QTableWidgetItem(item["filename"])
            self.table.setItem(row, 1, item_fn)

            # Category
            cat_map = {"video": "Video", "audio": "Audio", "docs": "Berkas", "torrent": "Torrent"}
            item_cat = QTableWidgetItem(cat_map.get(item["category"], "Lainnya"))
            item_cat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, item_cat)

            # Domain
            item_dom = QTableWidgetItem(item["domain"])
            self.table.setItem(row, 3, item_dom)

            # URL
            item_url = QTableWidgetItem(item["url"])
            item_url.setForeground(QColor("#38bdf8"))
            self.table.setItem(row, 4, item_url)

        self._update_summary()

    def _on_item_check_changed(self, item: dict, checked: bool):
        item["checked"] = checked
        self._update_summary()

    def _set_all_checks(self, checked: bool):
        for it in self.filtered_items:
            it["checked"] = checked
        self._populate_table()

    def _update_summary(self):
        sel_count = sum(1 for x in self.raw_items if x.get("checked", True))
        tot_count = len(self.raw_items)
        self.lbl_selected_summary.setText(f"{sel_count} link dipilih dari total {tot_count}")
        self.btn_submit.setEnabled(sel_count > 0)
        self.btn_submit.setText(f"Tambahkan ({sel_count}) ke Unduhan")

    def _submit_links(self):
        selected = [x for x in self.raw_items if x.get("checked", True)]
        if not selected:
            QMessageBox.information(self, "Informasi", "Tidak ada link yang dipilih.")
            return

        save_dir = self.txt_dest.text().strip()
        if not os.path.exists(save_dir):
            try:
                os.makedirs(save_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Peringatan", f"Folder tujuan tidak dapat dibuat: {e}")
                return

        start_now = self.chk_start_now.isChecked()
        self.links_submitted.emit(selected, save_dir, start_now)
        self.accept()

    def _export_to_txt(self):
        selected = [x["url"] for x in self.raw_items if x.get("checked", True)]
        if not selected:
            QMessageBox.information(self, "Informasi", "Tidak ada link yang dipilih untuk diekspor.")
            return

        f, _ = QFileDialog.getSaveFileName(self, "Simpan Daftar Link", "links.txt", "Text Files (*.txt);;All Files (*.*)")
        if f:
            try:
                with open(f, "w", encoding="utf-8") as fp:
                    fp.write("\n".join(selected))
                QMessageBox.information(self, "Berhasil", f"Berhasil menyimpan {len(selected)} link ke {f}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Gagal menyimpan file: {e}")
