import sys
import os
import traceback

if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Anti-Reverse-Engineering, Anti-Tamper & Security Hardening
try:
    from app.utils.security_guard import SecurityGuard
    SecurityGuard.init_protection()
except Exception:
    pass

# Early AppUserModelID registration: critical for taskbar icon & grouping
if sys.platform == "win32":
    try:
        import ctypes
        app_user_model_id = "Krolix.DownloadManager.App.v2"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_user_model_id)
    except Exception:
        pass

import subprocess

if sys.platform == "win32":
    _orig_popen = subprocess.Popen
    class NoWindowPopen(_orig_popen):
        def __init__(self, *args, **kwargs):
            # Check if this command is intended to open an explorer window
            cmd_target = ""
            if args:
                first = args[0]
                if isinstance(first, (list, tuple)) and first:
                    cmd_target = str(first[0]).lower()
                elif isinstance(first, str):
                    cmd_target = first.lower()

            if "explorer" not in cmd_target:
                cflags = kwargs.get("creationflags", 0)
                cflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                kwargs["creationflags"] = cflags

                sinfo = kwargs.get("startupinfo")
                if sinfo is None:
                    sinfo = subprocess.STARTUPINFO()
                sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                sinfo.wShowWindow = 0  # SW_HIDE
                kwargs["startupinfo"] = sinfo

            super().__init__(*args, **kwargs)

    subprocess.Popen = NoWindowPopen

def exception_hook(exctype, value, tb):
    """Prevent unhandled exceptions in PyQt slots from terminating the application."""
    err_msg = "".join(traceback.format_exception(exctype, value, tb))
    if sys.stderr is not None:
        try:
            sys.stderr.write(f"[FATAL CAUGHT] {err_msg}\n")
        except Exception:
            pass
    try:
        log_dir = os.path.join(os.path.expanduser("~"), ".krolix")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "crash.log"), "a", encoding="utf-8") as f:
            f.write(f"\n--- Crash Report ---\n{err_msg}\n")
    except Exception:
        pass

sys.excepthook = exception_hook

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from app.core.database import Database
from app.core.speed_limiter import SpeedLimiter
from app.core.downloader import DownloadEngine
from app.ui.main_window import MainWindow
from app.utils.helpers import get_app_icon, apply_taskbar_icon

def parse_standard_cli(argv):
    """
    Parses standard CLI switches:
    /d URL            - URL to download
    /p local_path     - Destination folder
    /f local_filename - Output file name
    /q                - Quit after completion
    /h                - Hangup / disconnect after download
    /n                - Silent mode (no prompt dialogs)
    /a                - Add to queue only, do not start immediately
    /s                - Start queue processing
    """
    if len(argv) <= 1:
        return None

    cli_args = {
        "url": None,
        "save_dir": None,
        "filename": None,
        "quit_after": False,
        "hangup": False,
        "silent": False,
        "queue_only": False,
        "start_queue": False
    }

    has_cli_flag = False
    i = 1
    while i < len(argv):
        arg = argv[i]
        lower = arg.lower().replace("-", "/").strip()
        if lower in ("/d", "/url") and i + 1 < len(argv):
            cli_args["url"] = argv[i + 1]
            has_cli_flag = True
            i += 2
        elif lower in ("/p", "/path", "/dir") and i + 1 < len(argv):
            cli_args["save_dir"] = argv[i + 1]
            has_cli_flag = True
            i += 2
        elif lower in ("/f", "/file", "/filename") and i + 1 < len(argv):
            cli_args["filename"] = argv[i + 1]
            has_cli_flag = True
            i += 2
        elif lower in ("/n", "/silent"):
            cli_args["silent"] = True
            has_cli_flag = True
            i += 1
        elif lower in ("/a", "/queue"):
            cli_args["queue_only"] = True
            has_cli_flag = True
            i += 1
        elif lower in ("/q", "/quit"):
            cli_args["quit_after"] = True
            has_cli_flag = True
            i += 1
        elif lower in ("/h", "/hangup"):
            cli_args["hangup"] = True
            has_cli_flag = True
            i += 1
        elif lower in ("/s", "/start"):
            cli_args["start_queue"] = True
            has_cli_flag = True
            i += 1
        elif arg.startswith("http://") or arg.startswith("https://") or arg.startswith("ftp://") or arg.startswith("magnet:"):
            if not cli_args["url"]:
                cli_args["url"] = arg
                has_cli_flag = True
            i += 1
        else:
            i += 1

    return cli_args if (has_cli_flag and (cli_args["url"] or cli_args["start_queue"])) else None


