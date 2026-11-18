import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QGridLayout, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QStackedWidget, QCheckBox, QSpinBox
)
from PyQt6.QtGui import QIcon, QColor, QPainter, QBrush, QPen, QLinearGradient
from PyQt6.QtCore import Qt, QTimer, QRectF
from ..core.models import DownloadTask, DownloadStatus
from ..core.downloader import DownloadEngine
from ..utils.helpers import format_bytes, format_speed, format_eta, apply_windows_dark_titlebar


class MultiColorSegmentBar(QWidget):
    """
    Precision Chrome & Dark Soft Slate Connection Segment Visualizer.
    Replaces multi-color rainbow with sleek metallic chrome and titanium tones.
    """
    # Alternating refined chrome / titanium tones for subtle thread distinction
    CHROME_PALETTE = [
        ("#f1f5f9", "#cbd5e1", "#94a3b8", "#64748b"),  # Polished Chrome
        ("#e2e8f0", "#94a3b8", "#64748b", "#475569"),  # Brushed Titanium
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.segments = []
        self.overall_progress = 0.0
        self.is_stream = False
        self.setFixedHeight(12)

    def set_segments(self, segments, overall_progress: float = 0.0, is_stream: bool = False):
        self.segments = segments or []
        self.overall_progress = min(1.0, max(0.0, overall_progress))
        self.is_stream = is_stream
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()

        # Dark soft matte track
        painter.setPen(QPen(QColor("#1e293b"), 1))
        painter.setBrush(QBrush(QColor("#0a0e16")))
        painter.drawRoundedRect(QRectF(0, 0, w - 1, h - 1), 3, 3)

        avail_w = float(w - 4)
        if avail_w <= 0:
            return

        # Check if segments represent real partitioned file ranges
        # or virtual stream / connection slots
        is_partitioned = False
        if self.segments and not self.is_stream:
            starts = [getattr(s, "start_byte", 0) for s in self.segments]
            ends = [getattr(s, "end_byte", 0) for s in self.segments]
            if len(self.segments) > 1 and any(s > 0 for s in starts) and any(e > 1000000 for e in ends):
                is_partitioned = True

        if not is_partitioned:
            # Unified continuous track representing overall file progress
            painter.fillRect(QRectF(2, 2, avail_w, h - 4), QColor("#0f1520"))
            fill_w = max(0.0, avail_w * self.overall_progress)
            if fill_w > 0:
                grad = QLinearGradient(2, 2, 2, h - 2)
                grad.setColorAt(0.0, QColor("#f1f5f9"))
                grad.setColorAt(0.35, QColor("#cbd5e1"))
                grad.setColorAt(0.75, QColor("#94a3b8"))
                grad.setColorAt(1.0, QColor("#64748b"))
                painter.fillRect(QRectF(2, 2, min(fill_w, avail_w), h - 4), grad)
            return

        # Spatial partitioned file ranges (Standard multi-segment HTTP Range download)
        total_bytes = sum(s.total_bytes for s in self.segments)
        if total_bytes <= 0:
            total_bytes = len(self.segments)

        curr_x = 2.0
        for i, seg in enumerate(self.segments):
            seg_w = (seg.total_bytes / total_bytes) * avail_w if total_bytes > 0 else (avail_w / len(self.segments))
            seg_w = max(2.0, seg_w)

            # Slot background (subtle dark graphite)
            painter.fillRect(QRectF(curr_x, 2, seg_w - 1, h - 4), QColor("#0f1520"))

            # Progress fill inside segment using metallic chrome gradient
            prog = seg.progress if hasattr(seg, "progress") else 0.0
            fill_w = max(1.0, seg_w * prog) if prog > 0 else 0

            if fill_w > 0:
                c_top, c_mid, c_low, c_shadow = self.CHROME_PALETTE[i % len(self.CHROME_PALETTE)]
                grad = QLinearGradient(curr_x, 2, curr_x, h - 2)
                grad.setColorAt(0.0, QColor(c_top))
                grad.setColorAt(0.35, QColor(c_mid))
                grad.setColorAt(0.75, QColor(c_low))
                grad.setColorAt(1.0, QColor(c_shadow))
                painter.fillRect(QRectF(curr_x, 2, fill_w - 1, h - 4), grad)

            # 1px divider between threads
            painter.setPen(QPen(QColor("#0a0e16"), 1))
            painter.drawLine(int(curr_x + seg_w - 1), 2, int(curr_x + seg_w - 1), int(h - 3))

            curr_x += seg_w


class DownloadProgressDialog(QDialog):
    """
    Modern Download Progress Dialog faithfully styled after the user's reference mockup:
    - Tab pill bar (Download status, Speed Limiter, Options on completion)
    - Cyan underlined URL
    - Precision telemetry grid (Status, File size, Downloaded, Transfer rate, Time left, Resume pill)
    - Cyan-to-emerald gradient progress bar
    - << Hide details toggle
    - Multi-color connection segments bar
    - Connection stream table (N., Downloaded, Info)
    - Connected thread counter & Vortex version footer
    """
    def __init__(self, task: DownloadTask, engine: DownloadEngine, parent=None):
        super().__init__(parent)
        self.task = task
        self.engine = engine
        self.is_live = (
            getattr(self.task, "is_live", False)
            or (self.task.headers and (
                self.task.headers.get("is_live") in [True, "true", "True", 1, "1"]
                or any(d in str(self.task.headers.get("Referer", "")).lower() for d in ("chaturbate", "stripchat"))
                or any(d in str(self.task.headers.get("master_url", "")).lower() for d in ("chaturbate", "stripchat", "mmcdn", "doppiocdn"))
            ))
            or any(d in (self.task.url or "").lower() for d in ("chaturbate.com", "stripchat.com", "cb.live", "mmcdn.com", "highwebmedia.com", "doppiocdn", "stripcdn"))
        )
        import re
        self.clean_filename = re.sub(r'^\d+%\s*', '', self.task.filename)
        if self.is_live:
            self.setWindowTitle(f"Merekam Live - {self.clean_filename}")
        else:
            self.setWindowTitle(f"{int(task.progress)}% - {self.clean_filename}")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumWidth(540)
        self.setMinimumHeight(440)
        self.resize(560, 480)
        apply_windows_dark_titlebar(self)
        self.setStyleSheet("""
            QDialog {
                background-color: #070a0f;
                border: 1px solid #1b273d;
                border-radius: 8px;
            }
            QLabel {
                font-family: 'Inter', -apple-system, sans-serif;
                color: #cbd5e1;
                font-size: 12px;
            }
        """)

        # Set Window Icon
        logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "logo_32.png"))
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.details_visible = True
        self._expanded_height = 480
        self._init_ui()

        # Update timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_stats)
        self.timer.start(250)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(12)

        # Retain self.lbl_title_text in memory for stats update compatibility without rendering duplicate header
        self.lbl_title_text = QLabel(f"{int(self.task.progress)}% {self.clean_filename}")

        # 2. Top Pill Tab Bar (Download status, Speed Limiter, Options on completion)
        tab_bar = QHBoxLayout()
        tab_bar.setSpacing(6)

        self.btn_tab_status = QPushButton("●  Download status")
        self.btn_tab_limiter = QPushButton("Speed Limiter")
        self.btn_tab_options = QPushButton("Options on completion")

        for b in [self.btn_tab_status, self.btn_tab_limiter, self.btn_tab_options]:
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #94a3b8;
                    border: 1px solid transparent;
                    border-radius: 4px;
                    padding: 5px 12px;
                    font-size: 11px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #0b0f17;
                    color: #e2e8f0;
                }
            """)

        self.btn_tab_status.setStyleSheet("""
            QPushButton {
                background-color: #0f1724;
                color: #f1f5f9;
                border: 1px solid #1b273d;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 600;
            }
        """)

        tab_bar.addWidget(self.btn_tab_status)
        tab_bar.addWidget(self.btn_tab_limiter)
        tab_bar.addWidget(self.btn_tab_options)
        tab_bar.addStretch()
        main_layout.addLayout(tab_bar)

        self.btn_tab_status.clicked.connect(lambda: self._switch_tab(0))
        self.btn_tab_limiter.clicked.connect(lambda: self._switch_tab(1))
        self.btn_tab_options.clicked.connect(lambda: self._switch_tab(2))

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        # --- Page 0: Main Download Status ---
        page_status = QWidget()
        page_status_layout = QVBoxLayout(page_status)
        page_status_layout.setContentsMargins(0, 4, 0, 0)
        page_status_layout.setSpacing(10)

        # URL with cyan text & subtle underline
        url_box = QHBoxLayout()
        lbl_url_tag = QLabel("URL:")
        lbl_url_tag.setStyleSheet("color: #64748b; font-family: 'JetBrains Mono', monospace; font-size: 11px;")
        lbl_url_tag.setFixedWidth(36)

        self.lbl_url_val = QLabel(self.task.url)
        self.lbl_url_val.setStyleSheet("""
            color: #94a3b8;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            border-bottom: 1px solid #1e293b;
            padding-bottom: 2px;
        """)
        self.lbl_url_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        url_box.addWidget(lbl_url_tag)
        url_box.addWidget(self.lbl_url_val, 1)
        page_status_layout.addLayout(url_box)

        # Telemetry Grid (Status, Size, Downloaded, Transfer rate, Time left, Resume)
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setColumnMinimumWidth(0, 115)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)
        grid.addWidget(QWidget(), 0, 2)

        # Col 0: Label (compact width), Col 1: Value (aligned directly next to label), Col 2: Stretch
        lbl_st = QLabel("Status")
        lbl_st.setFixedWidth(115)
        lbl_st.setStyleSheet("color: #94a3b8; font-size: 11px;")
        grid.addWidget(lbl_st, 0, 0)
        self.val_status = QLabel("Receiving data...")
        self.val_status.setStyleSheet("color: #cbd5e1; font-family: 'JetBrains Mono', monospace; font-weight: 500; font-size: 11px;")
        grid.addWidget(self.val_status, 0, 1)

        lbl_sz = QLabel("File size")
        lbl_sz.setFixedWidth(115)
        lbl_sz.setStyleSheet("color: #94a3b8; font-size: 11px;")
        grid.addWidget(lbl_sz, 1, 0)
        self.val_size = QLabel(format_bytes(self.task.total_bytes))
        self.val_size.setStyleSheet("color: #f1f5f9; font-family: 'JetBrains Mono', monospace; font-size: 11px;")
        grid.addWidget(self.val_size, 1, 1)

        lbl_dl = QLabel("Downloaded")
        lbl_dl.setFixedWidth(115)
        lbl_dl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        grid.addWidget(lbl_dl, 2, 0)
        self.val_downloaded = QLabel("0 MB ( 0.0 % )")
        self.val_downloaded.setStyleSheet("color: #f1f5f9; font-family: 'JetBrains Mono', monospace; font-size: 11px;")
        grid.addWidget(self.val_downloaded, 2, 1)

        lbl_rate = QLabel("Transfer rate")
        lbl_rate.setFixedWidth(115)
        lbl_rate.setStyleSheet("color: #94a3b8; font-size: 11px;")
        grid.addWidget(lbl_rate, 3, 0)
        self.val_speed = QLabel("0 KB/sec")
        self.val_speed.setStyleSheet("color: #f1f5f9; font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 11px;")
        grid.addWidget(self.val_speed, 3, 1)

        lbl_tl = QLabel("Time left")
        lbl_tl.setFixedWidth(115)
        lbl_tl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        grid.addWidget(lbl_tl, 4, 0)
        self.val_eta = QLabel("--:--")
        self.val_eta.setStyleSheet("color: #cbd5e1; font-family: 'JetBrains Mono', monospace; font-size: 11px;")
        grid.addWidget(self.val_eta, 4, 1)

        lbl_res = QLabel("Resume capability")
        lbl_res.setFixedWidth(115)
        lbl_res.setStyleSheet("color: #94a3b8; font-size: 11px;")
        grid.addWidget(lbl_res, 5, 0)
        self.val_resume = QLabel("Yes" if self.task.resumable else "No")
        self.val_resume.setStyleSheet("""
            background-color: #1a2230;
            color: #e2e8f0;
            border: 1px solid #27344a;
            border-radius: 3px;
            padding: 1px 8px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 10px;
            font-weight: 600;
        """ if self.task.resumable else """
            background-color: #141a24;
            color: #94a3b8;
            border: 1px solid #1e293b;
            border-radius: 3px;
            padding: 1px 8px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 10px;
            font-weight: 600;
        """)
        self.val_resume.setFixedWidth(42)
        self.val_resume.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self.val_resume, 5, 1)

        page_status_layout.addLayout(grid)

        # Precision Metallic Chrome Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #090d14;
                border: 1px solid #1e293b;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f1f5f9, stop:0.3 #cbd5e1, stop:0.75 #94a3b8, stop:1 #64748b);
                border-radius: 3px;
            }
        """)
        page_status_layout.addWidget(self.progress_bar)

        # Action Buttons Row (Hide details, Pause, Cancel)
        action_bar = QHBoxLayout()
        self.btn_toggle_details = QPushButton("<< Hide details")
        self.btn_toggle_details.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_details.setStyleSheet("""
            QPushButton {
                background-color: #111722;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #1a2334;
                color: #f1f5f9;
                border-color: #334155;
            }
        """)
        self.btn_toggle_details.clicked.connect(self._toggle_details)
        action_bar.addWidget(self.btn_toggle_details)
        action_bar.addStretch()

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 6px 18px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
                border-color: #475569;
            }
        """)
        self.btn_pause.clicked.connect(self._toggle_pause)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #111722;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-radius: 4px;
                padding: 6px 18px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1e2433;
                color: #f1f5f9;
                border-color: #334155;
            }
        """)
        self.btn_cancel.clicked.connect(self._cancel_download)

        self.btn_refresh = QPushButton("Refresh URL")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setToolTip("Perbarui link/token yang kedaluwarsa tanpa mengulang unduhan")
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #0f1724;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)
        self.btn_refresh.clicked.connect(self._open_refresh_dialog)
        self.btn_refresh.setVisible(self.task.status != DownloadStatus.COMPLETED)

        action_bar.addWidget(self.btn_refresh)
        action_bar.addWidget(self.btn_pause)
        action_bar.addWidget(self.btn_cancel)
        page_status_layout.addLayout(action_bar)

        # Connection Segments Detail Area
        self.details_container = QWidget()
        details_layout = QVBoxLayout(self.details_container)
        details_layout.setContentsMargins(0, 6, 0, 0)
        details_layout.setSpacing(6)

        lbl_conn_title = QLabel("Start positions and download progress by connections")
        lbl_conn_title.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        details_layout.addWidget(lbl_conn_title)

        # Multi-color Segment Bar
        self.segment_bar = MultiColorSegmentBar()
        details_layout.addWidget(self.segment_bar)

        # Connection Stream Table (N., Downloaded, Info)
        self.conn_table = QTableWidget()
        self.conn_table.setColumnCount(3)
        self.conn_table.setHorizontalHeaderLabels(["N.", "Downloaded", "Info"])
        self.conn_table.verticalHeader().setVisible(False)
        self.conn_table.setFixedHeight(120)
        self.conn_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.conn_table.setColumnWidth(0, 36)
        self.conn_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.conn_table.setColumnWidth(1, 140)
        self.conn_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.conn_table.setStyleSheet("""
            QTableWidget {
                background-color: #05070b;
                border: 1px solid #151f30;
                border-radius: 4px;
                gridline-color: #0b0f17;
                font-family: 'JetBrains Mono', monospace;
                font-size: 11px;
            }
            QTableWidget::item:selected {
                background-color: #1e3a5f;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #070a0f;
                color: #64748b;
                padding: 4px 6px;
                border: none;
                border-bottom: 1px solid #151f30;
                font-size: 10px;
                font-weight: 600;
            }
        """)
        details_layout.addWidget(self.conn_table)

        page_status_layout.addWidget(self.details_container)
        page_status_layout.addStretch(1)
        self.stack.addWidget(page_status)

        # --- Page 1: Speed Limiter Tab ---
        page_limiter = QWidget()
        limiter_layout = QVBoxLayout(page_limiter)
        limiter_layout.setContentsMargins(12, 12, 12, 12)
        limiter_layout.setSpacing(12)

        self.chk_enable_limit = QCheckBox("Enable Speed Limiter for this download")
        self.chk_enable_limit.setStyleSheet("color: #f1f5f9; font-weight: 600;")
        limiter_layout.addWidget(self.chk_enable_limit)

        row_limit = QHBoxLayout()
        lbl_limit = QLabel("Maximum download speed:")
        lbl_limit.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        self.spn_limit_val = QSpinBox()
        self.spn_limit_val.setRange(10, 500000)
        self.spn_limit_val.setValue(1024)
        self.spn_limit_val.setSuffix(" KB/s")
        self.spn_limit_val.setFixedWidth(120)
        self.spn_limit_val.setEnabled(False)
        self.chk_enable_limit.toggled.connect(self.spn_limit_val.setEnabled)
        row_limit.addWidget(lbl_limit)
        row_limit.addWidget(self.spn_limit_val)
        row_limit.addStretch()
        limiter_layout.addLayout(row_limit)
        limiter_layout.addStretch()
        self.stack.addWidget(page_limiter)

        # --- Page 2: Options on completion Tab ---
        page_options = QWidget()
        options_layout = QVBoxLayout(page_options)
        options_layout.setContentsMargins(12, 12, 12, 12)
        options_layout.setSpacing(12)

        self.chk_opt_hangup = QCheckBox("Disconnect internet connection when done")
        self.chk_opt_hangup.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        self.chk_opt_shutdown = QCheckBox("Turn off computer when done")
        self.chk_opt_shutdown.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        self.chk_opt_force = QCheckBox("Force processes to close on shutdown")
        self.chk_opt_force.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        self.chk_opt_dialog = QCheckBox("Show download complete dialog")
        self.chk_opt_dialog.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        self.chk_opt_dialog.setChecked(True)

        options_layout.addWidget(self.chk_opt_hangup)
        options_layout.addWidget(self.chk_opt_shutdown)
        options_layout.addWidget(self.chk_opt_force)
        options_layout.addWidget(self.chk_opt_dialog)
        options_layout.addStretch()
        self.stack.addWidget(page_options)

        footer = QHBoxLayout()
        conn_indicator = QHBoxLayout()
        conn_indicator.setSpacing(6)
        dot_conn = QLabel()
        dot_conn.setFixedSize(6, 6)
        dot_conn.setStyleSheet("background-color: #86efac; border-radius: 3px;")
        conn_indicator.addWidget(dot_conn)

        self.lbl_conn_count = QLabel("Connected: 8 threads")
        self.lbl_conn_count.setStyleSheet("color: #94a3b8; font-family: 'JetBrains Mono', monospace; font-size: 11px;")
        conn_indicator.addWidget(self.lbl_conn_count)
        footer.addLayout(conn_indicator)

        footer.addStretch()

        lbl_brand = QLabel("Zero v2.6")
        lbl_brand.setStyleSheet("color: #475569; font-family: 'JetBrains Mono', monospace; font-size: 10px;")
        footer.addWidget(lbl_brand)

        main_layout.addLayout(footer)

    def _switch_tab(self, index: int):
        self.stack.setCurrentIndex(index)
        buttons = [self.btn_tab_status, self.btn_tab_limiter, self.btn_tab_options]
        for i, b in enumerate(buttons):
            if i == index:
                b.setStyleSheet("""
                    QPushButton {
                        background-color: #0f1724;
                        color: #f1f5f9;
                        border: 1px solid #1b273d;
                        border-radius: 4px;
                        padding: 5px 12px;
                        font-size: 11px;
                        font-weight: 600;
                    }
                """)
            else:
                b.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #94a3b8;
                        border: 1px solid transparent;
                        border-radius: 4px;
                        padding: 5px 12px;
                        font-size: 11px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background-color: #0b0f17;
                        color: #e2e8f0;
                    }
                """)

    def _toggle_details(self):
        self.details_visible = not self.details_visible
        self.details_container.setVisible(self.details_visible)
        self.btn_toggle_details.setText("<< Hide details" if self.details_visible else ">> Show details")

        # If the window is maximized, simply show/hide the container without altering window geometry
        if self.isMaximized():
            return

        if not self.details_visible:
            self._expanded_height = max(self.height(), 440)
            self.setMinimumHeight(260)
            target_h = max(260, self._expanded_height - 180)
            self.resize(self.width(), target_h)
        else:
            self.setMinimumHeight(440)
            target_h = getattr(self, "_expanded_height", 480)
            self.resize(self.width(), target_h)

    def _open_refresh_dialog(self):
        from .refresh_url_dialog import RefreshUrlDialog
        dlg = RefreshUrlDialog(task=self.task, engine=self.engine, parent=self)
        if dlg.exec():
            self._refresh_stats()

    def _refresh_stats(self):
        if hasattr(self, "btn_refresh"):
            self.btn_refresh.setVisible(self.task.status != DownloadStatus.COMPLETED)

        # Dynamically detect if worker switched to live stream mode
        if not self.is_live:
            if getattr(self.task, "headers", None) and (
                self.task.headers.get("is_live") in ["true", True, 1, "1"]
                or any(d in str(self.task.headers.get("Referer", "")).lower() for d in ("chaturbate", "stripchat"))
                or any(d in str(self.task.headers.get("master_url", "")).lower() for d in ("chaturbate", "stripchat", "mmcdn", "doppiocdn"))
            ):
                self.is_live = True
            elif any(d in (self.task.url or "").lower() for d in ("chaturbate.com", "stripchat.com", "cb.live", "mmcdn.com", "highwebmedia.com", "doppiocdn", "stripcdn")):
                self.is_live = True

        # Update Title & Progress
        pct = self.task.progress
        is_downloading = (self.task.status == DownloadStatus.DOWNLOADING)

        if self.is_live:
            if is_downloading:
                if getattr(self, "_finishing_live", False):
                    self.lbl_title_text.setText(f"Menyimpan Rekaman: {self.clean_filename} ({format_bytes(self.task.downloaded_bytes)})")
                    self.setWindowTitle(f"Menyimpan Video - {self.clean_filename}")
                    self.val_status.setText("Menyelesaikan & menyimpan ke MP4/WebM...")
                    self.val_status.setStyleSheet("color: #f59e0b; font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 11px;")
                    self.btn_pause.setText("Menyimpan...")
                    self.btn_pause.setEnabled(False)
                else:
                    self.lbl_title_text.setText(f"Merekam Siaran Langsung: {self.clean_filename} ({format_bytes(self.task.downloaded_bytes)})")
                    self.setWindowTitle(f"Merekam Live - {self.clean_filename}")
                    if self.progress_bar.maximum() != 0:
                        self.progress_bar.setRange(0, 0)
                    status_text = "Merekam siaran langsung..."
                    self.val_status.setText(status_text)
                    self.val_status.setStyleSheet("color: #f87171; font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 11px;")
                    self.val_size.setText("Live Broadcast")
                    self.val_downloaded.setText(format_bytes(self.task.downloaded_bytes))
                    self.val_eta.setText("Live (Merekam)")
                    self.val_resume.setText("Live HLS")
                    self.btn_pause.setEnabled(True)
                    self.btn_pause.setText("Selesai & Simpan")
                    self.btn_pause.setStyleSheet("""
                        QPushButton {
                            background-color: #7f1d1d;
                            color: #fecaca;
                            border: 1px solid #991b1b;
                            border-radius: 4px;
                            padding: 6px 18px;
                            font-size: 11px;
                            font-weight: 600;
                        }
                        QPushButton:hover {
                            background-color: #991b1b;
                            color: #ffffff;
                        }
                    """)
            elif self.task.status == DownloadStatus.COMPLETED:
                self._finishing_live = False
                self.clean_filename = os.path.basename(self.task.save_path or self.task.filename)
                self.btn_pause.setEnabled(True)
                self.lbl_title_text.setText(f"Rekaman Tersimpan: {self.clean_filename}")
                self.setWindowTitle(f"Rekaman Selesai - {self.clean_filename}")
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(100)
                self.val_status.setText("Selesai & Tersimpan")
                self.val_status.setStyleSheet("color: #86efac; font-weight: 600;")
                self.val_downloaded.setText(format_bytes(self.task.downloaded_bytes))
                self.val_eta.setText("Complete")
                self.btn_pause.setText("Buka File Video")
                self.btn_pause.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2b3648, stop:1 #1e2635);
                        color: #f8fafc;
                        border: 1px solid rgba(255, 255, 255, 0.2);
                        border-radius: 4px;
                        padding: 6px 18px;
                        font-size: 11px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #37455c, stop:1 #273347);
                        color: #ffffff;
                    }
                """)
                self.btn_cancel.setText("Close")
                self.timer.stop()
            else:
                self.lbl_title_text.setText(f"{self.clean_filename}")
                self.setWindowTitle(self.clean_filename)
                self.val_status.setText(self.task.status.value)
                self.val_status.setStyleSheet("color: #94a3b8;")
                self.val_downloaded.setText(format_bytes(self.task.downloaded_bytes))
        else:
            if self.task.total_bytes > 0:
                self.lbl_title_text.setText(f"{int(pct)}% {self.clean_filename}")
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(int(pct))
                if self.task.status == DownloadStatus.DOWNLOADING:
                    self.setWindowTitle(f"{int(pct)}% - {self.clean_filename}")
                elif self.task.status == DownloadStatus.COMPLETED:
                    self.setWindowTitle(f"Download Complete - {self.clean_filename}")
                else:
                    self.setWindowTitle(self.clean_filename)
            else:
                if is_downloading:
                    self.lbl_title_text.setText(f"Downloading: {self.clean_filename} ({format_bytes(self.task.downloaded_bytes)})")
                    self.setWindowTitle(f"Downloading - {self.clean_filename}")
                    if self.progress_bar.maximum() != 0:
                        self.progress_bar.setRange(0, 0)
                elif self.task.status == DownloadStatus.COMPLETED:
                    self.lbl_title_text.setText(f"Download Complete: {self.clean_filename}")
                    self.setWindowTitle(f"Download Complete - {self.clean_filename}")
                    self.progress_bar.setRange(0, 100)
                    self.progress_bar.setValue(100)
                else:
                    self.lbl_title_text.setText(self.clean_filename)
                    self.setWindowTitle(self.clean_filename)

            # Status & Downloaded
            is_tor = bool(getattr(self.task, "is_torrent", False) or (self.task.url and (self.task.url.startswith("magnet:") or self.task.url.lower().endswith(".torrent"))))
            if self.task.status == DownloadStatus.ERROR:
                err_msg = getattr(self.task, "error_message", None)
                if err_msg and ("11001" in err_msg or "getaddrinfo" in err_msg):
                    status_text = "Error: Server / Host tidak ditemukan (DNS Error)"
                elif err_msg:
                    status_text = f"Error: {err_msg}"
                else:
                    status_text = "Error"
                self.val_status.setText(status_text)
                self.val_status.setStyleSheet("color: #ef4444; font-weight: 500;")
            elif is_tor:
                if is_downloading:
                    seeds = getattr(self.task, "torrent_seeds", 0)
                    peers = getattr(self.task, "torrent_peers", 0)
                    tracker_st = getattr(self.task, "tracker_status", "")
                    if seeds > 0 or peers > 0:
                        status_text = f"Swarm Active ({seeds} seeds, {peers} peers)"
                        self.val_status.setStyleSheet("color: #10b981;")
                    elif tracker_st:
                        status_text = tracker_st
                        self.val_status.setStyleSheet("color: #f59e0b; font-weight: 500;")
                    else:
                        status_text = "Connecting to Swarm (DHT / Trackers)..."
                        self.val_status.setStyleSheet("color: #cbd5e1;")
                elif self.task.status == DownloadStatus.CONNECTING:
                    status_text = "Connecting to BitTorrent Swarm..."
                    self.val_status.setStyleSheet("color: #cbd5e1;")
                elif self.task.status == DownloadStatus.COMPLETED:
                    status_text = "Finished (Seeding)"
                    self.val_status.setStyleSheet("color: #10b981; font-weight: 600;")
                else:
                    status_text = self.task.status.value
                    self.val_status.setStyleSheet("color: #94a3b8;")
                self.val_status.setText(status_text)
            elif is_downloading:
                if self.task.speed > 0:
                    status_text = "Receiving data..."
                    self.val_status.setText(status_text)
                    self.val_status.setStyleSheet("color: #10b981;")
                else:
                    active_seg_status = None
                    if hasattr(self.task, "segments") and self.task.segments:
                        for s in self.task.segments:
                            if s.status and s.status not in ["Idle", "Send GET...", "Receiving data"]:
                                active_seg_status = s.status
                                break
                    if active_seg_status:
                        status_text = active_seg_status
                    elif self.task.downloaded_bytes > 0:
                        status_text = "Connecting to stream..." if (self.is_live or getattr(self.task, "is_hls", False) or ".m3u8" in (self.task.url or "").lower()) else "Waiting for data..."
                    else:
                        status_text = "Connecting..."
                    self.val_status.setText(status_text)
                    self.val_status.setStyleSheet("color: #38bdf8;")
            elif self.task.status == DownloadStatus.CONNECTING:
                status_text = "Connecting..."
                self.val_status.setText(status_text)
                self.val_status.setStyleSheet("color: #cbd5e1;")
            else:
                status_text = self.task.status.value
                self.val_status.setText(status_text)
                self.val_status.setStyleSheet("color: #94a3b8;")

            if self.task.total_bytes > 0:
                dl_str = format_bytes(self.task.downloaded_bytes)
                self.val_size.setText(format_bytes(self.task.total_bytes))
            else:
                dl_str = format_bytes(self.task.downloaded_bytes)
                if is_tor:
                    sz_str = "BitTorrent Swarm"
                elif getattr(self, "is_hls", False) or getattr(self.task, "is_hls", False) or ".m3u8" in (self.task.url or "").lower():
                    sz_str = "Stream (Auto MP4)"
                else:
                    sz_str = "Unknown"
                self.val_size.setText(sz_str)
            self.val_downloaded.setText(dl_str)

            # Resume capability dynamic update
            is_resumable = bool(self.task.resumable)
            self.val_resume.setText("Yes" if is_resumable else "No")
            self.val_resume.setStyleSheet("""
                background-color: #1a2230;
                color: #e2e8f0;
                border: 1px solid #27344a;
                border-radius: 3px;
                padding: 1px 8px;
                font-family: 'JetBrains Mono', monospace;
                font-size: 10px;
                font-weight: 600;
            """ if is_resumable else """
                background-color: #141a24;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-radius: 3px;
                padding: 1px 8px;
                font-family: 'JetBrains Mono', monospace;
                font-size: 10px;
                font-weight: 600;
            """)

        # Transfer rate & ETA
        if is_downloading:
            if getattr(self.task, "is_torrent", False):
                speed_str = f"↓ {format_speed(self.task.speed)}"
                if getattr(self.task, "upload_speed", 0) > 0:
                    speed_str += f"  ↑ {format_speed(self.task.upload_speed)}"
            else:
                speed_str = f"{format_speed(self.task.speed)}"
        else:
            speed_str = "0 KB/sec"
        self.val_speed.setText(speed_str)
        if not self.is_live or not is_downloading:
            eta_str = f"{format_eta(self.task.eta)}" if is_downloading else ("Complete" if self.task.status == DownloadStatus.COMPLETED else "--:--")
            self.val_eta.setText(eta_str)

        # Connection stream count
        if getattr(self.task, "is_torrent", False):
            seeds = getattr(self.task, "torrent_seeds", 0)
            peers = getattr(self.task, "torrent_peers", 0)
            self.lbl_conn_count.setText(f"Swarm: {seeds} seeds, {peers} peers")
        elif self.is_live:
            self.lbl_conn_count.setText("Live Stream: FFmpeg Direct Remux")
        else:
            conn_cnt = len(self.task.segments) if self.task.segments else (self.task.connections or 1)
            self.lbl_conn_count.setText(f"Connected: {conn_cnt} threads")

        # Segments Bar with accurate contiguous progress for streams
        tot_b = self.task.total_bytes if (self.task.total_bytes and self.task.total_bytes > 0) else 0
        overall_prog = (self.task.downloaded_bytes / tot_b) if tot_b > 0 else (self.task.progress / 100.0)
        is_stream_task = bool(self.is_live or getattr(self.task, "is_hls", False) or getattr(self.task, "is_ytdlp", False) or ".m3u8" in (self.task.url or "").lower())
        self.segment_bar.set_segments(self.task.segments, overall_progress=overall_prog, is_stream=is_stream_task)

        # Update Connection Table (Real-time thread activity, never stuck at 'Send GET...')
        if self.task.segments:
            if self.conn_table.rowCount() != len(self.task.segments):
                self.conn_table.setRowCount(len(self.task.segments))

            for i, seg in enumerate(self.task.segments):
                # Col 0: N.
                it_num = QTableWidgetItem(str(seg.index + 1))
                it_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it_num.setForeground(QColor("#94a3b8"))
                self.conn_table.setItem(i, 0, it_num)

                # Col 1: Downloaded
                dl_kb = seg.downloaded_bytes / 1024.0
                if seg.downloaded_bytes > 0 and dl_kb < 1.0:
                    dl_text = f"{seg.downloaded_bytes} B"
                else:
                    dl_text = f"{dl_kb:,.0f} KB"
                it_dl = QTableWidgetItem(dl_text)
                it_dl.setForeground(QColor("#cbd5e1"))
                self.conn_table.setItem(i, 1, it_dl)

                # Col 2: Info
                if is_downloading:
                    if seg.status and seg.status not in ["Idle", "Send GET..."]:
                        if "Receiving" in seg.status and self.task.speed <= 0:
                            seg_info = "Connecting..."
                        else:
                            seg_info = seg.status
                    elif self.task.speed > 0 and (seg.downloaded_bytes > 0 or seg.progress > 0):
                        seg_info = "Receiving data"
                    else:
                        seg_info = "Connecting..."
                else:
                    if self.task.status == DownloadStatus.COMPLETED:
                        seg_info = "Completed"
                    elif self.task.status == DownloadStatus.PAUSED:
                        seg_info = "Paused"
                    else:
                        seg_info = seg.status or "Idle"

                it_info = QTableWidgetItem(seg_info)
                if "Receiving" in seg_info:
                    it_info.setForeground(QColor("#e2e8f0"))
                elif "Completed" in seg_info:
                    it_info.setForeground(QColor("#cbd5e1"))
                elif "Connecting" in seg_info:
                    it_info.setForeground(QColor("#94a3b8"))
                else:
                    it_info.setForeground(QColor("#64748b"))
                self.conn_table.setItem(i, 2, it_info)

        # Pause / Resume Button State (non-live)
        if not self.is_live:
            if self.task.status in [DownloadStatus.PAUSED, DownloadStatus.QUEUED, DownloadStatus.CANCELED]:
                self.btn_pause.setText("Resume")
            elif self.task.status == DownloadStatus.ERROR:
                self.btn_pause.setText("Retry")
            elif self.task.status == DownloadStatus.DOWNLOADING:
                self.btn_pause.setText("Pause")

        # Completion Handling
        if self.task.status == DownloadStatus.COMPLETED:
            if not self.is_live:
                self.btn_pause.setText("Open File")
            self.btn_cancel.setText("Close")
            self.timer.stop()

    def _toggle_pause(self):
        if self.task.status == DownloadStatus.COMPLETED:
            if os.path.exists(self.task.save_path):
                os.startfile(self.task.save_path)
            return

        if self.task.status == DownloadStatus.DOWNLOADING:
            if self.is_live:
                self._finishing_live = True
                self.val_status.setText("Menyelesaikan & menyimpan ke MP4/WebM...")
                self.btn_pause.setText("Menyimpan...")
                self.btn_pause.setEnabled(False)
            self.engine.pause_download(self.task.id)
            if not self.is_live:
                self.btn_pause.setText("Resume")
        else:
            self.engine.start_download(self.task.id)
            if not self.is_live:
                self.btn_pause.setText("Pause")

    def closeEvent(self, event):
        if self.task.status == DownloadStatus.DOWNLOADING:
            self.engine.pause_download(self.task.id)
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        event.accept()

    def _cancel_download(self):
        if self.task.status == DownloadStatus.DOWNLOADING:
            if self.is_live:
                self._toggle_pause()
                return
            self.engine.cancel_download(self.task.id)
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        self.close()