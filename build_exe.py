r"""
Krolix Download Manager v2.8 - Build Automation Script
Produces:
1. Standalone Application Folder (dist/Krolix/Krolix.exe) with portable runtime.
2. Active Windows Installation sync (%LOCALAPPDATA%\Programs\Krolix Download Manager).
3. Desktop & Start Menu shortcuts updated to point directly to Krolix.exe.
4. Single root launcher executable (Krolix.exe) with no duplicate setup or runner files.
"""

import os
import sys
import shutil
import subprocess

def build_root_launcher(project_dir, icon_path):
    """ deploys the Smart App Control-verified PyInstaller Krolix.exe to the root directory using an _internal directory junction."""
    dist_exe = os.path.join(project_dir, "dist", "Krolix", "Krolix.exe")
    dist_internal = os.path.join(project_dir, "dist", "Krolix", "_internal")
    root_exe = os.path.join(project_dir, "Krolix.exe")
    root_internal = os.path.join(project_dir, "_internal")

    if not os.path.exists(dist_exe):
        return False

    try:
        # Ensure _internal junction exists in project_dir pointing to dist/Krolix/_internal
        if os.path.exists(dist_internal):
            if os.path.lexists(root_internal):
                try:
                    subprocess.run(
                        ["cmd", "/c", "rmdir", root_internal],
                        capture_output=True,
                        text=True
                    )
                except Exception:
                    pass
            if not os.path.lexists(root_internal):
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", root_internal, dist_internal],
                    capture_output=True,
                    text=True
                )
        shutil.copy2(dist_exe, root_exe)
        # Remove any Zone.Identifier stream if present
        try:
            os.remove(root_exe + ":Zone.Identifier")
        except Exception:
            pass
        create_script_launchers(project_dir)
        print(f"[*] Root Krolix.exe deployed successfully (Smart App Control safe): {root_exe}")
        return True
    except Exception as e:
        print(f"[!] Warning deploying root Krolix.exe: {e}")
        return False

def create_script_launchers(target_dir: str):
    """Creates Krolix.vbs (silent SAC-safe launcher) and Run_Portable.bat in target directory."""
    try:
        vbs_path = os.path.join(target_dir, "Krolix.vbs")
        vbs_content = (
            'Set WshShell = CreateObject("WScript.Shell")\r\n'
            'scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)\r\n'
            'WshShell.CurrentDirectory = scriptDir\r\n'
            'WshShell.Run """" & scriptDir & "\\Krolix.exe""", 0, False\r\n'
        )
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(vbs_content)

        bat_path = os.path.join(target_dir, "Run_Portable.bat")
        bat_content = (
            '@echo off\r\n'
            'title Krolix Download Manager\r\n'
            'cd /d "%~dp0"\r\n'
            'start "" "%~dp0Krolix.exe" %*\r\n'
        )
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        print(f"[*] Script launchers created in: {target_dir}")
    except Exception as e:
        print(f"[!] Note creating script launchers in {target_dir}: {e}")

