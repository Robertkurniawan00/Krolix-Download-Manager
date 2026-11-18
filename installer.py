"""
Krolix Download Manager v2.8 - Standalone Setup & Installation Wizard.
Compatible with Windows 7, 8, 8.1, 10, and 11 (64-bit).
Features:
- macOS Modern Dark UI wizard
- Component extraction & verification
- Desktop & Start Menu shortcut creation with Krolix icon
- Add/Remove Programs Windows Uninstaller registration
- Native Browser Integration registration
- Optional Windows Startup integration
"""

import os
import sys
import shutil
import subprocess
from typing import Optional
from PyQt6.QtWidgets import (
    QApplication, QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar,
    QFileDialog, QMessageBox, QFrame, QWidget
)
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import Qt, QThread, pyqtSignal


def _get_special_folder(folder_name: str) -> str:
    """Safely retrieves special folders (Desktop, Programs) across win32com, PowerShell, and env fallbacks."""
    try:
        import win32com.client
        f = win32com.client.Dispatch("WScript.Shell").SpecialFolders(folder_name)
        if f and os.path.exists(f):
            return f
    except Exception:
        pass
    try:
        sf_prop = "Desktop" if folder_name.lower() == "desktop" else "Programs"
        cmd = f"[Environment]::GetFolderPath([Environment+SpecialFolder]::{sf_prop})"
        creation_flag = 0x08000000 if sys.platform.startswith("win") else 0
        res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                             capture_output=True, text=True, creationflags=creation_flag)
        path = res.stdout.strip()
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    if folder_name.lower() == "desktop":
        for d in [os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
                  os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop")]:
            if os.path.exists(d):
                return d
    elif folder_name.lower() == "programs":
        p = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
        if os.path.exists(p):
            return p
    return ""


def _create_shortcut(lnk_path: str, target_path: str, work_dir: str, icon_path: str = "", desc: str = "", args: str = "") -> bool:
    """Creates a Windows shell shortcut with dual win32com and PowerShell fallback."""
    # Method 1: WScript.Shell COM
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        s = shell.CreateShortcut(lnk_path)
        s.TargetPath = target_path
        s.WorkingDirectory = work_dir
        if args:
            s.Arguments = args
        if icon_path:
            s.IconLocation = icon_path
        s.Description = desc
        s.Save()
        if os.path.exists(lnk_path):
            return True
    except Exception:
        pass

    # Method 2: PowerShell script fallback
    try:
        def _ps_esc(s: str) -> str:
            return (s or "").replace("'", "''")

        ps_cmd = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{_ps_esc(lnk_path)}'); "
            f"$s.TargetPath = '{_ps_esc(target_path)}'; "
            f"$s.WorkingDirectory = '{_ps_esc(work_dir)}'; "
            f"$s.Arguments = '{_ps_esc(args)}'; "
        )
        if icon_path:
            ps_cmd += f"$s.IconLocation = '{_ps_esc(icon_path)}'; "
        if desc:
            ps_cmd += f"$s.Description = '{_ps_esc(desc)}'; "
        ps_cmd += "$s.Save()"
        creation_flag = 0x08000000 if sys.platform.startswith("win") else 0
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                       capture_output=True, creationflags=creation_flag)
        if os.path.exists(lnk_path):
            return True
    except Exception:
        pass
    return False