def main():
    # 1. Native Messaging stdio handler (invoked by Chrome / Edge)
    if len(sys.argv) > 1 and (sys.argv[1].startswith("chrome-extension://") or sys.argv[1] == "--native-messaging"):
        from app.utils.browser_integration import handle_native_messaging
        handle_native_messaging()
        return

    # Check for background worker flag
    is_background = any(arg in sys.argv for arg in ("--background", "--silent", "--worker", "-b"))

    # 2. Acquire Windows Kernel Single-Instance Mutex
    global _GLOBAL_INSTANCE_MUTEX
    already_running = False
    _GLOBAL_INSTANCE_MUTEX = None
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            _GLOBAL_INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, "Local\\KrolixDownloadManager_SingleInstance_v2")
            if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                already_running = True
        except Exception:
            pass

    # If background worker requested and already running without new download: quiet exit
    if already_running and is_background and not any(arg.startswith("krolix-dl://") or arg.startswith("zero-dl://") or arg.startswith("zero://") or arg == "/d" for arg in sys.argv):
        sys.exit(0)

    # 3. Check for standard CLI or URL protocol invocation: zero-dl://... or /d URL /p path /f name /n /a
    initial_download_payload = None
    cli_payload = parse_standard_cli(sys.argv)
    if cli_payload:
        initial_download_payload = cli_payload
    elif len(sys.argv) > 1 and (sys.argv[1].startswith("krolix-dl://") or sys.argv[1].startswith("zero-dl://") or sys.argv[1].startswith("zero://")):
        from app.utils.browser_integration import decode_protocol_url
        initial_download_payload = decode_protocol_url(sys.argv[1])

    if initial_download_payload:
        # Forward to running instance on port 9666 (retry briefly if primary instance is still binding port)
        import json, urllib.request, time
        attempts = 6 if already_running else 2
        forwarded = False
        for _ in range(attempts):
            try:
                req = urllib.request.Request(
                    "http://127.0.0.1:9666/download",
                    data=json.dumps(initial_download_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-Krolix-Client": "krolix-cli"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        forwarded = True
                        sys.exit(0)
            except Exception:
                if already_running:
                    time.sleep(0.35)
                else:
                    break
        if already_running and forwarded:
            sys.exit(0)

    # 4. Single-instance check for normal desktop launches (bring existing window to front)
    if already_running:
        restored = False
        try:
            import urllib.request, json
            req = urllib.request.Request(
                "http://127.0.0.1:9666/restore",
                data=b"{}",
                headers={"Content-Type": "application/json", "X-Krolix-Client": "desktop"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode('utf-8'))
                    if sys.platform == "win32":
                        try:
                            import ctypes, time
                            user32 = ctypes.windll.user32
                            user32.AllowSetForegroundWindow(-1)

                            target_hwnd = body.get("hwnd", 0)
                            # Poll briefly up to 400ms for window to be restored by background worker
                            for _ in range(4):
                                if target_hwnd and user32.IsWindow(target_hwnd) and user32.IsWindowVisible(target_hwnd):
                                    break
                                found = user32.FindWindowW(None, "Krolix Download Manager")
                                if found and user32.IsWindow(found) and user32.IsWindowVisible(found):
                                    target_hwnd = found
                                    break
                                time.sleep(0.1)

                            if target_hwnd and user32.IsWindow(target_hwnd):
                                VK_MENU = 0x12
                                KEYEVENTF_KEYUP = 0x0002
                                user32.keybd_event(VK_MENU, 0, 0, 0)
                                user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

                                user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
                                user32.ShowWindow(target_hwnd, 5)  # SW_SHOW
                                user32.BringWindowToTop(target_hwnd)
                                user32.SetForegroundWindow(target_hwnd)
                                restored = True
                            else:
                                # Target window was not found on this desktop station
                                restored = False
                                # If the reported PID is a ghost without a desktop window, terminate it to free port 9666
                                zombie_pid = body.get("pid")
                                if zombie_pid and zombie_pid != os.getpid():
                                    try:
                                        import signal
                                        os.kill(zombie_pid, signal.SIGTERM)
                                    except Exception:
                                        pass
                        except Exception:
                            restored = False
                    else:
                        restored = body.get("success", False)
        except Exception:
            restored = False

        if restored:
            # Existing instance was successfully notified and brought to foreground
            sys.exit(0)
        # If restore failed (e.g. background worker unresponsive or zombie), fall through and launch GUI normally!

    # Explicit Windows AppUserModelID: critical for taskbar grouping and custom icon rendering
    if sys.platform == "win32":
        try:
            import ctypes
            app_user_model_id = "Krolix.DownloadManager.App.v2"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_user_model_id)
        except Exception:
            pass

    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Krolix")
    app.setApplicationDisplayName("")

    # Set Application Icon (Multi-Resolution 16-256px for Taskbar, Titlebar & Tray)
    app_icon = get_app_icon()
    if app_icon and not app_icon.isNull():
        app.setWindowIcon(app_icon)

    # Ensure browser integrations (URL protocol & Native Messaging host) are registered
    try:
        from app.utils.browser_integration import setup_all_browser_integrations
        setup_all_browser_integrations()
    except Exception as e:
        print(f"[!] Browser integration setup warning: {e}")

    db = Database()
    from app.ui.styles import get_app_stylesheet
    theme_id = db.get_setting("ui_theme", db.get_setting("theme", "oled_black"))
    accent_id = db.get_setting("ui_accent", "krolix_green")
    if accent_id in ("chrome", "cyan", "emerald", "violet", "amber", "rose", "sky", "default"):
        accent_id = "krolix_green"
    app.setStyleSheet(get_app_stylesheet(theme_id, accent_id))

    speed_limit_kbps = int(db.get_setting("speed_limit_kbps", "0"))
    speed_limiter = SpeedLimiter(max_bytes_per_sec=speed_limit_kbps * 1024)

    engine = DownloadEngine(db=db, speed_limiter=speed_limiter)

    window = MainWindow(db=db, engine=engine, speed_limiter=speed_limiter)
    if app_icon and not app_icon.isNull():
        window.setWindowIcon(app_icon)
    apply_taskbar_icon(window)
    if not is_background:
        window.show()
        window.raise_()
        window.activateWindow()
    else:
        window.hide()

    # If launched with a download payload from browser, trigger the download dialog right away!
    if initial_download_payload:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(250, lambda: window._handle_incoming_download(initial_download_payload))

    sys.exit(app.exec())

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        try:
            log_dir = os.path.join(os.path.expanduser("~"), ".krolix")
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, "startup_error.log"), "w", encoding="utf-8") as f:
                f.write(err)
        except Exception:
            pass
        raise