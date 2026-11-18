"""
Krolix Download Manager - Browser Integration & Native Messaging Setup
Handles:
1. Windows URL Protocol registration (zero-dl:// and zero://) in HKCU
2. Chrome & Microsoft Edge Native Messaging Host registration (com.zero.downloader)
3. Dynamic detection of browser extension IDs from Chrome and Edge profiles
4. Chrome stdio Native Messaging Host protocol handler
5. Parsing and decoding zero-dl:// protocol payloads from browser extension
"""

import os
import sys
import json
import base64
import struct
import urllib.parse
import urllib.request
import subprocess
from typing import Optional, List, Set

PROTOCOL_SCHEME = "krolix-dl"
NATIVE_HOST_NAME = "com.krolix.downloader"
DEFAULT_EXTENSION_IDS = [
    "ndcpkimcihhghdcddljkfmmjccdmcmof",
    "dlmghihibfmgdfjkcfedcecdljoeamah",
    "bcfcjeddkhklkknmfhckpiigablapbab",
]


def get_sac_safe_pythonw() -> str:
    """Returns absolute path to pythonw.exe."""
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    if os.path.exists(pythonw):
        return os.path.abspath(pythonw)
    local_pythonw = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")
    if os.path.exists(local_pythonw):
        return local_pythonw
    return os.path.abspath(sys.executable)


def get_current_executable() -> str:
    """Returns absolute path to Krolix.exe or current python runner."""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)

    # Prioritize installed or dist Krolix.exe / Krolix.exe binary
    for cand in [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krolix Download Manager\Krolix.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krolix Download Manager\Krolix.exe"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "dist", "Krolix", "Krolix.exe")),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krolix Download Manager\Krolix.exe"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "dist", "Zero", "Krolix.exe")),
    ]:
        if os.path.exists(cand):
            return os.path.abspath(cand)

    # Fallback to python runner
    return get_sac_safe_pythonw()


def find_installed_extension_ids() -> List[str]:
    """Scans Chrome, Edge, and Brave preferences for installed Zero extensions."""
    ids: Set[str] = set(DEFAULT_EXTENSION_IDS)
    if sys.platform != "win32":
        return list(ids)

    user_data_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data")
    ]

    for base in user_data_paths:
        if not os.path.exists(base):
            continue
        try:
            for root, dirs, files in os.walk(base):
                # Skip deep storage caches
                dirs[:] = [d for d in dirs if d not in [
                    "Cache", "Code Cache", "IndexedDB", "blob_storage", "Service Worker", "GPUCache", "DawnCache"
                ]]
                for fname in ["Preferences", "Secure Preferences"]:
                    if fname in files:
                        pref_file = os.path.join(root, fname)
                        try:
                            with open(pref_file, "r", encoding="utf-8", errors="ignore") as f:
                                data = json.load(f)
                                extensions = data.get("extensions", {}).get("settings", {})
                                for ext_id, details in extensions.items():
                                    path = details.get("path", "")
                                    if "DOWNLOAD MANAGER" in path or "zero" in path.lower() or "extension" in path.lower():
                                        if len(ext_id) == 32 and ext_id.isalnum():
                                            ids.add(ext_id)
                        except Exception:
                            pass
        except Exception:
            pass

    return list(ids)


def register_url_protocol(exe_path: Optional[str] = None) -> bool:
    r"""Registers zero-dl:// protocol in HKCU\Software\Classes\zero-dl without requiring admin."""
    if sys.platform != "win32":
        return False

    exe = exe_path or get_current_executable()
    if not os.path.exists(exe):
        return False

    try:
        import winreg
        local_app_dir = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krolix Download Manager")
        if not os.path.exists(local_app_dir):
            local_app_dir = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krolix Download Manager")
        local_main = os.path.join(local_app_dir, "main.py")
        main_py = local_main if os.path.exists(local_main) else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
        pythonw = get_sac_safe_pythonw()

        for scheme in ["krolix-dl", "krolix", PROTOCOL_SCHEME, "zero"]:
            key_path = rf"Software\Classes\{scheme}"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:Krolix Download Manager Protocol")
                winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")

                with winreg.CreateKey(key, "DefaultIcon") as icon_key:
                    ico_p = os.path.join(local_app_dir, "app", "assets", "logo.ico")
                    if not os.path.exists(ico_p):
                        ico_p = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "logo.ico"))
                    if os.path.exists(ico_p):
                        winreg.SetValueEx(icon_key, "", 0, winreg.REG_SZ, f'"{ico_p}"')
                    else:
                        winreg.SetValueEx(icon_key, "", 0, winreg.REG_SZ, f'"{exe}",0')

                with winreg.CreateKey(key, r"shell\open\command") as cmd_key:
                    krolix_exe = os.path.join(local_app_dir, "Krolix.exe")
                    krolix_exe = os.path.join(local_app_dir, "Krolix.exe")
                    if os.path.exists(krolix_exe):
                        cmd_val = f'"{krolix_exe}" "%1"'
                    elif os.path.exists(krolix_exe):
                        cmd_val = f'"{krolix_exe}" "%1"'
                    elif "python" in exe.lower():
                        cmd_val = f'"{pythonw}" "{main_py}" "%1"'
                    else:
                        cmd_val = f'"{exe}" "%1"'
                    winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, cmd_val)

        return True
    except Exception as e:
        print(f"[!] Warning: Failed to register URL protocol: {e}")
        return False


