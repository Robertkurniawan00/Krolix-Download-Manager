"""
Krolix Download Manager v2.8 - macOS Modern Dark UI
Features:
- Windows 11 Fluent Design language with Mica-inspired surfaces (#111620, #161c28)
- Minimalist Command Bar with grouped capsules matching user's exact reference screenshot
- Circular green Add button, minimalist white Play and Pause action pills
- Clean Navigation Tree with category badge counters
- High-performance Data Grid with multi-connection stream visualization
- Integrated Status Bar and quick details drawer
"""

import os
import re
import sys
import subprocess
import time
import urllib.parse
import json
from pathlib import Path
from typing import Optional, List, Set
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QLabel, QPushButton, QLineEdit,
    QFrame, QHeaderView, QMenu, QMessageBox, QApplication,
    QTreeWidget, QTreeWidgetItem, QDialog, QFileDialog, QToolButton,
    QAbstractItemView, QCheckBox, QInputDialog, QMenuBar, QSizeGrip
)
from PyQt6.QtGui import QIcon, QColor, QPixmap, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QSize, QTimer

from ..core.models import DownloadTask, DownloadStatus
from ..core.downloader import DownloadEngine
from ..core.database import Database
from ..core.speed_limiter import SpeedLimiter
from ..core.scheduler import DownloadScheduler
from ..core.archive_extractor import ArchiveExtractor
from ..core.queue_manager import QueueManager
from ..core.post_actions import PostActionManager
from ..services.clipboard_service import ClipboardMonitor
from ..services.api_server import LocalAPIServer
from ..services.tray_service import TrayService
from ..core.audio_muxer import AudioMuxer
from ..utils.helpers import format_bytes, format_speed, format_eta, apply_windows_dark_titlebar, apply_taskbar_icon, sanitize_filename, get_app_icon
from .widgets import FileNameDelegate, ProgressSegmentsDelegate
from .floating_widget import FloatingDropWidget
from .speed_graph import SpeedGraphWidget
from . import fluent_icons
from .styles import get_app_stylesheet
from .tip_dialog import TipDialog
from .extension_dialog import ExtensionDialog


class SortableTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem with custom typed sorting key support."""
    def __init__(self, text="", sort_key=None):
        super().__init__(text)
        self.sort_key = sort_key if sort_key is not None else text

    def __lt__(self, other):
        if isinstance(other, SortableTableWidgetItem):
            k1 = self.sort_key
            k2 = other.sort_key
            if isinstance(k1, (int, float)) and isinstance(k2, (int, float)):
                return k1 < k2
            return str(k1).lower() < str(k2).lower()
        return super().__lt__(other)


class BridgeSignals(QObject):
    task_updated = pyqtSignal(DownloadTask)
    task_completed = pyqtSignal(DownloadTask)
    task_failed = pyqtSignal(DownloadTask, str)
    url_detected = pyqtSignal(str)
    download_requested = pyqtSignal(dict)
    batch_requested = pyqtSignal(dict)
    watchlist_updated = pyqtSignal(dict)
    watchlist_recording_started = pyqtSignal(dict, object)
    exit_requested = pyqtSignal()
    run_on_main = pyqtSignal(object)


class KrolixMacOSTitleBar(QWidget):
    """
    macOS Signature Titlebar with Traffic Light Window Controls.
    - Red (#FF5F56): Close window
    - Yellow (#FFBD2E): Minimize window
    - Green (#27C93F): Maximize / Zoom / Restore
    - Center: Krolix Rabbit Mascot Logo + 'Krolix Download Manager'
    - Smooth window dragging and double-click to maximize/restore.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("KrolixMacOSTitleBar")
        self.setFixedHeight(34)
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        # 1. macOS Traffic Lights (Close, Minimize, Maximize)
        traffic_widget = QWidget()
        traffic_widget.setStyleSheet("background: transparent;")
        traffic_layout = QHBoxLayout(traffic_widget)
        traffic_layout.setContentsMargins(0, 0, 0, 0)
        traffic_layout.setSpacing(8)

        self.btn_close = QPushButton()
        self.btn_close.setObjectName("macCloseBtn")
        self.btn_close.setFixedSize(12, 12)
        self.btn_close.setToolTip("Tutup")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet("QPushButton { background-color: #ff5f56; border: 1px solid #e0443e; border-radius: 6px; } QPushButton:hover { background-color: #ff3b30; } QPushButton:pressed { background-color: #bf3026; }")
        self.btn_close.clicked.connect(self._on_close)

        self.btn_min = QPushButton()
        self.btn_min.setObjectName("macMinBtn")
        self.btn_min.setFixedSize(12, 12)
        self.btn_min.setToolTip("Minimalkan")
        self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_min.setStyleSheet("QPushButton { background-color: #ffbd2e; border: 1px solid #dea123; border-radius: 6px; } QPushButton:hover { background-color: #ff9500; } QPushButton:pressed { background-color: #bf7400; }")
        self.btn_min.clicked.connect(self._on_min)

        self.btn_max = QPushButton()
        self.btn_max.setObjectName("macMaxBtn")
        self.btn_max.setFixedSize(12, 12)
        self.btn_max.setToolTip("Perbesar / Pulihkan")
        self.btn_max.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_max.setStyleSheet("QPushButton { background-color: #27c93f; border: 1px solid #1aab29; border-radius: 6px; } QPushButton:hover { background-color: #34c759; } QPushButton:pressed { background-color: #1f8b31; }")
        self.btn_max.clicked.connect(self._on_max)

        traffic_layout.addWidget(self.btn_close)
        traffic_layout.addWidget(self.btn_min)
        traffic_layout.addWidget(self.btn_max)
        layout.addWidget(traffic_widget)

        layout.addStretch(1)

        # 2. Centered Branding: Transparent Mascot Logo + Title
        brand_widget = QWidget()
        brand_widget.setStyleSheet("background: transparent;")
        brand_layout = QHBoxLayout(brand_widget)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(8)

        self.lbl_logo = QLabel()
        self.lbl_logo.setStyleSheet("background: transparent;")
        logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo_32.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.lbl_logo.setPixmap(pix)
        brand_layout.addWidget(self.lbl_logo)

        self.lbl_title = QLabel("Krolix Download Manager")
        self.lbl_title.setObjectName("macTitleLabel")
        self.lbl_title.setStyleSheet("background: transparent; font-size: 12px; font-weight: 600; color: #e4e4e7;")
        brand_layout.addWidget(self.lbl_title)
        layout.addWidget(brand_widget)

        layout.addStretch(1)

        # 3. Right Spacer to balance the traffic lights
        spacer = QWidget()
        spacer.setStyleSheet("background: transparent;")
        spacer.setFixedWidth(56)
        layout.addWidget(spacer)

    def _on_close(self):
        w = self.window()
        if w:
            w.close()

    def _on_min(self):
        w = self.window()
        if w:
            w.showMinimized()

    def _on_max(self):
        w = self.window()
        if w:
            if w.isMaximized():
                w.showNormal()
            else:
                w.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            w = self.window()
            if not w.isMaximized():
                self._drag_pos = event.globalPosition().toPoint() - w.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            w = self.window()
            if not w.isMaximized():
                w.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_max()
            event.accept()


class KrolixMacOSBar(QWidget):
    """
    macOS Unified Header (Titlebar + Command Bar in ONE cohesive 48px bar).
    Integrates:
    - Traffic light window controls: Red (#ff5f56), Yellow (#ffbd2e), Green (#27c93f)
    - Krolix mascot logo & title
    - Primary action: [+ Add Download ▾] (Krolix Green pill)
    - Transport buttons: Resume, Pause, Stop All, Delete, Clean Completed
    - Automation & Monitoring: Queue, Scheduler, Real-time Speed Graph
    - Symmetrical Centered Search: macOS Capsule Search Pill
    - Overflow Tools Menu (3-dot ...) & Settings Gear (⚙)
    - Window dragging & double-click to maximize/restore
    """
    add_url_clicked = pyqtSignal()
    resume_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()
    stop_all_clicked = pyqtSignal()
    delete_clicked = pyqtSignal()
    delete_permanent_clicked = pyqtSignal()
    delete_comp_clicked = pyqtSignal()
    delete_all_clicked = pyqtSignal()
    clean_missing_clicked = pyqtSignal()
    redownload_clicked = pyqtSignal()
    start_queue_clicked = pyqtSignal()
    stop_queue_clicked = pyqtSignal()
    scheduler_clicked = pyqtSignal()
    limiter_clicked = pyqtSignal()
    grabber_clicked = pyqtSignal()
    batch_clicked = pyqtSignal()
    hash_clicked = pyqtSignal()
    graph_clicked = pyqtSignal()
    options_clicked = pyqtSignal()
    torrent_search_clicked = pyqtSignal()
    add_torrent_file_clicked = pyqtSignal()
    add_magnet_clicked = pyqtSignal()
    seeder_clicked = pyqtSignal()
    spoofer_clicked = seeder_clicked
    ytdlp_clicked = pyqtSignal()
    dht_search_clicked = pyqtSignal()
    sniffer_clicked = pyqtSignal()
    refresh_link_clicked = pyqtSignal()
    watchlist_clicked = pyqtSignal()
    search_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("KrolixMacOSBar")
        self.setFixedHeight(48)
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)

        # -------------------------------------------------------------
        # 1. macOS Traffic Lights (Close, Minimize, Maximize)
        # -------------------------------------------------------------
        traffic_widget = QWidget()
        traffic_widget.setStyleSheet("background: transparent;")
        traffic_layout = QHBoxLayout(traffic_widget)
        traffic_layout.setContentsMargins(0, 0, 0, 0)
        traffic_layout.setSpacing(8)

        self.btn_close = QPushButton()
        self.btn_close.setObjectName("macCloseBtn")
        self.btn_close.setFixedSize(12, 12)
        self.btn_close.setToolTip("Tutup")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet("QPushButton { background-color: #ff5f56; border: 1px solid #e0443e; border-radius: 6px; } QPushButton:hover { background-color: #ff3b30; } QPushButton:pressed { background-color: #bf3026; }")
        self.btn_close.clicked.connect(self._on_close)

        self.btn_min = QPushButton()
        self.btn_min.setObjectName("macMinBtn")
        self.btn_min.setFixedSize(12, 12)
        self.btn_min.setToolTip("Minimalkan")
        self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_min.setStyleSheet("QPushButton { background-color: #ffbd2e; border: 1px solid #dea123; border-radius: 6px; } QPushButton:hover { background-color: #ff9500; } QPushButton:pressed { background-color: #bf7400; }")
        self.btn_min.clicked.connect(self._on_min)

        self.btn_max = QPushButton()
        self.btn_max.setObjectName("macMaxBtn")
        self.btn_max.setFixedSize(12, 12)
        self.btn_max.setToolTip("Perbesar / Pulihkan")
        self.btn_max.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_max.setStyleSheet("QPushButton { background-color: #27c93f; border: 1px solid #1aab29; border-radius: 6px; } QPushButton:hover { background-color: #34c759; } QPushButton:pressed { background-color: #1f8b31; }")
        self.btn_max.clicked.connect(self._on_max)

        traffic_layout.addWidget(self.btn_close)
        traffic_layout.addWidget(self.btn_min)
        traffic_layout.addWidget(self.btn_max)
        layout.addWidget(traffic_widget)

        layout.addWidget(self._create_divider())

        # -------------------------------------------------------------
        # 2. Branding: Mascot Logo + App Title
        # -------------------------------------------------------------
        brand_widget = QWidget()
        brand_widget.setStyleSheet("background: transparent;")
        brand_layout = QHBoxLayout(brand_widget)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(6)

        self.lbl_logo = QLabel()
        self.lbl_logo.setStyleSheet("background: transparent; border: none;")
        logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo_512.png")
        if not os.path.exists(logo_path):
            logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo_32.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.lbl_logo.setPixmap(pix)
        brand_layout.addWidget(self.lbl_logo)

        self.lbl_title = QLabel("Krolix")
        self.lbl_title.setObjectName("macTitleLabel")
        self.lbl_title.setStyleSheet("background: transparent; border: none; font-size: 12px; font-weight: 700; color: #ffffff;")
        brand_layout.addWidget(self.lbl_title)
        layout.addWidget(brand_widget)

        layout.addWidget(self._create_divider())

        # -------------------------------------------------------------
        # 3. Primary Action: [+ Add Download] Pill with Menu
        # -------------------------------------------------------------
        self.btn_add = QToolButton()
        self.btn_add.setObjectName("macAddBtn")
        self.btn_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_add.setIcon(fluent_icons.create_fluent_add_icon(color="#ffffff"))
        self.btn_add.setIconSize(QSize(14, 14))
        self.btn_add.setText("Add Download")
        self.btn_add.setToolTip("Add new download URL (Click arrow for Batch / Torrents / Media) [Ctrl+N]")
        self.btn_add.setFixedSize(124, 30)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.btn_add.setStyleSheet("""
            QToolButton#macAddBtn {
                background-color: #22c55e;
                color: #ffffff;
                font-weight: 600;
                font-size: 11px;
                border-radius: 6px;
                border: none;
                padding-left: 6px;
            }
            QToolButton#macAddBtn:hover {
                background-color: #16a34a;
            }
            QToolButton#macAddBtn:pressed {
                background-color: #15803d;
            }
            QToolButton#macAddBtn::menu-button {
                border-left: 1px solid rgba(255, 255, 255, 0.25);
                width: 16px;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }
        """)
        self.btn_add.clicked.connect(self.add_url_clicked.emit)

        add_menu = QMenu(self)
        add_menu.setStyleSheet("""
            QMenu {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 6px;
                color: #f4f4f5;
            }
            QMenu::item {
                padding: 6px 18px 6px 10px;
                border-radius: 4px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #27272a;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #27272a;
                margin: 4px 6px;
            }
        """)
        act_single = add_menu.addAction(fluent_icons.create_fluent_add_icon(color="#22c55e"), "Tambah Tautan URL (Ctrl+N)")
        act_single.triggered.connect(self.add_url_clicked.emit)
        act_batch = add_menu.addAction(fluent_icons.create_fluent_batch_icon(color="#3b82f6"), "Unduh Berkas Batch / Daftar URL (Ctrl+B)")
        act_batch.triggered.connect(self.batch_clicked.emit)
        add_menu.addSeparator()
        act_torrent = add_menu.addAction(fluent_icons.create_fluent_torrent_icon(color="#06b6d4"), "Buka Berkas .torrent (Ctrl+T)")
        act_torrent.triggered.connect(self.add_torrent_file_clicked.emit)
        act_magnet = add_menu.addAction(fluent_icons.create_fluent_magnet_icon(color="#a855f7"), "Tambah Tautan Magnet (Ctrl+M)")
        act_magnet.triggered.connect(self.add_magnet_clicked.emit)
        add_menu.addSeparator()
        act_ytdlp = add_menu.addAction(fluent_icons.create_fluent_video_icon(color="#ef4444"), "Unduh Video & Audio (YT-DLP)")
        act_ytdlp.triggered.connect(self.ytdlp_clicked.emit)
        act_grabber = add_menu.addAction(fluent_icons.create_fluent_grabber_icon(color="#f59e0b"), "Penangkap Konten Situs (Site Grabber)")
        act_grabber.triggered.connect(self.grabber_clicked.emit)
        act_sniffer = add_menu.addAction(fluent_icons.create_fluent_live_icon(color="#10b981"), "Sniffer Media Streaming")
        act_sniffer.triggered.connect(self.sniffer_clicked.emit)
        self.btn_add.setMenu(add_menu)
        layout.addWidget(self.btn_add)

        # -------------------------------------------------------------
        # 4. Transport Controls Cluster: Resume, Pause, Stop All, Delete, Clean
        # -------------------------------------------------------------
        self.command_capsule = QWidget()
        self.command_capsule.setStyleSheet("background: transparent;")
        c_layout = QHBoxLayout(self.command_capsule)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(2)

        self.btn_resume = self._create_icon_btn(fluent_icons.create_fluent_play_icon(color="#22c55e"), "Lanjutkan Unduhan (Space)", self.resume_clicked)
        self.btn_pause = self._create_icon_btn(fluent_icons.create_fluent_pause_icon(color="#f59e0b"), "Jeda Unduhan (Space)", self.pause_clicked)
        self.btn_stop_all = self._create_icon_btn(fluent_icons.create_fluent_stop_icon(color="#ef4444"), "Hentikan Semua Unduhan Aktif", self.stop_all_clicked)
        self.btn_delete = self._create_icon_btn(fluent_icons.create_fluent_delete_icon(color="#ef4444"), "Hapus Unduhan (Del)", self.delete_clicked)
        self.btn_del_comp = self._create_icon_btn(fluent_icons.create_fluent_broom_icon(color="#94a3b8"), "Bersihkan Berkas Selesai", self.delete_comp_clicked)

        for b in [self.btn_resume, self.btn_pause, self.btn_stop_all, self.btn_delete, self.btn_del_comp]:
            c_layout.addWidget(b)
        layout.addWidget(self.command_capsule)

        layout.addWidget(self._create_divider())

        # -------------------------------------------------------------
        # 5. Automation & Monitoring: Queue, Scheduler, Speed Graph
        # -------------------------------------------------------------
        self.btn_start_queue = self._create_icon_btn(fluent_icons.create_fluent_queue_icon(color="#06b6d4"), "Mulai / Hentikan Antrean Unduhan", self.start_queue_clicked)
        self.btn_stop_queue = self._create_icon_btn(fluent_icons.create_fluent_stop_queue_icon(color="#f43f5e"), "Hentikan Antrean", self.stop_queue_clicked)
        self.btn_stop_queue.hide()
        self.btn_scheduler = self._create_icon_btn(fluent_icons.create_fluent_scheduler_icon(color="#a855f7"), "Jadwalkan Unduhan Otomatis", self.scheduler_clicked)
        self.btn_graph = self._create_icon_btn(fluent_icons.create_fluent_graph_icon(color="#3b82f6"), "Grafik Kecepatan Real-time", self.graph_clicked)

        # Legacy dummy bindings
        self.btn_grabber = self._create_icon_btn(fluent_icons.create_fluent_grabber_icon(color="#f59e0b"), "Site Grabber", self.grabber_clicked)
        self.btn_grabber.hide()
        self.btn_torrent_search = self._create_icon_btn(fluent_icons.create_fluent_torrent_icon(color="#06b6d4"), "Pencarian Torrent", self.torrent_search_clicked)
        self.btn_torrent_search.hide()

        layout.addWidget(self.btn_start_queue)
        layout.addWidget(self.btn_scheduler)
        layout.addWidget(self.btn_graph)

        # -------------------------------------------------------------
        # 6. Symmetrical Centered Search Pill with Balanced Drag Areas
        # -------------------------------------------------------------
        layout.addStretch(1)  # Left balanced stretch (acts as clean window drag handle)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("KrolixSearchBar")
        self.search_input.setPlaceholderText("Cari unduhan... (Ctrl+F)")
        self.search_input.addAction(fluent_icons.create_fluent_search_icon(color="#71717a"), QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(220)
        self.search_input.setMaximumWidth(360)
        self.search_input.setFixedHeight(30)
        self.search_input.setStyleSheet("""
            QLineEdit#KrolixSearchBar {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid #27272a;
                border-radius: 15px;
                padding: 2px 10px 2px 8px;
                color: #f4f4f5;
                font-size: 11px;
            }
            QLineEdit#KrolixSearchBar:focus {
                border: 1px solid #22c55e;
                background-color: rgba(255, 255, 255, 0.09);
            }
        """)
        self.search_input.textChanged.connect(self.search_changed.emit)
        layout.addWidget(self.search_input)

        layout.addStretch(1)  # Right balanced stretch (acts as clean window drag handle)

        layout.addWidget(self._create_divider())

        # -------------------------------------------------------------
        # 7. Right Tools & Preferences Cluster (NO DUPLICATE GEAR ICONS)
        # -------------------------------------------------------------
        # Tools Overflow Menu Button with 3-dot More icon
        self.btn_tools = QToolButton()
        self.btn_tools.setObjectName("macToolsBtn")
        self.btn_tools.setIcon(fluent_icons.create_fluent_more_horizontal_icon(color="#a1a1aa"))
        self.btn_tools.setIconSize(QSize(18, 18))
        self.btn_tools.setToolTip("Alat & Utilitas Lanjutan (Torrent, Video, Sniffer, Checksum)")
        self.btn_tools.setFixedSize(30, 30)
        self.btn_tools.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tools.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_tools.setStyleSheet("""
            QToolButton#macToolsBtn {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
            }
            QToolButton#macToolsBtn:hover {
                background-color: rgba(255, 255, 255, 0.08);
                border-color: rgba(255, 255, 255, 0.12);
            }
            QToolButton#macToolsBtn::menu-indicator { image: none; }
        """)

        tools_menu = QMenu(self)
        tools_menu.setStyleSheet(add_menu.styleSheet())
        act_tsearch = tools_menu.addAction(fluent_icons.create_fluent_torrent_icon(color="#06b6d4"), "Pencarian Torrent & DHT")
        act_tsearch.triggered.connect(self.torrent_search_clicked.emit)
        act_ytdlp_t = tools_menu.addAction(fluent_icons.create_fluent_video_icon(color="#ef4444"), "Perekam Video (YT-DLP)...")
        act_ytdlp_t.triggered.connect(self.ytdlp_clicked.emit)
        act_grab_t = tools_menu.addAction(fluent_icons.create_fluent_grabber_icon(color="#f59e0b"), "Penangkap Konten Situs (Site Grabber)...")
        act_grab_t.triggered.connect(self.grabber_clicked.emit)
        act_hash = tools_menu.addAction(fluent_icons.create_fluent_hash_icon(color="#10b981"), "Verifikasi Checksum / Hash (MD5 / SHA-256)...")
        act_hash.triggered.connect(self.hash_clicked.emit)
        tools_menu.addSeparator()
        act_clean = tools_menu.addAction(fluent_icons.create_fluent_broom_icon(color="#94a3b8"), "Bersihkan Berkas Hilang")
        act_clean.triggered.connect(self.clean_missing_clicked.emit)
        self.btn_tools.setMenu(tools_menu)
        layout.addWidget(self.btn_tools)

        # Settings Gear Button (Distinctive Single Gear Icon)
        self.btn_options = self._create_icon_btn(fluent_icons.create_fluent_options_icon(color="#f4f4f5"), "Pengaturan & Preferensi (Ctrl+O)", self.options_clicked)
        layout.addWidget(self.btn_options)

    def _create_icon_btn(self, icon: QIcon, tooltip: str, signal: Optional[pyqtSignal] = None) -> QToolButton:
        btn = QToolButton()
        btn.setProperty("class", "mac-tool-btn")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setIcon(icon)
        btn.setIconSize(QSize(16, 16))
        btn.setToolTip(tooltip)
        btn.setFixedSize(30, 30)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.08);
                border-color: rgba(255, 255, 255, 0.12);
            }
            QToolButton:pressed {
                background-color: rgba(255, 255, 255, 0.14);
            }
        """)
        if signal is not None:
            btn.clicked.connect(signal.emit)
        return btn

    def _create_divider(self) -> QFrame:
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setFrameShadow(QFrame.Shadow.Plain)
        div.setStyleSheet("background-color: #27272a; max-width: 1px; min-width: 1px; margin: 12px 3px;")
        return div

    def _on_close(self):
        w = self.window()
        if w:
            w.close()

    def _on_min(self):
        w = self.window()
        if w:
            w.showMinimized()

    def _on_max(self):
        w = self.window()
        if w:
            if w.isMaximized():
                w.showNormal()
            else:
                w.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            w = self.window()
            if not w.isMaximized():
                self._drag_pos = event.globalPosition().toPoint() - w.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            w = self.window()
            if not w.isMaximized():
                w.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_max()
            event.accept()


class KrolixSidebarTree(QWidget):
    """
    macOS Source List Navigation Sidebar Tree.
    Organizes downloads into Categories, Queues, Unfinished, and Finished.
    """
    filter_selected = pyqtSignal(str)
    start_queue_requested = pyqtSignal(str)
    stop_queue_requested = pyqtSignal(str)
    schedule_queue_requested = pyqtSignal(str)
    category_settings_requested = pyqtSignal()
    open_category_folder_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("KrolixSidebar")
        self.setFixedWidth(230)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 6, 2, 6)
        layout.setSpacing(0)

        self.tree = QTreeWidget()
        self.tree.setObjectName("KrolixTree")
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(15)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        row_height = 34
        SIDE_ICON_COLOR = "#94a3b8"

        def _add_spacer(height=14):
            sp = QTreeWidgetItem(self.tree)
            sp.setFlags(Qt.ItemFlag.NoItemFlags)
            sp.setSizeHint(0, QSize(200, height))
            return sp

        # Root 1: Categories
        self.root_cat = QTreeWidgetItem(self.tree, ["Categories"])
        self.root_cat.setIcon(0, fluent_icons.create_fluent_folder_icon(color=SIDE_ICON_COLOR))
        self.root_cat.setData(0, Qt.ItemDataRole.UserRole, "ALL")
        self.root_cat.setSizeHint(0, QSize(200, row_height))

        self.item_all = QTreeWidgetItem(self.root_cat, ["All Downloads"])
        self.item_all.setIcon(0, fluent_icons.create_fluent_all_downloads_icon(color=SIDE_ICON_COLOR))
        self.item_all.setData(0, Qt.ItemDataRole.UserRole, "ALL")
        self.item_all.setSizeHint(0, QSize(200, row_height))

        self.item_compressed = QTreeWidgetItem(self.root_cat, ["Compressed"])
        self.item_compressed.setIcon(0, fluent_icons.create_fluent_compressed_icon(color=SIDE_ICON_COLOR))
        self.item_compressed.setData(0, Qt.ItemDataRole.UserRole, "CAT_Compressed")
        self.item_compressed.setSizeHint(0, QSize(200, row_height))

        self.item_docs = QTreeWidgetItem(self.root_cat, ["Documents"])
        self.item_docs.setIcon(0, fluent_icons.create_fluent_documents_icon(color=SIDE_ICON_COLOR))
        self.item_docs.setData(0, Qt.ItemDataRole.UserRole, "CAT_Documents")
        self.item_docs.setSizeHint(0, QSize(200, row_height))

        self.item_music = QTreeWidgetItem(self.root_cat, ["Music"])
        self.item_music.setIcon(0, fluent_icons.create_fluent_music_icon(color=SIDE_ICON_COLOR))
        self.item_music.setData(0, Qt.ItemDataRole.UserRole, "CAT_Audio")
        self.item_music.setSizeHint(0, QSize(200, row_height))

        self.item_programs = QTreeWidgetItem(self.root_cat, ["Programs"])
        self.item_programs.setIcon(0, fluent_icons.create_fluent_programs_icon(color=SIDE_ICON_COLOR))
        self.item_programs.setData(0, Qt.ItemDataRole.UserRole, "CAT_Applications")
        self.item_programs.setSizeHint(0, QSize(200, row_height))

        self.item_video = QTreeWidgetItem(self.root_cat, ["Video"])
        self.item_video.setIcon(0, fluent_icons.create_fluent_video_icon(color=SIDE_ICON_COLOR))
        self.item_video.setData(0, Qt.ItemDataRole.UserRole, "CAT_Videos")
        self.item_video.setSizeHint(0, QSize(200, row_height))

        self.item_torrents = QTreeWidgetItem(self.root_cat, ["Torrents"])
        self.item_torrents.setIcon(0, fluent_icons.create_fluent_torrent_icon(color=SIDE_ICON_COLOR))
        self.item_torrents.setData(0, Qt.ItemDataRole.UserRole, "CAT_Torrents")
        self.item_torrents.setSizeHint(0, QSize(200, row_height))

        # Spacer between Categories & Queues
        _add_spacer(14)

        # Root 2: Queues
        self.root_queues = QTreeWidgetItem(self.tree, ["Queues"])
        self.root_queues.setIcon(0, fluent_icons.create_fluent_queue_icon(color=SIDE_ICON_COLOR))
        self.root_queues.setData(0, Qt.ItemDataRole.UserRole, "ALL")
        self.root_queues.setSizeHint(0, QSize(200, row_height))

        self.item_main_q = QTreeWidgetItem(self.root_queues, ["Main download queue"])
        self.item_main_q.setIcon(0, fluent_icons.create_fluent_queue_icon(color=SIDE_ICON_COLOR))
        self.item_main_q.setData(0, Qt.ItemDataRole.UserRole, "QUEUE_Main Queue")
        self.item_main_q.setSizeHint(0, QSize(200, row_height))

        self.item_sync_q = QTreeWidgetItem(self.root_queues, ["Synchronization queue"])
        self.item_sync_q.setIcon(0, fluent_icons.create_fluent_queue_icon(color=SIDE_ICON_COLOR))
        self.item_sync_q.setData(0, Qt.ItemDataRole.UserRole, "QUEUE_Sync Queue")
        self.item_sync_q.setSizeHint(0, QSize(200, row_height))

        # Spacer between Queues & Status
        _add_spacer(14)

        # Root 3 & 4: Unfinished & Finished
        self.item_unfinished = QTreeWidgetItem(self.tree, ["Unfinished"])
        self.item_unfinished.setIcon(0, fluent_icons.create_fluent_clock_icon(color=SIDE_ICON_COLOR))
        self.item_unfinished.setData(0, Qt.ItemDataRole.UserRole, "UNFINISHED")
        self.item_unfinished.setSizeHint(0, QSize(200, row_height))

        self.item_finished = QTreeWidgetItem(self.tree, ["Finished"])
        self.item_finished.setIcon(0, fluent_icons.create_fluent_check_icon(color=SIDE_ICON_COLOR))
        self.item_finished.setData(0, Qt.ItemDataRole.UserRole, "FINISHED")
        self.item_finished.setSizeHint(0, QSize(200, row_height))

        self.tree.expandAll()
        self.tree.setCurrentItem(self.item_all)

        layout.addWidget(self.tree)

    def update_torrent_visibility(self, enabled: bool):
        self.item_torrents.setHidden(not enabled)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        tag = item.data(0, Qt.ItemDataRole.UserRole)
        if tag:
            self.filter_selected.emit(tag)

    def update_counts(self, counts: dict):
        total = counts.get("ALL", 0)
        self.item_all.setText(0, f"All Downloads ({total})")
        self.item_compressed.setText(0, f"Compressed ({counts.get('CAT_Compressed', 0)})")
        self.item_docs.setText(0, f"Documents ({counts.get('CAT_Documents', 0)})")
        self.item_music.setText(0, f"Music ({counts.get('CAT_Audio', 0)})")
        self.item_programs.setText(0, f"Programs ({counts.get('CAT_Applications', 0)})")
        self.item_video.setText(0, f"Video ({counts.get('CAT_Videos', 0)})")
        self.item_torrents.setText(0, f"Torrents ({counts.get('CAT_Torrents', 0)})")
        self.item_unfinished.setText(0, f"Unfinished ({counts.get('PAUSED', 0) + counts.get('DOWNLOADING', 0)})")
        self.item_finished.setText(0, f"Finished ({counts.get('COMPLETED', 0)})")

    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        tag = item.data(0, Qt.ItemDataRole.UserRole)
        if not tag:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0b0f17;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #1e293b;
                color: #ffffff;
            }
        """)

        if tag.startswith("QUEUE_"):
            q_name = tag.replace("QUEUE_", "")
            act_start = menu.addAction(f"Mulai Antrean ({q_name})")
            act_start.triggered.connect(lambda: self.start_queue_requested.emit(q_name))
            act_stop = menu.addAction(f"Hentikan Antrean ({q_name})")
            act_stop.triggered.connect(lambda: self.stop_queue_requested.emit(q_name))
            menu.addSeparator()
            act_sched = menu.addAction("Jadwal Antrean (Scheduler)...")
            act_sched.triggered.connect(lambda: self.schedule_queue_requested.emit(q_name))
        elif tag.startswith("CAT_"):
            cat_name = tag.replace("CAT_", "")
            display_title = item.text(0).split(" (")[0]
            act_filter = menu.addAction(f"Tampilkan Kategori '{display_title}'")
            act_filter.triggered.connect(lambda: self.filter_selected.emit(tag))
            act_open = menu.addAction("Buka Folder Kategori...")
            act_open.triggered.connect(lambda: self.open_category_folder_requested.emit(cat_name))
            menu.addSeparator()
            act_sett = menu.addAction("Atur Folder Kategori...")
            act_sett.triggered.connect(self.category_settings_requested.emit)
        else:
            act_filter = menu.addAction("Tampilkan Semua Unduhan")
            act_filter.triggered.connect(lambda: self.filter_selected.emit("ALL"))
            menu.addSeparator()
            act_sett = menu.addAction("Atur Jalur Folder Kategori...")
            act_sett.triggered.connect(self.category_settings_requested.emit)

        menu.exec(self.tree.viewport().mapToGlobal(pos))


