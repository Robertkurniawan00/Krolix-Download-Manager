import os
import threading
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QComboBox, QSpinBox, QMessageBox,
    QWidget, QCheckBox, QFrame, QMenu
)
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from ..core.downloader import DownloadEngine
from ..core.link_resolver import CloudLinkResolver
from ..utils.helpers import format_bytes, sanitize_filename, apply_windows_dark_titlebar, get_category_from_filename
from .conflict_dialog import FileConflictDialog


class ProbeWorker(QObject):
    finished = pyqtSignal(dict)

    def __init__(self, engine: DownloadEngine, url: str):
        super().__init__()
        self.engine = engine
        self.url = url

    def run(self):
        info = self.engine.probe_url(self.url)
        self.finished.emit(info)


class AddDownloadDialog(QDialog):
    """
    Download File Info Dialog.
    Faithfully styled after the reference mockup (media_1788889546179.png):
    - Glowing emerald green top rim light
    - Clean 'Download File Info' header with emerald wireframe globe icon
    - Obsidian dark card layout with aligned label fields
    - Monospace cyan URL input field
    - Telemetry status card showing probed file size and resume pill badge
    - Standard Category, Save To, Connections & Queue controls
    - Collapsible Advanced Options (Headers, Proxy, Checksum, Auto-extract)
    - High-contrast Emerald 'Start Download', 'Download Later', and 'Cancel' actions
    """
    probe_finished_signal = pyqtSignal(dict)
    mode_switch_requested = pyqtSignal(str)

    def __init__(self, engine: DownloadEngine, initial_url: str = "", default_save_dir: str = "", parent=None,
                 initial_filename: str = "", initial_filesize: int = -1, initial_headers: dict = None,
                 skip_probe: bool = False, initial_resolution: str = "", initial_bitrate: int = 0,
                 variants: list = None, initial_description: str = ""):
        super().__init__(parent)
        self.engine = engine
        self.default_save_dir = default_save_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        self.result_task = None
        self.start_immediately = True
        self.initial_filename = initial_filename
        self.initial_filesize = initial_filesize
        self.probed_size = initial_filesize
        self.initial_description = initial_description or ""
        self.selected_torrent_files = None
        self.current_resolution = initial_resolution or ""
        self.current_bitrate = initial_bitrate or 0
        self.variants = variants or []
        from ..core.link_resolver import CloudLinkResolver
        if initial_url:
            initial_url = CloudLinkResolver.resolve(initial_url)
            initial_headers = CloudLinkResolver.fix_headers(initial_url, initial_headers)
        self.initial_headers = initial_headers or {}
        self.skip_probe = skip_probe

        self.setWindowTitle("Download File Info")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumWidth(560)
        self.resize(580, 440)
        apply_windows_dark_titlebar(self)

        self.setStyleSheet("""
            QDialog {
                background-color: #070a0f;
                border: 1px solid #1b273d;
                border-radius: 8px;
            }
            QLabel {
                color: #cbd5e1;
                font-family: 'Inter', -apple-system, sans-serif;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #0b0f17;
                border: 1px solid #151f30;
                border-radius: 5px;
                padding: 6px 10px;
                color: #f1f5f9;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #10b981;
                background-color: #0d1320;
            }
        """)

        # Set Window Icon
        logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "logo_32.png"))
        globe_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "globe.png"))
        if os.path.exists(globe_path):
            self.setWindowIcon(QIcon(globe_path))
        elif os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.probe_finished_signal.connect(self._on_probe_complete)
        self._init_ui(initial_url)

        if initial_filename and hasattr(self, "txt_filename"):
            self.txt_filename.setText(initial_filename)

        if initial_headers and "Referer" in initial_headers and hasattr(self, "txt_referer"):
            self.txt_referer.setText(initial_headers["Referer"])

        is_hls = (initial_headers and (initial_headers.get("is_hls") == "true" or initial_headers.get("is_hls") is True)) or (".m3u8" in initial_url.lower()) or (".mpd" in initial_url.lower())
        if self.variants:
            self._populate_variants(self.variants, selected_url=initial_url)
        elif is_hls:
            self.lbl_probe_status.setText("● HLS Stream Detected")
            self.lbl_probe_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
            if initial_filesize > 0:
                self.lbl_probe_size.setText(f"Size: <b style='color: #f1f5f9;'>~{format_bytes(initial_filesize)}</b>")
            else:
                self.lbl_probe_size.setText("Size: <b style='color: #cbd5e1;'>Auto Convert to MP4</b>")
            self.lbl_probe_resume.setText("Resume: <span style='background-color: rgba(16,185,129,0.2); color: #34d399; padding: 2px 6px; border-radius: 3px; font-weight: 600;'>Yes</span>")
            if self.current_resolution:
                self.lbl_probe_res.setText(f"Res: <b style='color: #94a3b8;'>{self.current_resolution}</b>")
                self.lbl_probe_res.setVisible(True)
            if self.current_bitrate > 0:
                b_str = f"{self.current_bitrate/1000:.1f} Mbps" if self.current_bitrate >= 1000 else f"{self.current_bitrate} kbps"
                self.lbl_probe_bitrate.setText(f"Bitrate: <b style='color: #34d399;'>{b_str}</b>")
                self.lbl_probe_bitrate.setVisible(True)
            idx = self.cmb_cat.findText("Video")
            if idx >= 0:
                self.cmb_cat.setCurrentIndex(idx)
        elif initial_filesize > 0:
            size_str = format_bytes(initial_filesize)
            self.lbl_probe_status.setText("● Server Connected")
            self.lbl_probe_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
            self.lbl_probe_size.setText(f"Size: <b style='color: #f1f5f9;'>{size_str}</b>")
            self.lbl_probe_resume.setText("Resume: <span style='background-color: rgba(16,185,129,0.2); color: #34d399; padding: 2px 6px; border-radius: 3px; font-weight: 600;'>Yes</span>")
            cat = get_category_from_filename(initial_filename)
            idx = self.cmb_cat.findText(cat)
            if idx >= 0:
                self.cmb_cat.setCurrentIndex(idx)

        if initial_url and not skip_probe and not self.variants:
            self._start_probe()

    def _init_ui(self, initial_url: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(0)

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
        layout.addWidget(rim_line)

        # Content container
        content_box = QWidget()
        content_layout = QVBoxLayout(content_box)
        content_layout.setContentsMargins(18, 14, 18, 0)
        content_layout.setSpacing(12)
        layout.addWidget(content_box)

        # 2. Header Bar: Globe Icon + "Download File Info"
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        globe_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "globe.png"))
        if os.path.exists(globe_path):
            lbl_globe = QLabel()
            lbl_globe.setPixmap(QPixmap(globe_path).scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            header_layout.addWidget(lbl_globe)

        lbl_header_title = QLabel("Download File Info")
        lbl_header_title.setStyleSheet("font-weight: 600; font-size: 13px; color: #f1f5f9; letter-spacing: 0.3px;")
        header_layout.addWidget(lbl_header_title)

        header_layout.addStretch()

        badge_proto = QLabel("KROLIX ACCELERATOR")
        badge_proto.setStyleSheet("font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #34d399; font-weight: 600; letter-spacing: 1px;")
        header_layout.addWidget(badge_proto)

        content_layout.addLayout(header_layout)

        # 3. URL Input (Cyan Monospace styling as in reference)
        url_layout = QHBoxLayout()
        url_layout.setSpacing(10)
        lbl_url = QLabel("URL")
        lbl_url.setFixedWidth(72)
        lbl_url.setStyleSheet("font-weight: 600; color: #94a3b8; font-size: 11px;")
        url_layout.addWidget(lbl_url)

        self.txt_url = QLineEdit(initial_url)
        self.txt_url.setPlaceholderText("https://example.com/file.zip atau link video/m3u8...")
        self.txt_url.setStyleSheet("""
            QLineEdit {
                background-color: #050811;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 7px 10px;
                color: #f8fafc;
                font-family: 'Segoe UI Variable Text', monospace;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #2563eb;
                background-color: #080e1a;
            }
        """)
        self.txt_url.textChanged.connect(self._on_url_changed)
        url_layout.addWidget(self.txt_url)

        self.btn_batch_mode = QPushButton("Batch Mode")
        self.btn_batch_mode.setToolTip("Pilih mode unduhan lain (Batch, Sniffer, YT-DLP, Grabber)")
        self.btn_batch_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_batch_mode.setFixedHeight(30)
        self.btn_batch_mode.setStyleSheet("""
            QPushButton {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 5px;
                padding: 4px 10px;
                color: #38bdf8;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        batch_menu = QMenu(self.btn_batch_mode)
        batch_menu.setStyleSheet("""
            QMenu {
                background-color: #1e293b;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px;
                color: #f8fafc;
            }
            QMenu::item {
                padding: 7px 20px 7px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #334155;
                color: #ffffff;
            }
        """)
        act_b = batch_menu.addAction("Batch Download (Pola / Daftar URL)...")
        act_b.triggered.connect(lambda: self._switch_mode("batch"))
        act_s = batch_menu.addAction("Sniff & Ekstrak Link Massal (Clipboard)...")
        act_s.triggered.connect(lambda: self._switch_mode("sniffer"))
        act_y = batch_menu.addAction("Download YouTube & Media Sosial (YT-DLP)...")
        act_y.triggered.connect(lambda: self._switch_mode("ytdlp"))
        act_g = batch_menu.addAction("Site Grabber (Jelajahi & Unduh Situs Web)...")
        act_g.triggered.connect(lambda: self._switch_mode("grabber"))
        self.btn_batch_mode.setMenu(batch_menu)
        url_layout.addWidget(self.btn_batch_mode)

        content_layout.addLayout(url_layout)

        # 4. Probed Telemetry Status Card
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

        self.lbl_probe_status = QLabel("● Ready to probe")
        self.lbl_probe_status.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        info_layout.addWidget(self.lbl_probe_status)

        self.lbl_probe_res = QLabel("Res: --")
        self.lbl_probe_res.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.lbl_probe_res.setVisible(False)
        info_layout.addWidget(self.lbl_probe_res)

        self.lbl_probe_bitrate = QLabel("Bitrate: --")
        self.lbl_probe_bitrate.setStyleSheet("color: #34d399; font-size: 11px;")
        self.lbl_probe_bitrate.setVisible(False)
        info_layout.addWidget(self.lbl_probe_bitrate)

        info_layout.addStretch()

        self.lbl_probe_size = QLabel("Size: --")
        self.lbl_probe_size.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        info_layout.addWidget(self.lbl_probe_size)

        self.lbl_probe_resume = QLabel("Resume: --")
        self.lbl_probe_resume.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        info_layout.addWidget(self.lbl_probe_resume)

        content_layout.addWidget(self.info_card)

        # 4b. Stream Resolution / Quality Selector Row (Krolix Style)
        self.row_resolution = QWidget()
        res_layout = QHBoxLayout(self.row_resolution)
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_layout.setSpacing(10)

        lbl_res = QLabel("Quality")
        lbl_res.setFixedWidth(72)
        lbl_res.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        res_layout.addWidget(lbl_res)

        self.cmb_resolution = QComboBox()
        self.cmb_resolution.setStyleSheet("""
            QComboBox {
                background-color: #0b0f17;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 6px 10px;
                color: #f1f5f9;
                font-family: 'JetBrains Mono', 'Segoe UI', monospace;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox:hover {
                border-color: #475569;
                background-color: #111827;
            }
            QComboBox::drop-down {
                border: none;
                width: 22px;
            }
            QComboBox QAbstractItemView {
                background-color: #0b0f17;
                border: 1px solid #1e293b;
                selection-background-color: #1e293b;
                selection-color: #ffffff;
                color: #f1f5f9;
                padding: 4px;
            }
        """)
        self.cmb_resolution.currentIndexChanged.connect(self._on_resolution_changed)
        res_layout.addWidget(self.cmb_resolution, 1)

        self.btn_pick_res = QPushButton("Grabber...")
        self.btn_pick_res.setToolTip("Buka Media Grabber untuk opsi resolusi / audio lebih lanjut")
        self.btn_pick_res.setStyleSheet("""
            QPushButton {
                background-color: #0f1724;
                border: 1px solid #1b273d;
                border-radius: 4px;
                padding: 6px 10px;
                color: #cbd5e1;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #151f30;
                color: #ffffff;
                border-color: #475569;
            }
        """)
        self.btn_pick_res.clicked.connect(self._open_media_grabber)
        res_layout.addWidget(self.btn_pick_res)

        self.row_resolution.setVisible(False)
        content_layout.addWidget(self.row_resolution)

        # 5. File Name Row
        file_layout = QHBoxLayout()
        file_layout.setSpacing(10)
        lbl_file = QLabel("File Name")
        lbl_file.setFixedWidth(72)
        lbl_file.setStyleSheet("color: #94a3b8; font-size: 11px;")
        file_layout.addWidget(lbl_file)

        self.txt_filename = QLineEdit()
        self.txt_filename.setPlaceholderText("auto_detected_filename.ext")
        file_layout.addWidget(self.txt_filename)
        content_layout.addLayout(file_layout)

        # 6. Save Location Row
        save_layout = QHBoxLayout()
        save_layout.setSpacing(10)
        lbl_save = QLabel("Save To")
        lbl_save.setFixedWidth(72)
        lbl_save.setStyleSheet("color: #94a3b8; font-size: 11px;")
        save_layout.addWidget(lbl_save)

        self.txt_save_path = QLineEdit(self.default_save_dir)
        save_layout.addWidget(self.txt_save_path)

        btn_browse = QPushButton("Browse...")
        btn_browse.setStyleSheet("""
            QPushButton {
                background-color: #0f1724;
                border: 1px solid #1b273d;
                border-radius: 5px;
                padding: 6px 14px;
                color: #cbd5e1;
            }
            QPushButton:hover {
                background-color: #151f30;
                color: #ffffff;
                border-color: #253550;
            }
        """)
        btn_browse.clicked.connect(self._browse_folder)
        save_layout.addWidget(btn_browse)
        content_layout.addLayout(save_layout)

        # 6b. Description Row (Optional, empty by default)
        desc_layout = QHBoxLayout()
        desc_layout.setSpacing(10)
        lbl_desc = QLabel("Description")
        lbl_desc.setFixedWidth(72)
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        desc_layout.addWidget(lbl_desc)

        self.txt_description = QLineEdit(self.initial_description)
        self.txt_description.setPlaceholderText("Optional description or note")
        desc_layout.addWidget(self.txt_description)
        content_layout.addLayout(desc_layout)

        # 7. Category, Connections & Queue Row
        opts_layout = QHBoxLayout()
        opts_layout.setSpacing(10)

        lbl_cat = QLabel("Category")
        lbl_cat.setFixedWidth(72)
        lbl_cat.setStyleSheet("color: #94a3b8; font-size: 11px;")
        opts_layout.addWidget(lbl_cat)

        self.cmb_cat = QComboBox()
        cats = ["General", "Compressed", "Documents", "Music", "Video", "Programs"]
        self.cmb_cat.addItems(cats)
        self.cmb_cat.currentTextChanged.connect(self._on_category_changed)
        opts_layout.addWidget(self.cmb_cat, 1)

        lbl_conn = QLabel("Threads:")
        lbl_conn.setStyleSheet("color: #94a3b8; font-size: 11px;")
        opts_layout.addWidget(lbl_conn)

        self.spn_conn = QSpinBox()
        self.spn_conn.setRange(1, 64)
        def_conn = 16
        if hasattr(self.engine, "db") and self.engine.db:
            try:
                def_conn = int(self.engine.db.get_setting("connections_count", 16))
            except Exception:
                pass
        self.spn_conn.setValue(def_conn)
        self.spn_conn.setFixedWidth(80)
        opts_layout.addWidget(self.spn_conn)

        lbl_queue = QLabel("Queue:")
        lbl_queue.setStyleSheet("color: #94a3b8; font-size: 11px;")
        opts_layout.addWidget(lbl_queue)

        self.cmb_queue = QComboBox()
        queues = [q["name"] for q in self.engine.db.get_queues()] if hasattr(self.engine, "db") else ["Main Queue"]
        self.cmb_queue.addItems(queues if queues else ["Main Queue"])
        opts_layout.addWidget(self.cmb_queue, 1)

        content_layout.addLayout(opts_layout)

        # 8. Advanced Options Collapsible
        self.chk_show_advanced = QPushButton("▸ Show Advanced Options (Headers, Proxy, Checksum, Extract)")
        self.chk_show_advanced.setCheckable(True)
        self.chk_show_advanced.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #94a3b8;
                font-size: 11px;
                text-align: left;
                padding: 4px 0;
            }
            QPushButton:hover {
                color: #f1f5f9;
            }
        """)
        content_layout.addWidget(self.chk_show_advanced)

        self.adv_widget = QWidget()
        adv_layout = QVBoxLayout(self.adv_widget)
        adv_layout.setContentsMargins(0, 4, 0, 4)
        adv_layout.setSpacing(8)

        # Referer
        h_ref = QHBoxLayout()
        lbl_ref = QLabel("Referer")
        lbl_ref.setFixedWidth(72)
        lbl_ref.setStyleSheet("color: #94a3b8; font-size: 11px;")
        h_ref.addWidget(lbl_ref)
        self.txt_referer = QLineEdit()
        self.txt_referer.setPlaceholderText("https://example.com/download-page")
        h_ref.addWidget(self.txt_referer)
        adv_layout.addLayout(h_ref)

        # Proxy
        h_prox = QHBoxLayout()
        lbl_prox = QLabel("Proxy")
        lbl_prox.setFixedWidth(72)
        lbl_prox.setStyleSheet("color: #94a3b8; font-size: 11px;")
        h_prox.addWidget(lbl_prox)
        self.txt_proxy = QLineEdit()
        self.txt_proxy.setPlaceholderText("http://127.0.0.1:8080 or socks5://127.0.0.1:1080")
        h_prox.addWidget(self.txt_proxy)
        adv_layout.addLayout(h_prox)

        # Checksum
        h_check = QHBoxLayout()
        lbl_check = QLabel("Checksum")
        lbl_check.setFixedWidth(72)
        lbl_check.setStyleSheet("color: #94a3b8; font-size: 11px;")
        h_check.addWidget(lbl_check)
        self.txt_checksum = QLineEdit()
        self.txt_checksum.setPlaceholderText("Paste MD5 / SHA-256 hash here")
        self.cmb_hash_type = QComboBox()
        self.cmb_hash_type.addItems(["SHA-256", "MD5", "SHA-1"])
        self.cmb_hash_type.setFixedWidth(90)
        h_check.addWidget(self.txt_checksum)
        h_check.addWidget(self.cmb_hash_type)
        adv_layout.addLayout(h_check)

        # Auto Extract & Post Action
        h_post = QHBoxLayout()
        self.chk_auto_extract = QCheckBox("Auto-Extract if Archive (ZIP/RAR)")
        h_post.addWidget(self.chk_auto_extract)

        h_post.addSpacing(16)
        h_post.addWidget(QLabel("On Complete:"))
        self.cmb_post_action = QComboBox()
        self.cmb_post_action.addItems(["None", "Shutdown", "Sleep", "Hibernate", "Exit"])
        h_post.addWidget(self.cmb_post_action)
        h_post.addStretch()
        adv_layout.addLayout(h_post)

        self.adv_widget.setVisible(False)
        self.chk_show_advanced.toggled.connect(self._toggle_advanced)
        content_layout.addWidget(self.adv_widget)

        # 9. Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #151f30; background-color: #151f30; border: none; height: 1px;")
        content_layout.addWidget(div)

        # 10. Action Buttons Row
        h_btn = QHBoxLayout()
        h_btn.setSpacing(10)

        self.btn_download_now = QPushButton("Start Download")
        self.btn_download_now.setDefault(True)
        self.btn_download_now.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #2563eb;
                border-radius: 5px;
                padding: 7px 18px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3b82f6;
                border-color: #3b82f6;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
        """)
        self.btn_download_now.clicked.connect(lambda: self._create_task(start_now=True))

        self.btn_download_later = QPushButton("Download Later")
        self.btn_download_later.setStyleSheet("""
            QPushButton {
                background-color: #0f1724;
                color: #cbd5e1;
                border: 1px solid #1b273d;
                border-radius: 5px;
                padding: 7px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #151f30;
                color: #ffffff;
                border-color: #253550;
            }
        """)
        self.btn_download_later.clicked.connect(lambda: self._create_task(start_now=False))

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #94a3b8;
                border: 1px solid #151f30;
                border-radius: 5px;
                padding: 7px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #0f1724;
                color: #f1f5f9;
                border-color: #1b273d;
            }
        """)
        btn_cancel.clicked.connect(self.reject)

        h_btn.addStretch()
        h_btn.addWidget(self.btn_download_now)
        h_btn.addWidget(self.btn_download_later)
        h_btn.addWidget(btn_cancel)
        content_layout.addLayout(h_btn)

    def _browse_torrent_file(self):
        torrent_file, _ = QFileDialog.getOpenFileName(
            self, "Select BitTorrent File", "", "Torrent Files (*.torrent);;All Files (*.*)"
        )
        if torrent_file:
            self.txt_url.setText(torrent_file)
            self._start_probe()

    def _toggle_advanced(self, checked: bool):
        self.adv_widget.setVisible(checked)
        self.chk_show_advanced.setText("▾ Hide Advanced Options" if checked else "▸ Show Advanced Options (Headers, Proxy, Checksum, Extract)")
        self.adjustSize()

    def _switch_mode(self, mode: str):
        self.mode_switch_requested.emit(mode)
        self.reject()

    @staticmethod
    def _is_torrent_url(url: str) -> bool:
        u = (url or "").lower().strip()
        return u.startswith("magnet:") or u.endswith(".torrent") or ".torrent?" in u or (os.path.isfile(url) and u.endswith(".torrent"))

    def _on_url_changed(self):
        url = self.txt_url.text().strip()
        if self._is_torrent_url(url):
            self.lbl_probe_status.setText("Link Torrent terdeteksi. Gunakan tombol 'Torrents' di toolbar!")
            self.lbl_probe_status.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: 600;")
            self.lbl_probe_size.setText("Size: <span style='color: #ef4444;'>Khusus Menu Torrents</span>")
            self.lbl_probe_resume.setText("Torrent: <span style='color: #ef4444;'>Pindah ke Menu Torrents</span>")
            self.btn_download_now.setEnabled(False)
            self.btn_download_later.setEnabled(False)
            return

        if (
            url.startswith("http://")
            or url.startswith("https://")
        ):
            self.btn_download_now.setEnabled(True)
            self.btn_download_later.setEnabled(True)
            self._start_probe()

    def _start_probe(self):
        raw_url = self.txt_url.text().strip()
        if not raw_url or self._is_torrent_url(raw_url):
            return
        # Auto-resolve cloud links (Google Drive, Dropbox, Mediafire, etc.)
        url = CloudLinkResolver.resolve(raw_url)
        if url != raw_url:
            self.txt_url.setText(url)

        self.lbl_probe_status.setText("● Probing server headers...")
        self.lbl_probe_status.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 500;")
        self.probe_thread = threading.Thread(target=self._async_probe, args=(url,), daemon=True)
        self.probe_thread.start()

    def _async_probe(self, url: str):
        try:
            info = self.engine.probe_url(url, headers=self.initial_headers)
            self.probe_finished_signal.emit(info)
        except Exception:
            pass

    def _open_torrent_file_selector(self):
        from .torrent_file_selector import TorrentFileSelectorDialog
        url = self.txt_url.text().strip()
        if not url:
            return
        dlg = TorrentFileSelectorDialog(url, parent=self)
        if dlg.exec():
            selected = dlg.get_selected_indices()
            if selected:
                self.selected_torrent_files = selected
                if getattr(dlg, "all_files", None):
                    sel_set = set(selected)
                    sel_size = sum(f.get("size", 0) for f in dlg.all_files if f.get("index") in sel_set)
                    if sel_size > 0:
                        self.probed_size = sel_size
                        size_str = format_bytes(sel_size)
                        self.lbl_probe_size.setText(
                            f"Size: <b style='color: #f1f5f9;'>{size_str}</b> "
                            f"<span style='color: #10b981; font-size: 10px;'>({len(selected)}/{len(dlg.all_files)} dipilih)</span>"
                        )

    def _on_probe_complete(self, info: dict):
        # Update filename if not user-edited, or if current filename lacks an extension
        fn = info.get("filename", "")
        cur_fn = self.txt_filename.text().strip()
        _, cur_ext = os.path.splitext(cur_fn)
        _, probe_ext = os.path.splitext(fn)
        if fn and (not cur_fn or cur_fn in ("torrent_download", "download", "auto_detected_filename.ext") or (not cur_ext and probe_ext)):
            self.txt_filename.setText(fn)

        url = self.txt_url.text().strip()
        is_torrent = (
            url.startswith("magnet:")
            or url.lower().endswith(".torrent")
            or (os.path.isfile(url) and url.lower().endswith(".torrent"))
            or info.get("category") == "Torrents"
        )

        size_bytes = info.get("total_bytes", -1)
        if size_bytes <= 0 and self.initial_filesize > 0:
            size_bytes = self.initial_filesize
        self.probed_size = size_bytes
        size_str = format_bytes(size_bytes) if size_bytes > 0 else "Unknown Size"
        resumable = info.get("resumable", False) or (self.initial_filesize > 0)

        is_hls = (
            info.get("is_hls", False) or
            (".m3u8" in url.lower()) or
            (".mpd" in url.lower()) or
            any(d in url.lower() for d in ("chaturbate.com", "stripchat.com", "cb.live", "mmcdn.com", "highwebmedia.com", "doppiocdn", "stripcdn"))
        )

        if info.get("is_pikpak"):
            self.lbl_probe_status.setText("● PikPak Public Share Detected")
            self.lbl_probe_status.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 600;")
            self.lbl_probe_resume.setText("Resume: <span style='background-color: rgba(16,185,129,0.2); color: #34d399; padding: 2px 6px; border-radius: 3px; font-weight: 600;'>Yes (Direct CDN)</span>")
            if info.get("direct_url"):
                self.direct_url = info["direct_url"]
            if info.get("headers"):
                self.initial_headers.update(info["headers"])

        if hasattr(self, "btn_pick_torrent_files"):
            self.btn_pick_torrent_files.setVisible(False)

        if is_torrent:
            if not self.torrent_enabled:
                self.lbl_probe_status.setText("BitTorrent Dinonaktifkan")
                self.lbl_probe_status.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: 600;")
                self.lbl_probe_size.setText("Size: <span style='color: #94a3b8;'>Dinonaktifkan di Pengaturan</span>")
                self.lbl_probe_resume.setText("Torrent: <span style='color: #ef4444;'>Nonaktif</span>")
                self.btn_download_now.setEnabled(False)
                self.btn_download_later.setEnabled(False)
            else:
                self.lbl_probe_status.setText("● BitTorrent Swarm Detected")
                self.lbl_probe_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
                if hasattr(self, "btn_pick_torrent_files"):
                    self.btn_pick_torrent_files.setVisible(not url.startswith("magnet:") or bool(info.get("torrent_files")))
                if size_bytes > 0:
                    t_files = info.get("torrent_files", [])
                    count_info = f" ({len(t_files)} files)" if len(t_files) > 1 else ""
                    self.lbl_probe_size.setText(f"Size: <b style='color: #f1f5f9;'>{size_str}</b><span style='color: #94a3b8; font-size: 10px;'>{count_info}</span>")
                else:
                    self.lbl_probe_size.setText("Size: <b style='color: #cbd5e1;'>BitTorrent Swarm</b>")
                self.lbl_probe_resume.setText("Resume: <span style='background-color: rgba(16,185,129,0.2); color: #34d399; padding: 2px 6px; border-radius: 3px; font-weight: 600;'>Yes</span>")
                self.btn_download_now.setEnabled(True)
                self.btn_download_later.setEnabled(True)
        elif is_hls:
            if info.get("m3u8_content"):
                self.initial_headers["m3u8_content"] = info["m3u8_content"]
            self.lbl_probe_status.setText("● HLS Stream Detected")
            self.lbl_probe_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
            self.lbl_probe_resume.setText("Resume: <span style='background-color: rgba(16,185,129,0.2); color: #34d399; padding: 2px 6px; border-radius: 3px; font-weight: 600;'>Yes</span>")
            self.btn_download_now.setEnabled(True)
            self.btn_download_later.setEnabled(True)

            if info.get("variants"):
                self._populate_variants(info["variants"])
            else:
                res = info.get("resolution", "")
                bitrate = info.get("bitrate", 0)
                if res and res != "Auto":
                    self.current_resolution = res
                    self.lbl_probe_res.setText(f"Res: <b style='color: #94a3b8;'>{res}</b>")
                    self.lbl_probe_res.setVisible(True)
                if bitrate > 0:
                    self.current_bitrate = bitrate
                    bitrate_str = f"{bitrate/1000:.1f} Mbps" if bitrate >= 1000 else f"{bitrate} kbps"
                    self.lbl_probe_bitrate.setText(f"Bitrate: <b style='color: #34d399;'>{bitrate_str}</b>")
                    self.lbl_probe_bitrate.setVisible(True)
                if size_bytes > 0:
                    self.lbl_probe_size.setText(f"Size: <b style='color: #f1f5f9;'>~{size_str}</b>")
                elif info.get("is_live"):
                    self.initial_headers["is_live"] = "true"
                    self.probed_size = -1
                    self.initial_filesize = -1
                    self.lbl_probe_size.setText("Size: <b style='color: #cbd5e1;'>Live Stream (MP4 / WebM)</b>")
                else:
                    self.lbl_probe_size.setText("Size: <b style='color: #cbd5e1;'>Auto Convert to MP4</b>")
        else:
            self.lbl_probe_status.setText("● Server Connected")
            self.lbl_probe_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
            self.lbl_probe_size.setText(f"Size: <b style='color: #f1f5f9;'>{size_str}</b>")

            if resumable:
                self.lbl_probe_resume.setText("Resume: <span style='background-color: rgba(16,185,129,0.2); color: #34d399; padding: 2px 6px; border-radius: 3px; font-weight: 600;'>Yes</span>")
            else:
                self.lbl_probe_resume.setText("Resume: <span style='background-color: rgba(239,68,68,0.2); color: #f87171; padding: 2px 6px; border-radius: 3px;'>No</span>")
            self.btn_download_now.setEnabled(True)
            self.btn_download_later.setEnabled(True)

        cat = info.get("category", "General")
        idx = self.cmb_cat.findText(cat)
        if idx >= 0:
            self.cmb_cat.setCurrentIndex(idx)

    def _populate_variants(self, variants: list, selected_url: str = None):
        if not variants:
            return
        self.variants = variants
        self.cmb_resolution.blockSignals(True)
        self.cmb_resolution.clear()

        target_idx = 0
        for i, v in enumerate(variants):
            label = v.get("display_name") or f"{v.get('label', 'Stream')} ({v.get('resolution', '')})"
            self.cmb_resolution.addItem(label, v)
            if selected_url and v.get("url") == selected_url:
                target_idx = i

        self.cmb_resolution.setCurrentIndex(target_idx)
        self.cmb_resolution.blockSignals(False)
        self.row_resolution.setVisible(True)

        self._on_resolution_changed(target_idx)

    def _on_resolution_changed(self, idx: int):
        if idx < 0 or idx >= len(self.variants):
            return
        v = self.cmb_resolution.itemData(idx)
        if not v or not isinstance(v, dict):
            return

        new_url = v.get("url", "")
        if new_url:
            self.txt_url.blockSignals(True)
            self.txt_url.setText(new_url)
            self.txt_url.blockSignals(False)

        if v.get("master_url"):
            self.initial_headers["master_url"] = v["master_url"]
        if v.get("audio_url"):
            self.initial_headers["audio_url"] = v["audio_url"]
        if v.get("resolution"):
            self.initial_headers["resolution"] = v["resolution"]

        if v.get("is_live"):
            self.initial_headers["is_live"] = "true"
            self.initial_filesize = -1
            self.probed_size = -1
        elif v.get("m3u8_content"):
            self.initial_headers["m3u8_content"] = v["m3u8_content"]
            try:
                from ..core.hls_downloader import HLSInspector
                HLSInspector.cache_playlist(new_url or self.txt_url.text().strip(), v["m3u8_content"])
            except Exception:
                pass

        self.current_resolution = v.get("resolution", "")
        self.current_bitrate = v.get("bitrate", 0)
        tb = v.get("total_bytes", v.get("filesize", -1))
        if tb > 0 and not v.get("is_live"):
            self.initial_filesize = tb

        # Update Filename tag if present
        cur_fn = self.txt_filename.text().strip()
        v_label = v.get("label", "")
        desired_ext = v.get("ext")
        if cur_fn and v_label:
            import re
            new_fn = re.sub(r'(\[|\()(\d+p|Stream|\d+x\d+)(\]|\))', f'[{v_label}]', cur_fn)
            base_f, ext_f = os.path.splitext(new_fn)
            if desired_ext:
                ext_f = f".{desired_ext.lstrip('.')}"
            elif ext_f.lower() not in (".mp4", ".webm", ".mkv"):
                ext_f = ".mp4"
            if new_fn == cur_fn and not (f"[{v_label}]" in cur_fn):
                new_fn = f"{base_f} [{v_label}]{ext_f}"
            else:
                new_fn = f"{base_f}{ext_f}"
            self.txt_filename.setText(new_fn)
        elif not cur_fn and v.get("filename"):
            self.txt_filename.setText(v["filename"])

        self.lbl_probe_status.setText("● Live Stream Ready" if v.get("is_live") else "● HLS Stream Detected")
        self.lbl_probe_status.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 700;" if v.get("is_live") else "color: #10b981; font-size: 11px; font-weight: 600;")

        if self.current_resolution and self.current_resolution != "Auto":
            self.lbl_probe_res.setText(f"Res: <b style='color: #94a3b8;'>{self.current_resolution}</b>")
            self.lbl_probe_res.setVisible(True)

        if self.current_bitrate > 0:
            bitrate_str = f"{self.current_bitrate/1000:.1f} Mbps" if self.current_bitrate >= 1000 else f"{self.current_bitrate} kbps"
            self.lbl_probe_bitrate.setText(f"Bitrate: <b style='color: #34d399;'>{bitrate_str}</b>")
            self.lbl_probe_bitrate.setVisible(True)

        if self.initial_filesize > 0 and not v.get("is_live"):
            self.lbl_probe_size.setText(f"Size: <b style='color: #f1f5f9;'>~{format_bytes(self.initial_filesize)}</b>")
        elif v.get("is_live"):
            self.lbl_probe_size.setText("Size: <b style='color: #cbd5e1;'>Live Stream (MP4 / WebM)</b>")
        else:
            self.lbl_probe_size.setText("Size: <b style='color: #cbd5e1;'>Auto Convert to MP4</b>")

        self.lbl_probe_resume.setText("Resume: <span style='background-color: rgba(16,185,129,0.2); color: #34d399; padding: 2px 6px; border-radius: 3px; font-weight: 600;'>Yes</span>")

    def _open_media_grabber(self):
        from .media_dialog import MediaDialog
        url = self.txt_url.text().strip()
        dlg = MediaDialog(default_url=url, parent=self)
        if dlg.exec():
            res = dlg.get_result()
            if res and res.get("url"):
                self.media_res = res
                self.txt_url.setText(res["url"])
                if res.get("title"):
                    self.txt_filename.setText(res["title"])
                idx = self.cmb_cat.findText("Video")
                if idx >= 0:
                    self.cmb_cat.setCurrentIndex(idx)
                if res.get("is_live"):
                    self.lbl_probe_status.setText("● Siaran Langsung (Live Stream Ready)")
                    self.lbl_probe_status.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 700;")
                else:
                    self.lbl_probe_status.setText("● Resolusi Terpilih")
                    self.lbl_probe_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")

    def _browse_folder(self):
        dir_selected = QFileDialog.getExistingDirectory(self, "Select Download Folder", self.txt_save_path.text())
        if dir_selected:
            self.txt_save_path.setText(dir_selected)

    def _on_category_changed(self, cat_name: str):
        if not hasattr(self, "engine") or not self.engine or not hasattr(self.engine, "db"):
            return
        auto_sub = self.engine.db.get_setting("category_subfolders", "true") == "true"
        if not auto_sub:
            return

        cat_key = f"category_dir_{cat_name.lower()}"
        custom_dir = self.engine.db.get_setting(cat_key, "").strip()
        if custom_dir and os.path.isdir(custom_dir):
            self.txt_save_path.setText(custom_dir)
            return

        base_dir = self.engine.db.get_setting("download_dir", "") or self.engine.db.get_setting("default_save_path", os.path.join(os.path.expanduser("~"), "Downloads"))
        known_cats = {"general", "compressed", "documents", "music", "video", "videos", "programs", "torrents"}
        current_save = self.txt_save_path.text().strip() or base_dir
        curr_base = os.path.basename(current_save).lower()
        if curr_base in known_cats:
            parent_dir = os.path.dirname(current_save)
        else:
            parent_dir = current_save if os.path.isdir(current_save) else base_dir

        if cat_name.lower() != "general":
            sub_folder = "Videos" if cat_name.lower() == "video" else cat_name
            target_dir = os.path.join(parent_dir, sub_folder)
        else:
            target_dir = parent_dir
        self.txt_save_path.setText(target_dir)

    def _create_task(self, start_now: bool):
        url = self.txt_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid download URL.")
            return

        if self._is_torrent_url(url):
            QMessageBox.information(
                self,
                "Menu Khusus URL Langsung",
                "Tombol 'Add URL' hanya untuk mengunduh link langsung (HTTP/HTTPS, video streaming m3u8/mpd, dll).\n\n"
                "Untuk mengunduh File BitTorrent (.torrent) atau Magnet link, silakan gunakan tombol 'Torrents' pada toolbar utama."
            )
            return

        filename = self.txt_filename.text().strip()
        if not filename:
            # Fallback filename from URL
            filename = sanitize_filename(url.split("/")[-1].split("?")[0] or "download.bin")
            self.txt_filename.setText(filename)

        save_dir = self.txt_save_path.text().strip()
        conn = self.spn_conn.value()

        # Check for duplicate file conflict on disk
        target_path = os.path.join(save_dir, filename)
        if os.path.exists(target_path):
            dlg = FileConflictDialog(filename, target_path, parent=self)
            if not dlg.exec() or dlg.chosen_action == FileConflictDialog.ACTION_CANCEL:
                return
            elif dlg.chosen_action == FileConflictDialog.ACTION_OVERWRITE:
                try:
                    os.remove(target_path)
                except Exception:
                    pass
            elif dlg.chosen_action == FileConflictDialog.ACTION_RENAME:
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(os.path.join(save_dir, f"{base}_{counter}{ext}")):
                    counter += 1
                filename = f"{base}_{counter}{ext}"

        headers = dict(self.initial_headers) if self.initial_headers else {}
        if hasattr(self, "media_res") and self.media_res:
            if self.media_res.get("is_live"):
                headers["is_live"] = "true"
            if self.media_res.get("is_hls"):
                headers["is_hls"] = "true"
        if "chaturbate.com" in url.lower() or "stripchat.com" in url.lower():
            headers["is_live"] = "true"
            headers["is_hls"] = "true"

        # Explicitly tag HLS / stream tasks so downloader recognizes them regardless of probe
        is_stream = (".m3u8" in url.lower()) or (".mpd" in url.lower()) or (headers.get("is_hls") in ["true", True, 1, "1"]) or (headers.get("is_live") in ["true", True, 1, "1"])
        if is_stream:
            headers["is_hls"] = "true"
            if not filename.lower().endswith((".mp4", ".webm")):
                base_f, _ = os.path.splitext(filename)
                filename = f"{base_f}.mp4"
            if self.current_resolution:
                headers["resolution"] = self.current_resolution
            if self.current_bitrate > 0:
                headers["bitrate"] = str(self.current_bitrate)
            if self.initial_filesize > 0 and headers.get("is_live") not in ["true", True, 1, "1"]:
                headers["estimated_size"] = str(self.initial_filesize)
            elif headers.get("is_live") in ["true", True, 1, "1"]:
                self.probed_size = -1
                self.initial_filesize = -1

        if self.txt_referer.text().strip():
            headers["Referer"] = self.txt_referer.text().strip()

        from ..core.link_resolver import CloudLinkResolver
        headers = CloudLinkResolver.fix_headers(url, headers)

        proxy = self.txt_proxy.text().strip() or None
        checksum = self.txt_checksum.text().strip() or None
        checksum_type = self.cmb_hash_type.currentText()
        auto_extract = self.chk_auto_extract.isChecked()
        
        post_map = {
            "None": "none",
            "Shutdown": "shutdown",
            "Sleep": "sleep",
            "Hibernate": "hibernate",
            "Exit": "exit"
        }
        post_action = post_map.get(self.cmb_post_action.currentText(), "none")

        if getattr(self, "selected_torrent_files", None):
            headers["selected_files"] = self.selected_torrent_files

        self.start_immediately = start_now
        tb = self.probed_size if (hasattr(self, "probed_size") and self.probed_size > 0) else (self.initial_filesize if self.initial_filesize > 0 else None)
        res = True if (tb and tb > 0) else None

        # Zero log: read from DB global setting (individual task toggle via checkbox if added)
        from ..core.database import Database as _DB
        zero_log = str(_DB.get_instance().get_setting("zero_log_mode", "false")).lower() in ("true", "1", "yes")

        try:
            desc = self.txt_description.text().strip() if hasattr(self, "txt_description") else ""
            self.result_task = self.engine.create_task(
                url=url,
                save_dir=save_dir,
                filename=filename,
                connections=conn,
                headers=headers,
                proxy=proxy,
                checksum=checksum,
                checksum_type=checksum_type,
                auto_extract=auto_extract,
                post_action=post_action,
                total_bytes=tb,
                resumable=res,
                zero_log=zero_log,
                description=desc
            )
            self.result_task.description = desc
            self.result_task.category = self.cmb_cat.currentText()
            self.result_task.queue_name = self.cmb_queue.currentText()
            if hasattr(self.engine, "db") and not zero_log:
                self.engine.db.save_task(self.result_task)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error Creating Download", f"Could not create download task:\n{str(e)}")