def register_native_messaging_host(exe_path: Optional[str] = None) -> bool:
    """Registers com.zero.downloader Native Messaging Host for Chrome and Edge."""
    if sys.platform != "win32":
        return False

    exe = exe_path or get_current_executable()
    if not os.path.exists(exe):
        return False

    try:
        import winreg

        local_app_dir = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krolix Download Manager")
        if not os.path.exists(local_app_dir):
            local_app_dir = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krolix Download Manager")
        app_dir = local_app_dir if os.path.exists(local_app_dir) else os.path.join(os.path.expanduser("~"), ".krolix_download")
        os.makedirs(app_dir, exist_ok=True)
        manifest_path = os.path.join(app_dir, f"{NATIVE_HOST_NAME}.json")

        host_path = exe
        if "python" in exe.lower():
            bat_path = os.path.join(app_dir, "krolix_native_host.bat")
            local_main = os.path.join(local_app_dir, "main.py")
            main_py = local_main if os.path.exists(local_main) else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
            py_exe = exe.replace("pythonw.exe", "python.exe") if "pythonw.exe" in exe.lower() else exe
            with open(bat_path, "w", encoding="utf-8") as bf:
                bf.write(f'@echo off\r\n"{py_exe}" "{main_py}" --native-messaging %*\r\n')
            host_path = bat_path

        ext_ids = find_installed_extension_ids()
        allowed_origins = [f"chrome-extension://{eid}/" for eid in ext_ids] if ext_ids else []

        # Krolix Native Messaging Host manifest
        manifest_data = {
            "name": NATIVE_HOST_NAME,
            "description": "Krolix Download Manager Native Messaging Host",
            "path": host_path,
            "type": "stdio",
            "allowed_origins": allowed_origins
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        # Register in Windows Registry
        registry_mappings = [
            (rf"Software\Google\Chrome\NativeMessagingHosts\{NATIVE_HOST_NAME}", manifest_path),
            (rf"Software\Microsoft\Edge\NativeMessagingHosts\{NATIVE_HOST_NAME}", manifest_path),
            (rf"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\{NATIVE_HOST_NAME}", manifest_path),
        ]

        for reg_path, m_file in registry_mappings:
            try:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path) as reg_key:
                    winreg.SetValueEx(reg_key, "", 0, winreg.REG_SZ, m_file)
            except Exception:
                pass

        return True
    except Exception as e:
        print(f"[!] Warning: Failed to register Native Messaging host: {e}")
        return False