KrolixSidebarTree = KrolixSidebarTree


class KrolixDetailsDrawer(QWidget):
    """
    macOS Minimalist Telemetry & Status Bar (28px).
    Replaces clunky multi-line drawers with a unified, high-density status bar:
    - Left: Queue status & Selected task title
    - Right: Speed metrics, ratio, ETA, and clickable Limiter pill
    """
    pause_resume_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    limiter_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("KrolixDrawer")
        self.setFixedHeight(28)
        self._current_task = None
        self._status_msg_timer = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        # Left Section: Status dot + Task / Summary
        left_box = QHBoxLayout()
        left_box.setSpacing(8)

        self.dot = QLabel()
        self.dot.setFixedSize(7, 7)
        self.dot.setStyleSheet("background-color: #22c55e; border-radius: 3px;")
        left_box.addWidget(self.dot)

        self.lbl_file = QLabel("All Queues Idle")
        self.lbl_file.setStyleSheet("font-size: 11px; font-weight: 500; color: #d4d4d8;")
        left_box.addWidget(self.lbl_file)

        self.lbl_dest = QLabel("")
        self.lbl_dest.setStyleSheet("font-size: 11px; color: #71717a;")
        left_box.addWidget(self.lbl_dest)

        layout.addLayout(left_box, 1)

        # Right Section: Metrics, Limiter, Speed
        right_box = QHBoxLayout()
        right_box.setSpacing(14)

        self.lbl_ratio = QLabel("")
        self.lbl_ratio.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        right_box.addWidget(self.lbl_ratio)

        self.lbl_eta = QLabel("")
        self.lbl_eta.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        right_box.addWidget(self.lbl_eta)

        self.btn_limiter = QPushButton("Limiter: Off")
        self.btn_limiter.setObjectName("LimiterPill")
        self.btn_limiter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_limiter.setStyleSheet("""
            QPushButton#LimiterPill {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid #27272a;
                border-radius: 10px;
                padding: 1px 8px;
                font-size: 10px;
                color: #a1a1aa;
            }
            QPushButton#LimiterPill:hover {
                background-color: rgba(255, 255, 255, 0.1);
                color: #ffffff;
            }
        """)
        self.btn_limiter.clicked.connect(self.limiter_clicked.emit)
        right_box.addWidget(self.btn_limiter)

        self.lbl_speed = QLabel("0.0 KB/s")
        self.lbl_speed.setStyleSheet("font-size: 11px; font-weight: 600; color: #22c55e;")
        right_box.addWidget(self.lbl_speed)

        layout.addLayout(right_box)

        # Invisible compatibility widgets
        self.progress_line = QWidget()
        self.progress_line.hide()
        self.btn_pause_resume = QPushButton()
        self.btn_pause_resume.hide()
        self.btn_settings = QPushButton()
        self.btn_settings.hide()

    def set_limiter_status(self, text_or_active="Limiter: Off", is_active=False, *args, **kwargs):
        if isinstance(text_or_active, bool):
            is_active = text_or_active
            label = "Limiter: Active" if is_active else "Limiter: Off"
        else:
            label = str(text_or_active)
            if not label.startswith("Limiter:"):
                label = f"Limiter: {label}"
            if "is_active" in kwargs:
                is_active = kwargs["is_active"]
            else:
                is_active = "Off" not in label and "0" not in label

        self.btn_limiter.setText(label)
        if is_active and "Off" not in label:
            self.btn_limiter.setStyleSheet("QPushButton#LimiterPill { background-color: rgba(34, 197, 94, 0.15); border: 1px solid #22c55e; border-radius: 10px; padding: 1px 8px; font-size: 10px; color: #22c55e; font-weight: 600; }")
        else:
            self.btn_limiter.setStyleSheet("QPushButton#LimiterPill { background-color: rgba(255, 255, 255, 0.05); border: 1px solid #27272a; border-radius: 10px; padding: 1px 8px; font-size: 10px; color: #a1a1aa; }")

    def show_status_message(self, text: str, duration_ms: int = 3500):
        self.lbl_file.setText(text)
        if self._status_msg_timer is not None:
            self._status_msg_timer.stop()
        from PyQt6.QtCore import QTimer
        self._status_msg_timer = QTimer(self)
        self._status_msg_timer.setSingleShot(True)
        self._status_msg_timer.timeout.connect(self._restore_dest_text)
        self._status_msg_timer.start(duration_ms)

    def _restore_dest_text(self):
        if self._current_task:
            self.update_task(self._current_task)
        else:
            self.lbl_file.setText("All Queues Idle")

    def update_task(self, task):
        self._current_task = task
        if not task:
            self.dot.setStyleSheet("background-color: #71717a; border-radius: 3px;")
            self.lbl_file.setText("All Queues Idle")
            self.lbl_dest.setText("")
            self.lbl_ratio.setText("")
            self.lbl_eta.setText("")
            self.lbl_speed.setText("0.0 KB/s")
            return

        raw_status = getattr(task, "status", "")
        status = (raw_status.value if hasattr(raw_status, "value") else str(raw_status)).lower()
        if status in ("downloading", "active"):
            self.dot.setStyleSheet("background-color: #22c55e; border-radius: 3px;")
        elif status == "paused":
            self.dot.setStyleSheet("background-color: #f59e0b; border-radius: 3px;")
        elif status == "completed":
            self.dot.setStyleSheet("background-color: #3b82f6; border-radius: 3px;")
        elif status == "error":
            self.dot.setStyleSheet("background-color: #ef4444; border-radius: 3px;")
        else:
            self.dot.setStyleSheet("background-color: #71717a; border-radius: 3px;")

        self.lbl_file.setText(getattr(task, "filename", "Unduhan"))
        self.lbl_dest.setText(getattr(task, "save_dir", "") or "")

        is_active = status in ("downloading", "active")
        spd = getattr(task, "speed", 0) or 0
        self.lbl_speed.setText(format_speed(spd) if is_active else "0.0 KB/s")

        total_b = getattr(task, "total_bytes", 0) or 0
        done_b = getattr(task, "downloaded_bytes", 0) or 0
        size_str = format_bytes(total_b) if total_b > 0 else "--"
        done_str = format_bytes(done_b) if done_b >= 0 else "0 B"
        if total_b > 0:
            self.lbl_ratio.setText(f"{done_str} / {size_str}")
        elif done_b > 0:
            self.lbl_ratio.setText(done_str)
        else:
            self.lbl_ratio.setText("")

        eta_sec = getattr(task, "eta", 0) or 0
        eta_txt = format_eta(eta_sec) if (is_active and eta_sec > 0) else ""
        self.lbl_eta.setText(f"ETA {eta_txt}" if (eta_txt and eta_txt != "--") else "")


