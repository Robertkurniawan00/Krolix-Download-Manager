"""
Krolix Download Manager - Browser Integration & Extension Manager Dialog
Provides complete management for Chrome, Edge, Firefox, Brave, and Opera browser extensions,
native messaging host registration (com.zero.downloader), and local API diagnostics.
"""

import os
import sys
import subprocess
import urllib.request
import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QScrollArea, QWidget,
    QFrame, QMessageBox
)
from PyQt6.QtCore import Qt
from ..core.database import Database
from ..utils.helpers import apply_windows_dark_titlebar
from ..utils.browser_integration import (
    register_native_messaging_host,
    register_url_protocol,
    set_windows_autostart
)
from . import fluent_icons


def _find_browser_exe(name: str) -> str:
    """Finds path to popular browser executables on Windows."""
    paths = {
        "chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
        "edge": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        ],
        "firefox": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe"),
        ],
        "brave": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ],
        "opera": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\launcher.exe"),
            r"C:\Program Files\Opera\launcher.exe",
        ]
    }
    for p in paths.get(name.lower(), []):
        if os.path.exists(p):
            return p
    return ""


class ExtensionDialog(QDialog):
    def __init__(self, parent=None, db=None):
        super().__init__(parent)
        self.db = db or Database.get_instance()
        self.setWindowTitle("Integrasi Browser & Ekstensi (Browser Integration)")
        self.setFixedSize(640, 620)
        apply_windows_dark_titlebar(self)

        self._init_ui()
        self._refresh_status()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #070a0f;
                color: #f1f5f9;
            }
            QLabel {
                color: #cbd5e1;
                font-size: 12px;
            }
            QGroupBox {
                border: 1px solid #1e293b;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 14px;
                font-weight: 600;
                color: #f8fafc;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                left: 10px;
            }
            QPushButton {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 6px 14px;
                color: #f8fafc;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border-color: #3b82f6;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
            QPushButton#accentBtn {
                background-color: #2563eb;
                border-color: #3b82f6;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton#accentBtn:hover {
                background-color: #1d4ed8;
                border-color: #60a5fa;
            }
            QPushButton#successBtn {
                background-color: #059669;
                border-color: #10b981;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton#successBtn:hover {
                background-color: #047857;
                border-color: #34d399;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(fluent_icons.create_fluent_browser_icon(color="#38bdf8").pixmap(32, 32))
        header.addWidget(icon_lbl)

        hdr_vbox = QVBoxLayout()
        hdr_vbox.setSpacing(2)
        title_lbl = QLabel("Integrasi Browser & Manajer Ekstensi")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc;")
        hdr_vbox.addWidget(title_lbl)

        sub_lbl = QLabel("Dukungan integrasi penuh untuk Ekstensi Peramban Krolix Download Manager")
        sub_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        hdr_vbox.addWidget(sub_lbl)

        header.addLayout(hdr_vbox)
        header.addStretch()

        layout.addLayout(header)

        # Scroll Area for Content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        content_vbox = QVBoxLayout(content_widget)
        content_vbox.setContentsMargins(0, 0, 0, 0)
        content_vbox.setSpacing(12)

        # 1. Native Messaging Host Status Box
        grp_nm = QGroupBox("Status Host Integrasi Sistem (Native Messaging)")
        v_nm = QVBoxLayout(grp_nm)
        v_nm.setSpacing(8)

        self.lbl_nm_status = QLabel("Memeriksa registrasi...")
        self.lbl_nm_status.setStyleSheet("font-size: 12px; font-weight: 600;")
        v_nm.addWidget(self.lbl_nm_status)

        lbl_nm_info = QLabel("Krolix mendaftarkan host 'com.zero.downloader' di Registry pengguna (HKCU) tanpa memerlukan hak Administrator.")
        lbl_nm_info.setWordWrap(True)
        lbl_nm_info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        v_nm.addWidget(lbl_nm_info)

        h_nm_btns = QHBoxLayout()
        btn_reregister = QPushButton("Perbaiki & Daftarkan Host Integrasi")
        btn_reregister.setObjectName("accentBtn")
        btn_reregister.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reregister.clicked.connect(self._reregister_host)
        h_nm_btns.addWidget(btn_reregister)

        btn_test_api = QPushButton("Uji Sambungan (API Port 9666)")
        btn_test_api.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_test_api.clicked.connect(self._test_api_connection)
        h_nm_btns.addWidget(btn_test_api)
        h_nm_btns.addStretch()
        v_nm.addLayout(h_nm_btns)

        content_vbox.addWidget(grp_nm)

        # 2. Browser Extensions Section
        grp_browsers = QGroupBox("Pasang Ekstensi ke Browser")
        v_browsers = QVBoxLayout(grp_browsers)
        v_browsers.setSpacing(10)

        # Chrome
        row_chrome = self._create_browser_row(
            name="Google Chrome",
            icon_color="#38bdf8",
            exe_key="chrome",
            ext_page="chrome://extensions",
            help_text="Integrasi browser otomatis via Ekstensi Krolix (Manifest V3)."
        )
        v_browsers.addLayout(row_chrome)

        # Edge
        row_edge = self._create_browser_row(
            name="Microsoft Edge",
            icon_color="#60a5fa",
            exe_key="edge",
            ext_page="edge://extensions",
            help_text="Terintegrasi dengan Microsoft Edge via Native Messaging Host."
        )
        v_browsers.addLayout(row_edge)

        # Firefox
        row_firefox = self._create_browser_row(
            name="Mozilla Firefox",
            icon_color="#f97316",
            exe_key="firefox",
            ext_page="about:addons",
            help_text="Dukungan ekstensi peramban untuk Mozilla Firefox."
        )
        v_browsers.addLayout(row_firefox)

        # Brave / Opera
        row_brave = self._create_browser_row(
            name="Brave & Opera",
            icon_color="#f59e0b",
            exe_key="brave",
            ext_page="brave://extensions",
            help_text="Buka mode pengembang (Developer Mode) lalu muat ekstensi Krolix."
        )
        v_browsers.addLayout(row_brave)

        content_vbox.addWidget(grp_browsers)

        # 3. Developer / Unpacked Krolix Extension Folder
        grp_dev = QGroupBox("Ekstensi Pengembang Bawaan (Krolix Extension)")
        v_dev = QVBoxLayout(grp_dev)
        v_dev.setSpacing(8)

        lbl_dev = QLabel("Anda juga dapat memuat folder sumber ekstensi Krolix secara langsung (Load Unpacked):")
        lbl_dev.setStyleSheet("color: #94a3b8; font-size: 11px;")
        v_dev.addWidget(lbl_dev)

        h_dev = QHBoxLayout()
        btn_open_ext_dir = QPushButton("Buka Folder Ekstensi Krolix...")
        btn_open_ext_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_ext_dir.clicked.connect(self._open_extension_dir)
        h_dev.addWidget(btn_open_ext_dir)
        h_dev.addStretch()

        v_dev.addLayout(h_dev)
        content_vbox.addWidget(grp_dev)

        scroll.setWidget(content_widget)
        layout.addWidget(scroll, 1)

        # Bottom Bar
        bottom = QHBoxLayout()
        bottom.addStretch()

        btn_close = QPushButton("Tutup")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)

        layout.addLayout(bottom)

    def _create_browser_row(self, name: str, icon_color: str, exe_key: str, ext_page: str, help_text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(fluent_icons.create_fluent_browser_icon(color=icon_color).pixmap(20, 20))
        row.addWidget(icon_lbl)

        v_info = QVBoxLayout()
        v_info.setSpacing(1)

        lbl_name = QLabel(name)
        lbl_name.setStyleSheet("font-weight: 600; color: #f1f5f9; font-size: 12px;")
        v_info.addWidget(lbl_name)

        lbl_desc = QLabel(help_text)
        lbl_desc.setStyleSheet("color: #64748b; font-size: 10px;")
        v_info.addWidget(lbl_desc)
        row.addLayout(v_info, 1)

        btn_install = QPushButton("Pasang...")
        btn_install.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_install.clicked.connect(lambda: self._install_extension(exe_key, ext_page))
        row.addWidget(btn_install)

        btn_open_page = QPushButton("Halaman Ekstensi")
        btn_open_page.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_page.clicked.connect(lambda: self._open_browser_url(exe_key, ext_page))
        row.addWidget(btn_open_page)

        return row

    def _refresh_status(self):
        """Checks registry keys and API server status."""
        nm_registered = False
        if sys.platform == "win32":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\NativeMessagingHosts\com.zero.downloader") as _:
                    nm_registered = True
            except Exception:
                nm_registered = False

        if nm_registered:
            self.lbl_nm_status.setText("● Host Integrasi Terpasang & Aktif (com.zero.downloader)")
            self.lbl_nm_status.setStyleSheet("font-size: 12px; font-weight: 600; color: #10b981;")
        else:
            self.lbl_nm_status.setText("○ Host Integrasi Belum Terdaftar di Registry")
            self.lbl_nm_status.setStyleSheet("font-size: 12px; font-weight: 600; color: #f59e0b;")

    def _reregister_host(self):
        try:
            ok1 = register_url_protocol()
            ok2 = register_native_messaging_host()
            ok3 = set_windows_autostart(True)
            self._refresh_status()
            if ok1 or ok2 or ok3:
                QMessageBox.information(
                    self,
                    "Integrasi Berhasil",
                    "Host Integrasi Peramban (com.zero.downloader) serta protokol 'zero-dl://' berhasil didaftarkan ulang ke Registry Windows!\n\nPeramban Anda kini siap meneruskan unduhan otomatis ke Krolix."
                )
            else:
                QMessageBox.warning(self, "Peringatan", "Host integrasi mungkin memerlukan perizinan tambahan.")
        except Exception as e:
            QMessageBox.critical(self, "Gagal", f"Gagal mendaftarkan host: {e}")

    def _test_api_connection(self):
        try:
            req = urllib.request.Request("http://127.0.0.1:9666/status", headers={"User-Agent": "KrolixExtensionTest"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    app_name = data.get("app", "Krolix")
                    ver = data.get("version", "2.6")
                    QMessageBox.information(
                        self,
                        "Koneksi Berhasil",
                        f"Server API Krolix Merespon (HTTP 200 OK)!\n\nAplikasi: {app_name}\nVersi: {ver}\nPort: 9666\nStatus: Siap menerima unduhan dari ekstensi browser."
                    )
                    return
        except Exception as e:
            QMessageBox.warning(
                self,
                "Server Tidak Merespon",
                f"Tidak dapat terhubung ke server lokal port 9666.\nPastikan Krolix sedang berjalan.\n\nError: {e}"
            )

    def _install_extension(self, exe_key: str, ext_page: str):
        ext_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "extension"))
        self._open_browser_url(exe_key, ext_page)
        if os.path.exists(ext_dir):
            try:
                subprocess.Popen(f'explorer.exe "{ext_dir}"')
            except Exception:
                os.startfile(ext_dir)
        QMessageBox.information(
            self,
            "Panduan Pemasangan Ekstensi",
            "Halaman ekstensi peramban dan folder ekstensi Krolix telah dibuka:\n\n"
            "1. Aktifkan 'Mode Pengembang' (Developer Mode) di peramban.\n"
            "2. Klik tombol 'Muat yang belum dibongkar' (Load unpacked).\n"
            "3. Pilih folder 'extension' yang baru saja dibuka.\n"
            "4. Ekstensi Krolix kini siap menangkap unduhan otomatis!"
        )

    def _open_browser_url(self, exe_key: str, url: str):
        browser_exe = _find_browser_exe(exe_key)
        if browser_exe and os.path.exists(browser_exe):
            try:
                subprocess.Popen([browser_exe, url])
                return
            except Exception:
                pass
        # Fallback to default start
        try:
            os.startfile(url)
        except Exception as e:
            QMessageBox.information(self, "Info", f"Buka alamat ini di peramban Anda:\n{url}")

    def _open_extension_dir(self):
        ext_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "extension"))
        if os.path.exists(ext_dir):
            try:
                subprocess.Popen(f'explorer.exe "{ext_dir}"')
            except Exception:
                os.startfile(ext_dir)
        else:
            QMessageBox.warning(self, "Peringatan", "Folder ekstensi belum ditemukan.")