def set_windows_autostart(enable: bool = True) -> bool:
    r"""Configures HKCU\Software\Microsoft\Windows\CurrentVersion\Run for Always-On Background Worker."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "KrolixDownloadManager"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            if enable:
                pythonw = get_sac_safe_pythonw()
                local_app_dir = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krolix Download Manager")
                local_main = os.path.join(local_app_dir, "main.py")
                main_py = local_main if os.path.exists(local_main) else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
                cmd_val = f'"{pythonw}" "{main_py}" --background'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd_val)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"[!] Warning setting autostart: {e}")
        return False


def setup_all_browser_integrations():
    """Sets up URL protocol, native messaging host, and always-on background worker autostart."""
    register_url_protocol()
    register_native_messaging_host()
    set_windows_autostart(True)


def decode_protocol_url(raw_arg: str) -> Optional[dict]:
    """
    Decodes zero-dl://download?data=<base64_json> or zero-dl://<url> argument into task payload.
    """
    if not raw_arg or not (raw_arg.startswith("zero-dl://") or raw_arg.startswith("zero://")):
        return None

    try:
        scheme = "zero-dl://" if raw_arg.startswith("zero-dl://") else "zero://"
        remainder = raw_arg[len(scheme):]

        if "?" in remainder:
            parsed = urllib.parse.urlsplit(raw_arg)
            params = urllib.parse.parse_qs(parsed.query)
            if "data" in params and params["data"]:
                b64_data = params["data"][0]
                b64_data += "=" * (-len(b64_data) % 4)
                json_str = base64.b64decode(b64_data).decode("utf-8", errors="ignore")
                return json.loads(json_str)
            elif "url" in params and params["url"]:
                return {
                    "url": params["url"][0],
                    "filename": params.get("filename", [""])[0],
                    "title": params.get("title", [""])[0]
                }

        if remainder.startswith("http://") or remainder.startswith("https://") or remainder.startswith("ftp://"):
            return {"url": remainder}

        cleaned = remainder.strip("/").strip()
        cleaned += "=" * (-len(cleaned) % 4)
        try:
            json_str = base64.b64decode(cleaned).decode("utf-8", errors="ignore")
            data = json.loads(json_str)
            if isinstance(data, dict) and "url" in data:
                return data
        except Exception:
            pass

    except Exception as e:
        print(f"[!] Error decoding protocol URL {raw_arg}: {e}")

    return None


def handle_native_messaging():
    """
    Processes stdio input from Chrome/Edge/Brave Native Messaging, forwards to port 9666 if running,
    or launches detached Zero GUI if not running, then replies to browser and exits.
    """
    stdout_buf = None
    try:
        if sys.platform == "win32":
            try:
                import msvcrt
                msvcrt.setmode(0, os.O_BINARY)
                msvcrt.setmode(1, os.O_BINARY)
            except Exception:
                pass

        stdin_buf = getattr(sys.stdin, "buffer", None)
        stdout_buf = getattr(sys.stdout, "buffer", None)
        if stdin_buf is None:
            try:
                import io
                stdin_buf = io.open(0, "rb", closefd=False)
            except Exception:
                pass
        if stdout_buf is None:
            try:
                import io
                stdout_buf = io.open(1, "wb", closefd=False)
            except Exception:
                pass

        if stdin_buf is None:
            sys.exit(0)

        raw_len = stdin_buf.read(4)
        if not raw_len or len(raw_len) < 4:
            sys.exit(0)
        msg_len = struct.unpack("=I", raw_len)[0]
        msg_bytes = stdin_buf.read(msg_len)
        data = json.loads(msg_bytes.decode("utf-8"))

        forwarded = False
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:9666/download",
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Zero-Client": "native"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    forwarded = True
        except Exception:
            forwarded = False

        if not forwarded:
            # Check if primary instance is already running via /status or Windows mutex
            is_running = False
            try:
                with urllib.request.urlopen("http://127.0.0.1:9666/status", timeout=1.5) as sresp:
                    if sresp.status == 200:
                        is_running = True
            except Exception:
                pass

            if not is_running:
                exe = get_current_executable()
                slim_data = dict(data) if isinstance(data, dict) else {}
                slim_data.pop("m3u8_content", None)
                slim_data.pop("m3u8Content", None)
                slim_data.pop("variants", None)
                if isinstance(slim_data.get("headers"), dict):
                    slim_hdrs = dict(slim_data["headers"])
                    slim_hdrs.pop("m3u8_content", None)
                    slim_data["headers"] = slim_hdrs
                b64_payload = base64.b64encode(json.dumps(slim_data).encode("utf-8")).decode("ascii")
                proto_arg = f"zero-dl://download?data={b64_payload}"

                flag = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)

                if getattr(sys, "frozen", False) or (exe.lower().endswith(".exe") and not exe.lower().endswith("pythonw.exe") and not exe.lower().endswith("python.exe")):
                    cmd = [exe, proto_arg]
                else:
                    pythonw = get_sac_safe_pythonw()
                    local_app_dir = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krolix Download Manager")
                    local_main = os.path.join(local_app_dir, "main.py")
                    main_py = local_main if os.path.exists(local_main) else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
                    cmd = [pythonw, main_py, proto_arg]

                subprocess.Popen(cmd, creationflags=flag)

        lic_payload = {"is_full": False, "is_master": False, "tier": "Trial"}
        try:
            from ..core.license_manager import LicenseManager
            lic_info = LicenseManager.get_instance().get_license_display_info()
            lic_payload = {
                "is_full": bool(lic_info.get("is_full")),
                "is_master": bool(lic_info.get("is_master")),
                "registered_name": lic_info.get("registered_name", ""),
                "tier": "Advance Master Mode" if lic_info.get("is_master") else ("Full Version" if lic_info.get("is_full") else "Trial Mode")
            }
        except Exception:
            pass

        resp_obj = {"status": "ok", "forwarded": forwarded, "license": lic_payload}
        resp_bytes = json.dumps(resp_obj).encode("utf-8")
        if stdout_buf:
            stdout_buf.write(struct.pack("=I", len(resp_bytes)))
        if stdout_buf:
            stdout_buf.write(resp_bytes)
        if stdout_buf:
            stdout_buf.flush()
    except Exception as e:
        try:
            err_bytes = json.dumps({"status": "error", "error": str(e)}).encode("utf-8")
            if stdout_buf:
                stdout_buf.write(struct.pack("=I", len(err_bytes)))
            if stdout_buf:
                stdout_buf.write(err_bytes)
            if stdout_buf:
                stdout_buf.flush()
        except Exception:
            pass
    sys.exit(0)