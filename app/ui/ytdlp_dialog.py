"""
Krolix Download Manager - Advanced yt-dlp Media Downloader Dialog
Fluent Dark UI for YouTube, Social Media, Playlists, Audio extraction, and Subtitles.
"""

import os
import subprocess
import threading
import urllib.request
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QProgressBar,
    QFileDialog, QRadioButton, QHeaderView, QWidget, QButtonGroup,
    QTabWidget, QComboBox, QCheckBox, QFrame, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPixmap

from ..core.ytdlp_worker import YtdlpWorker
from ..core.torrent_downloader import TorrentWorker
from ..utils.helpers import sanitize_filename

try:
    from ..utils.helpers import apply_windows_dark_titlebar
except ImportError:
    def apply_windows_dark_titlebar(win):
        pass


class YtdlpInfoWorker(QThread):
    info_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url: str, cookies_browser: Optional[str] = None, proxy: Optional[str] = None):
        super().__init__()
        self.url = url
        self.cookies_browser = cookies_browser
        self.proxy = proxy

    def run(self):
        try:
            info = YtdlpWorker.fetch_info(
                url=self.url,
                cookies_browser=self.cookies_browser,
                proxy=self.proxy
            )
            self.info_ready.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class ThumbnailWorker(QThread):
    thumb_ready = pyqtSignal(QPixmap)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            req = urllib.request.Request(
                self.url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            data = urllib.request.urlopen(req, timeout=12).read()
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            self.thumb_ready.emit(pixmap)
        except Exception:
            pass


class YtdlpDialog(QDialog):
    download_started = pyqtSignal()
    progress_signal = pyqtSignal(int, int, float, float)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, str)

    def __init__(self, engine=None, initial_url='', parent=None):
        super().__init__(parent)
        self.engine = engine
        self.initial_url = (initial_url or "").strip()
        self.current_info: Optional[Dict[str, Any]] = None
        self.worker: Optional[YtdlpWorker] = None
        self.pause_event: Optional[threading.Event] = None
        self.cancel_event: Optional[threading.Event] = None
        self.final_download_path: str = ""

        self.setWindowTitle("Download dari YouTube & Media Sosial (YT-DLP)")
        self.resize(860, 720)
        self.setMinimumSize(780, 640)
        apply_windows_dark_titlebar(self)

        self._apply_styling()
        self._setup_ui()
        self._connect_signals()

        # Auto-detect URL from clipboard if no initial URL given
        target_url = self.initial_url
        if not target_url:
            cb = QApplication.clipboard()
            if cb:
                clip_text = cb.text().strip()
                if clip_text.startswith(('http://', 'https://')):
                    low = clip_text.lower()
                    if any(x in low for x in ('youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com', 'twitter.com', 'x.com', 'facebook.com', 'fb.watch', 'bilibili.com', 'vimeo.com', 'twitch.tv')):
                        target_url = clip_text

        if target_url:
            self.url_input.setText(target_url)
            self.start_analysis()

    def _apply_styling(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0b0f17;
                color: #e2e8f0;
                font-family: 'Segoe UI Variable Display', 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel {
                color: #e2e8f0;
            }
            QLineEdit, QComboBox {
                background-color: rgba(255, 255, 255, 0.05);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12);
                padding: 7px 11px;
                border-radius: 7px;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #10b981;
                background-color: rgba(255, 255, 255, 0.08);
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #141a27;
                color: #f8fafc;
                selection-background-color: #10b981;
                selection-color: #ffffff;
                border: 1px solid #27344a;
                border-radius: 6px;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.06);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.14);
                padding: 7px 16px;
                border-radius: 7px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.11);
                border: 1px solid rgba(255, 255, 255, 0.22);
                color: #ffffff;
            }
            QPushButton:disabled {
                background-color: #151b28;
                color: #475569;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
            QPushButton#btnAccent {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #059669, stop:1 #047857);
                border: 1px solid #10b981;
                border-radius: 7px;
                color: #ffffff;
                font-weight: 600;
                padding: 8px 20px;
            }
            QPushButton#btnAccent:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10b981, stop:1 #059669);
                border: 1px solid #34d399;
            }
            QPushButton#btnAccent:disabled {
                background-color: #151b28;
                color: #475569;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
            QTabWidget::pane {
                border: 1px solid rgba(255, 255, 255, 0.09);
                background-color: #0f1522;
                border-radius: 8px;
                padding: 10px;
            }
            QTabBar::tab {
                background-color: rgba(255, 255, 255, 0.04);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                padding: 7px 18px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: 500;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #0f1522;
                color: #10b981;
                border-bottom: 2px solid #10b981;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background-color: rgba(255, 255, 255, 0.08);
                color: #f1f5f9;
            }
            QTableWidget {
                background-color: #0d121c;
                color: #e2e8f0;
                gridline-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                selection-background-color: rgba(16, 185, 129, 0.15);
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #141a27;
                color: #94a3b8;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 5px;
                font-weight: 600;
                font-size: 11px;
            }
            QProgressBar {
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                text-align: center;
                color: #f8fafc;
                font-weight: 600;
                background-color: rgba(255, 255, 255, 0.04);
                height: 18px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #34d399);
                border-radius: 5px;
            }
            QCheckBox {
                color: #e2e8f0;
                font-size: 12px;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                background-color: rgba(255, 255, 255, 0.05);
            }
            QCheckBox::indicator:checked {
                background-color: #10b981;
                border: 1px solid #10b981;
            }
            QRadioButton {
                color: #e2e8f0;
                font-size: 12px;
                spacing: 6px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 0.05);
            }
            QRadioButton::indicator:checked {
                background-color: #10b981;
                border: 1px solid #10b981;
            }
        """)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Title Header
        header_layout = QVBoxLayout()
        header_title = QLabel("Download dari YouTube & Media Sosial")
        header_title.setStyleSheet("font-size: 17px; font-weight: bold; color: #f8fafc;")
        header_sub = QLabel("Ekstraksi video, audio, playlist, dan subtitle berkecepatan tinggi via yt-dlp")
        header_sub.setStyleSheet("font-size: 12px; color: #94a3b8;")
        header_layout.addWidget(header_title)
        header_layout.addWidget(header_sub)
        main_layout.addLayout(header_layout)

        # URL Input & Controls Row
        url_box = QHBoxLayout()
        url_box.setSpacing(8)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Tempel URL video atau playlist (YouTube, TikTok, Instagram, Twitter/X, dll)...")

        self.btn_paste = QPushButton("Tempel")
        self.btn_paste.setFixedWidth(70)

        # Browser Cookie Selector
        self.cookie_combo = QComboBox()
        self.cookie_combo.setFixedWidth(130)
        self.cookie_combo.addItems([
            "Tanpa Cookie",
            "Chrome",
            "Edge",
            "Firefox",
            "Brave",
            "Opera",
            "Vivaldi"
        ])
        self.cookie_combo.setToolTip("Gunakan autentikasi login browser untuk video berbatas usia atau khusus member")

        self.btn_analyze = QPushButton("Analisis")
        self.btn_analyze.setObjectName("btnAccent")
        self.btn_analyze.setFixedWidth(95)

        url_box.addWidget(self.url_input)
        url_box.addWidget(self.btn_paste)
        url_box.addWidget(self.cookie_combo)
        url_box.addWidget(self.btn_analyze)
        main_layout.addLayout(url_box)

        # Analyze Status label
        self.lbl_analyze_status = QLabel("")
        self.lbl_analyze_status.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 500;")
        self.lbl_analyze_status.hide()
        main_layout.addWidget(self.lbl_analyze_status)

        # Media Preview Card Frame
        self.card_frame = QFrame()
        self.card_frame.setStyleSheet("""
            QFrame {
                background-color: #0f1522;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 10px;
            }
        """)
        card_layout = QHBoxLayout(self.card_frame)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(14)

        # Thumbnail
        self.lbl_thumbnail = QLabel()
        self.lbl_thumbnail.setFixedSize(220, 124)
        self.lbl_thumbnail.setStyleSheet("""
            background-color: #141a27;
            border-radius: 6px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        """)
        self.lbl_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumbnail.setText("Pratinjau Media")
        card_layout.addWidget(self.lbl_thumbnail)

        # Media Info Details
        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(4)

        self.lbl_title = QLabel("Judul: -")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f8fafc;")

        self.lbl_uploader = QLabel("Kanal / Pembuat: -")
        self.lbl_uploader.setStyleSheet("font-size: 12px; color: #cbd5e1;")

        meta_sub_layout = QHBoxLayout()
        self.lbl_duration = QLabel("Durasi: -")
        self.lbl_duration.setStyleSheet("font-size: 12px; color: #94a3b8;")
        self.lbl_views = QLabel("Views: -")
        self.lbl_views.setStyleSheet("font-size: 12px; color: #94a3b8;")
        meta_sub_layout.addWidget(self.lbl_duration)
        meta_sub_layout.addWidget(self.lbl_views)
        meta_sub_layout.addStretch()

        # Playlist Options Container
        self.playlist_container = QWidget()
        pl_layout = QHBoxLayout(self.playlist_container)
        pl_layout.setContentsMargins(0, 4, 0, 0)
        pl_layout.setSpacing(10)

        self.lbl_playlist_badge = QLabel("Playlist: Terdeteksi")
        self.lbl_playlist_badge.setStyleSheet("""
            background-color: rgba(16, 185, 129, 0.15);
            color: #10b981;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 11px;
        """)

        self.rb_single_video = QRadioButton("Hanya video ini")
        self.rb_single_video.setChecked(True)
        self.rb_all_playlist = QRadioButton("Seluruh playlist")

        self.pl_range_input = QLineEdit()
        self.pl_range_input.setPlaceholderText("Urutan (misal: 1-10)")
        self.pl_range_input.setFixedWidth(120)
        self.pl_range_input.setEnabled(False)

        pl_layout.addWidget(self.lbl_playlist_badge)
        pl_layout.addWidget(self.rb_single_video)
        pl_layout.addWidget(self.rb_all_playlist)
        pl_layout.addWidget(self.pl_range_input)
        pl_layout.addStretch()
        self.playlist_container.hide()

        meta_layout.addWidget(self.lbl_title)
        meta_layout.addWidget(self.lbl_uploader)
        meta_layout.addLayout(meta_sub_layout)
        meta_layout.addWidget(self.playlist_container)
        meta_layout.addStretch()

        card_layout.addLayout(meta_layout)
        main_layout.addWidget(self.card_frame)

        # Tabs for Download Settings
        self.tabs = QTabWidget()

        # Tab 1: Video
        tab_video = QWidget()
        tv_layout = QVBoxLayout(tab_video)
        tv_layout.setSpacing(10)

        v_row1 = QHBoxLayout()
        v_row1.addWidget(QLabel("Kualitas Resolusi:"))
        self.combo_video_quality = QComboBox()
        self.combo_video_quality.addItems([
            "Kualitas Terbaik Otomatis (Best Quality)",
            "4K Ultra HD (2160p)",
            "2K Quad HD (1440p)",
            "1080p Full HD",
            "720p HD",
            "480p SD",
            "360p Hemat Kuota"
        ])
        v_row1.addWidget(self.combo_video_quality, 1)

        v_row1.addWidget(QLabel("Kontainer:"))
        self.combo_video_container = QComboBox()
        self.combo_video_container.addItems(["MP4 (Kompatibilitas Luas)", "MKV (Mendukung Semua Subtitle)", "WebM"])
        v_row1.addWidget(self.combo_video_container)
        tv_layout.addLayout(v_row1)

        # Subtitles Row
        v_row2 = QHBoxLayout()
        self.chk_subtitles = QCheckBox("Sertakan Subtitle")
        self.combo_sub_lang = QComboBox()
        self.combo_sub_lang.addItems(["Bahasa Indonesia (id)", "English (en)", "Semua Bahasa"])
        self.combo_sub_lang.setEnabled(False)
        v_row2.addWidget(self.chk_subtitles)
        v_row2.addWidget(self.combo_sub_lang, 1)
        tv_layout.addLayout(v_row2)

        # Video Metadata Checkbox
        self.chk_video_metadata = QCheckBox("Sematkan thumbnail & tag informasi ke file video")
        self.chk_video_metadata.setChecked(True)
        tv_layout.addWidget(self.chk_video_metadata)
        tv_layout.addStretch()
        self.tabs.addTab(tab_video, "Video")

        # Tab 2: Audio Only
        tab_audio = QWidget()
        ta_layout = QVBoxLayout(tab_audio)
        ta_layout.setSpacing(10)

        a_row1 = QHBoxLayout()
        a_row1.addWidget(QLabel("Format Audio:"))
        self.combo_audio_format = QComboBox()
        self.combo_audio_format.addItems([
            "MP3 (Standar Universal)",
            "M4A (AAC Kualitas Apple)",
            "FLAC (Lossless Studio)",
            "WAV (Lossless PCM)",
            "OPUS (Efisiensi Tinggi)"
        ])
        a_row1.addWidget(self.combo_audio_format, 1)

        a_row1.addWidget(QLabel("Bitrate:"))
        self.combo_audio_bitrate = QComboBox()
        self.combo_audio_bitrate.addItems([
            "320 kbps (Kualitas Maksimal)",
            "256 kbps (Kualitas Tinggi)",
            "192 kbps (Kualitas Standar)",
            "128 kbps (Hemat Ukuran)"
        ])
        a_row1.addWidget(self.combo_audio_bitrate)
        ta_layout.addLayout(a_row1)

        self.chk_audio_thumb = QCheckBox("Sematkan cover album (thumbnail) ke file audio")
        self.chk_audio_thumb.setChecked(True)
        ta_layout.addWidget(self.chk_audio_thumb)

        self.chk_audio_metadata = QCheckBox("Sematkan tag metadata ID3 (Artis, Judul, Album)")
        self.chk_audio_metadata.setChecked(True)
        ta_layout.addWidget(self.chk_audio_metadata)
        ta_layout.addStretch()
        self.tabs.addTab(tab_audio, "Audio Saja")

        # Tab 3: Detailed Streams Table
        tab_streams = QWidget()
        ts_layout = QVBoxLayout(tab_streams)
        ts_layout.setContentsMargins(4, 4, 4, 4)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Pilih", "Resolusi", "FPS", "Codec", "Ukuran", "Format Note"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        ts_layout.addWidget(self.table)
        self.format_btn_group = QButtonGroup(self)
        self.tabs.addTab(tab_streams, "Format Lengkap")

        # Tab 4: Performance & Network
        tab_perf = QWidget()
        tp_layout = QVBoxLayout(tab_perf)
        tp_layout.setSpacing(10)

        self.chk_parallel_fragments = QCheckBox("Download multi-fragment paralel (8 koneksi simultan)")
        self.chk_parallel_fragments.setChecked(True)
        tp_layout.addWidget(self.chk_parallel_fragments)

        has_aria2 = TorrentWorker.get_aria2_path() is not None
        self.chk_aria2 = QCheckBox("Akselerasi engine aria2c untuk segmen stream (16 koneksi)")
        self.chk_aria2.setChecked(has_aria2)
        self.chk_aria2.setEnabled(has_aria2)
        if not has_aria2:
            self.chk_aria2.setText("Akselerasi engine aria2c (tidak terdeteksi)")
        tp_layout.addWidget(self.chk_aria2)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Batas Kecepatan:"))
        self.combo_speed_limit = QComboBox()
        self.combo_speed_limit.addItems([
            "Tanpa Batas (Maksimal)",
            "1 MB/s",
            "2 MB/s",
            "5 MB/s",
            "10 MB/s"
        ])
        speed_row.addWidget(self.combo_speed_limit, 1)
        tp_layout.addLayout(speed_row)
        tp_layout.addStretch()
        self.tabs.addTab(tab_perf, "Akselerasi & Jaringan")

        main_layout.addWidget(self.tabs, 1)

        # Destination & Filename Section
        file_dest_layout = QVBoxLayout()
        file_dest_layout.setSpacing(6)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Simpan di:"), 0)
        self.path_input = QLineEdit()
        self.path_input.setText(os.path.expanduser("~/Downloads"))
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.setFixedWidth(80)
        path_row.addWidget(self.path_input, 1)
        path_row.addWidget(self.btn_browse, 0)
        file_dest_layout.addLayout(path_row)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Nama File:"), 0)
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Nama file keluaran...")
        name_row.addWidget(self.file_input, 1)
        file_dest_layout.addLayout(name_row)

        main_layout.addLayout(file_dest_layout)

        # Progress Area
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        self.lbl_progress_status = QLabel("")
        self.lbl_progress_status.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 500;")
        self.lbl_progress_status.hide()
        main_layout.addWidget(self.lbl_progress_status)

        # Bottom Buttons
        btn_bar = QHBoxLayout()
        self.btn_open_folder = QPushButton("Buka Folder")
        self.btn_open_folder.hide()
        self.btn_open_file = QPushButton("Buka File")
        self.btn_open_file.hide()

        btn_bar.addWidget(self.btn_open_folder)
        btn_bar.addWidget(self.btn_open_file)
        btn_bar.addStretch()

        self.btn_pause_resume = QPushButton("Jeda")
        self.btn_pause_resume.hide()
        self.btn_cancel = QPushButton("Batal")
        self.btn_queue = QPushButton("Tambah ke Antrean")
        self.btn_queue.setEnabled(False)
        if not self.engine:
            self.btn_queue.hide()
        self.btn_download = QPushButton("Unduh Sekarang")
        self.btn_download.setObjectName("btnAccent")
        self.btn_download.setEnabled(False)

        btn_bar.addWidget(self.btn_pause_resume)
        btn_bar.addWidget(self.btn_cancel)
        btn_bar.addWidget(self.btn_queue)
        btn_bar.addWidget(self.btn_download)
        main_layout.addLayout(btn_bar)

    def _connect_signals(self):
        self.btn_paste.clicked.connect(self._paste_clipboard)
        self.btn_analyze.clicked.connect(self.start_analysis)
        self.url_input.returnPressed.connect(self.start_analysis)
        self.btn_browse.clicked.connect(self.browse_path)
        self.btn_cancel.clicked.connect(self._handle_cancel)
        self.btn_queue.clicked.connect(self._add_to_main_queue)
        self.btn_download.clicked.connect(self.start_download)
        self.btn_pause_resume.clicked.connect(self._toggle_pause_resume)
        self.btn_open_folder.clicked.connect(self._open_folder)
        self.btn_open_file.clicked.connect(self._open_file)

        self.chk_subtitles.toggled.connect(self.combo_sub_lang.setEnabled)
        self.rb_all_playlist.toggled.connect(self.pl_range_input.setEnabled)

        self.progress_signal.connect(self.update_progress)
        self.status_signal.connect(self.update_status)
        self.finished_signal.connect(self.on_download_finished)

    def _paste_clipboard(self):
        cb = QApplication.clipboard()
        if cb:
            txt = cb.text().strip()
            if txt:
                self.url_input.setText(txt)
                self.start_analysis()

    def start_analysis(self):
        url = self.url_input.text().strip()
        if not url:
            return

        self.btn_analyze.setEnabled(False)
        self.lbl_analyze_status.setText("Menganalisis link media via yt-dlp...")
        self.lbl_analyze_status.setStyleSheet("color: #38bdf8; font-weight: 500;")
        self.lbl_analyze_status.show()
        self.table.setRowCount(0)
        self.btn_download.setEnabled(False)
        self.btn_queue.setEnabled(False)
        self.btn_open_folder.hide()
        self.btn_open_file.hide()

        # Selected browser cookie
        cookie_choice = self.cookie_combo.currentText().strip()
        browser_arg = None
        if cookie_choice != "Tanpa Cookie":
            browser_arg = cookie_choice.lower()

        # Proxy from engine DB if exists
        proxy_url = None
        if self.engine and hasattr(self.engine, 'db'):
            proxy_url = self.engine.db.get_setting("proxy_url", "")

        self.info_worker = YtdlpInfoWorker(url=url, cookies_browser=browser_arg, proxy=proxy_url)
        self.info_worker.info_ready.connect(self.on_info_ready)
        self.info_worker.error.connect(self.on_info_error)
        self.info_worker.start()

    @pyqtSlot(dict)
    def on_info_ready(self, info: dict):
        self.current_info = info
        self.lbl_analyze_status.setText("Analisis berhasil!")
        self.lbl_analyze_status.setStyleSheet("color: #10b981; font-weight: 500;")
        self.btn_analyze.setEnabled(True)

        title = info.get('title') or 'Unknown Title'
        uploader = info.get('uploader') or info.get('channel') or 'Unknown'
        duration_str = info.get('duration_str') or '--:--'
        views = info.get('view_count')
        views_str = f"Views: {views:,}" if views else ""

        self.lbl_title.setText(f"Judul: {title}")
        self.lbl_uploader.setText(f"Kanal / Pembuat: {uploader}")
        self.lbl_duration.setText(f"Durasi: {duration_str}")
        self.lbl_views.setText(views_str)

        # Playlist detection
        is_playlist = info.get('is_playlist', False)
        pl_count = info.get('playlist_count', 1)
        if is_playlist or pl_count > 1:
            self.lbl_playlist_badge.setText(f"Playlist: {pl_count} Video")
            self.playlist_container.show()
        else:
            self.playlist_container.hide()

        # Filename auto-fill
        clean_title = sanitize_filename(title)
        self.file_input.setText(clean_title)

        # Fetch Thumbnail
        thumb_url = info.get('thumbnail_url')
        if thumb_url:
            self.thumb_worker = ThumbnailWorker(thumb_url)
            self.thumb_worker.thumb_ready.connect(self.set_thumbnail)
            self.thumb_worker.start()

        # Populate Subtitles
        subtitles = info.get('subtitles', [])
        self.combo_sub_lang.clear()
        self.combo_sub_lang.addItem("Bahasa Indonesia (id)", "id")
        self.combo_sub_lang.addItem("English (en)", "en")
        self.combo_sub_lang.addItem("Semua Bahasa yang Tersedia", "all")
        for s in subtitles:
            code = s.get('code', '')
            name = s.get('name', code)
            if code not in ('id', 'en'):
                self.combo_sub_lang.addItem(f"{name} ({code})", code)

        # Populate Streams Table
        self.populate_formats(info.get('formats', []))
        self.btn_download.setEnabled(True)
        self.btn_queue.setEnabled(True)

    @pyqtSlot(str)
    def on_info_error(self, err: str):
        self.lbl_analyze_status.setText(f"Gagal menganalisis: {err}")
        self.lbl_analyze_status.setStyleSheet("color: #ef4444; font-weight: 500;")
        self.btn_analyze.setEnabled(True)

    @pyqtSlot(QPixmap)
    def set_thumbnail(self, pixmap: QPixmap):
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self.lbl_thumbnail.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_thumbnail.setPixmap(scaled)

    def populate_formats(self, formats: list):
        self.table.setRowCount(0)
        for btn in self.format_btn_group.buttons():
            self.format_btn_group.removeButton(btn)

        row = 0
        for fmt in formats:
            self.table.insertRow(row)

            rb = QRadioButton()
            rb.setProperty("format_id", fmt.get('id', ''))
            if row == 0:
                rb.setChecked(True)
            self.format_btn_group.addButton(rb)

            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(4, 0, 0, 0)
            l.addWidget(rb)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 0, w)

            self.table.setItem(row, 1, QTableWidgetItem(fmt.get('resolution', '-')))
            self.table.setItem(row, 2, QTableWidgetItem(str(fmt.get('fps') or '-')))

            codec_str = f"{fmt.get('vcodec', '-')} / {fmt.get('acodec', '-')}"
            self.table.setItem(row, 3, QTableWidgetItem(codec_str))

            self.table.setItem(row, 4, QTableWidgetItem(fmt.get('filesize_str', '-')))
            self.table.setItem(row, 5, QTableWidgetItem(fmt.get('format_note', '')))
            row += 1

    def browse_path(self):
        directory = QFileDialog.getExistingDirectory(self, "Pilih Folder Simpan", self.path_input.text())
        if directory:
            self.path_input.setText(directory)

    def start_download(self):
        url = self.url_input.text().strip()
        save_dir = self.path_input.text().strip()
        filename = self.file_input.text().strip()
        if not url or not save_dir:
            return

        current_tab = self.tabs.currentIndex()
        # Tab mapping: 0=Video, 1=Audio Saja, 2=Format Lengkap, 3=Akselerasi
        download_mode = "video"
        format_id = "best"
        video_quality = "best"
        container_format = "mp4"
        audio_format = "mp3"
        audio_bitrate = "320"
        embed_subtitles = False
        subtitle_langs = []
        embed_thumb = True
        embed_metadata = True

        if current_tab == 1:
            # Audio Tab
            download_mode = "audio"
            fmt_text = self.combo_audio_format.currentText()
            if "MP3" in fmt_text:
                audio_format = "mp3"
            elif "M4A" in fmt_text:
                audio_format = "m4a"
            elif "FLAC" in fmt_text:
                audio_format = "flac"
            elif "WAV" in fmt_text:
                audio_format = "wav"
            elif "OPUS" in fmt_text:
                audio_format = "opus"

            bitrate_text = self.combo_audio_bitrate.currentText()
            if "320" in bitrate_text:
                audio_bitrate = "320"
            elif "256" in bitrate_text:
                audio_bitrate = "256"
            elif "192" in bitrate_text:
                audio_bitrate = "192"
            else:
                audio_bitrate = "128"

            embed_thumb = self.chk_audio_thumb.isChecked()
            embed_metadata = self.chk_audio_metadata.isChecked()

        elif current_tab == 2:
            # Format Lengkap Tab
            download_mode = "custom"
            checked_btn = self.format_btn_group.checkedButton()
            if checked_btn:
                format_id = checked_btn.property("format_id")
            container_format = "mp4"

        else:
            # Video Tab (or perf tab default)
            download_mode = "video"
            qual_text = self.combo_video_quality.currentText()
            if "2160" in qual_text:
                video_quality = "2160"
            elif "1440" in qual_text:
                video_quality = "1440"
            elif "1080" in qual_text:
                video_quality = "1080"
            elif "720" in qual_text:
                video_quality = "720"
            elif "480" in qual_text:
                video_quality = "480"
            elif "360" in qual_text:
                video_quality = "360"
            else:
                video_quality = "best"

            cont_text = self.combo_video_container.currentText()
            if "MKV" in cont_text:
                container_format = "mkv"
            elif "WebM" in cont_text:
                container_format = "webm"
            else:
                container_format = "mp4"

            embed_subtitles = self.chk_subtitles.isChecked()
            if embed_subtitles:
                sel_lang_data = self.combo_sub_lang.currentData()
                if sel_lang_data == "all":
                    subtitle_langs = ['all']
                elif sel_lang_data:
                    subtitle_langs = [sel_lang_data]
                else:
                    subtitle_langs = ['id', 'en']

            embed_thumb = self.chk_video_metadata.isChecked()
            embed_metadata = self.chk_video_metadata.isChecked()

        # Playlist options
        is_playlist = self.rb_all_playlist.isChecked() if self.playlist_container.isVisible() else False
        playlist_items = self.pl_range_input.text().strip() if is_playlist else None

        # Network & Performance
        concurrent_frags = 8 if self.chk_parallel_fragments.isChecked() else 1
        use_aria2 = self.chk_aria2.isChecked()

        # Speed limit
        spd_text = self.combo_speed_limit.currentText()
        rate_limit = 0
        if "1 MB/s" in spd_text:
            rate_limit = 1024 * 1024
        elif "2 MB/s" in spd_text:
            rate_limit = 2 * 1024 * 1024
        elif "5 MB/s" in spd_text:
            rate_limit = 5 * 1024 * 1024
        elif "10 MB/s" in spd_text:
            rate_limit = 10 * 1024 * 1024

        # Browser cookie
        cookie_choice = self.cookie_combo.currentText().strip()
        browser_arg = cookie_choice.lower() if cookie_choice != "Tanpa Cookie" else None

        # Proxy
        proxy_url = None
        if self.engine and hasattr(self.engine, 'db'):
            proxy_url = self.engine.db.get_setting("proxy_url", "")

        self.pause_event = threading.Event()
        self.pause_event.set()
        self.cancel_event = threading.Event()
        self.cancel_event.clear()

        self.worker = YtdlpWorker(
            url=url,
            format_id=format_id,
            save_dir=save_dir,
            filename=filename,
            task_id="yt_task",
            pause_event=self.pause_event,
            cancel_event=self.cancel_event,
            on_progress=lambda d, t, s, e: self.progress_signal.emit(d, t, float(s or 0.0), float(e or 0.0)),
            on_status=lambda msg: self.status_signal.emit(msg),
            on_finished=lambda ok, err, path: self.finished_signal.emit(ok, err or "", path or ""),
            download_mode=download_mode,
            video_quality=video_quality,
            container_format=container_format,
            audio_format=audio_format,
            audio_bitrate=audio_bitrate,
            embed_subtitles=embed_subtitles,
            subtitle_langs=subtitle_langs,
            embed_thumbnail=embed_thumb,
            embed_metadata=embed_metadata,
            concurrent_fragments=concurrent_frags,
            use_aria2=use_aria2,
            cookies_browser=browser_arg,
            rate_limit=rate_limit,
            proxy=proxy_url,
            is_playlist=is_playlist,
            playlist_items=playlist_items
        )
        self.worker.start()

        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.lbl_progress_status.setText("Memulai proses unduhan...")
        self.lbl_progress_status.setStyleSheet("color: #10b981;")
        self.lbl_progress_status.show()

        self.btn_download.setEnabled(False)
        self.btn_queue.setEnabled(False)
        self.btn_pause_resume.setText("Jeda")
        self.btn_pause_resume.show()
        self.btn_open_folder.hide()
        self.btn_open_file.hide()
        self.download_started.emit()

    def _toggle_pause_resume(self):
        if not self.pause_event:
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause_resume.setText("Lanjutkan")
            self.lbl_progress_status.setText("Unduhan dijeda.")
        else:
            self.pause_event.set()
            self.btn_pause_resume.setText("Jeda")
            self.lbl_progress_status.setText("Melanjutkan unduhan...")

    def _handle_cancel(self):
        if self.worker and self.worker.is_alive():
            if self.cancel_event:
                self.cancel_event.set()
            if self.pause_event:
                self.pause_event.set()
            self.lbl_progress_status.setText("Membatalkan unduhan...")
            self.lbl_progress_status.setStyleSheet("color: #f59e0b;")
        else:
            self.close()

    @pyqtSlot(int, int, float, float)
    def update_progress(self, downloaded, total, speed, eta):
        pct = 0
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.progress_bar.setValue(min(100, max(0, pct)))

        speed_mb = speed / (1024 * 1024) if speed > 0 else 0.0
        dl_mb = downloaded / (1024 * 1024)
        tot_mb = total / (1024 * 1024) if total > 0 else 0.0

        eta_str = "--:--"
        if eta > 0:
            m, s = divmod(int(eta), 60)
            eta_str = f"{m:02d}:{s:02d}"

        if total > 0:
            self.lbl_progress_status.setText(
                f"Mengunduh... {pct}% ({dl_mb:.1f} MB / {tot_mb:.1f} MB) | Kecepatan: {speed_mb:.1f} MB/s | Sisa: {eta_str}"
            )
        else:
            self.lbl_progress_status.setText(
                f"Mengunduh... {dl_mb:.1f} MB terunduh | Kecepatan: {speed_mb:.1f} MB/s"
            )

    @pyqtSlot(str)
    def update_status(self, msg: str):
        if msg:
            self.lbl_progress_status.setText(msg)

    @pyqtSlot(bool, str, str)
    def on_download_finished(self, ok: bool, error: str, path: str):
        self.btn_pause_resume.hide()
        self.btn_download.setEnabled(True)
        self.btn_queue.setEnabled(True)

        if ok:
            self.final_download_path = path or ""
            self.progress_bar.setValue(100)
            self.lbl_progress_status.setText("Unduhan berhasil diselesaikan!")
            self.lbl_progress_status.setStyleSheet("color: #10b981; font-weight: 600;")
            self.btn_open_folder.show()
            if path and os.path.isfile(path):
                self.btn_open_file.show()
        else:
            if "dibatalkan" in (error or "").lower():
                self.lbl_progress_status.setText("Unduhan dibatalkan.")
                self.lbl_progress_status.setStyleSheet("color: #94a3b8;")
            else:
                self.lbl_progress_status.setText(f"Error: {error}")
                self.lbl_progress_status.setStyleSheet("color: #ef4444;")

    def _open_folder(self):
        target = self.final_download_path or self.path_input.text().strip()
        if target:
            folder = os.path.dirname(target) if os.path.isfile(target) else target
            if os.path.exists(folder):
                subprocess.Popen(f'explorer "{os.path.abspath(folder)}"')

    def _open_file(self):
        if self.final_download_path and os.path.isfile(self.final_download_path):
            os.startfile(os.path.abspath(self.final_download_path))

    def _add_to_main_queue(self):
        if not self.engine:
            return
        url = self.url_input.text().strip()
        save_dir = self.path_input.text().strip()
        filename = self.file_input.text().strip()
        if not url or not save_dir:
            return

        current_tab = self.tabs.currentIndex()
        download_mode = "video"
        format_id = "best"
        video_quality = "best"
        container_format = "mp4"
        audio_format = "mp3"
        audio_bitrate = "320"
        embed_subtitles = False

        if current_tab == 1:
            download_mode = "audio"
            fmt_text = self.combo_audio_format.currentText()
            if "MP3" in fmt_text:
                audio_format = "mp3"
            elif "M4A" in fmt_text:
                audio_format = "m4a"
            elif "FLAC" in fmt_text:
                audio_format = "flac"
            elif "WAV" in fmt_text:
                audio_format = "wav"
            elif "OPUS" in fmt_text:
                audio_format = "opus"

            bitrate_text = self.combo_audio_bitrate.currentText()
            if "320" in bitrate_text:
                audio_bitrate = "320"
            elif "256" in bitrate_text:
                audio_bitrate = "256"
            elif "192" in bitrate_text:
                audio_bitrate = "192"
            else:
                audio_bitrate = "128"
            ext = audio_format

        elif current_tab == 2:
            download_mode = "custom"
            checked_btn = self.format_btn_group.checkedButton()
            if checked_btn:
                format_id = checked_btn.property("format_id")
            container_format = "mp4"
            ext = "mp4"

        else:
            download_mode = "video"
            qual_text = self.combo_video_quality.currentText()
            if "2160" in qual_text:
                video_quality = "2160"
            elif "1440" in qual_text:
                video_quality = "1440"
            elif "1080" in qual_text:
                video_quality = "1080"
            elif "720" in qual_text:
                video_quality = "720"
            elif "480" in qual_text:
                video_quality = "480"
            elif "360" in qual_text:
                video_quality = "360"
            else:
                video_quality = "best"

            cont_text = self.combo_video_container.currentText()
            if "MKV" in cont_text:
                container_format = "mkv"
            elif "WebM" in cont_text:
                container_format = "webm"
            else:
                container_format = "mp4"

            embed_subtitles = self.chk_subtitles.isChecked()
            ext = container_format

        cookie_choice = self.cookie_combo.currentText().strip()
        browser_arg = cookie_choice.lower() if cookie_choice != "Tanpa Cookie" else ""

        base_fn = sanitize_filename(filename or "media_download")
        full_fn = base_fn if base_fn.lower().endswith(f".{ext}") else f"{base_fn}.{ext}"

        task = self.engine.create_task(
            url=url,
            save_dir=save_dir,
            filename=full_fn,
            headers={
                'is_ytdlp': 'true',
                'format_id': format_id,
                'download_mode': download_mode,
                'video_quality': video_quality,
                'container_format': container_format,
                'audio_format': audio_format,
                'audio_bitrate': audio_bitrate,
                'embed_subtitles': 'true' if embed_subtitles else 'false',
                'cookies_browser': browser_arg,
            },
            total_bytes=-1,
            resumable=True
        )
        self.engine.start_download(task.id)
        self.accept()