class InstallWorker(QThread):
    progress = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, target_dir: str, create_desktop_shortcut: bool,
                 create_start_menu: bool, register_startup: bool,
                 register_browser: bool):
        super().__init__()
        self.target_dir = target_dir
        self.create_desktop_shortcut = create_desktop_shortcut
        self.create_start_menu = create_start_menu
        self.register_startup = register_startup
        self.register_browser = register_browser

    def run(self):
        try:
            self.progress.emit(10, "Menyiapkan direktori instalasi...")
            os.makedirs(self.target_dir, exist_ok=True)

            # Source payload directory inside PyInstaller bundle or local folder
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            candidate_sources = [
                os.path.join(base_dir, "payload"),
                os.path.join(base_dir, "payload", "Zero"),
                os.path.join(base_dir, "payload", "Vortex"),
                os.path.join(base_dir, "dist", "Zero"),
                os.path.join(base_dir, "dist", "Vortex"),
                os.path.join(os.path.dirname(base_dir), "dist", "Zero"),
                os.path.join(os.path.dirname(base_dir), "dist", "Vortex"),
                os.path.join(base_dir, "Zero"),
                base_dir
            ]
            source_dir = None
            for c in candidate_sources:
                if os.path.isdir(c):
                    if (os.path.exists(os.path.join(c, "Krolix.exe")) or
                        os.path.exists(os.path.join(c, "Vortex.exe"))):
                        source_dir = c
                        break

            if not source_dir:
                self.finished_signal.emit(False, "File instalasi tidak ditemukan di dalam paket setup.")
                return

            # Security Integrity Verification: Detect unauthorized patches or rogue injection scripts
            for root, _, files in os.walk(source_dir):
                for f in files:
                    f_low = f.lower()
                    if f_low in ("sitecustomize.py", "usercustomize.py") or f_low.endswith(".pth"):
                        self.finished_signal.emit(False, "Integritas instalasi gagal: Terdeteksi file modifikasi tidak sah di dalam paket.")
                        return

            self.progress.emit(25, "Mengekstrak file program dan komponen Krolix Download Manager...")
            for item in os.listdir(source_dir):
                s_path = os.path.join(source_dir, item)
                d_path = os.path.join(self.target_dir, item)
                if os.path.isdir(s_path):
                    shutil.copytree(s_path, d_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(s_path, d_path)

            exe_path = os.path.join(self.target_dir, "Krolix.exe")
            if not os.path.exists(exe_path):
                for alt_name in ["Vortex.exe"]:
                    alt_exe = os.path.join(self.target_dir, alt_name)
                    if os.path.exists(alt_exe):
                        try:
                            shutil.copy2(alt_exe, exe_path)
                            break
                        except Exception:
                            exe_path = alt_exe

            # Ensure app/assets/logo.ico is installed for external shell references
            target_assets = os.path.join(self.target_dir, "app", "assets")
            os.makedirs(target_assets, exist_ok=True)
            installed_ico = os.path.join(target_assets, "logo.ico")

            src_ico = os.path.join(source_dir, "app", "assets", "logo.ico")
            if not os.path.exists(src_ico):
                src_ico = os.path.join(source_dir, "_internal", "app", "assets", "logo.ico")
            if os.path.exists(src_ico):
                try:
                    shutil.copy2(src_ico, installed_ico)
                except Exception:
                    pass

            # Primary icon location: use direct PE icon from exe or logo.ico
            icon_location = f"{exe_path},0" if os.path.exists(exe_path) else (installed_ico if os.path.exists(installed_ico) else "")
            uninst_ico = icon_location

            target_exe = exe_path
            target_args = ""
            target_work = self.target_dir

            self.progress.emit(60, "Membuat shortcut Desktop & Start Menu...")
            app_title = "Krolix Download Manager"

            if self.create_desktop_shortcut:
                desktop = _get_special_folder("Desktop")
                if desktop and os.path.exists(desktop):
                    _create_shortcut(os.path.join(desktop, f"{app_title}.lnk"), target_exe, target_work, icon_location, app_title, target_args)

            uninst_script = os.path.join(self.target_dir, "Uninstall_Krolix.bat")
            if self.create_start_menu:
                programs = _get_special_folder("Programs")
                if programs and os.path.exists(programs):
                    start_dir = os.path.join(programs, app_title)
                    os.makedirs(start_dir, exist_ok=True)
                    _create_shortcut(os.path.join(start_dir, f"{app_title}.lnk"), target_exe, target_work, icon_location, app_title, target_args)
                    _create_shortcut(os.path.join(start_dir, f"Uninstall {app_title}.lnk"), uninst_script, self.target_dir, uninst_ico, f"Uninstall {app_title}")

            # Notify Windows Shell to refresh icon cache immediately
            try:
                import ctypes
                ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
                subprocess.run(["ie4uinit.exe", "-show"], capture_output=True, check=False)
            except Exception:
                pass

            self.progress.emit(75, "Membuat konfigurasi uninstaller...")
            with open(uninst_script, "w", encoding="utf-8") as f:
                f.write(f"""@echo off
title Uninstall {app_title}
echo Menghapus instalasi {app_title}...
taskkill /f /im Krolix.exe 2>nul
taskkill /f /im Krolix.exe 2>nul
taskkill /f /im Vortex.exe 2>nul
timeout /t 1 /nobreak >nul
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\KrolixDownloadManager" /f 2>nul
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "KrolixDownloadManager" /f 2>nul
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "Zero" /f 2>nul
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Vortex" /f 2>nul
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "Vortex" /f 2>nul
echo Menghapus shortcut...
del /q "%USERPROFILE%\\Desktop\\{app_title}.lnk" 2>nul
rmdir /s /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\{app_title}" 2>nul
echo Menghapus file program...
cd /d "%TEMP%"
rmdir /s /q "{self.target_dir}" 2>nul
echo Selesai! {app_title} telah berhasil di-uninstall.
pause
""")

            # Register in Windows Add/Remove Programs (HKCU)
            try:
                import winreg
                uninst_reg = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\KrolixDownloadManager"
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, uninst_reg) as k:
                    winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "Krolix Download Manager v2.8")
                    winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, "2.6.0")
                    winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, "Krolix Core Team")
                    winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, icon_location)
                    winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, f'"{uninst_script}"')
                    winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, self.target_dir)
                    winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
                    winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
            except Exception:
                pass

            # Optional Startup integration
            if self.register_startup:
                self.progress.emit(85, "Mengkonfigurasi Startup Sistem...")
                try:
                    import winreg
                    run_reg = r"Software\Microsoft\Windows\CurrentVersion\Run"
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_reg, 0, winreg.KEY_SET_VALUE) as k:
                        winreg.SetValueEx(k, "KrolixDownloadManager", 0, winreg.REG_SZ, f'"{exe_path}" --tray')
                except Exception:
                    pass

            # Optional Browser Extension registration
            if self.register_browser:
                self.progress.emit(95, "Mengkonfigurasi integrasi browser...")
                try:
                    from app.utils.browser_integration import register_url_protocol, register_native_messaging_host
                    register_url_protocol(exe_path)
                    register_native_messaging_host(exe_path)
                except Exception:
                    pass

            self.progress.emit(100, "Instalasi selesai!")
            self.finished_signal.emit(True, exe_path)

        except Exception as e:
            self.finished_signal.emit(False, f"Terjadi kesalahan saat instalasi: {str(e)}")


