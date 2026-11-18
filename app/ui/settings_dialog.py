"""
Krolix Download Manager - Settings & Configuration Dialog (macOS Modern Dark)
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QCheckBox, QFileDialog, QComboBox,
    QGroupBox, QTabWidget, QWidget, QFrame, QApplication,
    QListWidget, QInputDialog, QMessageBox,
    QPlainTextEdit
)
from PyQt6.QtCore import Qt
from ..core.database import Database
from ..utils.helpers import apply_windows_dark_titlebar, get_default_download_dir
from ..core.ssl_manager import SSLManager
from ..ui.styles import get_app_stylesheet
from .proxy_manager_dialog import ProxyManagerDialog
from .extension_dialog import ExtensionDialog


class SettingsDialog(QDialog):
    def __init__(self, db=None, speed_limiter=None, parent=None):
        super().__init__(parent)
        self.db = db or Database.get_instance()
        self.speed_limiter = speed_limiter
        self.setWindowTitle("Pengaturan Krolix Download Manager")
        self.setFixedWidth(730)
        self.setMinimumHeight(580)
        apply_windows_dark_titlebar(self)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(14)

        chevron_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "chevron_down.svg")).replace("\\", "/")
        checkmark_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "checkmark.svg")).replace("\\", "/")
        spin_up_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "spinbox_up.svg")).replace("\\", "/")
        spin_down_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "spinbox_down.svg")).replace("\\", "/")

        self.setStyleSheet(f"""
            QDialog {{
                background-color: #0b0f17;
                color: #e2e8f0;
            }}
            QLabel {{
                color: #cbd5e1;
                font-size: 12px;
            }}
            QGroupBox {{
                border: 1px solid #1e293b;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 14px;
                font-weight: 600;
                color: #e2e8f0;
                font-size: 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                left: 10px;
            }}
            QLineEdit, QListWidget {{
                background-color: #050811;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 6px 10px;
                color: #f1f5f9;
                font-size: 12px;
            }}
            QSpinBox {{
                background-color: #050811;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 6px 24px 6px 10px;
                color: #f1f5f9;
                font-size: 12px;
            }}
            QSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 18px;
                border-left: 1px solid #1e293b;
                border-bottom: 1px solid #1e293b;
                background-color: #0f1724;
                border-top-right-radius: 5px;
            }}
            QSpinBox::up-button:hover {{
                background-color: #1e293b;
            }}
            QSpinBox::up-arrow {{
                image: url({spin_up_path});
                width: 8px;
                height: 5px;
            }}
            QSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 18px;
                border-left: 1px solid #1e293b;
                background-color: #0f1724;
                border-bottom-right-radius: 5px;
            }}
            QSpinBox::down-button:hover {{
                background-color: #1e293b;
            }}
            QSpinBox::down-arrow {{
                image: url({spin_down_path});
                width: 8px;
                height: 5px;
            }}
            QComboBox {{
                background-color: #050811;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 6px 28px 6px 10px;
                color: #f1f5f9;
                font-size: 12px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 26px;
                border-left: 1px solid #1e293b;
                background-color: #0f1724;
                border-top-right-radius: 5px;
                border-bottom-right-radius: 5px;
            }}
            QComboBox::drop-down:hover {{
                background-color: #1e293b;
            }}
            QComboBox::down-arrow {{
                image: url({chevron_path});
                width: 9px;
                height: 6px;
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QListWidget:focus {{
                border-color: #3b82f6;
            }}
            QCheckBox {{
                color: #e2e8f0;
                font-size: 12px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #334155;
                background-color: #050811;
            }}
            QCheckBox::indicator:hover {{
                border-color: #3b82f6;
            }}
            QCheckBox::indicator:checked {{
                background-color: #2563eb;
                border-color: #2563eb;
                image: url({checkmark_path});
            }}
            QPushButton {{
                background-color: #0f1724;
                border: 1px solid #1b273d;
                border-radius: 5px;
                padding: 7px 16px;
                color: #e2e8f0;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #162235;
                border-color: #2563eb;
            }}
            QPushButton#accentBtn {{
                background-color: #2563eb;
                color: #ffffff;
                border-color: #2563eb;
                font-weight: 600;
            }}
            QPushButton#accentBtn:hover {{
                background-color: #3b82f6;
                border-color: #3b82f6;
            }}
            QTabWidget::pane {{
                border: 1px solid #1e293b;
                border-radius: 6px;
                background-color: #0b0f17;
            }}
            QTabBar::tab {{
                background-color: #0b0f17;
                color: #94a3b8;
                padding: 8px 16px;
                border: 1px solid transparent;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: 600;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                color: #38bdf8;
                border-bottom: 2px solid #38bdf8;
                background-color: #0f172a;
            }}
            QTabBar::tab:hover {{
                color: #e2e8f0;
                background-color: #111827;
            }}
        """)

        self.tabs = QTabWidget()
        self.tab_unduhan = QWidget()
        self.tab_berkas = QWidget()
        self.tab_browser = QWidget()
        self.tab_jaringan = QWidget()
        self.tab_tampilan = QWidget()
        self.tab_keamanan = QWidget()

        self.tabs.addTab(self.tab_unduhan, "Unduhan")
        self.tabs.addTab(self.tab_berkas, "Jenis Berkas")
        self.tabs.addTab(self.tab_browser, "Integrasi Browser")
        self.tabs.addTab(self.tab_jaringan, "Jaringan")
        self.tabs.addTab(self.tab_tampilan, "Tampilan")
        self.tabs.addTab(self.tab_keamanan, "Keamanan")

        main_layout.addWidget(self.tabs)

        self._setup_unduhan_tab()
        self._setup_berkas_tab()
        self._setup_browser_tab()
        self._setup_jaringan_tab()
        self._setup_tampilan_tab()
        self._setup_keamanan_tab()

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Batal")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Simpan Pengaturan")
        btn_save.setObjectName("accentBtn")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._save_settings)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        main_layout.addLayout(btn_row)

    def _setup_unduhan_tab(self):
        layout = QVBoxLayout(self.tab_unduhan)
        
        # 1. Folder & Unduhan Group
        grp_dl = QGroupBox("Lokasi && Jalur Unduhan")
        v_dl = QVBoxLayout(grp_dl)
        v_dl.setSpacing(10)

        v_dl.addWidget(QLabel("Folder Unduhan Standar:"))
        h_dir = QHBoxLayout()
        current_dir = self.db.get_setting("download_dir", "") or self.db.get_setting("default_save_path", get_default_download_dir())
        self.txt_dir = QLineEdit(current_dir)
        btn_browse = QPushButton("Pilih Folder...")
        btn_browse.clicked.connect(self._browse_dir)
        h_dir.addWidget(self.txt_dir, 1)
        h_dir.addWidget(btn_browse)
        v_dl.addLayout(h_dir)

        h_cat_opt = QHBoxLayout()
        self.chk_category_subfolders = QCheckBox("Pisahkan unduhan otomatis ke folder kategori (Video, Musik, dll.)")
        self.chk_category_subfolders.setChecked(self.db.get_setting("category_subfolders", "true") == "true")
        h_cat_opt.addWidget(self.chk_category_subfolders, 1)

        btn_cat_paths = QPushButton("Atur Jalur Kategori...")
        btn_cat_paths.clicked.connect(self._open_category_folders_dialog)
        h_cat_opt.addWidget(btn_cat_paths)
        v_dl.addLayout(h_cat_opt)

        layout.addWidget(grp_dl)

        # 2. Mesin Unduh & BitTorrent
        grp_engine = QGroupBox("Mesin Unduh && Protokol Torrent")
        v_engine = QVBoxLayout(grp_engine)
        v_engine.setSpacing(10)

        h_eng = QHBoxLayout()
        h_eng.addWidget(QLabel("Mesin Unduh Utama (Engine):"))
        self.cmb_engine = QComboBox()
        self.cmb_engine.addItem("Turbo (C# Direct-to-Disk Native)", "turbo")
        self.cmb_engine.addItem("C++ (aria2c Multi-Source)", "aria2")
        self.cmb_engine.addItem("Standard (Python Engine)", "standard")
        current_eng = self.db.get_setting("engine", "turbo")
        for idx in range(self.cmb_engine.count()):
            if self.cmb_engine.itemData(idx) == current_eng:
                self.cmb_engine.setCurrentIndex(idx)
                break
        h_eng.addWidget(self.cmb_engine, 1)
        v_engine.addLayout(h_eng)

        # BitTorrent Toggle
        self.chk_torrent = QCheckBox("Aktifkan Dukungan BitTorrent / Magnet (Torrent Downloader)")
        torrent_enabled = self.db.is_torrent_enabled()
        self.chk_torrent.setChecked(torrent_enabled)
        v_engine.addWidget(self.chk_torrent)

        lbl_torrent_desc = QLabel("Jika dinonaktifkan, Krolix tidak akan menjalankan swarm P2P dan tombol Torrent disembunyikan.")
        lbl_torrent_desc.setStyleSheet("color: #64748b; font-size: 11px; margin-left: 24px;")
        lbl_torrent_desc.setWordWrap(True)
        v_engine.addWidget(lbl_torrent_desc)
        layout.addWidget(grp_engine)

        # 3. Integrasi & Perilaku
        grp_int = QGroupBox("Integrasi && Perilaku")
        v_int = QVBoxLayout(grp_int)
        v_int.setSpacing(8)

        self.chk_clip = QCheckBox("Pantau Papan Klip (Clipboard URL Monitoring)")
        self.chk_clip.setChecked(self.db.get_setting("monitor_clipboard", True) if "monitor_clipboard" in str(self.db.get_setting("monitor_clipboard", "")) else self.db.get_setting("clipboard_monitor", True))
        v_int.addWidget(self.chk_clip)

        self.chk_always_on = QCheckBox("Mode Always-On Worker (Tetap aktif di latar belakang saat jendela ditutup)")
        self.chk_always_on.setChecked(str(self.db.get_setting("always_on_worker", "true")).lower() in ("true", "1"))
        v_int.addWidget(self.chk_always_on)

        self.chk_autostart = QCheckBox("Jalankan otomatis saat sistem dinyalakan (Auto-start Background Worker)")
        self.chk_autostart.setChecked(str(self.db.get_setting("autostart_worker", "true")).lower() in ("true", "1"))
        v_int.addWidget(self.chk_autostart)

        self.chk_tray = QCheckBox("Minimalkan ke System Tray saat ditutup")
        self.chk_tray.setChecked(self.db.get_setting("minimize_to_tray", True))
        v_int.addWidget(self.chk_tray)

        self.chk_auto_extract = QCheckBox("Ekstrak otomatis file arsip (.zip, .rar, .tar) setelah selesai")
        self.chk_auto_extract.setChecked(self.db.get_setting("auto_extract", False))
        v_int.addWidget(self.chk_auto_extract)

        self.chk_comp_dlg = QCheckBox("Tampilkan dialog notifikasi saat unduhan selesai")
        self.chk_comp_dlg.setChecked(self.db.get_setting("show_complete_dialog", True))
        v_int.addWidget(self.chk_comp_dlg)

        self.chk_confirm_del = QCheckBox("Tampilkan dialog konfirmasi sebelum menghapus unduhan")
        skip_del = str(self.db.get_setting("skip_delete_confirm", "false")).lower() in ("true", "1")
        self.chk_confirm_del.setChecked(not skip_del)
        v_int.addWidget(self.chk_confirm_del)
        layout.addWidget(grp_int)
        
    def _setup_berkas_tab(self):
        layout = QVBoxLayout(self.tab_berkas)
        layout.setSpacing(12)

        # 1. File types
        grp_types = QGroupBox("Otomatis Tangkap Unduhan untuk Jenis Berkas (Ekstensi)")
        v_types = QVBoxLayout(grp_types)
        v_types.setSpacing(8)

        lbl_desc = QLabel("Krolix akan otomatis mengunduh berkas dengan ekstensi berikut dari peramban (pisahkan dengan spasi):")
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        v_types.addWidget(lbl_desc)

        default_exts = (
            "3GP 7Z AAC ACE AI AIF AIFC AIFF AMR ASF ASX AVI BIN BZ2 CAB CDA CFM CLASS CPL CSV CUR DCR DER DIB DLL DMG "
            "DOC DOCX DOT DOTX DRV DVD DWG DWF DXF EMF EPS EXE F4V FLA FLAC FLV FON GZ GZIP H HPP HTA HTM HTML ICO ICL "
            "IFO IMG INF INI INS INX ISO JAR JAV JAVA JFIF JPE JPEG JPG JS KML KMZ LNK LOG LZH LZMA M1V M2V M3U M4A M4V "
            "MDB MID MIDI MKV MOV MP2 MP3 MP4 MPA MPE MPEG MPG MSI NFO NRGI OGA OGG OGM OGX OPUS OTF PAGES PDF PNG POT "
            "PPS PPT PPTX PRG PS PSD PUB RAR REG RM RMVB RTF RTTTL RTK SEA SIT SITX SVG SWF TAR TGA TGZ THM TIF TIFF TS "
            "TTF TXT VCF VDO VOB WAV WMA WMD WMV WMX WMZ WRI WS WSH XLA XLS XLSX XLT XML XPS Z ZIP ZIPX"
        )
        saved_exts = self.db.get_setting("auto_download_extensions", default_exts)
        self.txt_extensions = QPlainTextEdit(saved_exts)
        self.txt_extensions.setMaximumHeight(85)
        self.txt_extensions.setStyleSheet("background-color: #050811; border: 1px solid #1e293b; border-radius: 5px; color: #f1f5f9; font-size: 11px;")
        v_types.addWidget(self.txt_extensions)

        h_ext_btns = QHBoxLayout()
        btn_reset_exts = QPushButton("Reset ke Ekstensi Default")
        btn_reset_exts.clicked.connect(lambda: self.txt_extensions.setPlainText(default_exts))
        h_ext_btns.addWidget(btn_reset_exts)
        h_ext_btns.addStretch()
        v_types.addLayout(h_ext_btns)

        layout.addWidget(grp_types)

        # 2. Exceptions list
        grp_excl = QGroupBox("Daftar Pengecualian Alamat Situs (Jangan Unduh Otomatis)")
        v_excl = QVBoxLayout(grp_excl)
        v_excl.setSpacing(8)

        lbl_excl_desc = QLabel("Jangan mulai mengunduh secara otomatis dari situs atau tautan dengan pola alamat berikut:")
        lbl_excl_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        v_excl.addWidget(lbl_excl_desc)

        self.list_exceptions = QListWidget()
        self.list_exceptions.setMaximumHeight(140)
        self._load_exceptions_list()
        v_excl.addWidget(self.list_exceptions)

        h_excl_btns = QHBoxLayout()
        btn_add_excl = QPushButton("Tambah Alamat...")
        btn_add_excl.clicked.connect(self._add_exception_entry)
        btn_rem_excl = QPushButton("Hapus")
        btn_rem_excl.clicked.connect(self._remove_exception_entry)
        btn_reset_excl = QPushButton("Reset ke Default")
        btn_reset_excl.clicked.connect(self._reset_exceptions_to_default)

        h_excl_btns.addWidget(btn_add_excl)
        h_excl_btns.addWidget(btn_rem_excl)
        h_excl_btns.addWidget(btn_reset_excl)
        h_excl_btns.addStretch()
        v_excl.addLayout(h_excl_btns)

        layout.addWidget(grp_excl)
        layout.addStretch()

    def _setup_browser_tab(self):
        layout = QVBoxLayout(self.tab_browser)
        layout.setSpacing(12)

        # 1. Integrasi Peramban
        grp_browsers = QGroupBox("Integrasi Peramban Web (Browser Integration)")
        v_b = QVBoxLayout(grp_browsers)
        v_b.setSpacing(10)

        lbl_info = QLabel("Aktifkan tangkapan unduhan otomatis untuk browser yang terpasang:")
        lbl_info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        v_b.addWidget(lbl_info)

        self.chk_browser_chrome = QCheckBox("Google Chrome")
        self.chk_browser_chrome.setChecked(self.db.get_setting("integrate_chrome", "true") == "true")
        v_b.addWidget(self.chk_browser_chrome)

        self.chk_browser_edge = QCheckBox("Microsoft Edge")
        self.chk_browser_edge.setChecked(self.db.get_setting("integrate_edge", "true") == "true")
        v_b.addWidget(self.chk_browser_edge)

        self.chk_browser_firefox = QCheckBox("Mozilla Firefox")
        self.chk_browser_firefox.setChecked(self.db.get_setting("integrate_firefox", "true") == "true")
        v_b.addWidget(self.chk_browser_firefox)

        self.chk_browser_brave = QCheckBox("Brave & Opera (Chromium-based)")
        self.chk_browser_brave.setChecked(self.db.get_setting("integrate_brave", "true") == "true")
        v_b.addWidget(self.chk_browser_brave)

        layout.addWidget(grp_browsers)

        # 2. Host Integrasi & Ekstensi
        grp_host = QGroupBox("Host Integrasi Peramban && Ekstensi")
        v_h = QVBoxLayout(grp_host)
        v_h.setSpacing(10)

        lbl_host_desc = QLabel(
            "Krolix menyediakan Native Messaging Host berkecepatan tinggi:\n"
            "• com.zero.downloader (Ekstensi Krolix Downloader)\n"
            "Terdaftar di Registry HKCU tanpa memerlukan izin Administrator."
        )
        lbl_host_desc.setStyleSheet("color: #cbd5e1; font-size: 11px; line-height: 1.4;")
        v_h.addWidget(lbl_host_desc)

        h_host_btns = QHBoxLayout()
        btn_open_mgr = QPushButton("Buka Manajer Ekstensi & Browser...")
        btn_open_mgr.setObjectName("accentBtn")
        btn_open_mgr.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_mgr.clicked.connect(self._open_extension_manager)
        h_host_btns.addWidget(btn_open_mgr)

        btn_reregister = QPushButton("Daftarkan Ulang Host Integrasi")
        btn_reregister.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reregister.clicked.connect(self._reregister_integration)
        h_host_btns.addWidget(btn_reregister)
        h_host_btns.addStretch()

        v_h.addLayout(h_host_btns)
        layout.addWidget(grp_host)
        layout.addStretch()

    def _setup_jaringan_tab(self):
        layout = QVBoxLayout(self.tab_jaringan)

        grp_conn = QGroupBox("Koneksi && Kecepatan")
        v_conn = QVBoxLayout(grp_conn)
        v_conn.setSpacing(10)

        h_conn = QHBoxLayout()
        h_conn.addWidget(QLabel("Koneksi per File (Threads):"))
        self.spn_conn = QSpinBox()
        self.spn_conn.setRange(1, 64)
        saved_conn = int(self.db.get_setting("connections_count", self.db.get_setting("max_connections", 8)))
        self.spn_conn.setValue(saved_conn)
        h_conn.addWidget(self.spn_conn)

        h_conn.addSpacing(16)
        h_conn.addWidget(QLabel("Unduhan Bersamaan:"))
        self.spn_conc = QSpinBox()
        self.spn_conc.setRange(1, 32)
        self.spn_conc.setValue(int(self.db.get_setting("max_concurrent", 3)))
        h_conn.addWidget(self.spn_conc)
        h_conn.addStretch()
        v_conn.addLayout(h_conn)

        h_speed = QHBoxLayout()
        h_speed.addWidget(QLabel("Batas Kecepatan Global (0 = Tanpa Batas):"))
        self.spn_speed = QSpinBox()
        self.spn_speed.setRange(0, 500000)
        self.spn_speed.setSuffix(" KB/s")
        self.spn_speed.setValue(int(self.db.get_setting("speed_limit_kbps", 0)))
        h_speed.addWidget(self.spn_speed)
        h_speed.addStretch()
        v_conn.addLayout(h_speed)
        layout.addWidget(grp_conn)

        grp_adv = QGroupBox("Pengaturan Jaringan Lanjutan")
        v_adv = QVBoxLayout(grp_adv)
        
        self.chk_ipv6 = QCheckBox("Prioritaskan koneksi IPv6 (lebih cepat di CDN dual-stack)")
        self.chk_ipv6.setChecked(self.db.get_setting("prefer_ipv6", False) in [True, "true", "1"])
        v_adv.addWidget(self.chk_ipv6)
        
        h_proxy = QHBoxLayout()
        h_proxy.addWidget(QLabel("Proxy Global:"))
        self.cmb_proxy = QComboBox()
        self.cmb_proxy.addItem("Tidak Ada")
        
        # Load proxies from DB
        try:
            proxies = self.db.get_proxies()
            if proxies:
                for p in proxies:
                    # Assuming proxy format is string or dict, handling string here
                    proxy_val = p.get('url') if isinstance(p, dict) else str(p)
                    self.cmb_proxy.addItem(proxy_val)
        except Exception:
            pass # Fallback if get_proxies fails or isn't implemented

        current_proxy = self.db.get_setting("proxy_url", "")
        if current_proxy:
            idx = self.cmb_proxy.findText(current_proxy)
            if idx >= 0:
                self.cmb_proxy.setCurrentIndex(idx)
            else:
                self.cmb_proxy.addItem(current_proxy)
                self.cmb_proxy.setCurrentIndex(self.cmb_proxy.count() - 1)

        btn_manage_proxy = QPushButton("Kelola Proxy...")
        btn_manage_proxy.clicked.connect(self._open_proxy_manager)
        
        h_proxy.addWidget(self.cmb_proxy, 1)
        h_proxy.addWidget(btn_manage_proxy)
        v_adv.addLayout(h_proxy)
        
        layout.addWidget(grp_adv)

        # 3. BitTorrent Public Trackers Group
        grp_trackers = QGroupBox("BitTorrent Public Trackers")
        v_trk = QVBoxLayout(grp_trackers)
        v_trk.setSpacing(8)

        self.chk_auto_trackers = QCheckBox("Perbarui daftar tracker publik otomatis (Auto-fetch best trackers)")
        self.chk_auto_trackers.setChecked(self.db.get_setting("auto_update_trackers", "true") == "true")
        v_trk.addWidget(self.chk_auto_trackers)

        h_trk_status = QHBoxLayout()
        import time
        from ..core.tracker_manager import TrackerManager
        tm = TrackerManager.get_instance()
        t_info = tm.get_status_info()
        t_count = t_info.get("count", 16)
        t_time = t_info.get("last_updated", 0)
        t_time_str = time.strftime("%d/%m/%Y %H:%M", time.localtime(t_time)) if t_time > 0 else "Bawaan"
        self.lbl_tracker_status = QLabel(f"Aktif: {t_count} tracker (Pembaruan: {t_time_str})")
        self.lbl_tracker_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        h_trk_status.addWidget(self.lbl_tracker_status, 1)

        self.btn_refresh_trackers = QPushButton("Perbarui Sekarang")
        self.btn_refresh_trackers.clicked.connect(self._manual_refresh_trackers)
        h_trk_status.addWidget(self.btn_refresh_trackers)
        v_trk.addLayout(h_trk_status)
        layout.addWidget(grp_trackers)

        layout.addStretch()

    def _setup_tampilan_tab(self):
        layout = QVBoxLayout(self.tab_tampilan)
        
        grp_theme = QGroupBox("Tema && Warna")
        v_theme = QVBoxLayout(grp_theme)

        h_theme = QHBoxLayout()
        h_theme.addWidget(QLabel("Tema Aplikasi:"))
        self.cmb_theme = QComboBox()
        themes = {
            "macOS Sonoma Dark": "mica_dark",
            "macOS OLED Midnight": "oled_black",
            "macOS Space Gray": "nordic_navy",
            "macOS Light": "fluent_light"
        }
        for label, val in themes.items():
            self.cmb_theme.addItem(label, val)
        
        current_theme = self.db.get_setting("ui_theme", "mica_dark")
        for idx in range(self.cmb_theme.count()):
            if self.cmb_theme.itemData(idx) == current_theme:
                self.cmb_theme.setCurrentIndex(idx)
                break
        
        self.cmb_theme.currentIndexChanged.connect(self._update_preview)
        h_theme.addWidget(self.cmb_theme, 1)
        v_theme.addLayout(h_theme)

        v_theme.addSpacing(10)
        v_theme.addWidget(QLabel("Warna Aksen:"))
        
        self.accent_colors = {
            "Krolix Green": "#22c55e",
            "macOS Blue": "#0a84ff",
            "Chrome Silver": "#94a3b8",
            "Dark Titanium": "#64748b",
            "Platinum White": "#cbd5e1",
            "Slate Steel": "#475569",
            "Muted Cobalt": "#3b82f6",
            "Muted Sage": "#10b981"
        }
        
        h_accents = QHBoxLayout()
        saved_acc = self.db.get_setting("ui_accent", "#94a3b8")
        if saved_acc in ("#06b6d4", "#2563eb", "#8b5cf6", "#f59e0b", "#f43f5e", "#0284c7", "cyan", "emerald", "violet", "amber", "rose", "sky"):
            saved_acc = "#94a3b8"
        self.current_accent = saved_acc
        self.accent_btns = []
        
        for name, color in self.accent_colors.items():
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setToolTip(name)
            # Add dynamic border to indicate selection later
            style = f"""
                QPushButton {{
                    background-color: {color};
                    border-radius: 14px;
                    border: 2px solid transparent;
                }}
                QPushButton:hover {{
                    border: 2px solid #ffffff;
                }}
            """
            btn.setStyleSheet(style)
            btn.clicked.connect(lambda checked, c=color: self._set_accent(c))
            h_accents.addWidget(btn)
            self.accent_btns.append((btn, color))
            
        h_accents.addStretch()
        v_theme.addLayout(h_accents)
        self._update_accent_selection()

        layout.addWidget(grp_theme)
        
        # Live Preview
        grp_preview = QGroupBox("Pratinjau")
        v_prev = QVBoxLayout(grp_preview)
        self.frame_preview = QFrame()
        self.frame_preview.setFixedHeight(80)
        self.frame_preview.setStyleSheet("border-radius: 8px; border: 1px solid #1e293b;")
        v_prev.addWidget(self.frame_preview)
        
        btn_apply_theme = QPushButton("Terapkan Sekarang")
        btn_apply_theme.clicked.connect(self._apply_theme_now)
        v_prev.addWidget(btn_apply_theme)
        
        layout.addWidget(grp_preview)
        self._update_preview()
        
        layout.addStretch()

    def _set_accent(self, color):
        self.current_accent = color
        self._update_accent_selection()
        self._update_preview()

    def _update_accent_selection(self):
        for btn, color in self.accent_btns:
            if color == self.current_accent:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        border-radius: 14px;
                        border: 2px solid #ffffff;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        border-radius: 14px;
                        border: 2px solid transparent;
                    }}
                    QPushButton:hover {{
                        border: 2px solid #ffffff;
                    }}
                """)

    def _update_preview(self):
        theme_val = self.cmb_theme.currentData()
        
        # Generate some mock colors for preview based on theme
        bg_color = "#0b0f17"
        if theme_val == "oled_black":
            bg_color = "#000000"
        elif theme_val == "nordic_navy":
            bg_color = "#1e222a"
        elif theme_val == "fluent_light":
            bg_color = "#f3f4f6"
            
        self.frame_preview.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: 8px;
                border: 2px solid {self.current_accent};
            }}
        """)

    def _apply_theme_now(self):
        theme = self.cmb_theme.currentData()
        accent = self.current_accent
        try:
            stylesheet = get_app_stylesheet(theme, accent)
            QApplication.instance().setStyleSheet(stylesheet)
        except Exception as e:
            pass # Ignore if module is not fully implemented or app instance unavailable

    def _setup_keamanan_tab(self):
        layout = QVBoxLayout(self.tab_keamanan)
        
        grp_ssl = QGroupBox("Pengaturan SSL")
        v_ssl = QVBoxLayout(grp_ssl)
        
        v_ssl.addWidget(QLabel("Domain yang diizinkan SSL bypass:"))
        self.list_ssl = QListWidget()
        try:
            bypassed = SSLManager.get_instance().list_bypassed()
            for domain in bypassed:
                self.list_ssl.addItem(domain)
        except Exception:
            pass
            
        h_ssl_btns = QHBoxLayout()
        btn_add_ssl = QPushButton("Tambah")
        btn_add_ssl.clicked.connect(self._add_ssl_bypass)
        btn_rem_ssl = QPushButton("Hapus")
        btn_rem_ssl.clicked.connect(self._rem_ssl_bypass)
        h_ssl_btns.addWidget(btn_add_ssl)
        h_ssl_btns.addWidget(btn_rem_ssl)
        h_ssl_btns.addStretch()
        
        v_ssl.addWidget(self.list_ssl)
        v_ssl.addLayout(h_ssl_btns)
        layout.addWidget(grp_ssl)
        
        grp_priv = QGroupBox("Privasi")
        v_priv = QVBoxLayout(grp_priv)
        
        self.chk_zero_log = QCheckBox("Mode Krolix Log — Download tanpa jejak (tidak tersimpan di history)")
        self.chk_zero_log.setChecked(self.db.get_setting("zero_log_mode", False) in [True, "true", "1"])
        v_priv.addWidget(self.chk_zero_log)
        
        lbl_warn = QLabel("Peringatan: Saat mode ini aktif, semua riwayat unduhan akan dihapus begitu aplikasi ditutup.")
        lbl_warn.setStyleSheet("color: #f59e0b; font-size: 11px; margin-left: 24px;")
        lbl_warn.setWordWrap(True)
        v_priv.addWidget(lbl_warn)
        layout.addWidget(grp_priv)
        
        layout.addStretch()

    def _add_ssl_bypass(self):
        domain, ok = QInputDialog.getText(self, "Tambah Domain", "Masukkan domain (contoh: example.com):")
        if ok and domain.strip():
            self.list_ssl.addItem(domain.strip())
            try:
                SSLManager.get_instance().add_bypass(domain.strip())
            except Exception:
                pass

    def _rem_ssl_bypass(self):
        current = self.list_ssl.currentItem()
        if current:
            domain = current.text()
            self.list_ssl.takeItem(self.list_ssl.row(current))
            try:
                SSLManager.get_instance().remove_bypass(domain)
            except Exception:
                pass

    def _open_proxy_manager(self):
        dlg = ProxyManagerDialog(self.db, self)
        if dlg.exec():
            # Refresh proxy list
            self.cmb_proxy.clear()
            self.cmb_proxy.addItem("Tidak Ada")
            try:
                proxies = self.db.get_proxies()
                if proxies:
                    for p in proxies:
                        proxy_val = p.get('url') if isinstance(p, dict) else str(p)
                        self.cmb_proxy.addItem(proxy_val)
            except Exception:
                pass

    def _browse_dir(self):
        sel = QFileDialog.getExistingDirectory(self, "Pilih Folder Unduhan", self.txt_dir.text())
        if sel:
            self.txt_dir.setText(sel)

    def _open_category_folders_dialog(self):
        from .category_folders_dialog import CategoryFoldersDialog
        dlg = CategoryFoldersDialog(self.db, self)
        dlg.exec()

    def _manual_refresh_trackers(self):
        from ..core.tracker_manager import TrackerManager
        tm = TrackerManager.get_instance()
        self.btn_refresh_trackers.setEnabled(False)
        self.lbl_tracker_status.setText("Sedang memperbarui dari upstream GitHub...")

        def _on_done(ok, count, msg):
            def _ui_update():
                self.btn_refresh_trackers.setEnabled(True)
                import time
                t_str = time.strftime("%d/%m/%Y %H:%M", time.localtime())
                self.lbl_tracker_status.setText(f"Aktif: {count} tracker (Pembaruan: {t_str})")
                QMessageBox.information(self, "Tracker Diperbarui", msg)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, _ui_update)

        tm.update_trackers_async(force=True, on_completed=_on_done)

    def _load_exceptions_list(self):
        self.list_exceptions.clear()
        raw = self.db.get_setting("auto_download_exceptions", "")
        items = []
        if raw:
            items = [x.strip() for x in raw.split("\n") if x.strip()]
        else:
            defex_path = os.path.join(os.path.dirname(__file__), "..", "assets", "defexclist.txt")
            if os.path.exists(defex_path):
                try:
                    with open(defex_path, "r", encoding="utf-8", errors="ignore") as f:
                        items = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                except Exception:
                    pass
        for it in items[:150]:
            self.list_exceptions.addItem(it)

    def _add_exception_entry(self):
        val, ok = QInputDialog.getText(self, "Tambah Pengecualian", "Masukkan pola URL (contoh: http://*.contoh.com/*):")
        if ok and val.strip():
            self.list_exceptions.addItem(val.strip())

    def _remove_exception_entry(self):
        cur = self.list_exceptions.currentItem()
        if cur:
            self.list_exceptions.takeItem(self.list_exceptions.row(cur))

    def _reset_exceptions_to_default(self):
        self.db.set_setting("auto_download_exceptions", "")
        self._load_exceptions_list()

    def _open_extension_manager(self):
        dlg = ExtensionDialog(self, self.db)
        dlg.exec()

    def _reregister_integration(self):
        from ..utils.browser_integration import register_native_messaging_host, register_url_protocol, set_windows_autostart
        ok1 = register_url_protocol()
        ok2 = register_native_messaging_host()
        ok3 = set_windows_autostart(True)
        if ok1 or ok2 or ok3:
            QMessageBox.information(self, "Sukses", "Host integrasi browser (com.zero.downloader) berhasil didaftarkan ulang ke Registry Windows.")
        else:
            QMessageBox.warning(self, "Peringatan", "Host integrasi mungkin memerlukan perizinan tambahan.")

    def _save_settings(self):
        # 1. Unduhan Tab
        folder = self.txt_dir.text().strip()
        self.db.set_setting("download_dir", folder)
        self.db.set_setting("default_save_path", folder)
        self.db.set_setting("engine", self.cmb_engine.currentData())
        self.db.set_setting("enable_torrent", self.chk_torrent.isChecked())
        self.db.set_setting("category_subfolders", "true" if self.chk_category_subfolders.isChecked() else "false")
        
        clip_val = self.chk_clip.isChecked()
        self.db.set_setting("monitor_clipboard", "true" if clip_val else "false")
        self.db.set_setting("clipboard_monitor", clip_val)
        self.db.set_setting("always_on_worker", "true" if self.chk_always_on.isChecked() else "false")
        self.db.set_setting("autostart_worker", "true" if self.chk_autostart.isChecked() else "false")
        self.db.set_setting("minimize_to_tray", "true" if self.chk_tray.isChecked() else "false")
        self.db.set_setting("auto_extract", "true" if self.chk_auto_extract.isChecked() else "false")
        self.db.set_setting("show_complete_dialog", "true" if self.chk_comp_dlg.isChecked() else "false")
        self.db.set_setting("skip_delete_confirm", "false" if self.chk_confirm_del.isChecked() else "true")
        try:
            from ..utils.browser_integration import set_windows_autostart
            set_windows_autostart(self.chk_autostart.isChecked())
        except Exception:
            pass

        # 2. Jenis Berkas & Pengecualian Tab
        if hasattr(self, 'txt_extensions'):
            self.db.set_setting("auto_download_extensions", self.txt_extensions.toPlainText().strip())
        if hasattr(self, 'list_exceptions'):
            excl_items = [self.list_exceptions.item(i).text() for i in range(self.list_exceptions.count())]
            self.db.set_setting("auto_download_exceptions", "\n".join(excl_items))

        # 3. Integrasi Browser Tab
        if hasattr(self, 'chk_browser_chrome'):
            self.db.set_setting("integrate_chrome", "true" if self.chk_browser_chrome.isChecked() else "false")
            self.db.set_setting("integrate_edge", "true" if self.chk_browser_edge.isChecked() else "false")
            self.db.set_setting("integrate_firefox", "true" if self.chk_browser_firefox.isChecked() else "false")
            self.db.set_setting("integrate_brave", "true" if self.chk_browser_brave.isChecked() else "false")

        # 4. Jaringan Tab
        self.db.set_setting("connections_count", self.spn_conn.value())
        self.db.set_setting("max_connections", str(self.spn_conn.value()))
        self.db.set_setting("max_concurrent", self.spn_conc.value())
        
        speed_kbps = self.spn_speed.value()
        self.db.set_setting("speed_limit_kbps", speed_kbps)
        if self.speed_limiter:
            self.speed_limiter.set_limit(speed_kbps * 1024)
            
        self.db.set_setting("prefer_ipv6", "true" if self.chk_ipv6.isChecked() else "false")
        self.db.set_setting("auto_update_trackers", "true" if self.chk_auto_trackers.isChecked() else "false")
        
        proxy_val = self.cmb_proxy.currentText()
        if proxy_val == "Tidak Ada":
            self.db.set_setting("proxy_url", "")
        else:
            self.db.set_setting("proxy_url", proxy_val)

        # 5. Tampilan Tab
        self.db.set_setting("ui_theme", self.cmb_theme.currentData())
        self.db.set_setting("ui_accent", self.current_accent)

        # 6. Keamanan Tab
        self.db.set_setting("zero_log_mode", "true" if self.chk_zero_log.isChecked() else "false")

        self.accept()