class KrolixEmptyStateOverlay(QWidget):
    """Modern macOS Empty State Overlay shown when download table is empty."""
    add_url_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("KrolixEmptyState")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("""
            QWidget#KrolixEmptyState {
                background: transparent;
                background-color: transparent;
                border: none;
            }
            QLabel {
                background: transparent;
                background-color: transparent;
                border: none;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 40, 20, 40)
        layout.setSpacing(12)

        # Empty Icon
        icon_lbl = QLabel()
        icon_lbl.setObjectName("EmptyStateIcon")
        icon_pix = fluent_icons.create_fluent_all_downloads_icon(color="#52525b").pixmap(52, 52)
        icon_lbl.setPixmap(icon_pix)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon_lbl)

        # Title
        title_lbl = QLabel("No Downloads Yet")
        title_lbl.setObjectName("EmptyStateTitle")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #f4f4f5; background: transparent; border: none; margin-top: 2px;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        # Subtitle
        sub_lbl = QLabel("Click '+ Add Download' on the toolbar or paste links to start.")
        sub_lbl.setObjectName("EmptyStateSubtitle")
        sub_lbl.setStyleSheet("font-size: 12px; color: #71717a; background: transparent; border: none;")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub_lbl)

        # Action Button
        btn_box = QHBoxLayout()
        btn_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_add = QPushButton("+ Add Download")
        btn_add.setObjectName("EmptyAddBtn")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setFixedHeight(34)
        btn_add.setMinimumWidth(136)
        btn_add.setStyleSheet("""
            QPushButton#EmptyAddBtn {
                background-color: #22c55e;
                color: #ffffff;
                font-weight: 600;
                font-size: 12px;
                border-radius: 6px;
                border: none;
                padding: 6px 16px;
            }
            QPushButton#EmptyAddBtn:hover {
                background-color: #16a34a;
            }
            QPushButton#EmptyAddBtn:pressed {
                background-color: #15803d;
            }
        """)
        btn_add.clicked.connect(self.add_url_requested.emit)
        btn_box.addWidget(btn_add)
        layout.addLayout(btn_box)


class MainWindow(QMainWindow):
    """
    Krolix Download Manager Main Application Window.
    Blends modern macOS design language with high-performance multi-segment engine.
    """
    def __init__(self, db: Database, engine: DownloadEngine, speed_limiter: SpeedLimiter):
        super().__init__()
        self.db = db
        self.engine = engine
        self.speed_limiter = speed_limiter
        self.signals = BridgeSignals()

        self.setWindowTitle("Krolix Download Manager")
        self.resize(1180, 720)
        self.setMinimumSize(960, 560)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMouseTracking(True)
        self._resizing_edge = None
        self._drag_start_pos = None
        self._drag_start_geo = None

        # Apply saved theme and accent (defaults to macOS Sonoma Dark and Krolix Green)
        _theme = self.db.get_setting('ui_theme', 'mica_dark')
        _accent = self.db.get_setting('ui_accent', 'krolix_green')
        if _accent in ('chrome', 'cyan', 'emerald', 'violet', 'amber', 'rose', 'sky', 'default'):
            _accent = 'krolix_green'
        self.apply_theme(_theme, _accent)

        # Set Window Icon to Multi-Resolution Krolix Icon
        win_icon = get_app_icon()
        if win_icon and not win_icon.isNull():
            self.setWindowIcon(win_icon)
        apply_taskbar_icon(self)
        try:
            self._cached_hwnd = int(self.winId())
        except Exception:
            self._cached_hwnd = 0
        self._is_light_theme = False

        self._active_dialogs = {}
        self._complete_dialogs = {}
        self._dash_pairs = {}
        self._hidden_tasks = set()
        self.current_filter_tag = "ALL"
        self._current_add_dialog = None
        self._current_media_dialog = None
        self._recent_urls = {}

        # Connect engine callbacks to Qt signals
        self.engine.on_task_updated = lambda t: self.signals.task_updated.emit(t)
        self.engine.on_task_completed = lambda t: self.signals.task_completed.emit(t)
        self.engine.on_task_failed = lambda t, err: self.signals.task_failed.emit(t, err or "Failed")
        self.engine.on_exit_requested = lambda: self.signals.exit_requested.emit()
        self.signals.task_updated.connect(self._on_task_updated)
        self.signals.task_completed.connect(self._on_task_completed)
        self.signals.task_failed.connect(self._on_task_failed)
        self.signals.url_detected.connect(self._prompt_add_url)
        self.signals.download_requested.connect(self._handle_incoming_download)
        self.signals.batch_requested.connect(self._handle_incoming_batch_download)
        self.signals.exit_requested.connect(self._force_quit)
        self.signals.run_on_main.connect(lambda fn: fn() if callable(fn) else None)

        # Initialize Queue Manager, Scheduler, Watchlist & Tray Service
        self.queue_mgr = QueueManager(self.engine, self.db)
        self.scheduler = DownloadScheduler(self.engine, self.db, self.speed_limiter)
        from ..core.stream_watchlist import StreamWatchlistManager
        self._watchlist_dialog = None
        self.watchlist_mgr = StreamWatchlistManager(
            engine=self.engine,
            db=self.db,
            on_item_updated=lambda item: self.signals.watchlist_updated.emit(item),
            on_recording_started=lambda item, task: self.signals.watchlist_recording_started.emit(item, task),
        )
        self.signals.watchlist_updated.connect(self._on_watchlist_updated)
        self.signals.watchlist_recording_started.connect(self._on_watchlist_recording_started)
        self.tray = TrayService(self)
        self.tray.show_window_requested.connect(self._restore_from_tray)
        self.tray.hide_window_requested.connect(self.hide)
        self.tray.add_url_requested.connect(lambda: self._show_add_dialog())
        self.tray.pause_all_requested.connect(self._stop_all)
        self.tray.resume_all_requested.connect(self._resume_all)
        self.tray.exit_requested.connect(self._confirm_force_quit)

        # Desktop Floating Drop Target Widget
        self.floating_widget = FloatingDropWidget()
        self.floating_widget.url_dropped.connect(self._prompt_add_url)
        self.floating_widget.restore_window_requested.connect(self._restore_from_tray)

        self._init_layout()
        self._init_menu_bar()
        self._init_shortcuts()
        self._populate_table()
        self._update_all_telemetry()

        # Start clipboard monitor
        monitor_enabled = self.db.get_setting("monitor_clipboard", "true") == "true"
        self.clip_monitor = ClipboardMonitor(
            on_url_detected=lambda u: self.signals.url_detected.emit(u),
            enabled=monitor_enabled,
            is_torrent_enabled=lambda: self.db.is_torrent_enabled()
        )
        self.clip_monitor.start()

        # Start local API server for browser extensions
        self.api_server = LocalAPIServer(
            port=9666,
            parent=self,
            on_download_requested=lambda d: self.signals.download_requested.emit(d)
        )
        self.api_server.batch_requested.connect(lambda d: self.signals.batch_requested.emit(d))
        self.api_server.restore_requested.connect(self._restore_from_tray)
        self.api_server.start()

        self._current_sort_col = -1
        self._current_sort_order = Qt.SortOrder.AscendingOrder

        if self.db.get_setting("show_tips_on_startup", "true") == "true":
            QTimer.singleShot(700, self._show_tip_dialog)

        # Check startup license status and update title
        self._update_window_title()
        QTimer.singleShot(1200, self._check_startup_license)

    def _init_menu_bar(self):
        menubar = self.menu_bar

        # 1. Tasks Menu (Standard Clean Style)
        tasks_menu = menubar.addMenu("&Tasks")
        act_add = tasks_menu.addAction("Add new download...")
        act_add.setShortcut(QKeySequence("Ctrl+N"))
        act_add.triggered.connect(lambda: self._show_add_dialog())

        act_ytdlp = tasks_menu.addAction("Download dari YouTube & Media Sosial... (YT-DLP)")
        act_ytdlp.setShortcut(QKeySequence("Ctrl+Y"))
        act_ytdlp.triggered.connect(lambda: self._show_ytdlp_dialog())

        act_batch = tasks_menu.addAction("Add batch download...")
        act_batch.triggered.connect(self._show_batch_dialog)

        act_batch_clip = tasks_menu.addAction("Add batch download from clipboard")
        act_batch_clip.triggered.connect(self._batch_from_clipboard)

        act_sniffer = tasks_menu.addAction("Sniff & Ekstrak Link Massal...")
        act_sniffer.setShortcut(QKeySequence("Ctrl+Shift+B"))
        act_sniffer.triggered.connect(lambda: self._show_batch_sniffer_dialog())

        act_grabber = tasks_menu.addAction("Run site grabber")
        act_grabber.triggered.connect(lambda: self._show_site_grabber_dialog())

        act_watchlist = tasks_menu.addAction(fluent_icons.create_fluent_live_icon("#f43f5e"), "Live Stream Watchlist & Auto-Recorder...")
        act_watchlist.setShortcut(QKeySequence("Ctrl+Shift+L"))
        act_watchlist.triggered.connect(lambda: self._show_watchlist_dialog())

        tasks_menu.addSeparator()
        export_sub = tasks_menu.addMenu("Export")
        act_export = export_sub.addAction("to text file...")
        act_export.triggered.connect(self._export_downloads)

        import_sub = tasks_menu.addMenu("Import")
        act_import = import_sub.addAction("from text file...")
        act_import.triggered.connect(self._import_downloads)

        tasks_menu.addSeparator()
        act_close = tasks_menu.addAction("Close Window (Worker Remains Active)")
        act_close.setShortcut(QKeySequence("Ctrl+W"))
        act_close.triggered.connect(self.hide)

        act_exit = tasks_menu.addAction("Exit Completely (Stop Worker)...")
        act_exit.triggered.connect(self._confirm_force_quit)

        # 2. File Menu
        file_menu = menubar.addMenu("&File")
        act_stop = file_menu.addAction("Stop download")
        act_stop.triggered.connect(self._pause_selected)

        act_pause = file_menu.addAction("Pause")
        act_pause.triggered.connect(self._pause_selected)

        act_resume = file_menu.addAction("Resume")
        act_resume.triggered.connect(self._resume_selected)

        act_redownload = file_menu.addAction("Redownload")
        act_redownload.triggered.connect(self._redownload_selected)

        act_refresh_file = file_menu.addAction("Refresh Download Address (Perbarui URL)...")
        act_refresh_file.setShortcut(QKeySequence("Ctrl+U"))
        act_refresh_file.triggered.connect(self._on_toolbar_refresh_link)

        file_menu.addSeparator()
        act_preview = file_menu.addAction("Preview / Play Media")
        act_preview.setShortcut(QKeySequence("Ctrl+P"))
        act_preview.triggered.connect(self._preview_selected_media)

        act_rename = file_menu.addAction("Rename File...")
        act_rename.setShortcut(QKeySequence("F2"))
        act_rename.triggered.connect(self._rename_selected_task)

        file_menu.addSeparator()
        act_del = file_menu.addAction("Delete")
        act_del.setShortcut(QKeySequence.StandardKey.Delete)
        act_del.triggered.connect(self._delete_selected)

        act_del_comp = file_menu.addAction("Delete completed")
        act_del_comp.triggered.connect(self._delete_all_completed)

        act_del_all = file_menu.addAction("Delete all")
        act_del_all.triggered.connect(self._delete_all_tasks)

        act_clean_missing = file_menu.addAction("Clean Missing / Dead Files")
        act_clean_missing.triggered.connect(self._clean_missing_files)

        file_menu.addSeparator()
        act_verify = file_menu.addAction("Verify Checksum / Hash...")
        act_verify.triggered.connect(self._verify_selected_hash)

        act_extract = file_menu.addAction("Extract Archive...")
        act_extract.triggered.connect(self._extract_selected_archive)

        # 3. Torrent Menu (Dedicated BitTorrent Operations)
        torrent_menu = menubar.addMenu("&Torrent")
        act_add_torrent = torrent_menu.addAction("Add BitTorrent file (.torrent)...")
        act_add_torrent.triggered.connect(self._open_add_torrent_file_dialog)

        act_add_magnet = torrent_menu.addAction("Add Magnet link...")
        act_add_magnet.triggered.connect(self._open_add_magnet_dialog)

        torrent_menu.addSeparator()
        act_torrent = torrent_menu.addAction("Search Torrents & Media...")
        act_torrent.setShortcut(QKeySequence("Ctrl+T"))
        act_torrent.triggered.connect(lambda: self._show_torrent_search_dialog())

        act_dht = torrent_menu.addAction("Cari Torrent via DHT & BTDIG...")
        act_dht.setShortcut(QKeySequence("Ctrl+D"))
        act_dht.triggered.connect(self._show_dht_search_dialog)

        torrent_menu.addSeparator()
        act_seeder = torrent_menu.addAction("BitTorrent Seeding Manager...")
        act_seeder.setShortcut(QKeySequence("Ctrl+Shift+S"))
        act_seeder.triggered.connect(self._show_torrent_seeder_dialog)

        # 4. Downloads Menu
        dl_menu = menubar.addMenu("&Downloads")
        limiter_sub = dl_menu.addMenu("Speed Limiter")
        self.act_limiter_toggle = limiter_sub.addAction("Turn on")
        self.act_limiter_toggle.setCheckable(True)
        self.act_limiter_toggle.setChecked(self.speed_limiter.enabled)
        self.act_limiter_toggle.triggered.connect(self._toggle_limiter_menu)

        act_limiter_sett = limiter_sub.addAction("Settings...")
        act_limiter_sett.triggered.connect(self._show_settings)

        post_sub = dl_menu.addMenu("When All Downloads Complete")
        self._post_action_group = []
        saved_post = self.db.get_setting("post_download_action", "none")
        for label, val in [
            ("Do Nothing (Default)", "none"),
            ("Play Sound Alert", "beep"),
            ("Open Downloads Folder", "open_folder"),
            ("Put Computer to Sleep", "sleep"),
            ("Shutdown Computer", "shutdown"),
        ]:
            act_p = post_sub.addAction(label)
            act_p.setCheckable(True)
            act_p.setChecked(saved_post == val)
            act_p.triggered.connect(lambda checked, v=val: self._set_post_download_action(v))
            self._post_action_group.append((act_p, val))

        dl_menu.addSeparator()
        act_options = dl_menu.addAction("Options")
        act_options.triggered.connect(self._show_settings)

        act_sched = dl_menu.addAction("Scheduler")
        act_sched.triggered.connect(self._show_scheduler_dialog)

        act_dl_watchlist = dl_menu.addAction(fluent_icons.create_fluent_live_icon("#f43f5e"), "Live Stream Watchlist & Auto-Recorder...")
        act_dl_watchlist.triggered.connect(lambda: self._show_watchlist_dialog())

        act_cred = dl_menu.addAction("Site Logins / Credentials...")
        act_cred.triggered.connect(self._show_credentials_dialog)

        dl_menu.addSeparator()
        queue_start_sub = dl_menu.addMenu("Start Queue")
        act_start_main_q = queue_start_sub.addAction("Main download queue")
        act_start_main_q.triggered.connect(lambda: self.queue_mgr.start_queue("Main Queue"))

        queue_stop_sub = dl_menu.addMenu("Stop Queue")
        act_stop_main_q = queue_stop_sub.addAction("Main download queue")
        act_stop_main_q.triggered.connect(lambda: self.queue_mgr.stop_queue("Main Queue"))

        # 5. View Menu
        view_menu = menubar.addMenu("&View")
        self.act_view_tb = view_menu.addAction("Command Bar")
        self.act_view_tb.setCheckable(True)
        self.act_view_tb.setChecked(True)
        self.act_view_tb.triggered.connect(lambda c: self.command_bar.setVisible(c))

        self.act_view_tree = view_menu.addAction("Categories Tree")
        self.act_view_tree.setCheckable(True)
        self.act_view_tree.setChecked(True)
        self.act_view_tree.triggered.connect(lambda c: self.sidebar.setVisible(c))

        self.act_view_sb = view_menu.addAction("Status Bar")
        self.act_view_sb.setCheckable(True)
        self.act_view_sb.setChecked(True)
        self.act_view_sb.triggered.connect(lambda c: self.statusBar().setVisible(c))

        view_menu.addSeparator()
        arrange_sub = view_menu.addMenu("Arrange files")
        act_arr_add = arrange_sub.addAction("by addition order")
        act_arr_add.triggered.connect(lambda: self._arrange_files(5, Qt.SortOrder.AscendingOrder))
        act_arr_name = arrange_sub.addAction("by file name")
        act_arr_name.triggered.connect(lambda: self._arrange_files(0, Qt.SortOrder.AscendingOrder))
        act_arr_size = arrange_sub.addAction("by size")
        act_arr_size.triggered.connect(lambda: self._arrange_files(1, Qt.SortOrder.DescendingOrder))
        act_arr_status = arrange_sub.addAction("by status")
        act_arr_status.triggered.connect(lambda: self._arrange_files(2, Qt.SortOrder.AscendingOrder))
        act_arr_time = arrange_sub.addAction("by time left")
        act_arr_time.triggered.connect(lambda: self._arrange_files(3, Qt.SortOrder.AscendingOrder))
        act_arr_rate = arrange_sub.addAction("by transfer rate")
        act_arr_rate.triggered.connect(lambda: self._arrange_files(4, Qt.SortOrder.DescendingOrder))
        act_arr_date = arrange_sub.addAction("by last try date")
        act_arr_date.triggered.connect(lambda: self._arrange_files(5, Qt.SortOrder.DescendingOrder))
        act_arr_desc = arrange_sub.addAction("by description")
        act_arr_desc.triggered.connect(lambda: self._arrange_files(6, Qt.SortOrder.AscendingOrder))
        act_arr_seed = arrange_sub.addAction("by masa seeding")
        act_arr_seed.triggered.connect(lambda: self._arrange_files(7, Qt.SortOrder.DescendingOrder))

        view_menu.addSeparator()
        self.act_graph = view_menu.addAction("Real-Time Speed Graph")
        self.act_graph.setCheckable(True)
        self.act_graph.triggered.connect(self._toggle_speed_graph)

        act_drop = view_menu.addAction("Desktop Drop Target")
        act_drop.setCheckable(True)
        act_drop.triggered.connect(self._toggle_floating_widget)

        # 7. Help Menu
        help_menu = menubar.addMenu("&Help")
        act_tutorials = help_menu.addAction("Tutorials")
        act_tutorials.triggered.connect(lambda: QMessageBox.information(self, "Krolix Tutorials", "Krolix Download Manager integrates with your browser to accelerate downloads up to 5x with intelligent dynamic segmentation."))

        act_tip = help_menu.addAction("Tip of the Day (Tip Hari Ini)...")
        act_tip.triggered.connect(self._show_tip_dialog)

        act_ext = help_menu.addAction("Browser Integration & Extension Manager...")
        act_ext.triggered.connect(self._show_extension_dialog)

        act_update = help_menu.addAction("Quick Update")
        act_update.triggered.connect(lambda: QMessageBox.information(self, "Quick Update", "You are using the latest version of Krolix Download Manager v2.8."))

        help_menu.addSeparator()
        self.act_registration = help_menu.addAction("Registration...")
        self.act_registration.triggered.connect(self._show_license_dialog)

        self.act_buy = help_menu.addAction("Order Full Version Online...")
        self.act_buy.triggered.connect(self._order_license_online)

        help_menu.addSeparator()
        act_about = help_menu.addAction("About Krolix")
        act_about.triggered.connect(self._show_about_dialog)

        self._update_registration_menu_state()

    def _init_layout(self):
        container = QWidget()
        container.setObjectName("KrolixRootContainer")
        container.setStyleSheet("""
            QWidget#KrolixRootContainer {
                background-color: #141418;
                border: 1px solid #27272e;
                border-radius: 8px;
            }
        """)
        main_vbox = QVBoxLayout(container)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        # 0. Menu Bar (Internal action host for keyboard shortcuts; visually hidden for sleek macOS chrome)
        self.menu_bar = QMenuBar(self)
        self.menu_bar.hide()

        # 1. macOS Unified Header (Titlebar + Toolbar in ONE cohesive 48px bar)
        self.command_bar = KrolixMacOSBar(self)
        self.title_bar = self.command_bar  # Alias for window title and branding compatibility
        self.command_bar.add_url_clicked.connect(lambda: self._show_add_dialog())
        self.command_bar.resume_clicked.connect(self._resume_selected)
        self.command_bar.pause_clicked.connect(self._pause_selected)
        self.command_bar.stop_all_clicked.connect(self._stop_all)
        self.command_bar.delete_clicked.connect(self._delete_selected)
        self.command_bar.delete_permanent_clicked.connect(lambda: self._delete_selected(delete_files=True))
        self.command_bar.btn_delete.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.command_bar.btn_delete.customContextMenuRequested.connect(self._on_del_btn_context_menu)
        self.command_bar.delete_comp_clicked.connect(self._delete_all_completed)
        self.command_bar.btn_del_comp.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.command_bar.btn_del_comp.customContextMenuRequested.connect(self._on_del_comp_context_menu)
        self.command_bar.delete_all_clicked.connect(lambda: self._delete_all_tasks(delete_files=False))
        self.command_bar.clean_missing_clicked.connect(self._clean_missing_files)
        self.command_bar.redownload_clicked.connect(self._redownload_selected)
        self.command_bar.start_queue_clicked.connect(lambda: self.queue_mgr.start_queue("Main Queue"))
        self.command_bar.stop_queue_clicked.connect(lambda: self.queue_mgr.stop_queue("Main Queue"))
        self.command_bar.scheduler_clicked.connect(self._show_scheduler_dialog)
        self.command_bar.limiter_clicked.connect(self._show_settings)
        self.command_bar.grabber_clicked.connect(lambda: self._show_site_grabber_dialog())
        self.command_bar.batch_clicked.connect(self._show_batch_dialog)
        self.command_bar.hash_clicked.connect(self._verify_selected_hash)
        self.command_bar.graph_clicked.connect(self._toggle_speed_graph)
        self.command_bar.options_clicked.connect(self._show_settings)
        self.command_bar.torrent_search_clicked.connect(lambda: self._show_torrent_search_dialog())
        self.command_bar.add_torrent_file_clicked.connect(self._open_add_torrent_file_dialog)
        self.command_bar.add_magnet_clicked.connect(self._open_add_magnet_dialog)
        self.command_bar.seeder_clicked.connect(self._show_torrent_seeder_dialog)
        self.command_bar.ytdlp_clicked.connect(lambda: self._show_ytdlp_dialog())
        self.command_bar.dht_search_clicked.connect(self._show_dht_search_dialog)
        self.command_bar.sniffer_clicked.connect(self._show_batch_sniffer_dialog)
        self.command_bar.refresh_link_clicked.connect(self._on_toolbar_refresh_link)
        self.command_bar.watchlist_clicked.connect(lambda: self._show_watchlist_dialog())
        self.command_bar.search_changed.connect(self._apply_filters)
        main_vbox.addWidget(self.command_bar)

        # 2. Central Splitter (Navigation Sidebar + Downloads Table)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #1a1a1a; width: 1px; }")

        self.sidebar = KrolixSidebarTree(self)
        self.sidebar.update_torrent_visibility(self.db.is_torrent_enabled())
        self.sidebar.filter_selected.connect(self._on_filter_changed)
        self.sidebar.start_queue_requested.connect(self.queue_mgr.start_queue)
        self.sidebar.stop_queue_requested.connect(self.queue_mgr.stop_queue)
        self.sidebar.schedule_queue_requested.connect(lambda _: self._show_scheduler_dialog())
        self.sidebar.category_settings_requested.connect(self._open_category_folders_dialog)
        self.sidebar.open_category_folder_requested.connect(self._open_category_folder_by_name)
        self.splitter.addWidget(self.sidebar)

        # Right Content Panel: Table + Optional Graph
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Main Download Table Columns
        self.table = QTableWidget()
        self.table.setObjectName("DownloadTable")
        self.table.setShowGrid(False)
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "File Name", "Size", "Status", "Time left", "Transfer rate", "Last Try Date", "Description", "Seed Time"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        # Dynamic & Interactive Table Header (Drag to lengthen & shorten columns)
        self._init_table_header()

        self.table.setItemDelegateForColumn(0, FileNameDelegate(self.table))
        self.table.setItemDelegateForColumn(2, ProgressSegmentsDelegate(self.table))

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)

        right_layout.addWidget(self.table)

        # Empty State Overlay
        self.empty_overlay = KrolixEmptyStateOverlay(self.table)
        self.empty_overlay.add_url_requested.connect(lambda: self._show_add_dialog())
        self.empty_overlay.hide()

        # Collapsible Real-Time Speed Graph
        self.speed_graph = SpeedGraphWidget(max_points=60)
        self.speed_graph.setVisible(False)
        right_layout.addWidget(self.speed_graph)

        self.splitter.addWidget(right_panel)
        self.splitter.setSizes([230, 950])
        self.splitter.splitterMoved.connect(lambda pos, idx: self._adjust_column_widths_to_viewport())
        main_vbox.addWidget(self.splitter, 1)

        # 3. Bottom Quick Details Card (Unified Status & Telemetry Bar)
        self.drawer = KrolixDetailsDrawer(self)
        self.drawer.pause_resume_clicked.connect(self._toggle_active_download)
        self.drawer.settings_clicked.connect(self._show_settings)
        self.drawer.limiter_clicked.connect(self._show_settings)
        self.size_grip = QSizeGrip(self.drawer)
        self.size_grip.setStyleSheet("background: transparent; width: 14px; height: 14px;")
        self.drawer.layout().addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        main_vbox.addWidget(self.drawer)

        self.setCentralWidget(container)

        # 4. Status Bar (Hidden - Unified into Bottom Details Card)
        self.status_bar = self.statusBar()
        self.lbl_status_main = QLabel("Ready")
        self.lbl_status_speed = QLabel("0.0 KB/s")
        self.lbl_status_speed.setStyleSheet("color: #10b981; font-weight: 600; font-family: 'Segoe UI Variable Text', monospace;")
        self.lbl_status_limiter = QLabel("Speed Limiter: Off")
        self.lbl_status_limiter.setStyleSheet("color: #94a3b8;")

        self.status_bar.addWidget(self.lbl_status_main, 1)
        self.status_bar.addPermanentWidget(self.lbl_status_limiter)
        self.status_bar.addPermanentWidget(self.lbl_status_speed)
        self.status_bar.hide()

    def _init_shortcuts(self):
        from PyQt6.QtGui import QKeySequence, QShortcut
        # Primary global hotkeys (menu QActions already handle Ctrl+N/Y/D/T/U/P/W, Ctrl+Shift+B/L/S, F2, Delete)
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self._show_settings)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_search)
        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(self._focus_search)
        QShortcut(QKeySequence("F5"), self).activated.connect(self._populate_table)
        QShortcut(QKeySequence("Ctrl+A"), self.table).activated.connect(self.table.selectAll)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._on_escape_pressed)
        QShortcut(QKeySequence("Space"), self.table).activated.connect(self._toggle_pause_selected)
        QShortcut(QKeySequence("Ctrl+V"), self).activated.connect(self._paste_from_clipboard)
        QShortcut(QKeySequence("Shift+Delete"), self.table).activated.connect(lambda: self._delete_selected(delete_files=True))

    def _on_escape_pressed(self):
        if hasattr(self, "command_bar") and hasattr(self.command_bar, "search_input"):
            if self.command_bar.search_input.text():
                self.command_bar.search_input.clear()
        self.table.setFocus()

    def _toggle_pause_selected(self):
        tasks = self._get_selected_tasks()
        if not tasks:
            return
        any_downloading = any(t.status == DownloadStatus.DOWNLOADING for t in tasks)
        if any_downloading:
            self._pause_selected()
        else:
            self._resume_selected()

    def _paste_from_clipboard(self):
        try:
            text = QApplication.clipboard().text().strip()
            if text and (text.startswith("http://") or text.startswith("https://") or text.startswith("magnet:") or text.startswith("ftp://")):
                if text.startswith("magnet:") and not self.db.is_torrent_enabled():
                    QMessageBox.warning(
                        self,
                        "BitTorrent Dinonaktifkan",
                        "Fitur unduhan BitTorrent / Magnet sedang dinonaktifkan.\n\n"
                        "Buka Pengaturan (Options) dan beri centang pada 'Aktifkan Dukungan BitTorrent / Magnet' untuk mengaktifkannya."
                    )
                    return
                self._prompt_add_url(text)
        except Exception:
            pass

    def _focus_search(self):
        self.command_bar.search_input.setFocus()
        self.command_bar.search_input.selectAll()

    def apply_theme(self, theme_id: str = "mica_dark", accent_id: str = "cyan"):
        """Live applies application theme, stylesheet, dynamic delegate highlights, and speed chart accent."""
        try:
            from .styles import get_app_stylesheet, ACCENTS, HEX_TO_ACCENT
            stylesheet = get_app_stylesheet(theme_id, accent_id)
            QApplication.instance().setStyleSheet(stylesheet)
            self._is_light_theme = ("light" in str(theme_id).lower() or "white" in str(theme_id).lower())

            acc_key = HEX_TO_ACCENT.get(str(accent_id).lower(), str(accent_id).lower())
            acc_info = ACCENTS.get(acc_key, ACCENTS["chrome"])
            acc_primary = acc_info["primary"]
            acc_end = acc_info["gradient_end"]

            FileNameDelegate.set_accent_color(acc_primary)
            ProgressSegmentsDelegate.set_accent_color(acc_primary)
            FileNameDelegate.set_light_theme(self._is_light_theme)
            ProgressSegmentsDelegate.set_light_theme(self._is_light_theme)

            if hasattr(self, "speed_graph"):
                self.speed_graph.set_accent_color(acc_primary, acc_end)

            if hasattr(self, "table"):
                self._populate_table()
                self.table.viewport().update()
        except Exception as e:
            print("apply_theme error:", e)

    def _toggle_speed_graph(self):
        visible = not self.speed_graph.isVisible()
        self.speed_graph.setVisible(visible)
        if hasattr(self, "act_graph"):
            self.act_graph.setChecked(visible)

    def _on_filter_changed(self, tag: str):
        self.current_filter_tag = tag
        self._apply_filters()

    def _task_matches_filters(self, task: DownloadTask) -> bool:
        query = self.command_bar.search_input.text().strip().lower() if hasattr(self, "command_bar") and hasattr(self.command_bar, "search_input") else ""
        tag = getattr(self, "current_filter_tag", "ALL")

        tag_match = True
        if tag == "ALL":
            tag_match = True
        elif tag == "FINISHED" or tag == "COMPLETED":
            tag_match = (task.status == DownloadStatus.COMPLETED)
        elif tag == "UNFINISHED":
            tag_match = (task.status != DownloadStatus.COMPLETED)
        elif tag.startswith("CAT_"):
            cat = tag.replace("CAT_", "").lower()
            t_cat = (task.category or "").lower()
            if cat in ["video", "videos"]:
                tag_match = t_cat in ["video", "videos"]
            elif cat in ["applications", "programs"]:
                tag_match = t_cat in ["applications", "programs"]
            elif cat in ["audio", "music"]:
                tag_match = t_cat in ["audio", "music"]
            elif cat in ["torrents", "torrent"]:
                tag_match = getattr(task, "is_torrent", False) or t_cat in ["torrents", "torrent"]
            else:
                tag_match = (t_cat == cat)
        elif tag.startswith("QUEUE_"):
            q_name = tag.replace("QUEUE_", "")
            tag_match = (getattr(task, "queue_name", "Main Queue") == q_name)

        if not tag_match:
            return False

        if query:
            match_name = query in (task.filename or "").lower()
            match_url = query in (task.url or "").lower()
            if not (match_name or match_url):
                return False

        return True

    def _apply_filters(self):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if not it:
                continue
            meta = it.data(Qt.ItemDataRole.UserRole)
            if not isinstance(meta, dict):
                continue
            task_id = meta.get("task_id")
            task = self.engine.tasks.get(task_id)
            if not task:
                continue
            self.table.setRowHidden(r, not self._task_matches_filters(task))

    def _populate_table(self):
        self.table.setRowCount(0)
        tasks = list(self.engine.tasks.values())
        for task in tasks:
            if getattr(task, 'is_hidden', False) or task.id in self._hidden_tasks:
                continue
            self._insert_or_update_row(task)
        self._apply_filters()
        self._update_empty_state()
        self._update_all_telemetry()

    def _insert_or_update_row(self, task: DownloadTask):
        # Guard: If task is hidden or companion audio, do not display in table
        if getattr(task, 'is_hidden', False) or task.id in self._hidden_tasks:
            return

        # Guard: If task was deleted from engine, ensure row is removed and exit
        if task.id not in self.engine.tasks:
            row = self._find_row_by_id(task.id)
            if row >= 0:
                self.table.removeRow(row)
                self._update_empty_state()
            return

        was_sorting = self.table.isSortingEnabled()
        if was_sorting:
            self.table.setSortingEnabled(False)
        try:
            row = self._find_row_by_id(task.id)
            if row < 0:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._update_empty_state()

            is_light = getattr(self, "_is_light_theme", False)
            fg_primary = QColor("#1e293b") if is_light else QColor("#cbd5e1")
            fg_active = QColor("#334155") if is_light else QColor("#94a3b8")
            fg_muted = QColor("#64748b")

            parsed = urllib.parse.urlparse(task.url)
            domain = parsed.netloc or "direct-stream"
            ext = Path(task.filename).suffix.lstrip(".").upper() or "FILE"
            domain_subtext = f"{domain} • HTTP 206" if task.resumable else f"{domain} • Direct"

            is_active = (task.status == DownloadStatus.DOWNLOADING)

            # 0: File Name (Delegate)
            it_name = SortableTableWidgetItem(task.filename, task.filename.lower())
            it_name.setData(Qt.ItemDataRole.UserRole, {
                "task_id": task.id,
                "filename": task.filename,
                "ext": ext,
                "domain": domain_subtext,
                "is_active": is_active
            })
            self.table.setItem(row, 0, it_name)

            # 1: Size
            size_bytes = task.total_bytes if task.total_bytes > 0 else (task.downloaded_bytes if task.downloaded_bytes > 0 else 0)
            size_str = format_bytes(task.total_bytes) if task.total_bytes > 0 else (format_bytes(task.downloaded_bytes) if task.downloaded_bytes > 0 else "--")
            it_size = SortableTableWidgetItem(size_str, size_bytes)
            it_size.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            it_size.setForeground(fg_primary)
            self.table.setItem(row, 1, it_size)

            # 2: Status & Progress (Delegate)
            streams_cnt = len(task.segments) if task.segments else 8
            is_seeding = bool(task.is_torrent and is_active and (getattr(task, "is_seeding", False) or task.progress >= 100.0 or (task.upload_speed > 0 and task.speed == 0)))

            if is_seeding:
                streams_txt = f"Seeding (▲ {format_bytes(task.upload_speed)}/s)" if task.upload_speed > 0 else f"Seeding ({getattr(task, 'torrent_peers', 0)} peers)"
            elif is_active:
                streams_txt = f"{streams_cnt} streams"
            elif task.status == DownloadStatus.COMPLETED:
                streams_txt = "Complete"
            else:
                streams_txt = task.status.value

            prog_val = 100.0 if (is_seeding or task.status == DownloadStatus.COMPLETED) else task.progress
            it_prog = SortableTableWidgetItem(streams_txt, prog_val)
            it_prog.setData(Qt.ItemDataRole.UserRole, {
                "progress": prog_val,
                "streams_text": streams_txt,
                "status": "Seeding" if is_seeding else task.status.value
            })
            self.table.setItem(row, 2, it_prog)

            # 3: Time left
            eta_val = 0 if task.status == DownloadStatus.COMPLETED else (task.eta if (is_active and task.eta) else 999999999)
            eta_str = "Seeding" if is_seeding else (format_eta(task.eta) if is_active else ("--" if task.status != DownloadStatus.COMPLETED else "Complete"))
            it_eta = SortableTableWidgetItem(eta_str, eta_val)
            it_eta.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            it_eta.setForeground(fg_active if is_active else fg_muted)
            self.table.setItem(row, 3, it_eta)

            # 4: Transfer rate (Soft chrome / metallic mint, not neon)
            if is_seeding:
                rate_val = task.upload_speed
                rate_str = f"▲ {format_bytes(task.upload_speed)}/s"
                it_rate = SortableTableWidgetItem(rate_str, rate_val)
                it_rate.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                it_rate.setForeground(QColor("#059669") if is_light else QColor("#86efac"))
                self.table.setItem(row, 4, it_rate)
            else:
                rate_val = task.speed if is_active else 0
                if task.is_torrent and is_active and task.upload_speed > 0:
                    rate_str = f"▼ {format_bytes(task.speed)}/s  ▲ {format_bytes(task.upload_speed)}/s"
                else:
                    rate_str = format_speed(task.speed) if is_active else "--"
                it_rate = SortableTableWidgetItem(rate_str, rate_val)
                it_rate.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                it_rate.setForeground(fg_primary if is_active else fg_muted)
                self.table.setItem(row, 4, it_rate)

            # 5: Last Try Date
            date_val = getattr(task, 'created_at', 0) or 0
            created_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(task.created_at)) if hasattr(task, 'created_at') and task.created_at else "--"
            it_date = SortableTableWidgetItem(created_str, date_val)
            it_date.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            it_date.setForeground(fg_muted)
            self.table.setItem(row, 5, it_date)

            # 6: Description (Empty by default, optional user note)
            desc_str = getattr(task, 'description', '') or ''
            it_desc = SortableTableWidgetItem(desc_str, desc_str.lower())
            it_desc.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            it_desc.setForeground(fg_primary if desc_str else fg_muted)
            self.table.setItem(row, 6, it_desc)

            # 7: Masa Seeding (1 - 31 Hari)
            is_torrent = (
                getattr(task, "is_torrent", False) or
                (task.category or "").lower() in ["torrents", "torrent"] or
                (task.url and (task.url.lower().startswith("magnet:") or ".torrent" in task.url.lower()))
            )

            seed_sort_val = 0
            if is_torrent:
                configured_days = 3
                if task.headers and "seed_duration_days" in task.headers:
                    try:
                        configured_days = int(task.headers["seed_duration_days"])
                    except Exception:
                        pass
                if is_seeding:
                    seed_str = f"Seeding ({configured_days} Hari)"
                    seed_col = QColor("#059669") if is_light else QColor("#10b981")
                elif task.status == DownloadStatus.COMPLETED:
                    seed_str = f"{configured_days} Hari (Selesai)"
                    seed_col = QColor("#059669") if is_light else QColor("#10b981")
                else:
                    seed_str = f"{configured_days} Hari"
                    seed_col = fg_primary
                seed_sort_val = configured_days
            else:
                seed_str = "--"
                seed_col = QColor("#94a3b8") if is_light else QColor("#475569")
                seed_sort_val = 0

            it_seed = SortableTableWidgetItem(seed_str, seed_sort_val)
            it_seed.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            it_seed.setForeground(seed_col)
            self.table.setItem(row, 7, it_seed)
            self.table.setRowHidden(row, not self._task_matches_filters(task))
        finally:
            if was_sorting:
                self.table.setSortingEnabled(True)

    def _find_row_by_id(self, task_id: str) -> int:
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                meta = it.data(Qt.ItemDataRole.UserRole)
                if isinstance(meta, dict) and meta.get("task_id") == task_id:
                    return r
        return -1

    def _get_selected_tasks(self) -> list[DownloadTask]:
        task_ids = []
        seen = set()

        # 1. Check selectedRows
        sel_model = self.table.selectionModel()
        if sel_model:
            for idx in sel_model.selectedRows():
                it = self.table.item(idx.row(), 0)
                if it:
                    meta = it.data(Qt.ItemDataRole.UserRole)
                    if isinstance(meta, dict):
                        tid = meta.get("task_id")
                        if tid and tid not in seen:
                            seen.add(tid)
                            task_ids.append(tid)

        # 2. Check selectedItems (in case of partial row selection)
        for it in self.table.selectedItems():
            item_0 = self.table.item(it.row(), 0)
            if item_0:
                meta = item_0.data(Qt.ItemDataRole.UserRole)
                if isinstance(meta, dict):
                    tid = meta.get("task_id")
                    if tid and tid not in seen:
                        seen.add(tid)
                        task_ids.append(tid)

        # 3. Fallback to currentRow
        if not task_ids:
            cr = self.table.currentRow()
            if cr >= 0:
                it = self.table.item(cr, 0)
                if it:
                    meta = it.data(Qt.ItemDataRole.UserRole)
                    if isinstance(meta, dict):
                        tid = meta.get("task_id")
                        if tid and tid not in seen:
                            seen.add(tid)
                            task_ids.append(tid)

        result = []
        for tid in task_ids:
            task = self.engine.tasks.get(tid)
            if task:
                result.append(task)
        return result

    def _get_selected_task(self) -> DownloadTask:
        tasks = self._get_selected_tasks()
        return tasks[0] if tasks else None

    def _on_table_selection_changed(self):
        selected_task = self._get_selected_task()
        if hasattr(self, 'drawer') and self.drawer:
            self.drawer.update_task(selected_task)

    def _update_all_telemetry(self):
        all_tasks = [t for t in self.engine.tasks.values() if not getattr(t, 'is_hidden', False) and t.id not in self._hidden_tasks]
        active_tasks = [t for t in all_tasks if t.status == DownloadStatus.DOWNLOADING]
        total_speed = sum(t.speed for t in active_tasks)

        # 1. Status Bar & Unified Bottom Drawer Telemetry
        if active_tasks:
            self.lbl_status_main.setText(f"Downloading {len(active_tasks)} file(s) ({format_speed(total_speed)})")
        else:
            self.lbl_status_main.setText("Ready")
        self.lbl_status_speed.setText(format_speed(total_speed))

        limiter_state = "ON" if self.speed_limiter.enabled else "Off"
        limit_val = f" ({format_speed(self.speed_limiter.max_bytes_per_sec)})" if self.speed_limiter.enabled else ""
        self.lbl_status_limiter.setText(f"Speed Limiter: {limiter_state}{limit_val}")

        if hasattr(self, "drawer") and self.drawer:
            limiter_btn_text = f"⚡ {format_speed(self.speed_limiter.max_bytes_per_sec)}" if self.speed_limiter.enabled else "⚡ Limiter: Off"
            self.drawer.set_limiter_status(limiter_btn_text, is_active=self.speed_limiter.enabled)
            if not getattr(self.drawer, "_current_task", None):
                if active_tasks:
                    self.drawer.lbl_file.setText(f"Downloading {len(active_tasks)} file(s)")
                    self.drawer.lbl_speed.setText(format_speed(total_speed))
                    self.drawer.dot.setStyleSheet("background-color: #86efac; border-radius: 3px;")
                else:
                    self.drawer.lbl_file.setText("All Queues Idle")
                    self.drawer.lbl_speed.setText("0.0 KB/s")
                    self.drawer.dot.setStyleSheet("background-color: #475569; border-radius: 3px;")

        # 2. Sidebar Badge Counts
        comp_cat = sum(1 for t in all_tasks if (t.category or "").lower() == "compressed")
        vid_cat = sum(1 for t in all_tasks if (t.category or "").lower() in ["video", "videos"])
        app_cat = sum(1 for t in all_tasks if (t.category or "").lower() in ["programs", "applications"])
        aud_cat = sum(1 for t in all_tasks if (t.category or "").lower() in ["music", "audio"])
        doc_cat = sum(1 for t in all_tasks if (t.category or "").lower() == "documents")
        tor_cat = sum(1 for t in all_tasks if getattr(t, "is_torrent", False) or (t.category or "").lower() in ["torrents", "torrent"])

        self.sidebar.update_counts({
            "ALL": len(all_tasks),
            "DOWNLOADING": len(active_tasks),
            "COMPLETED": sum(1 for t in all_tasks if t.status == DownloadStatus.COMPLETED),
            "PAUSED": sum(1 for t in all_tasks if t.status in [DownloadStatus.PAUSED, DownloadStatus.QUEUED, DownloadStatus.ERROR]),
            "CAT_Compressed": comp_cat,
            "CAT_Videos": vid_cat,
            "CAT_Applications": app_cat,
            "CAT_Audio": aud_cat,
            "CAT_Documents": doc_cat,
            "CAT_Torrents": tor_cat,
        })

        # 3. Speed Graph & Floating Widget
        self.speed_graph.add_speed(total_speed)
        self.floating_widget.update_stats(len(active_tasks), total_speed)

        selected_task = self._get_selected_task()
        target_task = None
        if selected_task:
            target_task = selected_task
        elif active_tasks:
            target_task = max(active_tasks, key=lambda t: t.speed)
        elif self.engine.tasks:
            visible_tasks = [t for t in self.engine.tasks.values() if not getattr(t, 'is_hidden', False) and t.id not in self._hidden_tasks]
            target_task = visible_tasks[-1] if visible_tasks else None

        self.drawer.update_task(target_task)

    def _toggle_active_download(self):
        task = self._get_selected_task()
        if not task:
            active_tasks = [t for t in self.engine.tasks.values() if t.status == DownloadStatus.DOWNLOADING and not getattr(t, 'is_hidden', False) and t.id not in self._hidden_tasks]
            if active_tasks:
                task = active_tasks[0]

        if task:
            if task.status == DownloadStatus.DOWNLOADING:
                self._pause_task(task)
            else:
                self._resume_task(task)

    def _on_task_updated(self, task: DownloadTask):
        if getattr(task, 'is_hidden', False) or task.id in self._hidden_tasks:
            return
        self._insert_or_update_row(task)
        self._update_all_telemetry()

    def _on_task_completed(self, task: DownloadTask):
        # 1. If this is a hidden companion audio task
        if getattr(task, 'is_hidden', False) or task.id in self._hidden_tasks:
            parent_id = None
            for v_id, a_id in self._dash_pairs.items():
                if a_id == task.id:
                    parent_id = v_id
                    break
            if parent_id:
                parent_task = self.engine.tasks.get(parent_id)
                if parent_task and parent_task.status == DownloadStatus.COMPLETED:
                    self._mux_dash_pair(parent_task, task)
            return

        self._insert_or_update_row(task)
        self._update_all_telemetry()

        # 2. If this is a video task with a companion audio
        companion_id = self._dash_pairs.get(task.id)
        if companion_id:
            companion_task = self.engine.tasks.get(companion_id)
            if companion_task:
                if companion_task.status == DownloadStatus.COMPLETED:
                    self._mux_dash_pair(task, companion_task)
                else:
                    self.tray.show_notification("Krolix Download Manager", f"Downloading audio for '{task.filename}'...")
                return

        # Close active progress dialog if open so Download Complete popup replaces it cleanly
        prog_dlg = self._active_dialogs.pop(task.id, None)
        if prog_dlg:
            try:
                prog_dlg.close()
            except Exception:
                pass

        self.tray.show_notification("Krolix Download Manager", f"'{task.filename}' has finished downloading.")
        if self.db.get_setting("show_complete_dialog", "true") != "false":
            self._show_completion_dialog(task)
        self._check_post_download_action(task)

    def _on_task_failed(self, task: DownloadTask, error_msg: str):
        self._insert_or_update_row(task)
        self._update_all_telemetry()
        err_clean = (error_msg or "Download failed").strip()
        self.tray.show_notification("Krolix Download Manager", f"Download failed for '{task.filename}': {err_clean}")

    def _show_completion_dialog(self, task: DownloadTask):
        try:
            if not hasattr(self, "_complete_dialogs") or self._complete_dialogs is None:
                self._complete_dialogs = {}
            from .complete_dialog import DownloadCompleteDialog
            dlg = DownloadCompleteDialog(task, db=self.db, parent=None)
            self._complete_dialogs[task.id] = dlg
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            try:
                from ..utils.win32_native import Win32Native
                Win32Native.force_foreground_window(int(dlg.winId()))
            except Exception:
                pass
        except Exception as e:
            print(f"[!] Error displaying completion dialog: {e}")

    def _mux_dash_pair(self, video_task: DownloadTask, audio_task: DownloadTask):
        v_path = video_task.save_path
        a_path = audio_task.save_path
        if not os.path.exists(v_path) or not os.path.exists(a_path):
            self.tray.show_notification("Krolix Download Manager", f"'{video_task.filename}' has finished downloading.")
            return

        self.tray.show_notification("Krolix Download Manager", f"Combining video and audio for '{video_task.filename}'...")

        def on_mux_success(final_path):
            def _handle_main():
                self.tray.show_notification("Krolix Download Manager", f"Full HD/4K Video '{video_task.filename}' is ready with sound!")
                try:
                    self.engine.delete_task(audio_task.id, delete_file=True)
                    self._hidden_tasks.discard(audio_task.id)
                    self._dash_pairs.pop(video_task.id, None)
                    self._update_all_telemetry()
                except Exception:
                    pass
                video_task.save_path = final_path
                self.signals.task_updated.emit(video_task)
                if self.db.get_setting("show_complete_dialog", "true") == "true":
                    self._show_completion_dialog(video_task)
            self.signals.run_on_main.emit(_handle_main)

        def on_mux_error(err):
            def _handle_err():
                print(f"[!] Mux error for {video_task.filename}: {err}")
                self.tray.show_notification("Krolix Download Manager", f"'{video_task.filename}' download complete.")
            self.signals.run_on_main.emit(_handle_err)

        AudioMuxer.mux_dash_pair_async(v_path, a_path, on_success=on_mux_success, on_error=on_mux_error)

    def _is_url_debounced(self, url: str, window_sec: float = 3.0) -> bool:
        clean_url = (url or "").strip().lower()
        if not clean_url:
            return False
        import time
        now = time.time()
        self._recent_urls = {u: t for u, t in self._recent_urls.items() if now - t < 30.0}
        last_time = self._recent_urls.get(clean_url, 0)
        if now - last_time < window_sec:
            return True
        self._recent_urls[clean_url] = now
        return False

    def _show_add_dialog(self, initial_url: str = ""):
        # Check if an AddDownloadDialog is already active on screen
        if self._current_add_dialog is not None and self._current_add_dialog.isVisible():
            try:
                self._current_add_dialog.raise_()
                self._current_add_dialog.activateWindow()
                from ..utils.win32_native import Win32Native
                Win32Native.force_foreground_window(int(self._current_add_dialog.winId()))
                if initial_url and hasattr(self._current_add_dialog, "txt_url"):
                    cur_txt = self._current_add_dialog.txt_url.text().strip()
                    if not cur_txt or cur_txt == "https://example.com/file.zip":
                        self._current_add_dialog.txt_url.setText(initial_url)
            except Exception:
                pass
            return

        from .add_dialog import AddDownloadDialog
        default_dir = self.db.get_setting("default_save_path", os.path.join(os.path.expanduser("~"), "Downloads"))
        dlg = AddDownloadDialog(self.engine, initial_url=initial_url, default_save_dir=default_dir, parent=self)
        dlg.mode_switch_requested.connect(self._handle_mode_switch)
        self._current_add_dialog = dlg
        dlg.raise_()
        dlg.activateWindow()
        try:
            from ..utils.win32_native import Win32Native
            Win32Native.force_foreground_window(int(dlg.winId()))
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, lambda: Win32Native.force_foreground_window(int(dlg.winId())))
        except Exception:
            pass
        try:
            if dlg.exec():
                task = dlg.result_task
                if task:
                    self._insert_or_update_row(task)
                    self._update_all_telemetry()
                    if dlg.start_immediately:
                        self.engine.start_download(task.id)
                        self._show_progress_dialog(task)
        finally:
            self._current_add_dialog = None

    def _handle_mode_switch(self, mode: str):
        """Switches to another download mode when requested from AddDownloadDialog."""
        if mode == "batch":
            self._show_batch_dialog()
        elif mode == "sniffer":
            self._show_batch_sniffer_dialog()
        elif mode == "ytdlp":
            self._show_ytdlp_dialog()
        elif mode == "grabber":
            self._show_site_grabber_dialog()

    def _show_add_torrent_dialog(self, initial_source: str = "", is_magnet: bool = False, headers: Optional[dict] = None):
        try:
            from .torrent_add_dialog import TorrentAddDialog
            default_dir = self.db.get_setting("default_save_path", os.path.join(os.path.expanduser("~"), "Downloads"))
            dlg = TorrentAddDialog(
                engine=self.engine,
                initial_source=initial_source,
                default_save_dir=default_dir,
                is_magnet=is_magnet,
                is_magnet_mode=is_magnet,
                headers=headers,
                parent=self
            )
            dlg.raise_()
            dlg.activateWindow()
            if dlg.exec():
                task = dlg.result_task
                if task:
                    self._insert_or_update_row(task)
                    self._update_all_telemetry()
                    if dlg.start_immediately:
                        self.engine.start_download(task.id)
                        self._show_progress_dialog(task)
        except Exception as e:
            QMessageBox.critical(self, "Torrent Error", f"Gagal membuka dialog Torrent: {e}")

    def _open_add_torrent_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih File BitTorrent (.torrent)",
            "",
            "Torrent Files (*.torrent);;All Files (*.*)"
        )
        if file_path:
            self._show_add_torrent_dialog(initial_source=file_path, is_magnet=False)

    def _open_add_magnet_dialog(self):
        clipboard_text = QApplication.clipboard().text().strip()
        initial_source = clipboard_text if clipboard_text.lower().startswith("magnet:") else ""
        self._show_add_torrent_dialog(initial_source=initial_source, is_magnet=True)

    def _prompt_add_url(self, url: str):
        clean_url = (url or "").strip()
        if not clean_url:
            return

        if self._is_url_debounced(clean_url, window_sec=3.0):
            print(f"[!] Ignoring duplicate debounced URL detection: {clean_url}")
            return

        url_lower = clean_url.lower()
        if any(url_lower.startswith(p) for p in ["blob:", "data:", "filesystem:", "chrome:", "chrome-extension:"]) or "streamsaver" in url_lower or "fetchv.net" in url_lower:
            print(f"[!] Ignoring internal browser virtual stream URL: {clean_url}")
            return

        if (url_lower.startswith("magnet:") or url_lower.endswith(".torrent")) and not self.db.is_torrent_enabled():
            print(f"[!] Ignoring torrent/magnet because BitTorrent is disabled: {clean_url}")
            return

        video_domains = [
            "youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "fb.watch",
            "twitter.com", "x.com", "bilibili.com", "vimeo.com", "twitch.tv", "dailymotion.com",
            "chaturbate.com", "stripchat.com"
        ]
        if any(domain in clean_url.lower() for domain in video_domains):
            self._show_media_dialog(default_url=clean_url)
        elif url_lower.startswith("magnet:") or ".torrent" in url_lower:
            self._show_add_torrent_dialog(initial_source=clean_url, is_magnet=url_lower.startswith("magnet:"))
        else:
            self._show_add_dialog(initial_url=clean_url)

    def _show_torrent_search_dialog(self, initial_query: str = ""):
        try:
            from .torrent_search_dialog import TorrentSearchDialog
            dlg = TorrentSearchDialog(self, initial_query=initial_query)
            dlg.download_requested.connect(lambda magnet: self._show_add_torrent_dialog(initial_source=magnet, is_magnet=True))
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Torrent Search Error", f"Failed to open Torrent Search: {e}")

    def _show_torrent_seeder_dialog(self):
        try:
            from .torrent_seeding_dialog import TorrentSeedingDialog
            dlg = TorrentSeedingDialog(engine=self.engine, parent=self)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "BitTorrent Seeding Error", f"Failed to open BitTorrent Seeding Dashboard: {e}")

    _show_torrent_spoofer_dialog = _show_torrent_seeder_dialog

    def _show_ytdlp_dialog(self, initial_url=""):
        from .ytdlp_dialog import YtdlpDialog
        dlg = YtdlpDialog(engine=self.engine, initial_url=initial_url, parent=self)
        dlg.exec()

    def _show_dht_search_dialog(self):
        from .dht_search_dialog import DHTSearchDialog
        dlg = DHTSearchDialog(parent=self)
        dlg.download_requested.connect(lambda mag: self._show_add_torrent_dialog(initial_source=mag, is_magnet=True))
        dlg.exec()

    def _on_toolbar_refresh_link(self):
        task = self._get_selected_task()
        if not task:
            unfinished = [
                t for t in self.engine.tasks.values()
                if t.status in (DownloadStatus.ERROR, DownloadStatus.PAUSED, DownloadStatus.DOWNLOADING, DownloadStatus.QUEUED)
            ]
            if len(unfinished) == 1:
                task = unfinished[0]
            elif len(unfinished) > 1:
                err_or_paused = [t for t in unfinished if t.status in (DownloadStatus.ERROR, DownloadStatus.PAUSED)]
                if len(err_or_paused) == 1:
                    task = err_or_paused[0]
                else:
                    target_list = err_or_paused if err_or_paused else unfinished
                    from PyQt6.QtWidgets import QInputDialog
                    items = [f"{t.filename} ({t.status.value})" for t in target_list]
                    item, ok = QInputDialog.getItem(
                        self, "Pilih Tugas Unduhan",
                        "Pilih unduhan yang ingin diperbarui alamatnya:",
                        items, 0, False
                    )
                    if ok and item:
                        idx = items.index(item)
                        task = target_list[idx]
                    else:
                        return
            else:
                QMessageBox.information(
                    self,
                    "Pilih Unduhan",
                    "Silakan pilih tugas unduhan dalam daftar yang ingin diperbarui tautannya terlebih dahulu."
                )
                return

        self._refresh_task_url(task)

    def _show_batch_sniffer_dialog(self, initial_text: str = ""):
        from ..core.license_manager import LicenseManager
        if not LicenseManager.get_instance(self.db).is_feature_allowed("batch_download"):
            from .nag_dialog import TrialExpiredNagDialog
            dlg = TrialExpiredNagDialog(locked_feature_name="Batch Sniffer Media", parent=self)
            dlg.exec()
            return
        from .batch_sniffer_dialog import BatchSnifferDialog
        dlg = BatchSnifferDialog(initial_text=initial_text, parent=self)
        dlg.links_submitted.connect(self._handle_batch_sniffer_links)
        dlg.exec()

    def _handle_batch_sniffer_links(self, items: list, save_dir: str, start_now: bool):
        from PyQt6.QtWidgets import QMessageBox
        added_count = 0
        for item in items:
            url = item.get("url")
            if not url:
                continue
            fn = item.get("filename") or "download.bin"
            try:
                task = self.engine.create_task(
                    url=url,
                    save_dir=save_dir,
                    filename=fn,
                    resumable=True
                )
                if start_now:
                    self.engine.start_download(task.id)
                added_count += 1
            except Exception as e:
                print(f"[!] Error adding sniffer task: {e}")

        self._populate_table()
        self.lbl_status_main.setText(f"Berhasil menambahkan {added_count} tugas dari Link Sniffer.")
        QMessageBox.information(
            self,
            "Link Ditambahkan",
            f"Berhasil menambahkan {added_count} tugas unduhan ke daftar{' dan langsung mengunduh' if start_now else ' (dalam antrean)'}."
        )

    def _handle_incoming_download(self, data: dict):
        try:
            url = (data.get("url") or "").strip()
            if not url:
                return

            # Resolve relative URLs using page_url or Referer header if needed
            if url.startswith("//"):
                url = "https:" + url
            elif not (url.startswith("http://") or url.startswith("https://") or url.startswith("magnet:") or url.startswith("ftp://")):
                base_page = (data.get("page_url") or data.get("pageUrl") or (data.get("headers") or {}).get("Referer") or "").strip()
                if base_page:
                    url = urllib.parse.urljoin(base_page, url)
                else:
                    print(f"[!] Warning: Cannot resolve relative URL without origin page: {url}")

            # Check if an active Refresh Download Address dialog is waiting for a new link
            active_refresher = getattr(DownloadEngine, "active_refresh_dialog", None)
            if active_refresher is None and hasattr(self, "engine"):
                active_refresher = getattr(self.engine, "active_refresh_dialog", None)

            if active_refresher is not None and hasattr(active_refresher, "isVisible") and active_refresher.isVisible():
                if hasattr(active_refresher, "handle_incoming_refreshed_download"):
                    data_resolved = dict(data)
                    data_resolved["url"] = url
                    if active_refresher.handle_incoming_refreshed_download(data_resolved):
                        print(f"[*] Incoming download consumed as refreshed link for task {active_refresher.task.id}")
                        return

            if self._is_url_debounced(url, window_sec=3.0):
                print(f"[!] Ignoring duplicate debounced incoming download: {url}")
                if self._current_add_dialog is not None and self._current_add_dialog.isVisible():
                    self._current_add_dialog.raise_()
                    self._current_add_dialog.activateWindow()
                return

            url_lower = url.lower()
            if any(url_lower.startswith(p) for p in ["blob:", "data:", "filesystem:", "chrome:", "chrome-extension:"]) or "streamsaver" in url_lower or "fetchv.net" in url_lower:
                print(f"[!] Ignoring internal browser virtual stream URL: {url}")
                return

            # Check if an AddDownloadDialog is ALREADY open
            if not data.get("silent", False) and self._current_add_dialog is not None and self._current_add_dialog.isVisible():
                print(f"[!] AddDownloadDialog is already active. Focusing existing dialog instead of creating duplicate.")
                try:
                    self._current_add_dialog.raise_()
                    self._current_add_dialog.activateWindow()
                    from ..utils.win32_native import Win32Native
                    Win32Native.force_foreground_window(int(self._current_add_dialog.winId()))
                except Exception:
                    pass
                return

            # Restore and bring window to front
            self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
            self.show()
            self.raise_()
            self.activateWindow()
            try:
                from ..utils.win32_native import Win32Native
                Win32Native.force_foreground_window(int(self.winId()))
            except Exception:
                pass

            if not data.get("silent", False) and (url_lower.startswith("magnet:") or ".torrent" in url_lower):
                self._show_add_torrent_dialog(initial_source=url, is_magnet=url_lower.startswith("magnet:"), headers=data.get("headers"))
                return

            is_media = data.get("is_media", False)
            video_domains = [
                "youtube.com", "youtu.be", "tiktok.com", "vimeo.com",
                "facebook.com", "instagram.com", "twitch.tv", "dailymotion.com",
                "twitter.com", "x.com", "bilibili.com", "chaturbate.com", "stripchat.com"
            ]
            is_video_platform = any(domain in url.lower() for domain in video_domains)

            if data.get("open_grabber") or (is_video_platform and not data.get("filename") and not data.get("filesize")):
                self._show_media_dialog(default_url=url)
            else:
                filename = data.get("filename", "")
                is_live = bool(data.get("is_live", False))
                is_hls = (
                    is_live or
                    data.get("is_hls", False) or 
                    ".m3u8" in url.lower() or 
                    ".mpd" in url.lower()
                )
                headers = dict(data.get("headers") or {}) if isinstance(data.get("headers"), dict) else {}
                if data.get("referer") and "Referer" not in headers:
                    headers["Referer"] = str(data["referer"])
                if data.get("user_agent") and "User-Agent" not in headers:
                    headers["User-Agent"] = str(data["user_agent"])
                if data.get("cookies") and "Cookie" not in headers:
                    headers["Cookie"] = str(data["cookies"])
                if data.get("masterUrl") or data.get("master_url"):
                    headers["master_url"] = data.get("masterUrl") or data.get("master_url")
                if data.get("fallbackUrls") or data.get("fallback_urls"):
                    fb = data.get("fallbackUrls") or data.get("fallback_urls")
                    headers["fallback_urls"] = fb if isinstance(fb, str) else "|||".join(fb)
                if data.get("pageUrl") or data.get("page_url"):
                    headers["page_url"] = data.get("pageUrl") or data.get("page_url")
                if data.get("m3u8Content") or data.get("m3u8_content") or headers.get("m3u8_content"):
                    m3u8_txt = data.get("m3u8Content") or data.get("m3u8_content") or headers.get("m3u8_content")
                    headers["m3u8_content"] = m3u8_txt
                    try:
                        from ..core.hls_downloader import HLSInspector
                        HLSInspector.cache_playlist(url, m3u8_txt)
                    except Exception:
                        pass
                from ..core.link_resolver import CloudLinkResolver
                url = CloudLinkResolver.resolve(url)
                headers = CloudLinkResolver.fix_headers(url, headers)
                if is_live:
                    headers["is_live"] = "true"

                if is_hls:
                    if not filename:
                        title = data.get("title") or ("Live_Stream" if is_live else "Video_Stream")
                        filename = f"{sanitize_filename(title)}.mp4"
                    elif not filename.lower().endswith(".mp4"):
                        base_fn, _ = os.path.splitext(filename)
                        filename = f"{base_fn}.mp4"
                    headers["is_hls"] = "true"

                if filename:
                    filename = sanitize_filename(filename)
                filesize = data.get("filesize", -1)
                default_dir = self.db.get_setting("default_save_path", os.path.join(os.path.expanduser("~"), "Downloads"))
                custom_dir = data.get("save_dir")
                effective_dir = custom_dir if (custom_dir and os.path.isdir(custom_dir)) else default_dir
                silent = bool(data.get("silent", False))
                queue_only = bool(data.get("queue_only", False))

                # API Silent Mode: Add and run/queue without prompting
                if silent:
                    task = self.engine.create_task(
                        url=url,
                        save_dir=effective_dir,
                        filename=filename if filename else None,
                        headers=headers,
                        description=data.get("description", "") or ""
                    )
                    self._insert_or_update_row(task)
                    self._update_all_telemetry()
                    if not queue_only:
                        self.engine.start_download(task.id)
                        self._show_progress_dialog(task)
                    return

                from .add_dialog import AddDownloadDialog
                variants_list = data.get("variants") or []
                initial_res = data.get("resolution") or (f"{data.get('height')}p" if data.get("height") else "")
                initial_bw = data.get("bitrate") or 0
                dlg = AddDownloadDialog(
                    self.engine,
                    initial_url=url,
                    default_save_dir=effective_dir,
                    parent=self,
                    initial_filename=filename,
                    initial_filesize=filesize,
                    initial_headers=headers,
                    skip_probe=True if (variants_list or (filesize > 0 and filename and not is_hls)) else False,
                    initial_resolution=initial_res,
                    initial_bitrate=initial_bw,
                    variants=variants_list,
                    initial_description=data.get("description", "") or ""
                )
                dlg.mode_switch_requested.connect(self._handle_mode_switch)
                self._current_add_dialog = dlg
                dlg.raise_()
                dlg.activateWindow()
                try:
                    from ..utils.win32_native import Win32Native
                    Win32Native.force_foreground_window(int(dlg.winId()))
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(50, lambda: Win32Native.force_foreground_window(int(dlg.winId())))
                except Exception:
                    pass

                try:
                    if dlg.exec():
                        task = dlg.result_task
                        if task:
                            self._insert_or_update_row(task)
                            self._update_all_telemetry()
                            if dlg.start_immediately:
                                self.engine.start_download(task.id)
                                self._show_progress_dialog(task)

                            # Handle companion audio for DASH streams (stored in temp, completely hidden from UI table)
                            companion_audio = data.get("companion_audio")
                            if companion_audio and companion_audio.get("url"):
                                try:
                                    temp_dir = os.path.join(os.path.expanduser("~"), ".krolix_download", "temp")
                                    os.makedirs(temp_dir, exist_ok=True)
                                    audio_ext = companion_audio.get("ext", "m4a")
                                    temp_audio_name = f"__dash_audio_{task.id}.{audio_ext}"
                                    audio_size = companion_audio.get("filesize") or companion_audio.get("total_bytes") or -1
                                    audio_task = self.engine.create_task(
                                        url=companion_audio["url"],
                                        save_dir=temp_dir,
                                        filename=temp_audio_name,
                                        headers=headers,
                                        total_bytes=audio_size if audio_size > 0 else None,
                                        resumable=True if audio_size > 0 else None
                                    )
                                    audio_task.is_hidden = True
                                    self._hidden_tasks.add(audio_task.id)
                                    self._dash_pairs[task.id] = audio_task.id
                                    self._dash_pairs[audio_task.id] = task.id
                                    # DO NOT add audio_task to UI table! Merged stream only displays primary task!
                                    if dlg.start_immediately:
                                        self.engine.start_download(audio_task.id)
                                except Exception as audio_err:
                                    print(f"[!] Warning: Failed to create companion audio task: {audio_err}")
                finally:
                    self._current_add_dialog = None
        except Exception as e:
            import traceback
            print(f"[!] Error in _handle_incoming_download: {e}")
            traceback.print_exc()

    def _show_progress_dialog(self, task: DownloadTask):
        from .progress_dialog import DownloadProgressDialog
        if task.id in self._active_dialogs:
            existing_dlg = self._active_dialogs[task.id]
            if existing_dlg is not None and hasattr(existing_dlg, "isVisible") and existing_dlg.isVisible():
                existing_dlg.raise_()
                existing_dlg.activateWindow()
                return
        dlg = DownloadProgressDialog(task, self.engine, parent=self)
        self._active_dialogs[task.id] = dlg
        dlg.show()

    def _resume_task(self, task: DownloadTask):
        if not task:
            return
        if task.status in [DownloadStatus.PAUSED, DownloadStatus.QUEUED, DownloadStatus.ERROR, DownloadStatus.CANCELED]:
            self.engine.start_download(task.id)
            if task.id in self._dash_pairs:
                self.engine.start_download(self._dash_pairs[task.id])
            self.lbl_status_main.setText(f"Melanjutkan unduhan: {task.filename}")
        elif task.status == DownloadStatus.COMPLETED:
            self.engine.start_download(task.id)
            self.lbl_status_main.setText(f"Mengunduh ulang: {task.filename}")
        else:
            self.lbl_status_main.setText(f"Unduhan '{task.filename}' sedang berstatus: {task.status.value}")

    def _pause_task(self, task: DownloadTask):
        if not task:
            return
        if task.status in [DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING]:
            self.engine.pause_download(task.id)
            if task.id in self._dash_pairs:
                self.engine.pause_download(self._dash_pairs[task.id])
            self.lbl_status_main.setText(f"Menjeda unduhan: {task.filename}")
        else:
            self.lbl_status_main.setText(f"Unduhan '{task.filename}' tidak sedang berjalan.")

    def _resume_selected(self):
        task = self._get_selected_task()
        if not task:
            # Fallback to first resumable task in list
            for t in self.engine.tasks.values():
                if t.status in [DownloadStatus.PAUSED, DownloadStatus.QUEUED, DownloadStatus.ERROR, DownloadStatus.CANCELED]:
                    task = t
                    break
        if task:
            self._resume_task(task)
        else:
            self.lbl_status_main.setText("Pilih unduhan di tabel terlebih dahulu untuk melanjutkan (Resume).")

    def _pause_selected(self):
        task = self._get_selected_task()
        if not task:
            # Fallback to first active downloading task
            for t in self.engine.tasks.values():
                if t.status in [DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING]:
                    task = t
                    break
        if task:
            self._pause_task(task)
        else:
            self.lbl_status_main.setText("Pilih unduhan aktif di tabel untuk dijeda (Pause).")

    def _stop_all(self):
        stopped = 0
        for task in self.engine.tasks.values():
            if task.status in [DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING]:
                self.engine.pause_download(task.id)
                stopped += 1
        if stopped > 0:
            self.lbl_status_main.setText(f"Menghentikan {stopped} unduhan aktif.")
        else:
            self.lbl_status_main.setText("Tidak ada unduhan aktif yang sedang berjalan.")

    def _resume_all(self):
        resumed = 0
        for task in self.engine.tasks.values():
            if task.status in [DownloadStatus.PAUSED, DownloadStatus.QUEUED, DownloadStatus.ERROR, DownloadStatus.CANCELED]:
                self.engine.start_download(task.id)
                resumed += 1
        if resumed > 0:
            self.lbl_status_main.setText(f"Melanjutkan {resumed} unduhan.")
        else:
            self.lbl_status_main.setText("Tidak ada unduhan yang dapat dilanjutkan.")

    def _redownload_selected(self):
        task = self._get_selected_task()
        if not task:
            for t in self.engine.tasks.values():
                if t.status in [DownloadStatus.COMPLETED, DownloadStatus.ERROR, DownloadStatus.CANCELED]:
                    task = t
                    break
        if task:
            if task.status == DownloadStatus.COMPLETED:
                self.engine.redownload_task(task.id)
            else:
                self._resume_task(task)
            msg = f"Mengunduh ulang: {task.filename}"
            self.lbl_status_main.setText(msg)
            if hasattr(self, "drawer") and self.drawer:
                self.drawer.show_status_message(msg)
        else:
            msg = "Pilih unduhan di tabel untuk diunduh ulang."
            self.lbl_status_main.setText(msg)
            if hasattr(self, "drawer") and self.drawer:
                self.drawer.show_status_message(msg)

    def _delete_selected(self, delete_files: bool = False):
        tasks = self._get_selected_tasks()
        if not tasks:
            t = self._get_selected_task()
            if t:
                tasks = [t]
        if tasks:
            self._delete_tasks(tasks, delete_files=delete_files)
        else:
            all_tasks = [t for t in self.engine.tasks.values() if not getattr(t, 'is_hidden', False) and t.id not in self._hidden_tasks]
            if not all_tasks:
                QMessageBox.information(self, "Delete", "Daftar unduhan kosong.")
            elif len(all_tasks) == 1:
                self._delete_tasks(all_tasks, delete_files=delete_files)
            else:
                reply = QMessageBox.question(
                    self,
                    "Delete Downloads",
                    f"Tidak ada baris unduhan yang dipilih secara spesifik di tabel.\n\nApakah Anda ingin menghapus SEMUA ({len(all_tasks)}) unduhan dari daftar?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._delete_all_tasks(delete_files=delete_files)

    def _confirm_delete_dialog(self, title: str, msg: str, default_delete_files: bool = False, show_disk_checkbox: bool = True) -> tuple[bool, bool]:
        """
        Shows a dark-themed confirmation dialog with:
        - 'Also delete downloaded file(s) from hard disk' checkbox
        - 'Don't show this dialog box again' checkbox
        Returns (confirmed: bool, delete_files: bool).
        """
        skip_confirm = str(self.db.get_setting("skip_delete_confirm", "false")).lower() in ("true", "1")
        if skip_confirm and not default_delete_files:
            return True, False

        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setFixedWidth(450)
        apply_windows_dark_titlebar(dlg)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #000000;
                color: #ffffff;
            }
            QLabel {
                color: #e2e8f0;
                font-size: 12px;
            }
            QCheckBox {
                color: #cbd5e1;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #27272a;
                background-color: #09090b;
            }
            QCheckBox::indicator:checked {
                background-color: #10b981;
                border-color: #10b981;
            }
            QPushButton {
                background-color: #0f0f11;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 6px 18px;
                color: #f1f5f9;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1c1c1f;
                border-color: #38bdf8;
            }
            QPushButton#yesBtn {
                background-color: #ef4444;
                border-color: #ef4444;
                color: #ffffff;
            }
            QPushButton#yesBtn:hover {
                background-color: #dc2626;
                border-color: #dc2626;
            }
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        lbl_msg = QLabel(msg)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("font-size: 13px; font-weight: 500; color: #f8fafc;")
        layout.addWidget(lbl_msg)

        chk_disk = QCheckBox("Also delete downloaded file(s) from hard disk")
        chk_disk.setChecked(default_delete_files)
        if show_disk_checkbox:
            layout.addWidget(chk_disk)

        chk_dont_show = QCheckBox("Don't show this dialog box again")
        chk_dont_show.setChecked(False)
        layout.addWidget(chk_dont_show)

        layout.addSpacing(4)
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_yes = QPushButton("Yes")
        btn_yes.setObjectName("yesBtn")
        btn_yes.setDefault(True)
        btn_yes.clicked.connect(dlg.accept)

        btn_no = QPushButton("No")
        btn_no.clicked.connect(dlg.reject)

        btn_row.addWidget(btn_yes)
        btn_row.addWidget(btn_no)
        layout.addLayout(btn_row)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            if chk_dont_show.isChecked():
                self.db.set_setting("skip_delete_confirm", "true")
            return True, (chk_disk.isChecked() if show_disk_checkbox else default_delete_files)
        return False, False

    def _delete_tasks(self, tasks: list[DownloadTask], delete_files: bool = False):
        if not tasks:
            return

        names = ", ".join([f"'{t.filename}'" for t in tasks[:3]])
        if len(tasks) > 3:
            names += f" and {len(tasks) - 3} other file(s)"

        title = "Delete Download" if len(tasks) == 1 else "Delete Downloads"
        msg = f"Are you sure you want to delete {names} from the download list?"

        confirmed, del_disk = self._confirm_delete_dialog(
            title=title,
            msg=msg,
            default_delete_files=delete_files,
            show_disk_checkbox=True
        )
        if confirmed:
            for t in tasks:
                self.engine.delete_task(t.id, delete_file=del_disk)
            self._populate_table()
            self._update_all_telemetry()
            self.lbl_status_main.setText(f"Dihapus {len(tasks)} unduhan dari daftar.")

    def _delete_all_completed(self):
        completed_tasks = [t for t in self.engine.tasks.values() if t.status == DownloadStatus.COMPLETED and not getattr(t, 'is_hidden', False)]
        if not completed_tasks:
            all_tasks = [t for t in self.engine.tasks.values() if not getattr(t, 'is_hidden', False) and t.id not in self._hidden_tasks]
            if not all_tasks:
                QMessageBox.information(self, "Delete Completed", "Tidak ada unduhan di dalam daftar.")
                return
            reply = QMessageBox.question(
                self,
                "Delete Downloads",
                f"Tidak ada unduhan berstatus 'Selesai' (Completed).\n\nApakah Anda ingin menghapus SEMUA {len(all_tasks)} unduhan yang ada di daftar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._delete_all_tasks()
            return

        confirmed, del_disk = self._confirm_delete_dialog(
            title="Delete Completed Downloads",
            msg=f"Are you sure you want to remove all {len(completed_tasks)} completed downloads from the list?",
            default_delete_files=False,
            show_disk_checkbox=True
        )
        if confirmed:
            for task in completed_tasks:
                self.engine.delete_task(task.id, delete_file=del_disk)
            self._populate_table()
            self._update_all_telemetry()
            self.lbl_status_main.setText(f"Menghapus {len(completed_tasks)} unduhan selesai.")

    def _delete_all_tasks(self, delete_files: bool = False):
        all_tasks = [t for t in self.engine.tasks.values() if not getattr(t, 'is_hidden', False) and t.id not in self._hidden_tasks]
        if not all_tasks:
            QMessageBox.information(self, "Delete All", "Daftar unduhan kosong.")
            return

        confirmed, del_disk = self._confirm_delete_dialog(
            title="Delete All Downloads",
            msg=f"Apakah Anda yakin ingin menghapus SEMUA {len(all_tasks)} unduhan dari daftar?",
            default_delete_files=delete_files,
            show_disk_checkbox=True
        )
        if confirmed:
            for t in all_tasks:
                self.engine.delete_task(t.id, delete_file=del_disk)
            self._populate_table()
            self._update_all_telemetry()
            self.lbl_status_main.setText(f"Dihapus {len(all_tasks)} unduhan dari daftar.")

    def _on_del_btn_context_menu(self, pos):
        menu = QMenu(self)
        act_sel = menu.addAction("Delete Selected Download(s)")
        act_sel.triggered.connect(lambda: self._delete_selected(delete_files=False))
        act_sel_files = menu.addAction("Delete Selected + Files on Disk")
        act_sel_files.triggered.connect(lambda: self._delete_selected(delete_files=True))
        menu.addSeparator()
        act_all = menu.addAction("Delete All Downloads...")
        act_all.triggered.connect(lambda: self._delete_all_tasks(delete_files=False))
        menu.exec(self.command_bar.btn_delete.mapToGlobal(pos))

    def _on_del_comp_context_menu(self, pos):
        menu = QMenu(self)
        act_comp = menu.addAction("Delete Completed Downloads")
        act_comp.triggered.connect(self._delete_all_completed)
        menu.addSeparator()
        act_all = menu.addAction("Delete All Downloads...")
        act_all.triggered.connect(lambda: self._delete_all_tasks(delete_files=False))
        menu.exec(self.command_bar.btn_del_comp.mapToGlobal(pos))

    def _preview_selected_media(self):
        task = self._get_selected_task()
        if not task:
            self.lbl_status_main.setText("Pilih file video/audio di tabel terlebih dahulu untuk pratinjau (Preview).")
            return
        self._preview_media_task(task)

    def _preview_media_task(self, task: DownloadTask):
        """Launches instant preview for completed or actively downloading video/audio files."""
        candidates = []
        if task.save_path:
            candidates.append(task.save_path)
            candidates.append(task.save_path + ".part")
            candidates.append(task.save_path + ".tmp")
            # Also check HLS temp folder if downloading HLS stream
            base_dir = os.path.dirname(task.save_path)
            hls_temp = os.path.join(base_dir, f".hls_tmp_{task.id}")
            if os.path.isdir(hls_temp):
                try:
                    seg_files = sorted(
                        [os.path.join(hls_temp, f) for f in os.listdir(hls_temp) if f.endswith((".ts", ".mp4", ".m4s"))],
                        key=lambda p: os.path.getmtime(p)
                    )
                    if seg_files:
                        candidates.extend(seg_files[-3:])
                except Exception:
                    pass

        for path in candidates:
            if path and os.path.exists(path) and os.path.getsize(path) > 0:
                try:
                    os.startfile(path)
                    self.lbl_status_main.setText(f"▶ Membuka pratinjau media: {os.path.basename(path)}")
                    return
                except Exception as e:
                    QMessageBox.warning(self, "Preview Media", f"Gagal membuka media player:\n{e}")
                    return

        QMessageBox.information(
            self,
            "Preview Media",
            f"Data pratinjau untuk '{task.filename}' belum tersedia di disk."
        )

    def _fix_video_seek_task(self, task: DownloadTask):
        """Repairs broken PTS/DTS timestamps, MPEG-TS-in-MP4 containers, and faststart seek index."""
        if not task or not task.save_path or not os.path.exists(task.save_path):
            QMessageBox.warning(self, "Fix Video Seek", "File video tidak ditemukan di disk.")
            return

        self.lbl_status_main.setText(f"Memperbaiki indeks seek & container: {task.filename}...")
        QApplication.processEvents()

        from ..core.hls_downloader import HLSWorker
        ok = HLSWorker.fix_media_seek_and_container(task.save_path)
        if ok:
            try:
                new_sz = os.path.getsize(task.save_path)
                task.downloaded_bytes = new_sz
                task.total_bytes = new_sz
                self.db.save_task(task)
                self._insert_or_update_row(task)
            except Exception:
                pass
            self.lbl_status_main.setText(f"Berhasil memperbaiki seek & container: {task.filename}")
            QMessageBox.information(
                self,
                "Universal M3U8/MP4 Seek Fixer",
                f"Berhasil memperbaiki indeks seek, PTS/DTS timestamp, dan container faststart (0% penurunan kualitas):\n\n{task.save_path}"
            )
        else:
            self.lbl_status_main.setText(f"Gagal memperbaiki seek video: {task.filename}")
            QMessageBox.warning(
                self,
                "Universal M3U8/MP4 Seek Fixer",
                f"Gagal memproses remuxing pada file:\n{task.save_path}"
            )

    def _rename_selected_task(self):
        task = self._get_selected_task()
        if not task:
            self.lbl_status_main.setText("Pilih unduhan di tabel terlebih dahulu untuk mengubah nama file.")
            return
        self._rename_task_file(task)

    def _rename_task_file(self, task: DownloadTask):
        if task.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING):
            QMessageBox.warning(
                self,
                "Rename Error",
                "Tidak dapat mengubah nama file saat proses unduhan sedang berlangsung.\n"
                "Silakan jeda (pause) unduhan terlebih dahulu sebelum mengubah nama file."
            )
            return

        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Download File",
            "Masukkan nama file baru:",
            text=task.filename
        )
        if not ok or not new_name.strip() or new_name.strip() == task.filename:
            return
        clean_name = new_name.strip()
        for ch in '<>:"/\\|?*':
            clean_name = clean_name.replace(ch, "_")

        old_path = task.save_path
        save_dir = os.path.dirname(old_path) if old_path else self.db.get_setting("default_save_path", "")
        new_path = os.path.join(save_dir, clean_name)

        if old_path and os.path.exists(old_path) and old_path != new_path:
            try:
                os.rename(old_path, new_path)
            except Exception as e:
                QMessageBox.warning(self, "Rename Error", f"Tidak dapat mengubah nama file di disk:\n{e}")
                return

        task.filename = clean_name
        task.save_path = new_path
        self.db.save_task(task)
        self._insert_or_update_row(task)
        self.lbl_status_main.setText(f"Nama file diubah menjadi: {clean_name}")

    def _edit_task_description(self, task: DownloadTask):
        """Allows user to edit optional description or note for a task."""
        from PyQt6.QtWidgets import QInputDialog
        cur_desc = getattr(task, "description", "") or ""
        new_desc, ok = QInputDialog.getText(
            self,
            "Edit Description",
            f"Deskripsi / Catatan opsional untuk file:\n{task.filename}",
            text=cur_desc
        )
        if ok:
            task.description = new_desc.strip()
            self.db.save_task(task)
            self._insert_or_update_row(task)
            self.lbl_status_main.setText(f"Deskripsi diperbarui untuk: {task.filename}")

    def _clean_missing_files(self):
        """Removes completed tasks from the list if their file on disk no longer exists."""
        missing_tasks = [
            t for t in self.engine.tasks.values()
            if t.status == DownloadStatus.COMPLETED and t.save_path and not os.path.exists(t.save_path)
        ]
        if not missing_tasks:
            QMessageBox.information(
                self,
                "Clean Missing Files",
                "Semua file unduhan yang selesai masih ada di disk (tidak ditemukan file hilang)."
            )
            return
        for t in missing_tasks:
            self.engine.delete_task(t.id, delete_file=False)
        self._populate_table()
        self._update_all_telemetry()
        self.lbl_status_main.setText(f"Dibersihkan {len(missing_tasks)} entri file yang sudah tidak ada di disk.")

    def _set_post_download_action(self, action_val: str):
        self.db.set_setting("post_download_action", action_val)
        if hasattr(self, "_post_action_group"):
            for act, val in self._post_action_group:
                act.setChecked(val == action_val)
        labels = {
            "none": "Tidak ada aksi khusus",
            "beep": "Bunyikan notifikasi suara",
            "open_folder": "Buka folder unduhan otomatis",
            "sleep": "Mode Sleep komputer",
            "shutdown": "Matikan komputer (Shutdown)"
        }
        self.lbl_status_main.setText(f"Aksi setelah semua unduhan selesai: {labels.get(action_val, action_val)}")

    def _check_post_download_action(self, last_completed_task: DownloadTask):
        action_val = self.db.get_setting("post_download_action", "none")
        if not action_val or action_val == "none":
            return
        # Check if any other task is still downloading or connecting or queued
        active_remaining = [
            t for t in self.engine.tasks.values()
            if t.id != last_completed_task.id and t.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING, DownloadStatus.QUEUED)
        ]
        if active_remaining:
            return
        if action_val == "beep":
            QApplication.beep()
        elif action_val == "open_folder" and last_completed_task.save_path and os.path.exists(last_completed_task.save_path):
            subprocess.Popen(["explorer", f"/select,{os.path.abspath(last_completed_task.save_path)}"])
        elif action_val == "sleep":
            self.db.set_setting("post_download_action", "none")
            PostActionManager.execute("sleep")
        elif action_val == "shutdown":
            self.db.set_setting("post_download_action", "none")
            PostActionManager.execute("shutdown")
        elif action_val == "hibernate":
            self.db.set_setting("post_download_action", "none")
            PostActionManager.execute("hibernate")
        elif action_val == "restart":
            self.db.set_setting("post_download_action", "none")
            PostActionManager.execute("restart")

    def _show_settings(self):
        from .settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.db, self.speed_limiter, parent=self)
        if dlg.exec():
            is_enabled = self.db.get_setting("monitor_clipboard", "true") == "true"
            self.clip_monitor.enabled = is_enabled
            self.sidebar.update_torrent_visibility(self.db.is_torrent_enabled())
            if hasattr(self, 'act_limiter_toggle'):
                self.act_limiter_toggle.setChecked(self.speed_limiter.enabled)
            _theme = self.db.get_setting('ui_theme', 'mica_dark')
            _accent = self.db.get_setting('ui_accent', 'chrome')
            if _accent in ('chrome', 'cyan', 'emerald', 'violet', 'amber', 'rose', 'sky', 'default'):
                _accent = 'chrome'
            self.apply_theme(_theme, _accent)
            self._update_all_telemetry()


    def _toggle_limiter_menu(self, checked: bool):
        self.speed_limiter.set_enabled(checked)
        self.db.set_setting("limiter_enabled", "true" if checked else "false")
        self._update_all_telemetry()

    def _on_item_double_clicked(self, item):
        row = item.row()
        it = self.table.item(row, 0)
        if not it:
            return
        meta = it.data(Qt.ItemDataRole.UserRole)
        if not isinstance(meta, dict):
            return
        task = self.engine.tasks.get(meta.get("task_id"))
        if not task:
            return


        # Double clicking column 6 ("Description") allows editing description
        if item.column() == 6:
            self._edit_task_description(task)
            return

        # Double clicking column 7 ("Masa Seeding") allows quickly editing seeding days
        if item.column() == 7:
            is_torrent = (
                getattr(task, "is_torrent", False) or
                (task.category or "").lower() in ["torrents", "torrent"] or
                (task.url and (task.url.lower().startswith("magnet:") or ".torrent" in task.url.lower())) or
                False
            )
            if is_torrent:
                self._change_torrent_seed_days(task)
                return

        if task.status == DownloadStatus.COMPLETED and task.save_path and os.path.exists(task.save_path):
            os.startfile(task.save_path)
        else:
            self._show_progress_dialog(task)

    def _change_torrent_seed_days(self, task: DownloadTask):
        cur_days = 3
        if task.headers and "seed_duration_days" in task.headers:
            try:
                cur_days = int(task.headers["seed_duration_days"])
            except Exception:
                pass
        # Read configured days

        new_days, ok = QInputDialog.getInt(
            self,
            "Masa Seeding BitTorrent",
            f"Tentukan batas durasi seeding (hari) untuk:\n{task.filename}\n\n(Jika target rasio tercapai sebelum masa seeding habis, upload di-throttle ke 0 B/s)",
            value=cur_days,
            min=1,
            max=31,
            step=1
        )
        if ok:
            if not task.headers:
                task.headers = {}
            task.headers["seed_duration_days"] = new_days
            self.db.save_task(task)
            if self.engine and task.id in getattr(self.engine, "torrent_workers", {}):
                self.engine.torrent_workers[task.id].seed_duration_days = new_days
            self._insert_or_update_row(task)
            self.lbl_status_main.setText(f"Masa seeding untuk '{task.filename}' diatur ke {new_days} hari.")

    def _show_context_menu(self, pos):
        task = self._get_selected_task()
        if not task:
            menu = QMenu(self)
            act_del_comp = menu.addAction("Delete Completed Downloads")
            act_del_comp.triggered.connect(self._delete_all_completed)
            act_del_all = menu.addAction("Delete All Downloads...")
            act_del_all.triggered.connect(lambda: self._delete_all_tasks(delete_files=False))
            menu.exec(self.table.viewport().mapToGlobal(pos))
            return

        menu = QMenu(self)
        if task.status == DownloadStatus.COMPLETED:
            act_open = menu.addAction("Open File")
            act_open.triggered.connect(lambda: os.startfile(task.save_path) if (task.save_path and os.path.exists(task.save_path)) else None)

            act_folder = menu.addAction("Open Folder")
            act_folder.triggered.connect(lambda: subprocess.Popen(["explorer", f"/select,{os.path.abspath(task.save_path)}"]) if (task.save_path and os.path.exists(task.save_path)) else None)

            act_hash = menu.addAction("Verify Checksum / Hash...")
            def _open_hash():
                from .hash_dialog import HashDialog
                if task.save_path and os.path.exists(task.save_path):
                    HashDialog(task.save_path, parent=self).exec()
            act_hash.triggered.connect(_open_hash)

            if task.save_path and ArchiveExtractor.is_archive(task.save_path):
                act_ext = menu.addAction("Extract Archive Here...")
                act_ext.triggered.connect(lambda: self._extract_archive(task.save_path))

            menu.addSeparator()

        act_preview = menu.addAction("Preview / Play Media")
        act_preview.triggered.connect(lambda: self._preview_media_task(task))

        if task.save_path and os.path.exists(task.save_path) and task.save_path.lower().endswith((".mp4", ".mkv", ".ts", ".webm")):
            act_fix_seek = menu.addAction("Fix Video Seek / Container (M3U8 -> MP4/MKV)")
            act_fix_seek.triggered.connect(lambda: self._fix_video_seek_task(task))

        hdrs = task.headers or {}
        watch_candidate = hdrs.get("Referer") or hdrs.get("page_url") or (task.url if any(k in (task.url or "").lower() for k in ("chaturbate", "stripchat", "twitch.tv", "youtube.com", "kick.com", ".m3u8")) else "")
        if watch_candidate:
            act_watch = menu.addAction(fluent_icons.create_fluent_live_icon("#f43f5e"), "Pantau Channel di Live Watchlist...")
            act_watch.triggered.connect(lambda _c=False, u=watch_candidate: self._add_task_to_watchlist(u))

        act_rename = menu.addAction("Rename File...")
        act_rename.triggered.connect(lambda: self._rename_task_file(task))

        act_desc = menu.addAction("Edit Description...")
        act_desc.triggered.connect(lambda: self._edit_task_description(task))

        is_torrent = (
            getattr(task, "is_torrent", False) or
            (task.category or "").lower() in ["torrents", "torrent"] or
            (task.url and (task.url.lower().startswith("magnet:") or ".torrent" in task.url.lower())) or
            False
        )
        if is_torrent:
            act_seed_days = menu.addAction("Atur Masa Seeding (1-31 Hari)...")
            act_seed_days.triggered.connect(lambda: self._change_torrent_seed_days(task))

        menu.addSeparator()

        if task.status == DownloadStatus.DOWNLOADING:
            act_pause = menu.addAction("Pause")
            act_pause.triggered.connect(lambda: self._pause_task(task))
        elif task.status in [DownloadStatus.PAUSED, DownloadStatus.QUEUED, DownloadStatus.ERROR]:
            act_resume = menu.addAction("Resume / Retry")
            act_resume.triggered.connect(lambda: self._resume_task(task))

        if task.status != DownloadStatus.COMPLETED:
            act_refresh = menu.addAction("Perbarui Alamat Unduhan... (Refresh Download Address)")
            act_refresh.setShortcut(QKeySequence("Ctrl+U"))
            act_refresh.triggered.connect(lambda: self._refresh_task_url(task))

        menu.addSeparator()
        act_up = menu.addAction("Move Up in Queue")
        act_up.triggered.connect(lambda: self._move_queue(task, -1))
        act_down = menu.addAction("Move Down in Queue")
        act_down.triggered.connect(lambda: self._move_queue(task, 1))

        menu.addSeparator()
        act_copy = menu.addAction("Copy Download Link")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(task.url))

        selected_tasks = self._get_selected_tasks()
        target_tasks = selected_tasks if selected_tasks else [task]

        act_del = menu.addAction("Delete from List")
        act_del.triggered.connect(lambda: self._delete_tasks(target_tasks, delete_files=False))

        act_del_file = menu.addAction("Delete File and List")
        act_del_file.triggered.connect(lambda: self._delete_tasks(target_tasks, delete_files=True))

        menu.addSeparator()
        act_del_comp = menu.addAction("Delete Completed Downloads")
        act_del_comp.triggered.connect(self._delete_all_completed)

        act_del_all = menu.addAction("Delete All Downloads...")
        act_del_all.triggered.connect(lambda: self._delete_all_tasks(delete_files=False))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _extract_archive(self, file_path: str):
        success, res = ArchiveExtractor.extract(file_path)
        if success:
            QMessageBox.information(self, "Extraction Complete", f"Extracted to:\n{res}")
        else:
            QMessageBox.warning(self, "Extraction Failed", f"Error: {res}")

    def _verify_selected_hash(self):
        task = self._get_selected_task()
        if task and task.save_path and os.path.exists(task.save_path):
            from .hash_dialog import HashDialog
            HashDialog(task.save_path, parent=self).exec()
        else:
            QMessageBox.information(self, "Verify Checksum", "Please select a downloaded file first.")

    def _extract_selected_archive(self):
        task = self._get_selected_task()
        if task and task.save_path and os.path.exists(task.save_path):
            self._extract_archive(task.save_path)
        else:
            QMessageBox.information(self, "Extract Archive", "Please select an archive download first.")

    def _move_queue(self, task: DownloadTask, delta: int):
        task.queue_order += delta
        self.db.save_task(task)
        self._populate_table()

    def _toggle_floating_widget(self):
        if self.floating_widget.isVisible():
            self.floating_widget.hide()
        else:
            self.floating_widget.show()

    def _show_batch_dialog(self, initial_urls=None, initial_items=None):
        from ..core.license_manager import LicenseManager
        if not LicenseManager.get_instance(self.db).is_feature_allowed("batch_download"):
            from .nag_dialog import TrialExpiredNagDialog
            dlg = TrialExpiredNagDialog(locked_feature_name="Batch Download", parent=self)
            dlg.exec()
            return
        from .batch_dialog import BatchDialog
        default_dir = self.db.get_setting("default_save_path", os.path.join(os.path.expanduser("~"), "Downloads"))
        dlg = BatchDialog(initial_urls=initial_urls, initial_items=initial_items, default_save_dir=default_dir, parent=self)
        if dlg.exec():
            selected_items = dlg.get_selected_items()
            count = 0
            for it in selected_items:
                url = it.get("url")
                if not url:
                    continue
                save_path = it.get("save_path")
                save_dir = os.path.dirname(save_path) if save_path else default_dir
                fn = it.get("filename")
                task = self.engine.create_task(url=url, save_dir=save_dir, filename=fn)
                self._insert_or_update_row(task)
                self.engine.start_download(task.id)
                count += 1
            self._update_all_telemetry()
            if count > 0:
                self.statusBar().showMessage(f"Memulai {count} unduhan massal...", 4000)

    def _batch_from_clipboard(self):
        clip_text = QApplication.clipboard().text()
        if not clip_text:
            QMessageBox.information(self, "Unduh Massal", "Papan klip (clipboard) kosong.")
            return
        lines = [line.strip() for line in clip_text.splitlines() if line.strip()]
        self._show_batch_dialog(initial_urls=lines)

    def _handle_incoming_batch_download(self, data: dict):
        items = data.get("items", [])
        if data.get("silent") or data.get("queue_only"):
            default_dir = self.db.get_setting("default_save_path", os.path.join(os.path.expanduser("~"), "Downloads"))
            custom_dir = data.get("save_dir")
            save_dir = custom_dir if (custom_dir and os.path.isdir(custom_dir)) else default_dir
            queue_only = bool(data.get("queue_only"))
            base_headers = {}
            if data.get("referer"):
                base_headers["Referer"] = str(data["referer"])
            if data.get("user_agent"):
                base_headers["User-Agent"] = str(data["user_agent"])
            if data.get("cookies"):
                base_headers["Cookie"] = str(data["cookies"])

            count = 0
            for it in items:
                url = it.get("url") if isinstance(it, dict) else str(it)
                if not url:
                    continue
                fn = it.get("filename") if isinstance(it, dict) else None
                desc = (it.get("description", "") or "") if isinstance(it, dict) else ""
                item_headers = dict(base_headers)
                if isinstance(it, dict) and isinstance(it.get("headers"), dict):
                    item_headers.update(it["headers"])
                task = self.engine.create_task(
                    url=url,
                    save_dir=save_dir,
                    filename=fn if fn else None,
                    headers=item_headers or None,
                    description=desc
                )
                self._insert_or_update_row(task)
                if not queue_only:
                    self.engine.start_download(task.id)
                count += 1
            self._update_all_telemetry()
        else:
            self._restore_from_tray()
            self._show_batch_dialog(initial_items=items)

    def _export_downloads(self):
        path, sel_filter = QFileDialog.getSaveFileName(
            self,
            "Ekspor Daftar Unduhan - Krolix",
            "Krolix_Downloads.ef2",
            "Krolix Export Format (*.ef2);;Text File (*.txt);;Semua Berkas (*.*)"
        )
        if not path:
            return

        tasks = list(self.engine.tasks.values())
        if not tasks:
            QMessageBox.information(self, "Ekspor", "Tidak ada unduhan untuk diekspor.")
            return

        is_ef2 = path.lower().endswith(".ef2") or "ef2" in sel_filter.lower()
        try:
            with open(path, "w", encoding="utf-8") as f:
                if is_ef2:
                    for t in tasks:
                        f.write("<\n")
                        f.write(f"{t.url}\n")
                        if t.filename:
                            f.write(f"file={t.filename}\n")
                        if t.save_path:
                            f.write(f"path={os.path.dirname(t.save_path)}\n")
                        if hasattr(t, 'headers') and isinstance(t.headers, dict):
                            if t.headers.get("referer"):
                                f.write(f"referer={t.headers['referer']}\n")
                            if t.headers.get("cookie"):
                                f.write(f"cookies={t.headers['cookie']}\n")
                        f.write(">\n")
                else:
                    for t in tasks:
                        f.write(f"{t.url}\n")
            QMessageBox.information(self, "Ekspor Sukses", f"Berhasil mengekspor {len(tasks)} item unduhan ke:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Galat Ekspor", f"Gagal menyimpan berkas ekspor:\n{e}")

    def _import_downloads(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Impor Daftar Unduhan - Krolix",
            "",
            "Berkas Unduhan (*.ef2 *.txt);;Krolix Export Format (*.ef2);;Text File (*.txt);;Semua Berkas (*.*)"
        )
        if not path or not os.path.exists(path):
            return

        imported_items = []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if path.lower().endswith(".ef2") or ("<" in content and ">" in content):
                # Parse .ef2 format
                blocks = re.findall(r'<\s*(.*?)\s*>', content, re.DOTALL)
                for b in blocks:
                    lines = [ln.strip() for ln in b.strip().splitlines() if ln.strip()]
                    if not lines:
                        continue
                    item_url = lines[0]
                    item_file = None
                    item_path = None
                    for ln in lines[1:]:
                        if ln.lower().startswith("file="):
                            item_file = ln.split("=", 1)[1].strip()
                        elif ln.lower().startswith("path="):
                            item_path = ln.split("=", 1)[1].strip()
                    imported_items.append({
                        "url": item_url,
                        "filename": item_file,
                        "save_path": os.path.join(item_path, item_file) if (item_path and item_file) else None
                    })
            else:
                # Parse Plain text format (one URL per line or tab-separated)
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    url = parts[0].strip()
                    if url.startswith(("http://", "https://", "ftp://", "magnet:")):
                        fn = parts[1].strip() if len(parts) > 1 else None
                        imported_items.append({"url": url, "filename": fn})

            if not imported_items:
                QMessageBox.warning(self, "Impor Unduhan", "Tidak ada URL yang valid ditemukan dalam berkas tersebut.")
                return

            self._show_batch_dialog(initial_items=imported_items)
        except Exception as e:
            QMessageBox.critical(self, "Galat Impor", f"Gagal membaca berkas unduhan:\n{e}")

    def _show_media_dialog(self, default_url: str = ""):
        if self._current_media_dialog is not None and self._current_media_dialog.isVisible():
            try:
                self._current_media_dialog.raise_()
                self._current_media_dialog.activateWindow()
                from ..utils.win32_native import Win32Native
                Win32Native.force_foreground_window(int(self._current_media_dialog.winId()))
            except Exception:
                pass
            return

        from .media_dialog import MediaDialog
        dlg = MediaDialog(default_url=default_url, parent=self)
        self._current_media_dialog = dlg
        dlg.raise_()
        dlg.activateWindow()
        try:
            from ..utils.win32_native import Win32Native
            Win32Native.force_foreground_window(int(dlg.winId()))
        except Exception:
            pass
        try:
            if dlg.exec():
                res = dlg.get_result()
                if res and res.get("url"):
                    default_dir = self.db.get_setting("default_save_path", os.path.join(os.path.expanduser("~"), "Downloads"))
                    task_headers = dict(res.get("headers") or {})
                    if res.get("is_live"):
                        task_headers["is_live"] = "true"
                        task_headers["is_hls"] = "true"
                        if res.get("master_url"):
                            task_headers["master_url"] = res["master_url"]
                        if res.get("audio_url"):
                            task_headers["audio_url"] = res["audio_url"]
                        if res.get("format_id"):
                            task_headers["resolution"] = str(res["format_id"])
                    if res.get("original_page"):
                        task_headers["Referer"] = res["original_page"]

                    task = self.engine.create_task(
                        url=res["url"],
                        save_dir=default_dir,
                        filename=res.get("title"),
                        headers=task_headers
                    )
                    self._insert_or_update_row(task)
                    self._update_all_telemetry()
                    self.engine.start_download(task.id)

                    if not res.get("is_live") and res.get("audio_url"):
                        try:
                            temp_dir = os.path.join(os.path.expanduser("~"), ".krolix_download", "temp")
                            os.makedirs(temp_dir, exist_ok=True)
                            temp_audio_name = f"__dash_audio_{task.id}.m4a"
                            audio_task = self.engine.create_task(
                                url=res["audio_url"],
                                save_dir=temp_dir,
                                filename=temp_audio_name
                            )
                            audio_task.is_hidden = True
                            self._hidden_tasks.add(audio_task.id)
                            self._dash_pairs[task.id] = audio_task.id
                            self._dash_pairs[audio_task.id] = task.id
                            self.engine.start_download(audio_task.id)
                        except Exception as audio_err:
                            print(f"[!] Warning: Failed to create companion audio task: {audio_err}")

                    self._show_progress_dialog(task)
        finally:
            self._current_media_dialog = None

    def _refresh_task_url(self, task: DownloadTask):
        from .refresh_url_dialog import RefreshUrlDialog
        dlg = RefreshUrlDialog(task=task, engine=self.engine, parent=self)
        if dlg.exec():
            live_task = self.engine.tasks.get(task.id, task)
            self._insert_or_update_row(live_task)
            self._update_all_telemetry()
            self._populate_table()
            if live_task.status in [DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING]:
                self._show_progress_dialog(live_task)

    def _show_site_grabber_dialog(self, default_url: str = ""):
        from ..core.license_manager import LicenseManager
        if not LicenseManager.get_instance(self.db).is_feature_allowed("site_grabber"):
            from .nag_dialog import TrialExpiredNagDialog
            dlg = TrialExpiredNagDialog(locked_feature_name="Site Grabber & Crawler", parent=self)
            dlg.exec()
            return
        from .grabber_dialog import GrabberDialog
        default_dir = self.db.get_setting("default_save_path", os.path.join(os.path.expanduser("~"), "Downloads"))
        dlg = GrabberDialog(default_url=default_url, default_save_dir=default_dir, parent=self)
        if dlg.exec():
            res = dlg.get_results()
            items = res.get("items", [])
            save_dir = res.get("save_dir", default_dir)
            start_now = res.get("start_now", True)

            created_tasks = []
            for item in items:
                task = self.engine.create_task(
                    url=item.url,
                    save_dir=save_dir,
                    filename=item.filename
                )
                self._insert_or_update_row(task)
                created_tasks.append(task)

            self._populate_table()
            self._update_all_telemetry()

            if start_now:
                for t in created_tasks:
                    self.engine.start_download(t.id)

            QMessageBox.information(
                self,
                "Site Grabber Complete",
                f"Successfully added {len(created_tasks)} grabbed files to the download list."
            )

    def _show_scheduler_dialog(self):
        from ..core.license_manager import LicenseManager
        if not LicenseManager.get_instance(self.db).is_feature_allowed("scheduler"):
            from .nag_dialog import TrialExpiredNagDialog
            dlg = TrialExpiredNagDialog(locked_feature_name="Penjadwal Otomatis (Scheduler)", parent=self)
            dlg.exec()
            return
        from .scheduler_dialog import SchedulerDialog
        dlg = SchedulerDialog(self.db, self.scheduler, parent=self)
        dlg.exec()

    def _show_credentials_dialog(self):
        from .credentials_dialog import CredentialsDialog
        dlg = CredentialsDialog(self.db, parent=self)
        dlg.exec()

    def _show_watchlist_dialog(self, default_url: str = ""):
        from .watchlist_dialog import WatchlistDialog
        if self._watchlist_dialog is not None and self._watchlist_dialog.isVisible():
            if default_url:
                self._watchlist_dialog.txt_url.setText(default_url)
            self._watchlist_dialog.raise_()
            self._watchlist_dialog.activateWindow()
            return

        dlg = WatchlistDialog(self.watchlist_mgr, parent=self)
        if default_url:
            dlg.txt_url.setText(default_url)
        self._watchlist_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _add_task_to_watchlist(self, channel_url: str):
        try:
            item = self.watchlist_mgr.add_channel(channel_url)
            self.tray.show_notification(
                "Live Stream Watchlist",
                f"Channel '{item['name']}' ({item['platform']}) ditambahkan ke pemantauan otomatis.",
            )
            self._show_watchlist_dialog()
        except Exception as e:
            QMessageBox.warning(self, "Watchlist", str(e))

    def _on_watchlist_updated(self, _item: dict):
        if self._watchlist_dialog is not None and self._watchlist_dialog.isVisible():
            self._watchlist_dialog.refresh_requested.emit()

    def _on_watchlist_recording_started(self, item: dict, task: DownloadTask):
        if task:
            self._insert_or_update_row(task)
            self._update_all_telemetry()
        self.tray.show_notification(
            "Krolix Auto-Recorder (LIVE)",
            f"'{item.get('name', 'Channel')}' sedang LIVE! Mulai merekam otomatis...",
        )
        if self._watchlist_dialog is not None and self._watchlist_dialog.isVisible():
            self._watchlist_dialog.refresh_requested.emit()

    def _show_about_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("About Krolix")
        dlg.setFixedSize(510, 340)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #f5f5f7;
            }
        """)

        vbox = QVBoxLayout(dlg)
        vbox.setContentsMargins(22, 22, 22, 20)
        vbox.setSpacing(14)

        # Header with Logo & App Info
        top_box = QHBoxLayout()
        top_box.setSpacing(16)

        logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "logo_64.png"))
        if os.path.exists(logo_path):
            lbl_logo = QLabel()
            lbl_logo.setPixmap(QPixmap(logo_path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            top_box.addWidget(lbl_logo)

        info_box = QVBoxLayout()
        info_box.setSpacing(3)
        lbl_title = QLabel("Krolix Download Manager")
        lbl_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #f5f5f7; letter-spacing: 0.3px;")
        info_box.addWidget(lbl_title)

        lbl_ver = QLabel("Version 2.8.0 (macOS Edition Architecture)")
        lbl_ver.setStyleSheet("font-size: 11px; font-weight: 500; color: #22c55e;")
        info_box.addWidget(lbl_ver)

        lbl_sub = QLabel("High-Speed Multi-Threaded Engine with Live HLS & DPI Bypass")
        lbl_sub.setStyleSheet("font-size: 10px; color: #8e8e93;")
        info_box.addWidget(lbl_sub)

        top_box.addLayout(info_box)
        vbox.addLayout(top_box)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #1e293b; border: none; max-height: 1px;")
        vbox.addWidget(sep)

        # Authentic Registration Status Card
        from ..core.license_manager import LicenseManager
        lic_info = LicenseManager.get_instance(self.db).get_license_display_info()

        card = QFrame()
        card.setObjectName("aboutLicenseCard")
        card.setStyleSheet("""
            #aboutLicenseCard {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
            #aboutLicenseCard QLabel {
                border: none;
                background: transparent;
                padding: 0px;
            }
        """)
        card_vbox = QVBoxLayout(card)
        card_vbox.setContentsMargins(16, 12, 16, 12)
        card_vbox.setSpacing(6)

        if lic_info.get("is_full"):
            lbl_owner_hdr = QLabel("This product is registered to:")
            lbl_owner_hdr.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: 500;")
            card_vbox.addWidget(lbl_owner_hdr)

            reg_name = lic_info.get("registered_name", "Registered User")
            reg_email = lic_info.get("registered_email", "")
            lbl_owner = QLabel(f"<b>{reg_name}</b> <span style='color: #64748b;'>&lt;{reg_email}&gt;</span>" if reg_email else f"<b>{reg_name}</b>")
            lbl_owner.setStyleSheet("font-size: 12px; color: #f8fafc;")
            card_vbox.addWidget(lbl_owner)

            sn_masked = lic_info.get("serial_masked", "")
            if sn_masked:
                lbl_sn = QLabel(f"Serial Number: <span style='font-family: Consolas, monospace; font-weight: 600; color: #38bdf8; letter-spacing: 0.5px;'>{sn_masked}</span>")
                lbl_sn.setStyleSheet("font-size: 11px; color: #94a3b8;")
                card_vbox.addWidget(lbl_sn)

            # Badge
            badge_box = QHBoxLayout()
            badge_box.setContentsMargins(0, 4, 0, 0)
            if lic_info.get("is_master"):
                lbl_badge = QLabel("★ ADVANCE MASTER MODE (64 TURBO THREADS ENABLED)")
                lbl_badge.setStyleSheet("""
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #92400e, stop:1 #d97706);
                    color: #fffbeb;
                    font-size: 9px;
                    font-weight: 800;
                    padding: 3px 8px;
                    border-radius: 4px;
                    letter-spacing: 0.5px;
                """)
            else:
                lbl_badge = QLabel("✓ FULL REGISTERED VERSION")
                lbl_badge.setStyleSheet("""
                    background: rgba(16, 185, 129, 0.15);
                    color: #34d399;
                    border: 1px solid rgba(16, 185, 129, 0.35);
                    font-size: 9px;
                    font-weight: 700;
                    padding: 3px 8px;
                    border-radius: 4px;
                    letter-spacing: 0.5px;
                """)
            badge_box.addWidget(lbl_badge)
            badge_box.addStretch()
            card_vbox.addLayout(badge_box)
        elif lic_info.get("is_trial"):
            lbl_trial_hdr = QLabel("Evaluation Mode (Unregistered)")
            lbl_trial_hdr.setStyleSheet("font-size: 12px; font-weight: 700; color: #fbbf24;")
            card_vbox.addWidget(lbl_trial_hdr)

            days_left = lic_info.get("days_left", 30)
            lbl_trial_sub = QLabel(f"You have <b>{days_left} days left</b> in your evaluation period. Please register to unlock all Turbo features.")
            lbl_trial_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")
            lbl_trial_sub.setWordWrap(True)
            card_vbox.addWidget(lbl_trial_sub)
        else:
            lbl_exp_hdr = QLabel("Registration Expired / Unregistered")
            lbl_exp_hdr.setStyleSheet("font-size: 12px; font-weight: 700; color: #f87171;")
            card_vbox.addWidget(lbl_exp_hdr)

            lbl_exp_sub = QLabel("Evaluation period has ended. Commercial features disabled. Please register to reactivate.")
            lbl_exp_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")
            card_vbox.addWidget(lbl_exp_sub)

        vbox.addWidget(card)

        # Bottom Bar: Copyright & OK Button
        bot_box = QHBoxLayout()
        lbl_copy = QLabel("Copyright © Krolix Core Team. All rights reserved.")
        lbl_copy.setStyleSheet("font-size: 10px; color: #8e8e93;")
        bot_box.addWidget(lbl_copy)

        bot_box.addStretch()

        btn_ok = QPushButton("OK")
        btn_ok.setFixedSize(85, 28)
        btn_ok.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563eb, stop:1 #1d4ed8);
                color: #ffffff;
                border: 1px solid #3b82f6;
                border-radius: 4px;
                padding: 4px 14px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
            }
            QPushButton:pressed {
                background: #1e40af;
            }
        """)
        btn_ok.clicked.connect(dlg.accept)
        bot_box.addWidget(btn_ok)

        vbox.addLayout(bot_box)

        dlg.exec()

    def _arrange_files(self, col: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder):
        self._current_sort_col = col
        self._current_sort_order = order
        self.table.sortItems(col, order)

    def _on_header_section_clicked(self, col: int):
        if getattr(self, "_current_sort_col", -1) == col:
            new_order = Qt.SortOrder.DescendingOrder if self._current_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            new_order = Qt.SortOrder.AscendingOrder
        self._arrange_files(col, new_order)

    def _init_table_header(self):
        """Initializes fully dynamic, user-resizable table columns with persistence."""
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.sectionClicked.connect(self._on_header_section_clicked)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)
        header.setCascadingSectionResizes(True)
        header.setMinimumSectionSize(50)
        header.setStretchLastSection(False)

        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        self._restore_table_column_state()
        header.sectionResized.connect(self._on_column_section_resized)

        self._col_save_timer = QTimer(self)
        self._col_save_timer.setSingleShot(True)
        self._col_save_timer.setInterval(350)
        self._col_save_timer.timeout.connect(self._save_table_column_state_immediate)

    def _on_column_section_resized(self, col: int, old_size: int, new_size: int):
        if getattr(self, "_programmatic_col_resize", False):
            return
        if col == 0:
            self._col0_manually_resized = True
        if hasattr(self, "_col_save_timer"):
            self._col_save_timer.start()

    def _adjust_column_widths_to_viewport(self):
        """Intelligently expands File Name to fill available space unless manually sized by user."""
        if not hasattr(self, "table") or self.table is None:
            return
        viewport_w = self.table.viewport().width()
        if viewport_w <= 100:
            return

        if getattr(self, "_col0_manually_resized", False):
            return

        other_w = sum(self.table.columnWidth(i) for i in range(1, self.table.columnCount()) if not self.table.isColumnHidden(i))
        remaining = max(220, viewport_w - other_w)
        self._programmatic_col_resize = True
        try:
            self.table.setColumnWidth(0, remaining)
        finally:
            self._programmatic_col_resize = False

    def _update_empty_state(self):
        """Shows modern empty state illustration when download table has zero rows."""
        if hasattr(self, "empty_overlay") and hasattr(self, "table"):
            is_empty = (self.table.rowCount() == 0)
            self.empty_overlay.setVisible(is_empty)
            if is_empty:
                vp_size = self.table.viewport().size()
                self.empty_overlay.resize(vp_size)
                self.empty_overlay.move(0, 0)

    def _save_table_column_state_immediate(self):
        """Persists current column widths and visibility to database settings."""
        try:
            widths = [self.table.columnWidth(i) for i in range(self.table.columnCount())]
            hidden = [i for i in range(self.table.columnCount()) if self.table.isColumnHidden(i)]
            manual_col0 = getattr(self, "_col0_manually_resized", False)
            data = {
                "widths": widths,
                "hidden": hidden,
                "manual_col0": manual_col0
            }
            self.db.set_setting("table_columns_config", json.dumps(data))
        except Exception:
            pass

    def _restore_table_column_state(self):
        """Restores user-customized column widths or falls back to optimized defaults."""
        default_widths = [320, 95, 175, 90, 105, 130, 120, 110]
        try:
            cfg_raw = self.db.get_setting("table_columns_config", "")
            if cfg_raw:
                cfg = json.loads(cfg_raw)
                widths = cfg.get("widths", [])
                hidden = cfg.get("hidden", [])
                self._col0_manually_resized = cfg.get("manual_col0", False)
                for i, w in enumerate(widths):
                    if i < self.table.columnCount() and w > 20:
                        self.table.setColumnWidth(i, w)
                for h_idx in hidden:
                    if 0 < h_idx < self.table.columnCount():
                        self.table.setColumnHidden(h_idx, True)
                return
        except Exception:
            pass

        self._col0_manually_resized = False
        for col, w in enumerate(default_widths):
            self.table.setColumnWidth(col, w)
        self.table.setColumnHidden(6, True)
        self.table.setColumnHidden(7, True)

    def _show_header_context_menu(self, pos):
        """Right-click menu on table header for column visibility and sizing shortcuts."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0b0f17;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #1e293b;
                color: #38bdf8;
            }
            QMenu::separator {
                height: 1px;
                background-color: #1e293b;
                margin: 4px 6px;
            }
        """)

        labels = [
            "Nama Berkas (File Name)",
            "Ukuran (Size)",
            "Status & Progress",
            "Sisa Waktu (Time Left)",
            "Kecepatan (Transfer Rate)",
            "Terakhir Dicoba (Last Try Date)",
            "Deskripsi (Description)",
            "Masa Seeding (Torrent)"
        ]

        title_act = menu.addAction("Tampilkan / Sembunyikan Kolom:")
        title_act.setEnabled(False)
        menu.addSeparator()

        for col_idx in range(self.table.columnCount()):
            lbl = labels[col_idx] if col_idx < len(labels) else f"Kolom {col_idx+1}"
            act = menu.addAction(lbl)
            act.setCheckable(True)
            act.setChecked(not self.table.isColumnHidden(col_idx))
            if col_idx == 0:
                act.setEnabled(False)  # File Name cannot be hidden
            else:
                def make_toggle(idx=col_idx, action=act):
                    return lambda: self._toggle_column_visibility(idx, action.isChecked())
                act.triggered.connect(make_toggle(col_idx, act))

        menu.addSeparator()

        act_autofit = menu.addAction("Ratakan Kolom Otomatis (Auto-Fit)")
        act_autofit.triggered.connect(self._auto_fit_columns)

        act_reset = menu.addAction("Reset Ukuran Kolom Bawaan")
        act_reset.triggered.connect(self._reset_columns_to_default)

        header = self.table.horizontalHeader()
        menu.exec(header.mapToGlobal(pos))

    def _toggle_column_visibility(self, col: int, visible: bool):
        self.table.setColumnHidden(col, not visible)
        self._adjust_column_widths_to_viewport()
        self._save_table_column_state_immediate()

    def _auto_fit_columns(self):
        self._programmatic_col_resize = True
        try:
            self.table.resizeColumnsToContents()
            for i in range(self.table.columnCount()):
                cur = self.table.columnWidth(i)
                self.table.setColumnWidth(i, max(60, cur + 20))
            if self.table.columnWidth(0) < 220:
                self.table.setColumnWidth(0, 220)
        finally:
            self._programmatic_col_resize = False
        self._col0_manually_resized = True
        self._save_table_column_state_immediate()

    def _reset_columns_to_default(self):
        self._programmatic_col_resize = True
        try:
            default_widths = [280, 105, 190, 95, 110, 130, 140, 125]
            for col, w in enumerate(default_widths):
                self.table.setColumnWidth(col, w)
                self.table.setColumnHidden(col, False)
        finally:
            self._programmatic_col_resize = False
        self._col0_manually_resized = False
        self._adjust_column_widths_to_viewport()
        self._save_table_column_state_immediate()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(60, self._adjust_column_widths_to_viewport)
        QTimer.singleShot(70, self._update_empty_state)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_column_widths_to_viewport()
        self._update_empty_state()


    def _show_tip_dialog(self):
        dlg = TipDialog(self, self.db)
        dlg.exec()

    def _show_extension_dialog(self):
        dlg = ExtensionDialog(self, self.db)
        dlg.exec()

    def _open_category_folders_dialog(self):
        from .category_folders_dialog import CategoryFoldersDialog
        dlg = CategoryFoldersDialog(self.db, self)
        dlg.exec()

    def _open_category_folder_by_name(self, cat_name: str):
        from ..utils.helpers import get_default_download_dir
        cat_key = (cat_name or "").strip().lower()
        key_aliases = {
            "compressed": "compressed",
            "documents": "documents",
            "music": "music",
            "audio": "music",
            "programs": "programs",
            "video": "video",
            "videos": "video",
        }
        mapped = key_aliases.get(cat_key, cat_key)
        p = self.db.get_setting(f"category_dir_{mapped}", "")
        if not p or not os.path.exists(p):
            default_p = self.db.get_setting("default_save_path", "") or get_default_download_dir(mapped)
            p = default_p if os.path.exists(default_p) else get_default_download_dir()
        if p and os.path.exists(p):
            try:
                subprocess.Popen(["explorer.exe", os.path.normpath(p)])
            except Exception:
                try:
                    os.startfile(p)
                except Exception:
                    pass

    def _restore_from_tray(self):
        was_max = self.isMaximized()
        self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.show()
        if not was_max:
            self.showNormal()
        self.raise_()
        self.activateWindow()
        try:
            self._cached_hwnd = int(self.winId())
        except Exception:
            pass

        # Bring forward any active modal widget or child dialogs
        active_modal = QApplication.activeModalWidget()
        if not active_modal:
            for w in QApplication.topLevelWidgets():
                if isinstance(w, QDialog) and w.isVisible():
                    active_modal = w
                    break

        if active_modal:
            try:
                active_modal.show()
                active_modal.raise_()
                active_modal.activateWindow()
            except Exception:
                pass

        if sys.platform == "win32":
            try:
                from ..utils.win32_native import Win32Native
                Win32Native.force_foreground_window(int(self.winId()))
                if active_modal:
                    Win32Native.force_foreground_window(int(active_modal.winId()))
            except Exception:
                pass

    def _confirm_force_quit(self):
        """Shows a confirmation dialog before terminating the background worker."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Keluar dari Krolix Download Manager")
        msg.setText(
            "<b>Apakah Anda ingin mematikan Background Worker?</b><br><br>"
            "Jika background worker dimatikan, ekstensi browser (Chrome/Edge) "
            "tidak dapat menangkap unduhan secara otomatis sampai aplikasi dibuka kembali."
        )
        btn_keep = msg.addButton("Tetap Jalankan Worker di Latar Belakang", QMessageBox.ButtonRole.AcceptRole)
        btn_quit = msg.addButton("Matikan Worker & Keluar", QMessageBox.ButtonRole.DestructiveRole)
        msg.setDefaultButton(btn_keep)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.exec()

        if msg.clickedButton() == btn_quit:
            self._force_quit()
        else:
            self.hide()

    def _force_quit(self):
        self._is_quitting = True
        if hasattr(self, "watchlist_mgr") and self.watchlist_mgr:
            self.watchlist_mgr.stop()
        if hasattr(self, "clip_monitor") and self.clip_monitor:
            self.clip_monitor.stop()
        self._stop_all()
        if hasattr(self, "engine") and self.engine:
            try:
                self.engine.stop()
            except Exception:
                pass
        self.api_server.stop()
        self.scheduler.running = False
        if hasattr(self, "tray") and self.tray and getattr(self.tray, "tray_icon", None):
            self.tray.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        self._save_table_column_state_immediate()
        always_on = self.db.get_setting("always_on_worker", "true") == "true"
        minimize_to_tray = self.db.get_setting("minimize_to_tray", "true") == "true"
        if (always_on or minimize_to_tray) and not getattr(self, "_is_quitting", False):
            event.ignore()
            self.hide()
            if not getattr(self, "_tray_notified_once", False):
                self._tray_notified_once = True
                self.tray.show_notification(
                    "Krolix Download Manager",
                    "Aplikasi berjalan di latar belakang (Port 9666). Ekstensi browser tetap aktif."
                )
        else:
            self._force_quit()
            super().closeEvent(event)


    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.isMaximized():
            edge = self._get_resize_edge(event.position().toPoint())
            if edge:
                self._resizing_edge = edge
                self._drag_start_pos = event.globalPosition().toPoint()
                self._drag_start_geo = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if not self.isMaximized() and not getattr(self, "_resizing_edge", None):
            edge = self._get_resize_edge(pos)
            self._update_cursor_for_edge(edge)

        if getattr(self, "_resizing_edge", None) and event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            geo = self._drag_start_geo
            x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
            min_w, min_h = self.minimumWidth(), self.minimumHeight()

            edge = self._resizing_edge
            if "right" in edge:
                w = max(min_w, geo.width() + delta.x())
            if "bottom" in edge:
                h = max(min_h, geo.height() + delta.y())
            if "left" in edge:
                new_w = max(min_w, geo.width() - delta.x())
                x = geo.right() - new_w
                w = new_w
            if "top" in edge:
                new_h = max(min_h, geo.height() - delta.y())
                y = geo.bottom() - new_h
                h = new_h

            self.setGeometry(x, y, w, h)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizing_edge = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def _get_resize_edge(self, pos):
        margin = 8
        rect = self.rect()
        edge = []
        if pos.y() <= margin:
            edge.append("top")
        elif pos.y() >= rect.height() - margin:
            edge.append("bottom")
        if pos.x() <= margin:
            edge.append("left")
        elif pos.x() >= rect.width() - margin:
            edge.append("right")
        return "-".join(edge) if edge else None

    def _update_cursor_for_edge(self, edge):
        if not edge:
            self.unsetCursor()
            return
        if edge in ("left", "right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge in ("top", "bottom"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edge in ("top-left", "bottom-right"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge in ("top-right", "bottom-left"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)

    def _update_window_title(self):
        from ..core.license_manager import LicenseManager
        info = LicenseManager.get_instance(self.db).get_license_display_info()
        if info.get("is_master") or info.get("is_full"):
            title = "Krolix Download Manager"
        elif info.get("is_fake"):
            title = "Krolix Download Manager (Serial Number Palsu / Keygen Terdeteksi!)"
        elif info.get("is_trial"):
            title = f"Krolix Download Manager (30 Hari Uji Coba - {info['days_left']} Hari Tersisa)"
        else:
            title = "Krolix Download Manager (Versi Tidak Terdaftar - Fungsi Terbatas)"
        self.setWindowTitle(title)
        if hasattr(self, "title_bar") and hasattr(self.title_bar, "lbl_title"):
            self.title_bar.lbl_title.setText(title)

    def _show_license_dialog(self):
        from .license_dialog import LicenseRegistrationDialog
        dlg = LicenseRegistrationDialog(parent=self)
        dlg.license_status_changed.connect(self._on_license_status_changed)
        dlg.exec()

    def _update_registration_menu_state(self):
        from ..core.license_manager import LicenseManager
        is_full = LicenseManager.get_instance(self.db).is_full_version()
        if hasattr(self, "act_registration"):
            if is_full:
                self.act_registration.setEnabled(False)
                self.act_registration.setText("Registration (Registered)")
                self.act_registration.setToolTip("Aplikasi telah terdaftar dengan lisensi sah.")
            else:
                self.act_registration.setEnabled(True)
                self.act_registration.setText("Registration...")
                self.act_registration.setToolTip("Daftarkan produk dengan Serial Number resmi.")

        if hasattr(self, "act_buy"):
            self.act_buy.setEnabled(not is_full)

    def _on_license_status_changed(self):
        self._update_window_title()
        self._update_registration_menu_state()

    def _order_license_online(self):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Beli Lisensi Full Version Online",
            "Membuka halaman web pemesanan lisensi Krolix Download Manager.\n"
            "Dapatkan serial key instan untuk membuka seluruh fitur tanpa batasan."
        )

    def _check_startup_license(self):
        self._update_registration_menu_state()
        from ..core.license_manager import LicenseManager, LicenseStatus
        mgr = LicenseManager.get_instance(self.db)
        status = mgr.get_status()
        if status == LicenseStatus.FAKE_SERIAL:
            from .fake_serial_dialog import FakeSerialDetectedDialog
            info = mgr.get_license_display_info()
            dlg = FakeSerialDetectedDialog(reason=info.get("fake_reason", ""), serial_masked=info.get("serial_masked", ""), parent=self)
            dlg.exec()
        elif status == LicenseStatus.EXPIRED:
            from .nag_dialog import TrialExpiredNagDialog
            dlg = TrialExpiredNagDialog(parent=self)
            dlg.exec()
