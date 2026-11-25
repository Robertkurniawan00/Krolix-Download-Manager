"""
Krolix Download Manager - Live Stream Watchlist & Auto-Recorder Dialog
Provides a dark Fluent UI for managing monitored streamers/channels,
configuring check intervals, quality preferences, and instant live capture.
"""

import os
import time
import subprocess
import sys
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QMessageBox, QFrame,
    QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from ..core.stream_watchlist import StreamWatchlistManager, parse_stream_target
from ..utils.helpers import apply_windows_dark_titlebar, sanitize_filename
from . import fluent_icons


class WatchlistDialog(QDialog):
    """Fluent Dark UI Manager for Live Stream Watchlist & Auto-Recorder."""

    refresh_requested = pyqtSignal()

    def __init__(self, watchlist_mgr: StreamWatchlistManager, parent=None):
        super().__init__(parent)
        self.watchlist_mgr = watchlist_mgr
        self.db = watchlist_mgr.db

        self.setWindowTitle("Live Stream Watchlist & Auto-Recorder")
        self.setWindowIcon(fluent_icons.create_fluent_live_icon("#f43f5e"))
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(980, 620)
        self.setMinimumSize(820, 500)
        apply_windows_dark_titlebar(self)

        self._setup_ui()
        self._load_settings()
        self.refresh_table()

        self.refresh_requested.connect(self.refresh_table)
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(2500)
        self._ui_timer.timeout.connect(self.refresh_table)
        self._ui_timer.start()

    def showEvent(self, event):
        if hasattr(self, "_ui_timer") and self._ui_timer and not self._ui_timer.isActive():
            self._ui_timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        if hasattr(self, "_ui_timer") and self._ui_timer:
            self._ui_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        if hasattr(self, "_ui_timer") and self._ui_timer:
            self._ui_timer.stop()
        super().closeEvent(event)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # 1. Header Banner
        header = QHBoxLayout()
        header.setSpacing(12)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(fluent_icons.create_fluent_live_icon("#f43f5e").pixmap(34, 34))
        header.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        lbl_title = QLabel("Live Stream Watchlist & Auto-Recorder")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        lbl_sub = QLabel(
            "Pantau channel favorit (Chaturbate, Stripchat, Twitch, YouTube, Kick, atau HLS .m3u8) "
            "dan rekam otomatis saat siaran langsung dimulai."
        )
        lbl_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")
        title_col.addWidget(lbl_title)
        title_col.addWidget(lbl_sub)
        header.addLayout(title_col, 1)
        root.addLayout(header)

        # 2. Global Monitor Controls Bar
        ctrl_card = QFrame()
        ctrl_card.setStyleSheet(
            "QFrame { background-color: #0e131d; border: 1px solid #1f2937; border-radius: 8px; }"
            "QLabel { border: none; background: transparent; color: #cbd5e1; font-size: 12px; }"
            "QCheckBox { border: none; background: transparent; color: #f8fafc; font-weight: 600; font-size: 12px; }"
        )
        ctrl_lay = QHBoxLayout(ctrl_card)
        ctrl_lay.setContentsMargins(12, 10, 12, 10)
        ctrl_lay.setSpacing(14)

        self.chk_global_enable = QCheckBox("Aktifkan Auto-Monitor Latar Belakang")
        self.chk_global_enable.toggled.connect(self._on_global_toggle)
        ctrl_lay.addWidget(self.chk_global_enable)

        ctrl_lay.addWidget(QLabel("Interval Cek:"))
        self.cmb_interval = QComboBox()
        self.cmb_interval.addItem("30 detik", 30)
        self.cmb_interval.addItem("60 detik", 60)
        self.cmb_interval.addItem("2 menit", 120)
        self.cmb_interval.addItem("5 menit", 300)
        self.cmb_interval.currentIndexChanged.connect(self._on_interval_changed)
        ctrl_lay.addWidget(self.cmb_interval)

        ctrl_lay.addWidget(QLabel("Max Rekaman Aktif:"))
        self.spn_max_rec = QSpinBox()
        self.spn_max_rec.setRange(1, 8)
        self.spn_max_rec.setFixedWidth(56)
        self.spn_max_rec.valueChanged.connect(self._on_max_rec_changed)
        ctrl_lay.addWidget(self.spn_max_rec)

        ctrl_lay.addStretch(1)

        self.btn_check_all = QPushButton("Cek Semua Sekarang")
        self.btn_check_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check_all.setStyleSheet(
            "QPushButton { background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155; "
            "border-radius: 6px; padding: 6px 14px; font-weight: 600; font-size: 12px; }"
            "QPushButton:hover { background-color: #334155; color: #ffffff; }"
        )
        self.btn_check_all.clicked.connect(self._on_check_all_clicked)
        ctrl_lay.addWidget(self.btn_check_all)
        root.addWidget(ctrl_card)

        # 3. Quick-Add Channel Card
        add_card = QFrame()
        add_card.setStyleSheet(
            "QFrame { background-color: #0e131d; border: 1px solid #1f2937; border-radius: 8px; }"
            "QLabel { border: none; background: transparent; color: #94a3b8; font-size: 11px; font-weight: 600; }"
            "QCheckBox { border: none; background: transparent; color: #cbd5e1; font-size: 12px; }"
        )
        add_vbox = QVBoxLayout(add_card)
        add_vbox.setContentsMargins(12, 10, 12, 10)
        add_vbox.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("URL Channel atau username (mis. https://chaturbate.com/nama/, stripchat:nama, twitch.tv/nama, .m3u8)")
        self.txt_url.setMinimumHeight(32)
        self.txt_url.returnPressed.connect(self._on_add_clicked)
        row1.addWidget(self.txt_url, 3)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Nama tampilan (opsional)")
        self.txt_name.setMinimumHeight(32)
        self.txt_name.setMaximumWidth(190)
        row1.addWidget(self.txt_name, 1)

        self.cmb_quality = QComboBox()
        self.cmb_quality.setMinimumHeight(32)
        self.cmb_quality.addItem("Best (Tertinggi)", "best")
        self.cmb_quality.addItem("1080p", "1080p")
        self.cmb_quality.addItem("720p", "720p")
        self.cmb_quality.addItem("480p", "480p")
        row1.addWidget(self.cmb_quality)

        self.btn_add = QPushButton("+ Tambah ke Watchlist")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setMinimumHeight(32)
        self.btn_add.setStyleSheet(
            "QPushButton { background-color: #10b981; color: #052e16; border: none; "
            "border-radius: 6px; padding: 6px 16px; font-weight: 700; font-size: 12px; }"
            "QPushButton:hover { background-color: #34d399; }"
        )
        self.btn_add.clicked.connect(self._on_add_clicked)
        row1.addWidget(self.btn_add)
        add_vbox.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel("Folder Simpan (Opsional):"))

        self.txt_save_dir = QLineEdit()
        self.txt_save_dir.setPlaceholderText("Default: Downloads\\LiveCaptures\\<NamaChannel>")
        self.txt_save_dir.setMinimumHeight(28)
        row2.addWidget(self.txt_save_dir, 1)

        btn_browse = QPushButton("Browse...")
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.setMinimumHeight(28)
        btn_browse.clicked.connect(self._browse_save_dir)
        row2.addWidget(btn_browse)

        self.chk_auto_rec_new = QCheckBox("Otomatis Rekam Saat Live")
        self.chk_auto_rec_new.setChecked(True)
        row2.addWidget(self.chk_auto_rec_new)
        add_vbox.addLayout(row2)
        root.addWidget(add_card)

        # 4. Watchlist Channels Table
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "Aktif", "Channel", "Platform", "Kualitas", "Auto-Rec",
            "Status", "Rekaman", "Terakhir Cek", "Aksi"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 48)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 92)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 72)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 70)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 130)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 68)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(7, 115)
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(8, 225)

        root.addWidget(self.table, 1)

        # 5. Footer Info & Close
        footer = QHBoxLayout()
        self.lbl_summary = QLabel("0 channel dipantau")
        self.lbl_summary.setStyleSheet("color: #94a3b8; font-size: 11px;")
        footer.addWidget(self.lbl_summary)
        footer.addStretch(1)

        btn_close = QPushButton("Tutup (Tetap Pantau di Latar Belakang)")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(
            "QPushButton { background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; "
            "border-radius: 6px; padding: 7px 18px; font-weight: 600; font-size: 12px; }"
            "QPushButton:hover { background-color: #334155; }"
        )
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        root.addLayout(footer)

    def _load_settings(self):
        self.chk_global_enable.blockSignals(True)
        self.chk_global_enable.setChecked(self.watchlist_mgr.is_enabled())
        self.chk_global_enable.blockSignals(False)

        interval = self.watchlist_mgr.get_default_interval()
        self.cmb_interval.blockSignals(True)
        idx = self.cmb_interval.findData(interval)
        if idx >= 0:
            self.cmb_interval.setCurrentIndex(idx)
        else:
            self.cmb_interval.setCurrentIndex(1)
        self.cmb_interval.blockSignals(False)

        self.spn_max_rec.blockSignals(True)
        self.spn_max_rec.setValue(self.watchlist_mgr.get_max_concurrent_recordings())
        self.spn_max_rec.blockSignals(False)

    def _on_global_toggle(self, checked: bool):
        self.watchlist_mgr.set_enabled(checked)

    def _on_interval_changed(self, _idx: int):
        val = self.cmb_interval.currentData()
        if val:
            self.watchlist_mgr.set_default_interval(int(val))

    def _on_max_rec_changed(self, val: int):
        self.db.set_setting("watchlist_max_concurrent", str(max(1, val)))

    def _browse_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Pilih Folder Simpan Rekaman")
        if d:
            self.txt_save_dir.setText(d)

    def _on_add_clicked(self):
        raw_url = self.txt_url.text().strip()
        if not raw_url:
            QMessageBox.warning(self, "Input Kosong", "Masukkan URL channel atau username streamer terlebih dahulu.")
            return
        try:
            item = self.watchlist_mgr.add_channel(
                url_or_handle=raw_url,
                name=self.txt_name.text().strip(),
                quality_pref=self.cmb_quality.currentData() or "best",
                save_dir=self.txt_save_dir.text().strip(),
                check_interval_sec=self.cmb_interval.currentData() or 60,
                auto_record=self.chk_auto_rec_new.isChecked(),
                enabled=True,
            )
            self.txt_url.clear()
            self.txt_name.clear()
            self.refresh_table()
            self.watchlist_mgr.check_channel_async(item["id"], force_record=False)
        except Exception as e:
            QMessageBox.warning(self, "Gagal Menambah Channel", str(e))

    def _on_check_all_clicked(self):
        self.watchlist_mgr.check_all_async(force_record=False)
        self.lbl_summary.setText("Sedang memeriksa semua channel aktif di latar belakang...")

    def _toggle_item_enabled(self, item_id: str, checked: bool):
        item = self.db.get_watchlist_item(item_id)
        if not item:
            return
        item["enabled"] = checked
        if not checked:
            item["status"] = "Disabled"
        elif item.get("status") == "Disabled":
            item["status"] = "Queued"
        self.db.save_watchlist_item(item)
        if checked:
            self.watchlist_mgr.check_channel_async(item_id, force_record=False)
        self.refresh_table()

    def _toggle_item_autorec(self, item_id: str, checked: bool):
        item = self.db.get_watchlist_item(item_id)
        if not item:
            return
        item["auto_record"] = checked
        self.db.save_watchlist_item(item)
        self.refresh_table()

    def _open_channel_folder(self, item: dict):
        save_dir = (item.get("save_dir") or "").strip()
        if not save_dir:
            default_base = self.db.get_setting(
                "default_save_path",
                os.path.join(os.path.expanduser("~"), "Downloads"),
            )
            save_dir = os.path.join(default_base, "LiveCaptures", sanitize_filename(item.get("name") or "LiveStream"))
        os.makedirs(save_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(save_dir)
        else:
            subprocess.Popen(["xdg-open", save_dir])

    def _remove_item(self, item_id: str, name: str):
        ans = QMessageBox.question(
            self,
            "Hapus Channel",
            f"Hapus '{name}' dari Live Stream Watchlist?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.watchlist_mgr.remove_channel(item_id)
            self.refresh_table()

    def refresh_table(self):
        """Reload rows from database without jarring scroll jumps."""
        items = self.db.get_watchlist()
        self.table.setRowCount(len(items))

        recording_cnt = 0
        live_cnt = 0
        enabled_cnt = 0

        for row, item in enumerate(items):
            item_id = item["id"]
            if item.get("enabled"):
                enabled_cnt += 1

            status = item.get("status") or "Offline"
            if status == "Recording":
                recording_cnt += 1
            elif status.startswith("Live"):
                live_cnt += 1

            # Col 0: Enabled toggle
            chk_en = QCheckBox()
            chk_en.setChecked(bool(item.get("enabled", True)))
            chk_en.toggled.connect(lambda c, iid=item_id: self._toggle_item_enabled(iid, c))
            w_en = QWidget()
            l_en = QHBoxLayout(w_en)
            l_en.setContentsMargins(0, 0, 0, 0)
            l_en.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l_en.addWidget(chk_en)
            self.table.setCellWidget(row, 0, w_en)

            # Col 1: Channel Name + URL tooltip
            name_item = QTableWidgetItem(item.get("name", "Stream"))
            name_item.setToolTip(item.get("url", ""))
            font_b = QFont()
            font_b.setBold(True)
            name_item.setFont(font_b)
            self.table.setItem(row, 1, name_item)

            # Col 2: Platform
            plat_item = QTableWidgetItem(item.get("platform", "Auto"))
            plat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, plat_item)

            # Col 3: Quality
            qual_item = QTableWidgetItem(str(item.get("quality_pref", "best")).upper())
            qual_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, qual_item)

            # Col 4: Auto-Record toggle
            chk_ar = QCheckBox()
            chk_ar.setChecked(bool(item.get("auto_record", True)))
            chk_ar.toggled.connect(lambda c, iid=item_id: self._toggle_item_autorec(iid, c))
            w_ar = QWidget()
            l_ar = QHBoxLayout(w_ar)
            l_ar.setContentsMargins(0, 0, 0, 0)
            l_ar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l_ar.addWidget(chk_ar)
            self.table.setCellWidget(row, 4, w_ar)

            # Col 5: Status badge text
            st_item = QTableWidgetItem(status)
            st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if item.get("last_error"):
                st_item.setToolTip(item["last_error"])
            if status == "Recording":
                st_item.setForeground(QColor("#fb7185"))
                st_item.setFont(font_b)
            elif status.startswith("Live"):
                st_item.setForeground(QColor("#34d399"))
                st_item.setFont(font_b)
            elif "Private" in status or "Paused" in status:
                st_item.setForeground(QColor("#fbbf24"))
            else:
                st_item.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 5, st_item)

            # Col 6: Recording count
            cnt_item = QTableWidgetItem(str(item.get("record_count", 0)))
            cnt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 6, cnt_item)

            # Col 7: Last checked timestamp
            lc = float(item.get("last_checked") or 0)
            lc_str = datetime.fromtimestamp(lc).strftime("%H:%M:%S") if lc > 0 else "Belum dicek"
            lc_item = QTableWidgetItem(lc_str)
            lc_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            lc_item.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 7, lc_item)

            # Col 8: Action Buttons
            act_w = QWidget()
            act_l = QHBoxLayout(act_w)
            act_l.setContentsMargins(4, 2, 4, 2)
            act_l.setSpacing(4)

            is_recording = (status == "Recording" and bool(item.get("active_task_id")))
            if is_recording:
                btn_rec = QPushButton("Stop")
                btn_rec.setToolTip("Hentikan rekaman aktif saat ini")
                btn_rec.setStyleSheet(
                    "QPushButton { background-color: #7f1d1d; color: #fecaca; border: none; border-radius: 4px; padding: 3px 9px; font-size: 11px; font-weight: 600; }"
                    "QPushButton:hover { background-color: #991b1b; }"
                )
                btn_rec.clicked.connect(lambda _c=False, iid=item_id: self.watchlist_mgr.stop_channel_recording(iid))
            else:
                btn_rec = QPushButton("Rec Now")
                btn_rec.setToolTip("Cek & rekam sekarang jika sedang live")
                btn_rec.setStyleSheet(
                    "QPushButton { background-color: #065f46; color: #d1fae5; border: none; border-radius: 4px; padding: 3px 9px; font-size: 11px; font-weight: 600; }"
                    "QPushButton:hover { background-color: #047857; }"
                )
                btn_rec.clicked.connect(lambda _c=False, iid=item_id: self.watchlist_mgr.check_channel_async(iid, force_record=True))
            btn_rec.setCursor(Qt.CursorShape.PointingHandCursor)
            act_l.addWidget(btn_rec)

            btn_dir = QPushButton("Folder")
            btn_dir.setToolTip("Buka folder hasil rekaman")
            btn_dir.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_dir.setStyleSheet(
                "QPushButton { background-color: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-radius: 4px; padding: 3px 8px; font-size: 11px; }"
                "QPushButton:hover { background-color: #334155; }"
            )
            btn_dir.clicked.connect(lambda _c=False, it=item: self._open_channel_folder(it))
            act_l.addWidget(btn_dir)

            btn_del = QPushButton("Hapus")
            btn_del.setToolTip("Hapus channel dari watchlist")
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet(
                "QPushButton { background-color: #1e293b; color: #fca5a5; border: 1px solid #334155; border-radius: 4px; padding: 3px 8px; font-size: 11px; }"
                "QPushButton:hover { background-color: #7f1d1d; color: #ffffff; }"
            )
            btn_del.clicked.connect(lambda _c=False, iid=item_id, nm=item.get("name", "Stream"): self._remove_item(iid, nm))
            act_l.addWidget(btn_del)

            self.table.setCellWidget(row, 8, act_w)

        self.lbl_summary.setText(
            f"Total: {len(items)} channel | Aktif dipantau: {enabled_cnt} | Live standby: {live_cnt} | Sedang merekam: {recording_cnt}"
        )
