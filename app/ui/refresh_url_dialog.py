"""
Krolix Download Manager v2.8 - Simplified Refresh Download Address Dialog (Link Repair)
Compact, minimal, and fully automated workflow:
1. Opens with "... menunggu respon link download baru".
2. Automatically launches original webpage in browser.
3. Automatically catches new link from browser extension.
4. If active: continues download automatically.
5. If inactive: displays "new download link accepted".
"""

import os
import webbrowser
import urllib.parse
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QMessageBox, QApplication, QProgressBar, QWidget
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon

from ..core.models import DownloadTask, DownloadStatus
from ..core.downloader import DownloadEngine
from ..utils.helpers import format_bytes, apply_windows_dark_titlebar
from . import fluent_icons


class RefreshUrlDialog(QDialog):
    def __init__(self, task: DownloadTask, engine: Optional[DownloadEngine] = None, parent=None):
        super().__init__(parent)
        self.task = task
        if engine is not None:
            self.engine = engine
        elif hasattr(parent, "engine") and parent.engine:
            self.engine = parent.engine
        else:
            self.engine = DownloadEngine.get_instance()

        self._detected_new_url = ""
        self._new_headers = dict(self.task.headers or {})

        # Track active status (downloading / connecting)
        self.was_active = (self.task.status in [DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING])
        if self.was_active:
            try:
                self.engine.pause_download(self.task.id)
            except Exception as e:
                print(f"[RefreshUrlDialog] Note pausing active task: {e}")

        # Register this dialog as active listener in engine
        DownloadEngine.active_refresh_dialog = self
        DownloadEngine.active_refresh_task_id = self.task.id
        if hasattr(self.engine, "active_refresh_dialog"):
            self.engine.active_refresh_dialog = self
            self.engine.active_refresh_task_id = self.task.id

        self.setWindowTitle("... menunggu respon link download baru")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setFixedWidth(500)
        apply_windows_dark_titlebar(self)

        logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "logo_32.png"))
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.setStyleSheet("""
            QDialog {
                background-color: #070a0f;
                border: 1px solid #1b273d;
                border-radius: 10px;
            }
            QLabel {
                font-family: 'Segoe UI Variable Text', 'Inter', -apple-system, sans-serif;
                color: #cbd5e1;
            }
            QLineEdit {
                background-color: #0b111a;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 7px 10px;
                color: #e2e8f0;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #10b981;
                background-color: #0f1726;
            }
        """)

        self._init_ui()

        # Otomatis membuka laman web asal di browser
        QTimer.singleShot(200, self._open_original_webpage)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 16)
        main_layout.setSpacing(0)

        # Top Glowing Accent Rim
        rim = QFrame()
        rim.setFixedHeight(3)
        rim.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(16, 185, 129, 0.2),
                stop:0.5 rgba(16, 185, 129, 1.0),
                stop:1 rgba(16, 185, 129, 0.2));
        """)
        main_layout.addWidget(rim)

        content = QVBoxLayout()
        content.setContentsMargins(20, 16, 20, 0)
        content.setSpacing(12)
        main_layout.addLayout(content)

        # 1. Header Row
        header = QHBoxLayout()
        header.setSpacing(10)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(fluent_icons.create_fluent_refresh_link_icon("#10b981").pixmap(26, 26))
        header.addWidget(lbl_icon)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        lbl_title = QLabel("... menunggu respon link download baru")
        lbl_title.setStyleSheet("font-weight: 600; font-size: 14px; color: #f1f5f9;")
        title_vbox.addWidget(lbl_title)

        lbl_sub = QLabel("Laman web asal dibuka otomatis. Silakan klik tombol download di browser Anda.")
        lbl_sub.setStyleSheet("color: #94a3b8; font-size: 11px;")
        title_vbox.addWidget(lbl_sub)
        header.addLayout(title_vbox)

        header.addStretch()
        content.addLayout(header)

        # 2. Sleek Waiting Card
        wait_card = QFrame()
        wait_card.setStyleSheet("""
            QFrame {
                background-color: #0b111a;
                border: 1px solid #162235;
                border-radius: 8px;
            }
        """)
        wait_layout = QVBoxLayout(wait_card)
        wait_layout.setContentsMargins(14, 12, 14, 12)
        wait_layout.setSpacing(8)

        # Task summary line
        prog_val = max(0.0, min(100.0, self.task.progress))
        dl_str = format_bytes(self.task.downloaded_bytes)
        row_file = QHBoxLayout()
        lbl_fn = QLabel(f"Berkas: {self.task.filename}")
        lbl_fn.setStyleSheet("color: #f8fafc; font-size: 11px; font-weight: 600;")
        row_file.addWidget(lbl_fn, 1)

        lbl_pct = QLabel(f"{prog_val:.1f}% ({dl_str}) tersimpan")
        lbl_pct.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 500;")
        row_file.addWidget(lbl_pct)
        wait_layout.addLayout(row_file)

        # Single smooth indeterminate progress bar
        self.wait_bar = QProgressBar()
        self.wait_bar.setRange(0, 0)
        self.wait_bar.setFixedHeight(4)
        self.wait_bar.setTextVisible(False)
        self.wait_bar.setStyleSheet("""
            QProgressBar {
                background-color: #05070b;
                border: 1px solid #151f30;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #38bdf8);
                border-radius: 2px;
            }
        """)
        wait_layout.addWidget(self.wait_bar)

        # Status text
        self.lbl_status = QLabel("● Membuka web asal... Menunggu ekstensi menangkap link baru.")
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 500;")
        wait_layout.addWidget(self.lbl_status)

        content.addWidget(wait_card)

        # 3. Compact Manual Fallback (Optional toggle)
        self.manual_widget = QWidget()
        manual_layout = QHBoxLayout(self.manual_widget)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        manual_layout.setSpacing(6)

        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("Atau tempel link baru secara manual di sini...")
        manual_layout.addWidget(self.txt_url, 1)

        btn_paste = QPushButton("Tempel")
        btn_paste.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_paste.setStyleSheet("""
            QPushButton {
                background-color: #0f1724;
                color: #cbd5e1;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #182235;
                color: #ffffff;
            }
        """)
        btn_paste.clicked.connect(self._paste_clipboard)
        manual_layout.addWidget(btn_paste)

        btn_apply = QPushButton("Terapkan")
        btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2e3d54;
                border-color: #10b981;
            }
        """)
        btn_apply.clicked.connect(self._do_apply_and_resume)
        manual_layout.addWidget(btn_apply)

        self.manual_widget.setVisible(False)
        content.addWidget(self.manual_widget)

        # Toggle button for manual input
        self.btn_toggle_manual = QPushButton("▸ Tempel link manual")
        self.btn_toggle_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_manual.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748b;
                border: none;
                font-size: 11px;
                text-align: left;
                padding: 2px 0;
            }
            QPushButton:hover {
                color: #94a3b8;
            }
        """)
        self.btn_toggle_manual.clicked.connect(self._toggle_manual)
        content.addWidget(self.btn_toggle_manual)

        content.addStretch()

        # 4. Bottom Controls (Re-open web | Batal)
        btn_row = QHBoxLayout()
        btn_reopen = QPushButton("Buka Ulang Web")
        btn_reopen.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reopen.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #64748b;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #f1f5f9;
                border-color: #334155;
                background-color: #0f1724;
            }
        """)
        btn_reopen.clicked.connect(self._open_original_webpage)
        btn_row.addWidget(btn_reopen)

        btn_row.addStretch()

        btn_cancel = QPushButton("Batal")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #0f1724;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 6px 20px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #182235;
                color: #f1f5f9;
                border-color: #334155;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        content.addLayout(btn_row)

    def _toggle_manual(self):
        vis = not self.manual_widget.isVisible()
        self.manual_widget.setVisible(vis)
        self.btn_toggle_manual.setText("▾ Sembunyikan input manual" if vis else "▸ Tempel link manual")
        self.adjustSize()

    def _get_original_page_url(self) -> str:
        """Determines best source webpage URL to open in browser."""
        hdrs = self.task.headers or {}
        for key in ["page_url", "pageUrl", "Referer", "referer", "webpage_url"]:
            val = hdrs.get(key)
            if val and (val.startswith("http://") or val.startswith("https://")):
                return val

        if hasattr(self.task, "description") and self.task.description:
            d = self.task.description.strip()
            if d.startswith("http://") or d.startswith("https://"):
                return d

        try:
            parsed = urllib.parse.urlsplit(self.task.url)
            if parsed.scheme and parsed.netloc:
                if "pixeldrain.com" in parsed.netloc and "/api/file/" in parsed.path:
                    slug = parsed.path.split("/api/file/")[-1].split("/")[0]
                    return f"https://pixeldrain.com/u/{slug}"
                return f"{parsed.scheme}://{parsed.netloc}/"
        except Exception:
            pass

        return ""

    def _open_original_webpage(self):
        url = self._get_original_page_url()
        if url:
            try:
                webbrowser.open(url)
                self.lbl_status.setText("● Laman web dibuka. Silakan klik download pada web...")
                self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 500;")
            except Exception as e:
                self.lbl_status.setText(f"Tidak dapat membuka browser: {e}")
                self.lbl_status.setStyleSheet("color: #ef4444; font-size: 11px;")
        else:
            self.lbl_status.setText("Laman web asal tidak ditemukan. Buka situs secara manual.")
            self.lbl_status.setStyleSheet("color: #f59e0b; font-size: 11px;")

    def _paste_clipboard(self):
        text = (QApplication.clipboard().text() or "").strip()
        if text:
            self.txt_url.setText(text)

    def handle_incoming_refreshed_download(self, data: dict) -> bool:
        """
        Consumes incoming download from browser extension.
        - If task was active: automatically continues downloading.
        - If task was inactive: displays 'new download link accepted'.
        """
        new_url = (data.get("url") or "").strip()
        if not new_url:
            return False

        new_headers = dict(self.task.headers or {})
        if data.get("headers") and isinstance(data["headers"], dict):
            new_headers.update(data["headers"])

        if data.get("page_url") or data.get("pageUrl"):
            new_headers["Referer"] = data.get("page_url") or data.get("pageUrl")
            new_headers["page_url"] = data.get("page_url") or data.get("pageUrl")

        if data.get("cookies"):
            new_headers["Cookie"] = data.get("cookies")
        if data.get("userAgent"):
            new_headers["User-Agent"] = data.get("userAgent")

        self.lbl_status.setText("● Tautan baru diterima! Memverifikasi...")
        self.lbl_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
        QApplication.processEvents()

        ok, msg = self.engine.refresh_task_url(self.task.id, new_url, new_headers)
        if not ok:
            self.lbl_status.setText(f"Tautan tidak cocok: {msg}")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: 600;")
            return True

        self._detected_new_url = new_url
        self._new_headers = new_headers

        # Langsung jalankan unduhan secara otomatis tanpa jeda
        try:
            self.engine.start_download(self.task.id)
            if hasattr(self.parent(), "_dash_pairs") and self.task.id in self.parent()._dash_pairs:
                self.engine.start_download(self.parent()._dash_pairs[self.task.id])
        except Exception as e:
            print(f"[RefreshDialog] Error auto-starting refreshed task: {e}")

        self.lbl_status.setText("● Tautan baru diterima! Unduhan langsung dilanjutkan.")
        self.lbl_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
        QApplication.processEvents()
        self.accept()
        return True

    def _do_apply_and_resume(self):
        new_url = self.txt_url.text().strip()
        if not new_url:
            QMessageBox.warning(self, "Tautan Kosong", "Silakan masukkan atau tempel link download baru.")
            return

        if new_url == self.task.url:
            QMessageBox.warning(self, "Tautan Sama", "Tautan yang dimasukkan sama persis dengan tautan lama.")
            return

        ok, msg = self.engine.refresh_task_url(self.task.id, new_url, self._new_headers, auto_start=True)
        if ok:
            self._detected_new_url = new_url
            try:
                self.engine.start_download(self.task.id)
                if hasattr(self.parent(), "_dash_pairs") and self.task.id in self.parent()._dash_pairs:
                    self.engine.start_download(self.parent()._dash_pairs[self.task.id])
            except Exception as e:
                print(f"[RefreshDialog] Error resuming task: {e}")
            self.accept()
        else:
            QMessageBox.warning(self, "Gagal Memperbarui", f"Tidak dapat memperbarui tautan:\n{msg}")

    def _cleanup_listener(self):
        if getattr(DownloadEngine, "active_refresh_dialog", None) is self:
            DownloadEngine.active_refresh_dialog = None
            DownloadEngine.active_refresh_task_id = None
        if hasattr(self.engine, "active_refresh_dialog") and self.engine.active_refresh_dialog is self:
            self.engine.active_refresh_dialog = None
            self.engine.active_refresh_task_id = None

    def closeEvent(self, event):
        self._cleanup_listener()
        super().closeEvent(event)

    def reject(self):
        self._cleanup_listener()
        super().reject()

    def accept(self):
        self._cleanup_listener()
        super().accept()

    def get_results(self) -> dict:
        return {
            "new_url": self._detected_new_url or self.txt_url.text().strip(),
            "headers": self._new_headers
        }