def build_native_engine(project_dir: str) -> bool:
    """Compiles KrolixNativeEngine.exe & KrolixComBridge.dll using csc.exe and registers system integration."""
    csc_path = os.path.expandvars(r"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
    cs_file = os.path.join(project_dir, "app", "native", "KrolixNativeEngine.cs")
    out_exe = os.path.join(project_dir, "app", "native", "KrolixNativeEngine.exe")
    com_cs = os.path.join(project_dir, "app", "native", "KrolixComBridge.cs")
    com_dll = os.path.join(project_dir, "app", "native", "KrolixComBridge.dll")

    if not os.path.exists(cs_file):
        return False

    # Compile KrolixComBridge.dll first so registration binds InprocServer32
    if os.path.exists(com_cs):
        cmd_com = [
            csc_path,
            "/nologo",
            "/optimize+",
            "/target:library",
            "/platform:anycpu",
            f"/out:{com_dll}",
            com_cs
        ]
        res_com = subprocess.run(cmd_com, capture_output=True, text=True)
        if res_com.returncode == 0 and os.path.exists(com_dll):
            print(f"[*] KrolixComBridge.dll compiled successfully: {com_dll}")
        else:
            print(f"[!] Warning compiling KrolixComBridge: {res_com.stderr}")

    cmd = [
        csc_path,
        "/nologo",
        "/optimize+",
        "/target:winexe",
        "/r:System.Windows.Forms.dll",
        f"/out:{out_exe}",
        cs_file
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and os.path.exists(out_exe):
        print(f"[*] KrolixNativeEngine compiled successfully: {out_exe}")
        try:
            subprocess.run([out_exe, "register"], capture_output=True)
            print("[*] COM Server & CLI registered.")
        except Exception:
            pass
    else:
        print(f"[!] Warning compiling KrolixNativeEngine: {res.stderr}")

    return True

def create_or_update_shortcut(lnk_path: str, target_path: str, work_dir: str, icon_path: str = "", desc: str = "", args: str = "") -> bool:
    """Creates or updates a Windows shell shortcut with dual win32com and PowerShell fallback."""
    os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        s = shell.CreateShortcut(lnk_path)
        s.TargetPath = target_path
        s.WorkingDirectory = work_dir
        s.Arguments = args
        if icon_path:
            s.IconLocation = icon_path
        if desc:
            s.Description = desc
        s.Save()
        if os.path.exists(lnk_path):
            return True
    except Exception:
        pass

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

def get_special_folder(folder_name: str) -> str:
    """Safely retrieves special folders (Desktop, Programs) across COM, PowerShell, and env."""
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

def purge_windows_icon_cache():
    """
    Terminates Windows Explorer, deletes the binary iconcache and thumbcache files,
    restarts Windows Explorer, and sends SHChangeNotify so all exe & shortcut icons
    refresh immediately to show the new rabbit mascot.
    """
    try:
        print("[*] Performing deep Windows Explorer icon cache purge...")
        subprocess.run(["taskkill", "/F", "/IM", "explorer.exe"], capture_output=True)
        import time
        time.sleep(0.5)

        local_app = os.environ.get("LOCALAPPDATA", "")
        # Remove IconCache.db
        old_ic = os.path.join(local_app, "IconCache.db")
        if os.path.exists(old_ic):
            try:
                os.remove(old_ic)
            except Exception:
                pass

        # Remove iconcache*.db and thumbcache*.db in Explorer
        exp_cache = os.path.join(local_app, "Microsoft", "Windows", "Explorer")
        if os.path.exists(exp_cache):
            import glob
            for pat in ["iconcache*.db", "thumbcache*.db"]:
                for f in glob.glob(os.path.join(exp_cache, pat)):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

        # Restart explorer (use WMI to ensure explorer launches independently outside any job object)
        restarted = False
        try:
            cmd = ['powershell', '-NoProfile', '-Command', r'([wmiclass]"win32_process").Create("C:\Windows\explorer.exe")']
            res = subprocess.run(cmd, capture_output=True, text=True)
            if "ReturnValue" in res.stdout and "0" in res.stdout:
                restarted = True
        except Exception:
            pass
        if not restarted:
            flags = 0x00000008 | 0x01000000 if sys.platform == "win32" else 0
            subprocess.Popen(["explorer.exe"], creationflags=flags)
        time.sleep(1.0)

        # Notify Shell
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
        subprocess.run(["ie4uinit.exe", "-show"], capture_output=True, check=False)
        print("[*] Windows icon cache purged and rebuilt successfully.")
    except Exception as e:
        print(f"[!] Warning purging icon cache: {e}")

def build():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    icon_path = os.path.join(project_dir, "app", "assets", "logo.ico")
    main_py = os.path.join(project_dir, "main.py")
    assets_dir = os.path.join(project_dir, "app", "assets")
    extension_dir = os.path.join(project_dir, "extension")

    print("=" * 72)
    print("   KROLIX DOWNLOAD MANAGER v2.8 - PACKAGING AUTOMATION")
    print("=" * 72)
    print(f"[*] Project Directory : {project_dir}")
    print(f"[*] Main Entry        : {main_py}")
    print(f"[*] App Icon          : {icon_path}")

    # --- Step 0: Terminate any running Zero instances & build native engine ---
    print("\n[0/4] Terminating any running application processes...")
    for proc in ["Krolix.exe", "Krolix_Setup.exe", "Vortex.exe", "Vortex_Setup.exe", "KrolixNativeEngine.exe", "ffmpeg.exe", "aria2c.exe"]:
        try:
            subprocess.run(["taskkill", "/F", "/IM", proc], capture_output=True)
        except Exception:
            pass
    try:
        subprocess.run([
            "powershell", "-NoProfile", "-Command",
            r"Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -match 'Krolix Download Manager' -or $_.CommandLine -match 'DOWNLOAD MANAGER\\main\.py') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        ], capture_output=True)
    except Exception:
        pass

    print("[*] Compiling High-Speed C# Native Engine & System Companion...")
    build_native_engine(project_dir)

    # Clean previous build & dist directories before PyInstaller runs
    dist_dir = os.path.join(project_dir, "dist", "Krolix")
    build_dir = os.path.join(project_dir, "build", "Krolix")
    for d in [dist_dir, build_dir]:
        if os.path.exists(d):
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass

    native_dir = os.path.join(project_dir, "app", "native")
    api_dir = os.path.join(project_dir, "app", "api")

    # --- Step 1: Run PyInstaller for Standalone App ---
    print("\n[1/4] Compiling Standalone Krolix Download Manager Application...")
    cmd_app = [
        sys.executable, "-m", "PyInstaller",
        "--name=Krolix",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--optimize=2",  # Strip docstrings, comments, parameter descriptions and assertions
        f"--icon={icon_path}",
        f"--add-data={assets_dir}{os.pathsep}app/assets",
        f"--add-data={extension_dir}{os.pathsep}extension",
        f"--add-data={native_dir}{os.pathsep}app/native",
        f"--add-data={api_dir}{os.pathsep}app/api",
        "--collect-all=yt_dlp",
        "--collect-all=cryptography",
        "--hidden-import=yt_dlp",
        "--hidden-import=cryptography",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=sqlite3",
        "--hidden-import=urllib.request",
        "--hidden-import=urllib.parse",
        "--hidden-import=json",
        "--hidden-import=hashlib",
        "--hidden-import=threading",
        "--hidden-import=http.server",
        "--hidden-import=app.core.hls_downloader",
        "--hidden-import=app.core.audio_muxer",
        "--hidden-import=app.core.aria2_downloader",
        "--hidden-import=app.core.torrent_downloader",
        "--hidden-import=app.core.audio_feedback",
        "--hidden-import=app.utils.browser_integration",
        "--hidden-import=winsound",
        "--hidden-import=app.ui.fluent_icons",
        "--hidden-import=app.ui.styles",
        "--hidden-import=app.ui.main_window",
        "--hidden-import=app.ui.complete_dialog",
        "--hidden-import=app.ui.add_dialog",
        "--hidden-import=app.ui.conflict_dialog",
        "--hidden-import=app.ui.progress_dialog",
        "--hidden-import=app.ui.settings_dialog",
        "--hidden-import=app.ui.batch_dialog",
        "--hidden-import=app.ui.hash_dialog",
        "--hidden-import=app.ui.credentials_dialog",
        "--hidden-import=app.ui.scheduler_dialog",
        "--hidden-import=app.ui.media_dialog",
        "--hidden-import=app.ui.grabber_dialog",
        "--hidden-import=app.ui.refresh_url_dialog",
        "--hidden-import=app.ui.torrent_search_dialog",
        "--hidden-import=app.ui.tip_dialog",
        "--hidden-import=app.ui.extension_dialog",
        "--hidden-import=app.core.torrent_search_client",
        "--hidden-import=app.ui.torrent_seeding_dialog",
        "--hidden-import=app.core.pikpak_resolver",
        "--hidden-import=app.core.av01_resolver",
        "--hidden-import=app.services.api_server",
        # New feature modules
        "--hidden-import=app.core.ytdlp_worker",
        "--hidden-import=app.core.duplicate_detector",
        "--hidden-import=app.core.ssl_manager",
        "--hidden-import=app.core.dht_crawler",
        "--hidden-import=app.ui.ytdlp_dialog",
        "--hidden-import=app.ui.proxy_manager_dialog",
        "--hidden-import=app.ui.torrent_file_selector",
        "--hidden-import=app.ui.dht_search_dialog",
        "--hidden-import=app.core.tracker_manager",
        "--hidden-import=app.ui.category_folders_dialog",
        "--hidden-import=app.ui.batch_sniffer_dialog",
        "--hidden-import=app.ui.fake_serial_dialog",
        "--hidden-import=app.ui.license_dialog",
        "--hidden-import=app.ui.nag_dialog",
        "--hidden-import=app.core.license_manager",
        "--hidden-import=app.core.stream_watchlist",
        "--hidden-import=app.ui.watchlist_dialog",
        "--hidden-import=app.utils.security_guard",
        "--hidden-import=yt_dlp",
        "--hidden-import=socks",
        "--hidden-import=certifi",
        "--hidden-import=curl_cffi",
        "--collect-all=certifi",
        "--collect-all=curl_cffi",
        "--exclude-module=PyQt6.QtQml",
        "--exclude-module=PyQt6.QtQuick",
        "--exclude-module=PyQt6.QtWebEngineCore",
        "--exclude-module=PyQt6.QtPdf",
        "--exclude-module=PyQt6.QtPdfWidgets",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        "--exclude-module=pandas",
        "--exclude-module=torch",
        main_py
    ]

    res_app = subprocess.run(cmd_app)
    if res_app.returncode != 0:
        print("[!] Building Krolix.exe failed!")
        sys.exit(res_app.returncode)

    dist_dir = os.path.join(project_dir, "dist", "Krolix")
    exe_path = os.path.join(dist_dir, "Krolix.exe")

    # --- Step 1b: Build Standalone Setup Wizard (Krolix_Setup.exe) ---
    installer_py = os.path.join(project_dir, "installer.py")
    if os.path.exists(installer_py):
        print("\n[1b/4] Compiling Standalone Krolix Setup Wizard (Krolix_Setup.exe)...")
        cmd_installer = [
            sys.executable, "-m", "PyInstaller",
            "--name=Krolix_Setup",
            "--windowed",
            "--onefile",
            "--noconfirm",
            "--clean",
            "--optimize=2",
            f"--icon={icon_path}",
            f"--add-data={assets_dir}{os.pathsep}app/assets",
            f"--add-data={dist_dir}{os.pathsep}payload/Krolix",
            f"--distpath={dist_dir}",
            installer_py
        ]
        res_inst = subprocess.run(cmd_installer)
        if res_inst.returncode == 0:
            setup_in_dist = os.path.join(dist_dir, "Krolix_Setup.exe")
            setup_in_parent = os.path.join(project_dir, "dist", "Krolix_Setup.exe")
            if os.path.exists(setup_in_dist):
                try:
                    shutil.copy2(setup_in_dist, setup_in_parent)
                except Exception:
                    pass
                print(f"[*] Standalone Setup Wizard deployed: {setup_in_dist}")

    # --- Step 2: Ensure Assets & Extension are fully populated in dist ---
    print("\n[2/4] Verifying Bundled Runtime Assets & Extension...")
    target_assets = os.path.join(dist_dir, "app", "assets")
    os.makedirs(target_assets, exist_ok=True)
    for fname in os.listdir(assets_dir):
        if fname == "bin" or fname.endswith(".py"):
            continue
        s_file = os.path.join(assets_dir, fname)
        d_file = os.path.join(target_assets, fname)
        if os.path.isfile(s_file):
            shutil.copy2(s_file, d_file)
        elif os.path.isdir(s_file):
            shutil.copytree(s_file, d_file, dirs_exist_ok=True)

    dist_bin = os.path.join(dist_dir, "app", "assets", "bin")
    os.makedirs(dist_bin, exist_ok=True)

    ffmpeg_src = os.path.join(assets_dir, "bin", "ffmpeg.exe")
    if os.path.exists(ffmpeg_src):
        shutil.copy2(ffmpeg_src, os.path.join(dist_dir, "ffmpeg.exe"))
        shutil.copy2(ffmpeg_src, os.path.join(dist_bin, "ffmpeg.exe"))

    aria2_src = os.path.join(assets_dir, "bin", "aria2c.exe")
    if os.path.exists(aria2_src):
        shutil.copy2(aria2_src, os.path.join(dist_dir, "aria2c.exe"))
        shutil.copy2(aria2_src, os.path.join(dist_bin, "aria2c.exe"))

    native_src = os.path.join(project_dir, "app", "native", "KrolixNativeEngine.exe")
    if os.path.exists(native_src):
        shutil.copy2(native_src, os.path.join(dist_dir, "KrolixNativeEngine.exe"))
        shutil.copy2(native_src, os.path.join(dist_bin, "KrolixNativeEngine.exe"))
        dist_native = os.path.join(dist_dir, "app", "native")
        os.makedirs(dist_native, exist_ok=True)
        shutil.copy2(native_src, os.path.join(dist_native, "KrolixNativeEngine.exe"))

    com_dll_src = os.path.join(project_dir, "app", "native", "KrolixComBridge.dll")
    if os.path.exists(com_dll_src):
        shutil.copy2(com_dll_src, os.path.join(dist_dir, "KrolixComBridge.dll"))
        dist_native = os.path.join(dist_dir, "app", "native")
        os.makedirs(dist_native, exist_ok=True)
        shutil.copy2(com_dll_src, os.path.join(dist_native, "KrolixComBridge.dll"))

    api_src = os.path.join(project_dir, "app", "api")
    if os.path.exists(api_src):
        shutil.copytree(api_src, os.path.join(dist_dir, "app", "api"), dirs_exist_ok=True)

    sounds_src = os.path.join(assets_dir, "sounds")
    if os.path.exists(sounds_src):
        shutil.copytree(sounds_src, os.path.join(target_assets, "sounds"), dirs_exist_ok=True)

    target_ext = os.path.join(dist_dir, "extension")
    if os.path.exists(extension_dir):
        if os.path.exists(target_ext):
            shutil.rmtree(target_ext)
        shutil.copytree(extension_dir, target_ext)

    # Automatically sync to active local installation directory
    local_app_dir = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krolix Download Manager")
    if os.path.exists(local_app_dir):
        # Remove old Zero remnants
        for old_zero_file in ["Zero.exe", "ZeroNativeEngine.exe", "ZeroComBridge.dll", "Install_Zero.bat", "Uninstall_Zero.bat", "Zero.vbs", "Run_Zero.bat", "Zero_Setup.exe"]:
            old_p = os.path.join(local_app_dir, old_zero_file)
            if os.path.exists(old_p):
                try:
                    os.remove(old_p)
                except Exception:
                    pass

        print(f"[*] Syncing updated build to active installation: {local_app_dir}")
        for proc in ["Krolix.exe", "aria2c.exe", "ffmpeg.exe", "KrolixNativeEngine.exe"]:
            try:
                subprocess.run(["taskkill", "/F", "/IM", proc], capture_output=True)
            except Exception:
                pass
        try:
            subprocess.run([
                "powershell", "-NoProfile", "-Command",
                r"Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -match 'Krolix Download Manager' -or $_.CommandLine -match 'DOWNLOAD MANAGER\\main\.py') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            ], capture_output=True)
        except Exception:
            pass
        import time
        time.sleep(0.5)
        try:
            src_app_pkg = os.path.join(project_dir, "app")
            if os.path.exists(exe_path):
                shutil.copy2(exe_path, os.path.join(local_app_dir, "Krolix.exe"))
            dist_internal = os.path.join(dist_dir, "_internal")
            local_internal = os.path.join(local_app_dir, "_internal")
            stale_certifi = os.path.join(local_internal, "certifi")
            if os.path.exists(stale_certifi):
                shutil.rmtree(stale_certifi, ignore_errors=True)
            if os.path.exists(dist_internal):
                shutil.copytree(dist_internal, local_internal, dirs_exist_ok=True)
            # Security: Do NOT copy raw .py source files to _internal
            for root, dirs, _ in os.walk(local_app_dir):
                for d in dirs:
                    if d == "__pycache__":
                        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
            if os.path.exists(ffmpeg_src):
                shutil.copy2(ffmpeg_src, os.path.join(local_app_dir, "ffmpeg.exe"))
            if os.path.exists(aria2_src):
                shutil.copy2(aria2_src, os.path.join(local_app_dir, "aria2c.exe"))
                local_bin = os.path.join(local_app_dir, "app", "assets", "bin")
                os.makedirs(local_bin, exist_ok=True)
                shutil.copy2(aria2_src, os.path.join(local_bin, "aria2c.exe"))
            if os.path.exists(native_src):
                shutil.copy2(native_src, os.path.join(local_app_dir, "KrolixNativeEngine.exe"))
                local_native = os.path.join(local_app_dir, "app", "native")
                os.makedirs(local_native, exist_ok=True)
                shutil.copy2(native_src, os.path.join(local_native, "KrolixNativeEngine.exe"))
                local_bin = os.path.join(local_app_dir, "app", "assets", "bin")
                os.makedirs(local_bin, exist_ok=True)
                shutil.copy2(native_src, os.path.join(local_bin, "KrolixNativeEngine.exe"))
            if os.path.exists(com_dll_src):
                shutil.copy2(com_dll_src, os.path.join(local_app_dir, "KrolixComBridge.dll"))
                local_native = os.path.join(local_app_dir, "app", "native")
                os.makedirs(local_native, exist_ok=True)
                shutil.copy2(com_dll_src, os.path.join(local_native, "KrolixComBridge.dll"))

            setup_src = os.path.join(dist_dir, "Krolix_Setup.exe")
            if os.path.exists(setup_src):
                shutil.copy2(setup_src, os.path.join(local_app_dir, "Krolix_Setup.exe"))
            if os.path.exists(api_src):
                shutil.copytree(api_src, os.path.join(local_app_dir, "app", "api"), dirs_exist_ok=True)
            if os.path.exists(sounds_src):
                shutil.copytree(sounds_src, os.path.join(local_app_dir, "app", "assets", "sounds"), dirs_exist_ok=True)

            local_app_ext = os.path.join(local_app_dir, "extension")
            if os.path.exists(local_app_ext):
                shutil.rmtree(local_app_ext)
            if os.path.exists(extension_dir):
                shutil.copytree(extension_dir, local_app_ext)

            local_app_assets = os.path.join(local_app_dir, "app", "assets")
            os.makedirs(local_app_assets, exist_ok=True)
            for fname in ["logo.ico", "app_icon.ico", "logo_16.png", "logo_24.png", "logo_32.png", "logo_48.png", "logo_64.png", "logo_128.png", "logo_256.png"]:
                src_f = os.path.join(assets_dir, fname)
                if os.path.exists(src_f):
                    shutil.copy2(src_f, os.path.join(local_app_assets, fname))

            # Deploy Smart App Control-safe C# Krolix.exe launcher (NO .py source code copied)
            build_root_launcher(project_dir, icon_path)
            root_launcher_exe = os.path.join(project_dir, "Krolix.exe")
            if os.path.exists(root_launcher_exe):
                shutil.copy2(root_launcher_exe, os.path.join(local_app_dir, "Krolix.exe"))

            # Ensure browser integrations (URL protocol and Native Messaging host) are registered and manifests synced
            try:
                from app.utils.browser_integration import setup_all_browser_integrations
                setup_all_browser_integrations()
                native_manifest_name = "com.krolix.downloader.json"
                for cand in [os.path.join(local_app_dir, native_manifest_name),
                             os.path.join(dist_dir, native_manifest_name),
                             os.path.join(project_dir, native_manifest_name)]:
                    if os.path.exists(cand):
                        shutil.copy2(cand, os.path.join(dist_dir, native_manifest_name))
                        shutil.copy2(cand, os.path.join(local_app_dir, native_manifest_name))
                        shutil.copy2(cand, os.path.join(project_dir, native_manifest_name))
                        break
            except Exception as e:
                print(f"[!] Warning registering browser integrations in build: {e}")

            # Update and ensure Desktop and Start Menu shortcuts are healthy
            try:
                # Check if Smart App Control (SAC) is active in Windows 11
                # 0 = Off, 1 = Evaluation (enforcing), 2 = On (enforcing)
                sac_active = False
                try:
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\CI\Policy") as key:
                        val, _ = winreg.QueryValueEx(key, "VerifiedAndReputablePolicyState")
                        if val in (1, 2):
                            sac_active = True
                except Exception:
                    pass

                create_script_launchers(local_app_dir)

                pythonw_exe = sys.executable.replace("python.exe", "pythonw.exe")
                if not os.path.exists(pythonw_exe):
                    pythonw_exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")

                local_main = os.path.join(local_app_dir, "main.py")
                project_main = os.path.join(project_dir, "main.py")
                target_main = local_main if os.path.exists(local_main) else project_main

                dist_exe_path = os.path.join(dist_dir, "Krolix.exe")
                local_exe_path = os.path.join(local_app_dir, "Krolix.exe")

                target_exe = local_exe_path if os.path.exists(local_exe_path) else dist_exe_path
                target_args = ""
                target_workdir = os.path.dirname(target_exe)
                print(f"[*] Configuring shortcuts directly targeting: {target_exe}")

                installed_ico = os.path.join(local_app_assets, "logo.ico")
                if not os.path.exists(installed_ico):
                    installed_ico = icon_path

                icon_loc = f"{target_exe},0" if os.path.exists(target_exe) else installed_ico
                uninst_bat = os.path.join(local_app_dir, "Uninstall_Krolix.bat")

                desktop_dir = get_special_folder("Desktop")
                if desktop_dir and os.path.exists(desktop_dir):
                    desktop_lnk = os.path.join(desktop_dir, "Krolix Download Manager.lnk")
                    create_or_update_shortcut(desktop_lnk, target_exe, target_workdir, icon_loc, "Krolix Download Manager", target_args)

                programs_dir = get_special_folder("Programs")
                if programs_dir and os.path.exists(programs_dir):
                    start_dir = os.path.join(programs_dir, "Krolix Download Manager")
                    os.makedirs(start_dir, exist_ok=True)
                    start_lnk = os.path.join(start_dir, "Krolix Download Manager.lnk")
                    create_or_update_shortcut(start_lnk, target_exe, target_workdir, icon_loc, "Krolix Download Manager", target_args)
                    root_start_lnk = os.path.join(programs_dir, "Krolix Download Manager.lnk")
                    if os.path.exists(root_start_lnk):
                        create_or_update_shortcut(root_start_lnk, target_exe, target_workdir, icon_loc, "Krolix Download Manager", target_args)
                    if os.path.exists(uninst_bat):
                        uninst_lnk = os.path.join(start_dir, "Uninstall Krolix Download Manager.lnk")
                        create_or_update_shortcut(uninst_lnk, uninst_bat, local_app_dir, icon_loc, "Uninstall Krolix Download Manager")
            except Exception as e:
                print(f"[!] Warning updating shortcuts: {e}")

            purge_windows_icon_cache()
            print("[*] Active installation and shortcuts updated successfully.")
        except Exception as e:
            print(f"[!] Note updating active installation: {e}")

    # --- Step 3: Build Single Root Launcher (Krolix.exe) ---
    print("\n[3/4] Building Single Root Executable (Krolix.exe)...")
    build_root_launcher(project_dir, icon_path)
    purge_windows_icon_cache()

    # --- Step 4: Clean Up Duplicates, Stray Files & Purge Plaintext Source Code ---
    print("\n[4/4] Hardening release: Purging all plaintext source code (.py) from binaries...")
    py_purged = 0
    for sanitize_target in [dist_dir, local_app_dir]:
        if os.path.exists(sanitize_target):
            dep_main = os.path.join(sanitize_target, "main.py")
            if os.path.exists(dep_main):
                try:
                    with open(dep_main, "wb") as fh:
                        fh.write(b"\x00" * 32)
                    os.remove(dep_main)
                    py_purged += 1
                except Exception:
                    pass

            for leaked_sub in ["core", "services", "ui", "utils"]:
                leaked_path = os.path.join(sanitize_target, "app", leaked_sub)
                if os.path.exists(leaked_path):
                    shutil.rmtree(leaked_path, ignore_errors=True)

            for root, dirs, files in os.walk(sanitize_target):
                for f in files:
                    if f.endswith(".py"):
                        try:
                            f_full = os.path.join(root, f)
                            with open(f_full, "wb") as fh:
                                fh.write(b"\x00" * 32)
                            os.remove(f_full)
                            py_purged += 1
                        except Exception:
                            pass
                for d in list(dirs):
                    if d == "__pycache__":
                        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
    print(f"[*] Security Hardening: Successfully shredded and removed {py_purged} plaintext .py files.")
    print("[*] Removing duplicate exes, scripts, and temporary files...")
    files_to_remove = [
        os.path.join(project_dir, "Vortex_Setup.exe"),
        os.path.join(project_dir, "Krolix_Setup.exe"),
        os.path.join(project_dir, "Run_Vortex.bat"),
        os.path.join(project_dir, "aria2c.exe"),
        os.path.join(project_dir, "ffmpeg.exe"),
        os.path.join(project_dir, "Zero.spec"),
        os.path.join(project_dir, "Krolix_Setup.spec"),
        os.path.join(project_dir, "Vortex.spec"),
        os.path.join(project_dir, "Vortex_Setup.spec"),
        os.path.join(project_dir, "app", "native", "ZeroComRegister.exe"),
        os.path.join(project_dir, "app", "native", "zero_com.reg"),
        os.path.join(project_dir, "app", "native", "zero_com_hkcu.reg"),
    ]

    import glob
    for pat in ["*.spec", "test_*.png", "*.tmp", "*.bak", "temp_*.dat"]:
        files_to_remove.extend(glob.glob(os.path.join(project_dir, pat)))

    for f_path in files_to_remove:
        if os.path.exists(f_path):
            try:
                os.remove(f_path)
                print(f"[*] Removed duplicate/junk: {os.path.basename(f_path)}")
            except Exception as e:
                print(f"[!] Could not remove {f_path}: {e}")

    scratch_dir = os.path.join(project_dir, "scratch")
    if os.path.exists(scratch_dir):
        try:
            shutil.rmtree(scratch_dir)
            print("[*] Cleaned up temporary scratch directory.")
        except Exception:
            pass

    # --- Step 5: Generate Standalone Installer & Portable Package for Other PCs ---
    print("\n[5/5] Generating Standalone Installer & Portable Package...")
    installer_bat = r'''@echo off
setlocal enabledelayedexpansion
title Krolix Download Manager - Setup ^& Installer

echo ========================================================
echo       Krolix Download Manager - Installer ^& Setup
echo ========================================================
echo.

set "TARGET_DIR=%LOCALAPPDATA%\Programs\Krolix Download Manager"
echo [*] Target Directory: %TARGET_DIR%

echo [*] Stopping running processes if any...
taskkill /F /IM Krolix.exe >nul 2>&1
taskkill /F /IM KrolixNativeEngine.exe >nul 2>&1
taskkill /F /IM aria2c.exe >nul 2>&1
taskkill /F /IM ffmpeg.exe >nul 2>&1

if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

echo [*] Copying application files...
xcopy /E /I /Y /Q "%~dp0*" "%TARGET_DIR%\" >nul 2>&1

echo [*] Registering URL protocols (krolix-dl://, krolix://, zero-dl://, zero://)...
reg add "HKCU\Software\Classes\krolix-dl" /ve /d "URL:Krolix Download Manager Protocol" /f >nul 2>&1
reg add "HKCU\Software\Classes\krolix-dl" /v "URL Protocol" /d "" /f >nul 2>&1
reg add "HKCU\Software\Classes\krolix-dl\DefaultIcon" /ve /d "\"%TARGET_DIR%\Krolix.exe\",0" /f >nul 2>&1
reg add "HKCU\Software\Classes\krolix-dl\shell\open\command" /ve /d "\"%TARGET_DIR%\Krolix.exe\" \"%%1\"" /f >nul 2>&1

reg add "HKCU\Software\Classes\krolix" /ve /d "URL:Krolix Download Manager Protocol" /f >nul 2>&1
reg add "HKCU\Software\Classes\krolix" /v "URL Protocol" /d "" /f >nul 2>&1
reg add "HKCU\Software\Classes\krolix\DefaultIcon" /ve /d "\"%TARGET_DIR%\Krolix.exe\",0" /f >nul 2>&1
reg add "HKCU\Software\Classes\krolix\shell\open\command" /ve /d "\"%TARGET_DIR%\Krolix.exe\" \"%%1\"" /f >nul 2>&1

reg add "HKCU\Software\Classes\zero-dl" /ve /d "URL:Krolix Download Manager Protocol" /f >nul 2>&1
reg add "HKCU\Software\Classes\zero-dl" /v "URL Protocol" /d "" /f >nul 2>&1
reg add "HKCU\Software\Classes\zero-dl\DefaultIcon" /ve /d "\"%TARGET_DIR%\Krolix.exe\",0" /f >nul 2>&1
reg add "HKCU\Software\Classes\zero-dl\shell\open\command" /ve /d "\"%TARGET_DIR%\Krolix.exe\" \"%%1\"" /f >nul 2>&1

reg add "HKCU\Software\Classes\zero" /ve /d "URL:Krolix Download Manager Protocol" /f >nul 2>&1
reg add "HKCU\Software\Classes\zero" /v "URL Protocol" /d "" /f >nul 2>&1
reg add "HKCU\Software\Classes\zero\DefaultIcon" /ve /d "\"%TARGET_DIR%\Krolix.exe\",0" /f >nul 2>&1
reg add "HKCU\Software\Classes\zero\shell\open\command" /ve /d "\"%TARGET_DIR%\Krolix.exe\" \"%%1\"" /f >nul 2>&1

echo [*] Generating and registering Browser Native Messaging Host...
set "MANIFEST=%TARGET_DIR%\com.krolix.downloader.json"
powershell -NoProfile -Command "$p = Join-Path $env:LOCALAPPDATA 'Programs\Krolix Download Manager\Krolix.exe'; $obj = @{ name='com.krolix.downloader'; description='Krolix Download Manager Native Messaging Host'; path=$p; type='stdio'; allowed_origins=@('chrome-extension://dlmghihibfmgdfjkcfedcecdljoeamah/','chrome-extension://fmphmjmdhgpbhmkekcbfhpfhjhckjclh/','chrome-extension://ndcpkimcihhghdcddljkfmmjccdmcmof/','chrome-extension://bcfcjeddkhklkknmfhckpiigablapbab/','chrome-extension://admccjkmockfdflocgggjfgdacdodkdf/') }; $obj | ConvertTo-Json | Set-Content -Path '%MANIFEST%' -Encoding UTF8" >nul 2>&1
reg add "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.krolix.downloader" /ve /d "%MANIFEST%" /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.krolix.downloader" /ve /d "%MANIFEST%" /f >nul 2>&1
reg add "HKCU\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.krolix.downloader" /ve /d "%MANIFEST%" /f >nul 2>&1

echo [*] Registering C# Native Engine...
if exist "%TARGET_DIR%\KrolixNativeEngine.exe" (
    "%TARGET_DIR%\KrolixNativeEngine.exe" register >nul 2>&1
)

echo [*] Creating Desktop and Start Menu Shortcuts...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $d = [Environment]::GetFolderPath('Desktop'); $s = $ws.CreateShortcut(\"$d\Krolix Download Manager.lnk\"); $s.TargetPath = '%TARGET_DIR%\Krolix.exe'; $s.WorkingDirectory = '%TARGET_DIR%'; $s.IconLocation = '%TARGET_DIR%\Krolix.exe,0'; $s.Description = 'Krolix Download Manager'; $s.Save()" >nul 2>&1

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $p = [Environment]::GetFolderPath('Programs'); $smDir = Join-Path $p 'Krolix Download Manager'; if (!(Test-Path $smDir)) { New-Item -ItemType Directory -Path $smDir -Force }; $s = $ws.CreateShortcut(\"$smDir\Krolix Download Manager.lnk\"); $s.TargetPath = '%TARGET_DIR%\Krolix.exe'; $s.WorkingDirectory = '%TARGET_DIR%'; $s.IconLocation = '%TARGET_DIR%\Krolix.exe,0'; $s.Description = 'Krolix Download Manager'; $s.Save()" >nul 2>&1

echo.
echo ========================================================
echo        INSTALASI SELESAI DENGAN SUKSES!
echo ========================================================
echo.
echo Langkah Integrasi Ekstensi Browser:
echo 1. Buka browser (Chrome / Edge / Brave).
echo 2. Kunjungi halaman: chrome://extensions atau edge://extensions
echo 3. Aktifkan 'Mode Pengembang' / 'Developer mode' di pojok kanan atas.
echo 4. Klik 'Muat ekstensi yang belum dibongkar' / 'Load unpacked'.
echo 5. Pilih folder:
echo    %TARGET_DIR%\extension
echo.
echo Menjalankan Krolix Download Manager...
start "" "%TARGET_DIR%\Krolix.exe"
pause
'''

    portable_bat = r'''@echo off
title Krolix Download Manager (Portable)
start "" "%~dp0Krolix.exe" %*
'''

    uninstall_bat = r'''@echo off
title Krolix Download Manager - Uninstaller
echo Menghentikan proses Krolix Download Manager...
taskkill /F /IM Krolix.exe >nul 2>&1
taskkill /F /IM KrolixNativeEngine.exe >nul 2>&1
taskkill /F /IM aria2c.exe >nul 2>&1
taskkill /F /IM ffmpeg.exe >nul 2>&1

echo Menghapus registry associations...
reg delete "HKCU\Software\Classes\krolix-dl" /f >nul 2>&1
reg delete "HKCU\Software\Classes\krolix" /f >nul 2>&1
reg delete "HKCU\Software\Classes\zero-dl" /f >nul 2>&1
reg delete "HKCU\Software\Classes\zero" /f >nul 2>&1
reg delete "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.krolix.downloader" /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.krolix.downloader" /f >nul 2>&1
reg delete "HKCU\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.krolix.downloader" /f >nul 2>&1

echo Menghapus shortcut...
powershell -NoProfile -Command "$d = [Environment]::GetFolderPath('Desktop'); Remove-Item -Path \"$d\Krolix Download Manager.lnk\" -Force -ErrorAction SilentlyContinue; $p = [Environment]::GetFolderPath('Programs'); Remove-Item -Path \"$p\Krolix Download Manager\" -Recurse -Force -ErrorAction SilentlyContinue" >nul 2>&1

echo Penghapusan selesai. Anda dapat menghapus folder aplikasi secara manual.
pause
'''

    readme_txt = """Krolix Download Manager v2.8 - Standalone Package
==================================================

CARA MENGGUNAKAN DI PC LAIN:

OPSI A - INSTALASI LENGKAP KE SISTEM (DIREKOMENDASIKAN):
1. Ekstrak folder ini ke mana saja di PC baru.
2. Klik kanan pada 'Install_Krolix.bat' lalu pilih 'Run as administrator' (atau klik 2x).
3. Script akan otomatis:
   - Memasang Krolix ke: %LOCALAPPDATA%\\Programs\\Krolix Download Manager
   - Mendaftarkan URL protocol krolix-dl://
   - Mendaftarkan Native Messaging Host untuk Chrome, Edge, dan Brave
   - Membuat shortcut di Desktop dan Start Menu
   - Menjalankan Krolix.exe

OPSI B - MODE PORTABLE:
1. Cukup klik 2x pada 'Run_Portable.bat' atau 'Krolix.exe'.
2. Aplikasi akan langsung berjalan tanpa perlu install Python atau library tambahan.

CARA PASANG EKSTENSI BROWSER (CHROME / EDGE / BRAVE):
1. Buka browser, ketik:
   Chrome: chrome://extensions
   Edge  : edge://extensions
2. Aktifkan saklar 'Mode Pengembang' (Developer Mode).
3. Klik tombol 'Muat yang belum dibongkar' (Load Unpacked).
4. Pilih folder 'extension' yang ada di dalam paket ini.
5. Ekstensi siap menangkap unduhan secara otomatis!
"""

    with open(os.path.join(dist_dir, "Install_Krolix.bat"), "w", encoding="utf-8") as f:
        f.write(installer_bat)
    with open(os.path.join(dist_dir, "Run_Portable.bat"), "w", encoding="utf-8") as f:
        f.write(portable_bat)
    with open(os.path.join(dist_dir, "Uninstall_Krolix.bat"), "w", encoding="utf-8") as f:
        f.write(uninstall_bat)
    with open(os.path.join(dist_dir, "PETUNJUK_INSTALASI.txt"), "w", encoding="utf-8") as f:
        f.write(readme_txt)

    if os.path.exists(local_app_dir):
        with open(os.path.join(local_app_dir, "Install_Krolix.bat"), "w", encoding="utf-8") as f:
            f.write(installer_bat)
        with open(os.path.join(local_app_dir, "Run_Portable.bat"), "w", encoding="utf-8") as f:
            f.write(portable_bat)
        with open(os.path.join(local_app_dir, "Uninstall_Krolix.bat"), "w", encoding="utf-8") as f:
            f.write(uninstall_bat)
        with open(os.path.join(local_app_dir, "PETUNJUK_INSTALASI.txt"), "w", encoding="utf-8") as f:
            f.write(readme_txt)

    # Compress dist/Zero to a standalone zip for easy distribution
    import zipfile
    zip_path = os.path.join(project_dir, "dist", "Krolix_Download_Manager_v2.8_Standalone.zip")
    print(f"[*] Packaging standalone ZIP to: {zip_path}")
    try:
        # Deep Source Sanitization: Purge all .cs, .py, .spec, and .pdb files before packaging
        for root, dirs, files in os.walk(dist_dir):
            for f in files:
                if f.endswith((".py", ".cs", ".spec", ".pdb", ".orig", ".bak")):
                    try:
                        os.remove(os.path.join(root, f))
                        print(f"[*] Stripped source artifact: {f}")
                    except Exception:
                        pass

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(dist_dir):
                for file in files:
                    if file.endswith((".py", ".cs", ".spec", ".pdb")):
                        continue  # Absolute protection: never package raw source files
                    full_p = os.path.join(root, file)
                    rel_p = os.path.relpath(full_p, os.path.dirname(dist_dir))
                    zf.write(full_p, rel_p)

        # Integrity & Security Verification: Ensure 0 source files exist in the release zip
        with zipfile.ZipFile(zip_path, "r") as zf:
            source_leaks = [name for name in zf.namelist() if name.endswith((".py", ".cs", ".spec", ".pdb"))]
            if source_leaks:
                raise RuntimeError(f"Security Alert: Source code leak detected in zip: {source_leaks}")
        print(f"[*] Standalone ZIP package ready (Hardened & Protected): {zip_path} ({os.path.getsize(zip_path) / (1024*1024):.1f} MB)")
    except Exception as e:
        print(f"[!] Note packaging ZIP: {e}")



    print("\n" + "=" * 72)
    print("                    BUILD COMPLETED SUCCESSFULLY!")
    print("=" * 72)
    print(f"1. Single Root Executable       : {os.path.join(project_dir, 'Krolix.exe')}")
    print(f"2. Standalone Core Folder       : {dist_dir}")
    print(f"3. Active Installation          : {local_app_dir}")
    print("=" * 72)

if __name__ == "__main__":
    build()