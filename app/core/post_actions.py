import sys
import os
import subprocess
import ctypes
import shlex

class PostActionManager:
    @staticmethod
    def execute(action: str):
        action = (action or "").lower().strip()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
        if action == "shutdown":
            # Shutdown with 60 second delay to allow user to abort if needed
            subprocess.run(["shutdown", "/s", "/t", "60", "/c", "Zero Download Assistant: Downloads completed. PC will shutdown in 60s."], creationflags=flags)
        elif action == "restart":
            subprocess.run(["shutdown", "/r", "/t", "60", "/c", "Zero Download Assistant: Downloads completed. PC will restart in 60s."], creationflags=flags)
        elif action == "sleep":
            # Windows Sleep API
            try:
                ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
            except Exception:
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=flags)
        elif action == "hibernate":
            # Windows Hibernate API
            try:
                ctypes.windll.PowrProf.SetSuspendState(1, 1, 0)
            except Exception:
                subprocess.run(["shutdown", "/h"], creationflags=flags)
        elif action == "exit":
            sys.exit(0)

    @staticmethod
    def abort_shutdown():
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
        subprocess.run(["shutdown", "/a"], creationflags=flags)


class AntivirusScanner:
    """
    Zero Integrated Antivirus Scanner.
    Automatically scans downloaded files upon completion using Windows Defender (MpCmdRun.exe)
    or custom user-configured scanner executables.
    """
    @staticmethod
    def scan_file_async(file_path: str, db=None, on_scan_complete=None):
        def _worker():
            if not file_path or not os.path.exists(file_path):
                return
            
            if db:
                enabled = db.get_setting("antivirus_enabled", "true") == "true"
                if not enabled:
                    return
                scanner_cmd = db.get_setting("antivirus_cmd", "").strip()
            else:
                scanner_cmd = ""

            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
                if not scanner_cmd:
                    # Search standard Windows Defender CLI path
                    defender_path = r"C:\Program Files\Windows Defender\MpCmdRun.exe"
                    if not os.path.exists(defender_path):
                        platform_dir = r"C:\ProgramData\Microsoft\Windows Defender\Platform"
                        if os.path.exists(platform_dir):
                            candidates = []
                            for d in os.listdir(platform_dir):
                                cand = os.path.join(platform_dir, d, "MpCmdRun.exe")
                                if os.path.exists(cand):
                                    candidates.append(cand)
                            if candidates:
                                defender_path = sorted(candidates)[-1]
                    
                    if os.path.exists(defender_path):
                        res = subprocess.run(
                            [defender_path, "-Scan", "-ScanType", "3", "-File", os.path.abspath(file_path), "-DisableRemediation"],
                            capture_output=True,
                            text=True,
                            creationflags=flags
                        )
                        is_clean = (res.returncode == 0)
                        if on_scan_complete:
                            on_scan_complete(file_path, is_clean, "Clean" if is_clean else "Scan completed")
                else:
                    # Defensive: Parse into argument list with shlex without shell=True to prevent command injection
                    raw_tokens = shlex.split(scanner_cmd, posix=False)
                    abs_target = os.path.abspath(file_path)
                    
                    has_placeholder = False
                    cmd_args = []
                    for token in raw_tokens:
                        clean_token = token.strip('"\'')
                        if "%1" in clean_token or "%file%" in clean_token:
                            clean_token = clean_token.replace("%1", abs_target).replace("%file%", abs_target)
                            has_placeholder = True
                        cmd_args.append(clean_token)
                    
                    if not has_placeholder:
                        cmd_args.append(abs_target)

                    res = subprocess.run(
                        cmd_args,
                        capture_output=True,
                        creationflags=flags
                    )
                    is_clean = (res.returncode == 0)
                    if on_scan_complete:
                        on_scan_complete(file_path, is_clean, "Clean" if is_clean else "Scan completed")
            except Exception as e:
                print(f"[!] Antivirus scan notice: {e}")

        import threading
        threading.Thread(target=_worker, daemon=True).start()