def create_page_header(title: str, subtitle: str, show_logo=True) -> QWidget:
    container = QWidget()
    h_layout = QHBoxLayout(container)
    h_layout.setContentsMargins(0, 0, 0, 0)
    h_layout.setSpacing(12)

    if show_logo:
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(base_dir, "app", "assets", "logo_64.png")
        if not os.path.exists(logo_path):
            logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "assets", "logo_64.png")

        if os.path.exists(logo_path):
            lbl_logo = QLabel()
            lbl_logo.setPixmap(QPixmap(logo_path).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            h_layout.addWidget(lbl_logo)

    v_box = QVBoxLayout()
    v_box.setSpacing(2)
    t_lbl = QLabel(title)
    t_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #f1f5f9; letter-spacing: 0.5px;")
    s_lbl = QLabel(subtitle)
    s_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
    v_box.addWidget(t_lbl)
    v_box.addWidget(s_lbl)
    h_layout.addLayout(v_box)
    h_layout.addStretch()

    return container


class WelcomePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        hdr = create_page_header(
            "Selamat Datang di Krolix Setup",
            "Akselerator Unduhan Cepat Generasi Terbaru."
        )
        layout.addWidget(hdr)

        intro = QLabel("Wizard ini akan memandu Anda dalam instalasi Krolix Download Manager v2.8. Silakan klik 'Lanjut' untuk melanjutkan.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        layout.addWidget(intro)

        card = QFrame()
        card.setObjectName("FeatureCard")
        card.setStyleSheet("""
            QFrame#FeatureCard {
                background-color: #0b0f17;
                border: 1px solid #1b273d;
                border-radius: 6px;
                padding: 12px;
            }
            QLabel {
                color: #cbd5e1;
                font-size: 11px;
                line-height: 1.5;
            }
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setSpacing(7)

        features = [
            ("Akselerasi Multi-Thread", "Mesin dynamic segmentation hingga 32 koneksi paralel untuk kecepatan unduhan maksimal"),
            ("Download Queue & Scheduler", "Pengaturan antrean unduhan cerdas dengan penjadwalan otomatis"),
            ("Integrasi Browser Native", "Mendukung Google Chrome, Microsoft Edge, Firefox, Brave, dan Opera"),
            ("Site Grabber & Video Sniffer", "Unduh langsung video streaming HLS (.m3u8), DASH, dan file batch dari web"),
            ("Modern Windows 11 Interface", "Desain antarmuka modern Windows 11 Fluent Dark dengan command bar elegan")
        ]

        for title, desc in features:
            f_lbl = QLabel(f"<span style='color: #38bdf8; font-weight: bold;'>• {title}:</span> <span style='color: #94a3b8;'>{desc}</span>")
            f_lbl.setWordWrap(True)
            c_layout.addWidget(f_lbl)

        layout.addWidget(card)
        layout.addStretch()


class DirectoryPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        hdr = create_page_header(
            "Pilih Lokasi Instalasi",
            "Pilih folder tempat Krolix Download Manager akan diinstall.",
            show_logo=False
        )
        layout.addWidget(hdr)

        lbl = QLabel("Folder Tujuan:")
        lbl.setStyleSheet("font-weight: 600; color: #e2e8f0; font-size: 12px;")
        layout.addWidget(lbl)

        default_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", "Krolix Download Manager")

        row = QHBoxLayout()
        row.setSpacing(8)
        self.dir_input = QLineEdit(default_dir)
        row.addWidget(self.dir_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        opts_frame = QFrame()
        opts_frame.setObjectName("OptionsCard")
        opts_frame.setStyleSheet("""
            QFrame#OptionsCard {
                background-color: #0b0f17;
                border: 1px solid #1b273d;
                border-radius: 6px;
                padding: 12px;
                margin-top: 6px;
            }
            QCheckBox {
                color: #cbd5e1;
                font-size: 12px;
                spacing: 8px;
            }
        """)
        f_layout = QVBoxLayout(opts_frame)
        f_layout.setSpacing(8)

        self.desktop_chk = QCheckBox("Buat shortcut di Desktop")
        self.desktop_chk.setChecked(True)
        f_layout.addWidget(self.desktop_chk)

        self.start_chk = QCheckBox("Buat shortcut di Start Menu")
        self.start_chk.setChecked(True)
        f_layout.addWidget(self.start_chk)

        self.startup_chk = QCheckBox("Jalankan otomatis saat sistem dinyalakan (Startup)")
        self.startup_chk.setChecked(True)
        f_layout.addWidget(self.startup_chk)

        self.browser_chk = QCheckBox("Daftarkan integrasi browser native (Chrome, Edge, Firefox)")
        self.browser_chk.setChecked(True)
        f_layout.addWidget(self.browser_chk)

        layout.addWidget(opts_frame)
        layout.addStretch()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Pilih Folder Instalasi", self.dir_input.text())
        if d:
            self.dir_input.setText(os.path.join(d, "Krolix Download Manager"))


class InstallingPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.worker: Optional[InstallWorker] = None
        self.exe_path = ""
        self.success = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        hdr = create_page_header(
            "Menginstall Krolix Download Manager",
            "Tunggu beberapa saat, file sedang diekstrak dan dipasang...",
            show_logo=False
        )
        layout.addWidget(hdr)

        layout.addSpacing(10)
        self.status_label = QLabel("Menyiapkan instalasi...")
        self.status_label.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        self.pbar.setStyleSheet("""
            QProgressBar {
                background-color: #0b0f17;
                color: #ffffff;
                border: 1px solid #1b273d;
                border-radius: 4px;
                text-align: center;
                height: 22px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background-color: #10b981;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.pbar)
        layout.addStretch()

    def initializePage(self):
        self.wizard().button(QWizard.WizardButton.BackButton).setEnabled(False)
        self.wizard().button(QWizard.WizardButton.NextButton).setEnabled(False)

        dir_page: DirectoryPage = self.wizard().page(1)
        target_dir = dir_page.dir_input.text().strip()

        self.worker = InstallWorker(
            target_dir=target_dir,
            create_desktop_shortcut=dir_page.desktop_chk.isChecked(),
            create_start_menu=dir_page.start_chk.isChecked(),
            register_startup=dir_page.startup_chk.isChecked(),
            register_browser=dir_page.browser_chk.isChecked()
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, val: int, msg: str):
        self.pbar.setValue(val)
        self.status_label.setText(msg)

    def _on_finished(self, success: bool, res: str):
        self.success = success
        if success:
            self.exe_path = res
            self.status_label.setText("Instalasi selesai!")
            self.wizard().button(QWizard.WizardButton.NextButton).setEnabled(True)
            self.wizard().next()
        else:
            self.status_label.setText(f"Instalasi gagal: {res}")
            QMessageBox.critical(self, "Instalasi Gagal", res)
            self.wizard().button(QWizard.WizardButton.CancelButton).setEnabled(True)

    def isComplete(self) -> bool:
        return self.success


class FinishedPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        hdr = create_page_header(
            "Instalasi Berhasil Diselesaikan",
            "Krolix Download Manager telah terinstall dan siap digunakan.",
            show_logo=True
        )
        layout.addWidget(hdr)

        card = QFrame()
        card.setObjectName("FeatureCard")
        card.setStyleSheet("""
            QFrame#FeatureCard {
                background-color: #0b0f17;
                border: 1px solid #1b273d;
                border-radius: 6px;
                padding: 14px;
            }
            QLabel {
                color: #cbd5e1;
                font-size: 12px;
                line-height: 1.6;
            }
        """)
        c_layout = QVBoxLayout(card)
        lbl = QLabel(
            "Krolix Download Manager siap mempercepat proses unduhan file, video, dan media Anda.\n\n"
            "Klik Selesai untuk menutup wizard instalasi."
        )
        lbl.setWordWrap(True)
        c_layout.addWidget(lbl)
        layout.addWidget(card)

        self.run_chk = QCheckBox("Jalankan Krolix Download Manager sekarang")
        self.run_chk.setChecked(True)
        self.run_chk.setStyleSheet("font-weight: bold; font-size: 13px; color: #10b981; margin-top: 6px;")
        layout.addWidget(self.run_chk)
        layout.addStretch()


class KrolixInstallerWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Krolix Download Manager Setup")
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.resize(620, 450)
        self.setMinimumSize(600, 420)

        self.setButtonText(QWizard.WizardButton.BackButton, "< Kembali")
        self.setButtonText(QWizard.WizardButton.NextButton, "Lanjut >")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Batal")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Selesai")

        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "app", "assets", "logo.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "assets", "logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setStyleSheet("""
            QWizard, QWizardPage {
                background-color: #0b0f19;
                color: #f1f5f9;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #cbd5e1;
            }
            QLineEdit {
                background-color: #131b2e;
                border: 1px solid #1e293b;
                color: #ffffff;
                padding: 6px 10px;
                border-radius: 4px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #10b981;
            }
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #334155;
                color: #e2e8f0;
                padding: 6px 18px;
                border-radius: 4px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }
            QPushButton:disabled {
                background-color: #0f172a;
                color: #475569;
                border-color: #1e293b;
            }
        """)

        self.welcome_page = WelcomePage()
        self.dir_page = DirectoryPage()
        self.installing_page = InstallingPage()
        self.finished_page = FinishedPage()

        self.addPage(self.welcome_page)
        self.addPage(self.dir_page)
        self.addPage(self.installing_page)
        self.addPage(self.finished_page)

    def accept(self):
        if hasattr(self, "finished_page") and self.finished_page.run_chk.isChecked():
            exe_path = self.installing_page.exe_path
            if exe_path and os.path.exists(exe_path):
                try:
                    subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
                except Exception:
                    pass
        super().accept()


def main():
    app = QApplication(sys.argv)
    wizard = KrolixInstallerWizard()
    wizard.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


KrolixInstallerWizard = KrolixInstallerWizard
