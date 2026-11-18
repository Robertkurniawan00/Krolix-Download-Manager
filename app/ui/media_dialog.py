import time
import threading
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QProgressBar,
    QCheckBox
)
from PyQt6.QtCore import pyqtSignal, QObject, Qt
from ..core.media_grabber import MediaGrabber
from ..utils.helpers import apply_windows_dark_titlebar

class MediaAnalyzerWorker(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            info, err = MediaGrabber.get_media_info(self.url)
            if info:
                self.finished.emit(info)
            else:
                self.error.emit(err or "Could not extract media info.")
        except Exception as e:
            self.error.emit(str(e))

class MediaDialog(QDialog):
    def __init__(self, default_url: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Media Grabber")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(700, 500)
        self.setMinimumSize(620, 440)
        apply_windows_dark_titlebar(self)
        self.selected_format = None
        self.media_info = None

        self._setup_ui(default_url)

    def _setup_ui(self, default_url: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        info_lbl = QLabel("Enter video, stream, or profile URL (YouTube, TikTok, Chaturbate, HLS m3u8, direct video):")
        info_lbl.setStyleSheet("color: #cccccc; font-size: 12px;")
        layout.addWidget(info_lbl)

        # URL Input
        url_layout = QHBoxLayout()
        self.txt_url = QLineEdit(default_url)
        self.txt_url.setPlaceholderText("https://chaturbate.com/username/ or https://youtu.be/...")
        self.txt_url.setStyleSheet("""
            QLineEdit {
                background-color: #050811;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 7px 10px;
                color: #f8fafc;
                font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #10b981;
                background-color: #080e1a;
            }
        """)
        self.txt_url.returnPressed.connect(self._analyze_url)
        url_layout.addWidget(self.txt_url)

        self.btn_analyze = QPushButton("Analyze Video")
        self.btn_analyze.setStyleSheet("""
            QPushButton {
                background-color: #0f1724;
                color: #34d399;
                border: 1px solid #1b273d;
                border-radius: 5px;
                font-weight: 600;
                padding: 7px 14px;
            }
            QPushButton:hover {
                background-color: #151f30;
                color: #ffffff;
                border-color: #10b981;
            }
        """)
        self.btn_analyze.clicked.connect(self._analyze_url)
        url_layout.addWidget(self.btn_analyze)
        layout.addLayout(url_layout)

        # Progress indicator
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Title of detected video
        self.lbl_title = QLabel("Available Streams & Formats:")
        self.lbl_title.setStyleSheet("color: #f1f5f9; font-weight: 600; font-size: 13px;")
        layout.addWidget(self.lbl_title)

        # Formats Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Resolution / Quality", "Format", "Size", "Details"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0b0f19;
                border: 1px solid #1e293b;
                border-radius: 6px;
                gridline-color: #1e293b;
                color: #e2e8f0;
                font-size: 12px;
            }
            QTableWidget::item:selected {
                background-color: #047857;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #0f172a;
                color: #94a3b8;
                font-weight: 600;
                font-size: 11px;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #1e293b;
            }
        """)
        layout.addWidget(self.table)

        self.chk_include_audio = QCheckBox("Unduh & Gabungkan Audio Berkualitas Tinggi Otomatis (DASH Mux)")
        self.chk_include_audio.setChecked(True)
        self.chk_include_audio.setStyleSheet("""
            QCheckBox {
                color: #cbd5e1;
                font-weight: 500;
                font-size: 12px;
                padding: 3px 0px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #475569;
                background-color: #0b0f19;
            }
            QCheckBox::indicator:checked {
                background-color: #334155;
                border-color: #64748b;
            }
        """)
        self.chk_include_audio.setVisible(False)
        layout.addWidget(self.chk_include_audio)

        self.lbl_note = QLabel("Catatan: YouTube DASH dialirkan terpisah oleh server Google. Opsi di atas otomatis mengunduh trek suara untuk video ini.")
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
        self.lbl_note.setVisible(False)
        layout.addWidget(self.lbl_note)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        self.btn_download = QPushButton("Download Selected Format")
        self.btn_download.setEnabled(False)
        self.btn_download.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #05070b;
                font-weight: 600;
                padding: 7px 18px;
                border: 1px solid #10b981;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #34d399;
                border-color: #34d399;
                color: #020617;
            }
            QPushButton:disabled {
                background-color: #0b0f17;
                color: #475569;
                border-color: #151f30;
            }
        """)
        self.btn_download.clicked.connect(self._on_download_clicked)
        btn_layout.addWidget(self.btn_download)

        layout.addLayout(btn_layout)

        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)

        if default_url:
            self._analyze_url()

    def _on_table_selection_changed(self):
        sel = self.table.selectedItems()
        if not sel or not self.media_info:
            return
        row = sel[0].row()
        formats = self.media_info.get("formats", [])
        if row < len(formats):
            fmt = formats[row]
            if fmt.get("has_video") and not fmt.get("has_audio") and fmt.get("companion_audio"):
                self.chk_include_audio.setVisible(True)
                self.lbl_note.setVisible(True)
            else:
                self.chk_include_audio.setVisible(False)
                self.lbl_note.setVisible(False)

    def _analyze_url(self):
        url = self.txt_url.text().strip()
        if not url:
            return

        self.btn_analyze.setEnabled(False)
        self.progress.setVisible(True)
        self.lbl_title.setText("Analyzing video stream...")
        self.table.setRowCount(0)
        self.chk_include_audio.setVisible(False)
        self.lbl_note.setVisible(False)

        worker = MediaAnalyzerWorker(url)
        thread = threading.Thread(target=worker.run, daemon=True)
        worker.finished.connect(self._on_analyzed)
        worker.error.connect(self._on_error)
        self._worker = worker
        thread.start()

    def _on_analyzed(self, info: dict):
        self.btn_analyze.setEnabled(True)
        self.progress.setVisible(False)
        self.media_info = info
        is_live = bool(info.get("is_live", False))
        title = info.get("title", "Unknown")

        if is_live:
            self.lbl_title.setText(f"LIVE STREAM: {title}")
            self.lbl_title.setStyleSheet("color: #ef4444; font-weight: 700; font-size: 13px;")
            self.btn_download.setText("Mulai Rekam Siaran Langsung (Record Live Stream)")
            self.btn_download.setStyleSheet("""
                QPushButton {
                    background-color: #dc2626;
                    color: #ffffff;
                    font-weight: 700;
                    padding: 8px 20px;
                    border: 1px solid #ef4444;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #b91c1c;
                    border-color: #f87171;
                    color: #ffffff;
                }
                QPushButton:disabled {
                    background-color: #0b0f17;
                    color: #475569;
                    border-color: #151f30;
                }
            """)
        else:
            self.lbl_title.setText(f"Title: {title}")
            self.lbl_title.setStyleSheet("color: #f1f5f9; font-weight: 600; font-size: 13px;")
            self.btn_download.setText("Download Selected Format")
            self.btn_download.setStyleSheet("""
                QPushButton {
                    background-color: #10b981;
                    color: #05070b;
                    font-weight: 600;
                    padding: 7px 18px;
                    border: 1px solid #10b981;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #34d399;
                    border-color: #34d399;
                    color: #020617;
                }
                QPushButton:disabled {
                    background-color: #0b0f17;
                    color: #475569;
                    border-color: #151f30;
                }
            """)

        formats = info.get("formats", [])
        self.table.setRowCount(0)
        for f in formats:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # Label
            item0 = QTableWidgetItem(f.get("label", "Standard"))
            item0.setFlags(item0.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item0)

            item1 = QTableWidgetItem(f.get("ext", "mp4").upper())
            item1.setFlags(item1.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item1.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, item1)
            
            size_mb = f.get("filesize", 0) / (1024 * 1024) if f.get("filesize") else 0
            size_str = f"{size_mb:.1f} MB" if size_mb > 0 else ("Live Feed" if is_live else "Direct Stream")
            item2 = QTableWidgetItem(size_str)
            item2.setFlags(item2.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item2.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, item2)

            codec_desc = f.get("codec_desc", "Video Stream")
            item3 = QTableWidgetItem(codec_desc)
            item3.setFlags(item3.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item3.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, item3)

        if formats:
            self.table.selectRow(0)
            self.btn_download.setEnabled(True)
            self._on_table_selection_changed()

    def _on_error(self, err: str):
        self.btn_analyze.setEnabled(True)
        self.progress.setVisible(False)
        self.lbl_title.setText("Analisis video gagal")

        clean_msg = (err or "Gagal mengekstrak informasi media dari URL ini.").strip()
        if clean_msg.startswith("ERROR:"):
            clean_msg = clean_msg[6:].strip()
            clean_msg = re.sub(r'^\[[^\]]+\]\s*[^:]*:\s*', '', clean_msg).strip()

        mb = QMessageBox(self)
        mb.setIcon(QMessageBox.Icon.Warning)
        mb.setWindowTitle("Media Grabber - Informasi Ekstraksi")
        mb.setText(f"<b>Tidak Dapat Mengambil Video</b><br><br>{clean_msg.replace(chr(10), '<br>')}")
        apply_windows_dark_titlebar(mb)
        mb.exec()

    def _on_download_clicked(self):
        sel = self.table.selectedItems()
        if not sel or not self.media_info:
            return

        row = sel[0].row()
        formats = self.media_info.get("formats", [])
        if row < len(formats):
            chosen = formats[row]
            title = self.media_info.get('title', 'video')
            ext = chosen.get('ext', 'mp4')
            if not title.lower().endswith(f".{ext.lower()}"):
                full_filename = f"{title}.{ext}"
            else:
                full_filename = title

            # Sanitize filename
            clean_filename = "".join(c for c in full_filename if c not in '<>:"/\\|?*').strip()
            if not clean_filename:
                clean_filename = f"stream_{int(time.time())}.{ext}"

            is_live = bool(self.media_info.get("is_live", False) or chosen.get("is_live", False))
            is_hls = is_live or chosen.get("is_hls", False) or (".m3u8" in chosen.get("url", "").lower())

            res = {
                "url": chosen.get("url"),
                "master_url": chosen.get("master_url") or self.media_info.get("m3u8_url"),
                "audio_url": chosen.get("audio_url"),
                "format_id": chosen.get("format_id"),
                "height": chosen.get("height"),
                "bitrate": chosen.get("bitrate"),
                "title": clean_filename,
                "original_page": self.media_info.get("webpage_url"),
                "is_live": is_live,
                "is_hls": is_hls
            }

            if (not is_live and chosen.get("has_video") and not chosen.get("has_audio")
                    and chosen.get("companion_audio") and self.chk_include_audio.isChecked()):
                comp = chosen["companion_audio"]
                audio_ext = comp.get("ext", "m4a")
                res["audio_url"] = comp.get("url")
                res["audio_title"] = f"{clean_filename} (Audio).{audio_ext}"

            self.selected_format = res
            self.accept()

    def get_result(self):
        return self.selected_format
