"""
Krolix Download Manager - Real BitTorrent Seeder & Swarm Dashboard
Monitor and manage authentic BitTorrent seeding sessions, real upload speeds,
share ratios, and swarm peers.
Designed with Windows 11 Fluent Dark Titanium / Obsidian aesthetics.
"""

import os
import time
from typing import Optional, List, Any
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame,
    QMessageBox, QInputDialog, QAbstractItemView, QWidget, QStackedWidget,
    QButtonGroup
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from ..core.database import Database
from ..core.models import DownloadTask, DownloadStatus
from ..utils.helpers import apply_windows_dark_titlebar, get_app_icon, format_bytes, format_eta


class SortableTableWidgetItem(QTableWidgetItem):
    def __init__(self, text: str, sort_val: Any = None):
        super().__init__(text)
        self.sort_val = sort_val if sort_val is not None else text

    def __lt__(self, other):
        if isinstance(other, SortableTableWidgetItem):
            return self.sort_val < other.sort_val
        return super().__lt__(other)


class TorrentSeedingDialog(QDialog):
    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BitTorrent Real Seeder & Swarm Monitor")
        self.resize(1060, 720)
        self.setMinimumSize(940, 640)

        # Apply Windows 11 dark title bar and icon
        apply_windows_dark_titlebar(self)
        try:
            self.setWindowIcon(get_app_icon())
        except Exception:
            pass

        self.engine = engine
        if not self.engine and parent and hasattr(parent, "engine"):
            self.engine = parent.engine

        self.db = getattr(self.engine, "db", None) if self.engine else Database()

        self._setup_style()
        self._init_ui()

        # Telemetry update timer (1 second interval)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_telemetry)
        self.timer.start(1000)

        self._refresh_telemetry()
        self._refresh_leaderboard()

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0b0f19;
                color: #f1f5f9;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            
            /* Metric Cards */
            QFrame.MetricCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #121929, stop:1 #0c1322);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 10px 14px;
            }
            QLabel.MetricTitle {
                font-size: 11px;
                color: #94a3b8;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.6px;
            }
            QLabel.MetricValue {
                font-size: 20px;
                font-weight: 700;
                color: #f1f5f9;
            }
            QLabel.MetricSub {
                font-size: 11px;
                color: #64748b;
            }

            /* Segmented Navigation Capsule */
            QFrame#SegmentCapsule {
                background-color: #101726;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 3px;
            }
            QPushButton.SegmentTab {
                background-color: transparent;
                border: none;
                border-radius: 6px;
                color: #94a3b8;
                font-size: 13px;
                font-weight: 600;
                padding: 6px 18px;
                min-height: 22px;
            }
            QPushButton.SegmentTab:hover {
                color: #f1f5f9;
                background-color: rgba(255, 255, 255, 0.04);
            }
            QPushButton.SegmentTab:checked {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #253347, stop:1 #1c2738);
                border: 1px solid rgba(255, 255, 255, 0.15);
                color: #ffffff;
            }

            /* Tables */
            QTableWidget {
                background-color: #0d1322;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                gridline-color: rgba(255, 255, 255, 0.03);
                color: #e2e8f0;
                font-size: 13px;
                selection-background-color: rgba(255, 255, 255, 0.08);
                selection-color: #ffffff;
                outline: none;
            }
            QTableWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            }
            QTableWidget::item:selected {
                background-color: rgba(255, 255, 255, 0.07);
            }
            QHeaderView::section {
                background-color: #111828;
                color: #94a3b8;
                font-weight: 600;
                font-size: 12px;
                padding: 8px 10px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }

            /* Control Deck */
            QFrame#ControlDeck {
                background-color: #101726;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 10px 14px;
            }
            QLabel.ControlLabel {
                font-size: 12px;
                font-weight: 600;
                color: #cbd5e1;
            }
            QSpinBox, QComboBox {
                background-color: #0b0f19;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                color: #f1f5f9;
                font-size: 13px;
                padding: 5px 10px;
                min-height: 22px;
            }
            QSpinBox:focus, QComboBox:focus {
                border: 1px solid #10b981;
            }

            /* Buttons */
            QPushButton#PrimaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10b981, stop:1 #059669);
                border: 1px solid #34d399;
                border-radius: 6px;
                color: #ffffff;
                font-weight: 600;
                font-size: 13px;
                padding: 6px 16px;
                min-height: 22px;
            }
            QPushButton#PrimaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #059669, stop:1 #047857);
            }
            QPushButton#SecondaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #253347, stop:1 #1c2738);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 6px;
                color: #e2e8f0;
                font-size: 13px;
                font-weight: 500;
                padding: 6px 14px;
                min-height: 22px;
            }
            QPushButton#SecondaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #32435c, stop:1 #243247);
                color: #ffffff;
            }
            QPushButton#DangerBtn {
                background-color: rgba(239, 68, 68, 0.12);
                border: 1px solid rgba(239, 68, 68, 0.28);
                border-radius: 6px;
                color: #fca5a5;
                font-size: 13px;
                font-weight: 500;
                padding: 6px 14px;
                min-height: 22px;
            }
            QPushButton#DangerBtn:hover {
                background-color: rgba(239, 68, 68, 0.24);
                color: #ffffff;
            }
        """)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        # 1. Header & Metric Cards Row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)

        # Card 1: Total Real Upload Speed
        card1 = QFrame()
        card1.setProperty("class", "MetricCard")
        c1_layout = QVBoxLayout(card1)
        c1_layout.setContentsMargins(0, 0, 0, 0)
        c1_layout.setSpacing(3)
        t1 = QLabel("Kecepatan Upload Riil")
        t1.setProperty("class", "MetricTitle")
        self.val_speed = QLabel("0.00 MB/s")
        self.val_speed.setProperty("class", "MetricValue")
        sub1 = QLabel("Real Peer Bandwidth")
        sub1.setProperty("class", "MetricSub")
        c1_layout.addWidget(t1)
        c1_layout.addWidget(self.val_speed)
        c1_layout.addWidget(sub1)
        cards_row.addWidget(card1, 1)

        # Card 2: Total Real Uploaded
        card2 = QFrame()
        card2.setProperty("class", "MetricCard")
        c2_layout = QVBoxLayout(card2)
        c2_layout.setContentsMargins(0, 0, 0, 0)
        c2_layout.setSpacing(3)
        t2 = QLabel("Total Terunggah Riil")
        t2.setProperty("class", "MetricTitle")
        self.val_credit = QLabel("0.00 GB")
        self.val_credit.setProperty("class", "MetricValue")
        sub2 = QLabel("Data Tersemai ke Swarm")
        sub2.setProperty("class", "MetricSub")
        c2_layout.addWidget(t2)
        c2_layout.addWidget(self.val_credit)
        c2_layout.addWidget(sub2)
        cards_row.addWidget(card2, 1)

        # Card 3: Active Seeding Torrents
        card3 = QFrame()
        card3.setProperty("class", "MetricCard")
        c3_layout = QVBoxLayout(card3)
        c3_layout.setContentsMargins(0, 0, 0, 0)
        c3_layout.setSpacing(3)
        t3 = QLabel("Torrent Seeding Aktif")
        t3.setProperty("class", "MetricTitle")
        self.val_active = QLabel("0 Aktif")
        self.val_active.setProperty("class", "MetricValue")
        sub3 = QLabel("BitTorrent Swarms")
        sub3.setProperty("class", "MetricSub")
        c3_layout.addWidget(t3)
        c3_layout.addWidget(self.val_active)
        c3_layout.addWidget(sub3)
        cards_row.addWidget(card3, 1)

        # Card 4: Swarm Connected
        card4 = QFrame()
        card4.setProperty("class", "MetricCard")
        c4_layout = QVBoxLayout(card4)
        c4_layout.setContentsMargins(0, 0, 0, 0)
        c4_layout.setSpacing(3)
        t4 = QLabel("Peers Terhubung")
        t4.setProperty("class", "MetricTitle")
        self.val_peers = QLabel("0 Peers")
        self.val_peers.setProperty("class", "MetricValue")
        sub4 = QLabel("Leechers Menerima Data")
        sub4.setProperty("class", "MetricSub")
        c4_layout.addWidget(t4)
        c4_layout.addWidget(self.val_peers)
        c4_layout.addWidget(sub4)
        cards_row.addWidget(card4, 1)

        root.addLayout(cards_row)

        # 2. Segmented Navigation Capsule
        nav_row = QHBoxLayout()
        nav_capsule = QFrame()
        nav_capsule.setObjectName("SegmentCapsule")
        capsule_layout = QHBoxLayout(nav_capsule)
        capsule_layout.setContentsMargins(3, 3, 3, 3)
        capsule_layout.setSpacing(4)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        self.tab_active = QPushButton("Sesi Seeding Aktif")
        self.tab_active.setProperty("class", "SegmentTab")
        self.tab_active.setCheckable(True)
        self.tab_active.setChecked(True)
        self.tab_active.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_group.addButton(self.tab_active, 0)
        capsule_layout.addWidget(self.tab_active)

        self.tab_history = QPushButton("Riwayat Seeding & Kontribusi")
        self.tab_history.setProperty("class", "SegmentTab")
        self.tab_history.setCheckable(True)
        self.tab_history.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_group.addButton(self.tab_history, 1)
        capsule_layout.addWidget(self.tab_history)

        self.btn_group.idClicked.connect(self._on_segment_switched)

        nav_row.addWidget(nav_capsule)
        nav_row.addStretch()
        root.addLayout(nav_row)

        # 3. Stacked Pages
        self.stack = QStackedWidget()

        # Page 0: Active Seeding Table
        page_active = QWidget()
        pa_layout = QVBoxLayout(page_active)
        pa_layout.setContentsMargins(0, 0, 0, 0)
        pa_layout.setSpacing(10)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Nama File / Rilis", "Ukuran", "Terunggah", "Kecepatan Upload",
            "Rasio Bagi", "Swarm (S/P)", "Masa Seeding", "Status"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 8):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        pa_layout.addWidget(self.table, 1)

        # Action Bar below Table
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self.btn_pause = QPushButton("Jeda Seeding")
        self.btn_pause.setObjectName("SecondaryBtn")
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.clicked.connect(self._pause_selected)
        action_bar.addWidget(self.btn_pause)

        self.btn_resume = QPushButton("Lanjutkan Seeding")
        self.btn_resume.setObjectName("SecondaryBtn")
        self.btn_resume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_resume.clicked.connect(self._resume_selected)
        action_bar.addWidget(self.btn_resume)

        self.btn_days = QPushButton("Ubah Masa Seeding...")
        self.btn_days.setObjectName("SecondaryBtn")
        self.btn_days.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_days.clicked.connect(self._edit_selected_days)
        action_bar.addWidget(self.btn_days)

        self.btn_open_folder = QPushButton("Buka Folder")
        self.btn_open_folder.setObjectName("SecondaryBtn")
        self.btn_open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_folder.clicked.connect(self._open_selected_folder)
        action_bar.addWidget(self.btn_open_folder)

        action_bar.addStretch()

        self.btn_close = QPushButton("Tutup")
        self.btn_close.setObjectName("SecondaryBtn")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        action_bar.addWidget(self.btn_close)

        pa_layout.addLayout(action_bar)
        self.stack.addWidget(page_active)

        # Page 1: Seeding History / Leaderboard
        page_history = QWidget()
        ph_layout = QVBoxLayout(page_history)
        ph_layout.setContentsMargins(0, 0, 0, 0)
        ph_layout.setSpacing(10)

        self.leaderboard_table = QTableWidget()
        self.leaderboard_table.setColumnCount(5)
        self.leaderboard_table.setHorizontalHeaderLabels([
            "Nama File / Rilis", "Info Hash", "Total Terunggah Riil", "Durasi Seeding", "Selesai Pada"
        ])
        self.leaderboard_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.leaderboard_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.leaderboard_table.verticalHeader().setVisible(False)
        self.leaderboard_table.setShowGrid(False)

        h_lead = self.leaderboard_table.horizontalHeader()
        h_lead.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h_lead.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_lead.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_lead.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_lead.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        ph_layout.addWidget(self.leaderboard_table, 1)

        btn_refresh_lead = QPushButton("Perbarui Riwayat")
        btn_refresh_lead.setObjectName("SecondaryBtn")
        btn_refresh_lead.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh_lead.clicked.connect(self._refresh_leaderboard)
        ph_layout.addWidget(btn_refresh_lead, 0, Qt.AlignmentFlag.AlignRight)

        self.stack.addWidget(page_history)
        root.addWidget(self.stack, 1)

    def _on_segment_switched(self, idx: int):
        self.stack.setCurrentIndex(idx)
        if idx == 1:
            self._refresh_leaderboard()

    def _get_active_torrent_tasks(self) -> List[DownloadTask]:
        if not self.engine:
            return []
        tasks = []
        with getattr(self.engine, "lock", threading.Lock()):
            for t in getattr(self.engine, "tasks", {}).values():
                is_torrent = (
                    getattr(t, "is_torrent", False) or
                    (t.category or "").lower() in ["torrents", "torrent"] or
                    (t.url and (t.url.lower().startswith("magnet:") or ".torrent" in t.url.lower()))
                )
                if is_torrent:
                    tasks.append(t)
        return tasks

    def _refresh_telemetry(self):
        tasks = self._get_active_torrent_tasks()
        total_upload_spd = 0.0
        total_uploaded_bytes = 0
        active_seeding_cnt = 0
        total_peers_cnt = 0

        for t in tasks:
            ul_spd = getattr(t, "upload_speed", 0.0) or 0.0
            total_upload_spd += ul_spd
            ul_b = getattr(t, "uploaded_bytes", 0) or 0
            total_uploaded_bytes += ul_b
            if getattr(t, "is_seeding", False) or (t.status == DownloadStatus.DOWNLOADING and t.progress >= 100.0):
                active_seeding_cnt += 1
            total_peers_cnt += getattr(t, "torrent_peers", 0) or 0

        # Include historical upload credit from database
        try:
            hist_credit = self.db.get_total_upload_credit() if hasattr(self.db, "get_total_upload_credit") else 0
        except Exception:
            hist_credit = 0

        grand_total_uploaded = total_uploaded_bytes + hist_credit

        self.val_speed.setText(f"{format_bytes(total_upload_spd)}/s")
        self.val_credit.setText(format_bytes(grand_total_uploaded))
        self.val_active.setText(f"{active_seeding_cnt} Seeding")
        self.val_peers.setText(f"{total_peers_cnt} Peers")

        # Update active table
        cur_row_count = self.table.rowCount()
        if cur_row_count != len(tasks):
            self.table.setRowCount(len(tasks))

        for row, t in enumerate(tasks):
            # 0: Name
            it_name = self.table.item(row, 0)
            if not it_name:
                it_name = QTableWidgetItem()
                self.table.setItem(row, 0, it_name)
            it_name.setText(t.filename or "Torrent Task")
            it_name.setData(Qt.ItemDataRole.UserRole, t.id)

            # 1: Size
            it_size = self.table.item(row, 1)
            if not it_size:
                it_size = SortableTableWidgetItem("", 0)
                self.table.setItem(row, 1, it_size)
            sz = t.total_bytes if t.total_bytes > 0 else t.downloaded_bytes
            it_size.setText(format_bytes(sz))
            it_size.sort_val = sz

            # 2: Real Uploaded Bytes
            it_ul = self.table.item(row, 2)
            if not it_ul:
                it_ul = SortableTableWidgetItem("", 0)
                self.table.setItem(row, 2, it_ul)
            ul_b = getattr(t, "uploaded_bytes", 0) or 0
            it_ul.setText(format_bytes(ul_b))
            it_ul.sort_val = ul_b
            it_ul.setForeground(QColor("#86efac"))  # Soft mint

            # 3: Real Upload Speed
            it_spd = self.table.item(row, 3)
            if not it_spd:
                it_spd = SortableTableWidgetItem("", 0.0)
                self.table.setItem(row, 3, it_spd)
            ul_spd = getattr(t, "upload_speed", 0.0) or 0.0
            it_spd.setText(f"▲ {format_bytes(ul_spd)}/s" if ul_spd > 0 else "--")
            it_spd.sort_val = ul_spd
            it_spd.setForeground(QColor("#86efac" if ul_spd > 0 else "#64748b"))

            # 4: Share Ratio (Uploaded / Total Size)
            it_ratio = self.table.item(row, 4)
            if not it_ratio:
                it_ratio = SortableTableWidgetItem("", 0.0)
                self.table.setItem(row, 4, it_ratio)
            ratio = (ul_b / sz) if sz > 0 else 0.0
            it_ratio.setText(f"{ratio:.2f}")
            it_ratio.sort_val = ratio
            it_ratio.setForeground(QColor("#38bdf8" if ratio >= 1.0 else "#94a3b8"))

            # 5: Swarm Seeds / Peers
            it_swarm = self.table.item(row, 5)
            if not it_swarm:
                it_swarm = QTableWidgetItem()
                self.table.setItem(row, 5, it_swarm)
            seeds = getattr(t, "torrent_seeds", 0) or 0
            peers = getattr(t, "torrent_peers", 0) or 0
            it_swarm.setText(f"{seeds}S / {peers}P")
            it_swarm.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 6: Masa Seeding
            it_days = self.table.item(row, 6)
            if not it_days:
                it_days = QTableWidgetItem()
                self.table.setItem(row, 6, it_days)
            cfg_days = t.headers.get("seed_duration_days", 3) if t.headers else 3
            it_days.setText(f"{cfg_days} Hari")
            it_days.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 7: Status
            it_stat = self.table.item(row, 7)
            if not it_stat:
                it_stat = QTableWidgetItem()
                self.table.setItem(row, 7, it_stat)
            is_active = bool(self.engine and t.id in getattr(self.engine, "torrent_workers", {}))
            is_seeding = getattr(t, "is_seeding", False) or (is_active and t.progress >= 100.0)
            if is_seeding:
                status_txt = "Seeding"
                status_col = QColor("#10b981")  # Emerald
            elif is_active:
                status_txt = f"Downloading ({t.progress:.1f}%)"
                status_col = QColor("#38bdf8")  # Sky blue
            elif t.status == DownloadStatus.COMPLETED:
                status_txt = "Selesai"
                status_col = QColor("#94a3b8")
            elif t.status == DownloadStatus.PAUSED:
                status_txt = "Dijeda"
                status_col = QColor("#fbbf24")  # Amber
            else:
                status_txt = str(t.status.value if hasattr(t.status, "value") else t.status)
                status_col = QColor("#64748b")
            it_stat.setText(status_txt)
            it_stat.setForeground(status_col)

    def _refresh_leaderboard(self):
        try:
            records = self.db.get_seeder_leaderboard(limit=50) if hasattr(self.db, "get_seeder_leaderboard") else []
        except Exception:
            records = []

        self.leaderboard_table.setRowCount(len(records))
        for row, rec in enumerate(records):
            # 0: Name
            it_name = QTableWidgetItem(rec.get("name", "Torrent"))
            self.leaderboard_table.setItem(row, 0, it_name)

            # 1: Info hash
            ih = rec.get("info_hash", "") or ""
            it_ih = QTableWidgetItem(ih[:12] + "..." if len(ih) > 12 else ih)
            it_ih.setForeground(QColor("#64748b"))
            self.leaderboard_table.setItem(row, 1, it_ih)

            # 2: Total Real Uploaded
            b_rep = rec.get("total_bytes_reported", 0) or 0
            it_rep = SortableTableWidgetItem(format_bytes(b_rep), b_rep)
            it_rep.setForeground(QColor("#86efac"))
            self.leaderboard_table.setItem(row, 2, it_rep)

            # 3: Seeding Duration
            dur_s = rec.get("duration_s", 0.0) or 0.0
            it_dur = SortableTableWidgetItem(format_eta(dur_s) if dur_s > 0 else "--", dur_s)
            it_dur.setForeground(QColor("#cbd5e1"))
            self.leaderboard_table.setItem(row, 3, it_dur)

            # 4: Completed At
            comp_at = rec.get("completed_at", 0.0) or 0.0
            if comp_at > 0:
                t_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(comp_at))
            else:
                t_str = "--"
            it_time = SortableTableWidgetItem(t_str, comp_at)
            it_time.setForeground(QColor("#94a3b8"))
            self.leaderboard_table.setItem(row, 4, it_time)

    def _get_selected_task(self) -> Optional[DownloadTask]:
        row = self.table.currentRow()
        if row < 0 or not self.engine:
            return None
        it = self.table.item(row, 0)
        if not it:
            return None
        task_id = it.data(Qt.ItemDataRole.UserRole)
        return getattr(self.engine, "tasks", {}).get(task_id)

    def _pause_selected(self):
        task = self._get_selected_task()
        if task and self.engine:
            self.engine.pause_download(task.id)
            self._refresh_telemetry()

    def _resume_selected(self):
        task = self._get_selected_task()
        if task and self.engine:
            self.engine.resume_download(task.id)
            self._refresh_telemetry()

    def _edit_selected_days(self):
        task = self._get_selected_task()
        if not task:
            QMessageBox.information(self, "Pilih Torrent", "Silakan pilih salah satu torrent pada tabel.")
            return

        cur_days = task.headers.get("seed_duration_days", 3) if task.headers else 3
        new_days, ok = QInputDialog.getInt(
            self,
            "Masa Seeding BitTorrent",
            f"Tentukan batas durasi seeding (hari) untuk:\n{task.filename}\n\n(Seeding riil ke swarm peers sesuai batas waktu)",
            value=cur_days,
            min=1,
            max=31,
            step=1
        )
        if ok:
            if not task.headers:
                task.headers = {}
            task.headers["seed_duration_days"] = new_days
            if hasattr(self.db, "save_task"):
                self.db.save_task(task)
            if self.engine and task.id in getattr(self.engine, "torrent_workers", {}):
                self.engine.torrent_workers[task.id].seed_duration_days = new_days
            self._refresh_telemetry()

    def _open_selected_folder(self):
        task = self._get_selected_task()
        if not task:
            return
        folder = os.path.dirname(task.save_path) if task.save_path else None
        if folder and os.path.isdir(folder):
            os.startfile(folder)
        else:
            QMessageBox.warning(self, "Folder Tidak Ditemukan", "Folder unduhan belum dibuat atau tidak ditemukan.")


# Backward compatibility alias
TorrentSpooferDialog = TorrentSeedingDialog
