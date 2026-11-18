"""
Zero Download Assistant - Helper Utilities
"""

import os
import re
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Set


def format_bytes(num_bytes: Optional[int]) -> str:
    if num_bytes is None or num_bytes < 0:
        return "0.0 B"
    if num_bytes == 0:
        return "0.0 B"
    val = float(num_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(val) < 1024.0:
            if unit == 'B':
                return f"{val:.1f} B"
            return f"{val:.2f} {unit}"
        val /= 1024.0
    return f"{val:.2f} PB"


def format_speed(bytes_per_sec: Optional[float]) -> str:
    if bytes_per_sec is None or bytes_per_sec <= 0:
        return "0.0 KB/s"
    val = float(bytes_per_sec)
    if val < 1024.0 * 1024.0:
        return f"{val / 1024.0:.1f} KB/s"
    else:
        mb = val / (1024.0 * 1024.0)
        return f"{mb:.1f} MB/s"


def format_time(seconds: Optional[float]) -> str:
    if seconds is None or seconds <= 0 or seconds > 86400 * 30 or seconds == float("inf"):
        return "--:--"
    secs = int(seconds)
    hours = secs // 3600
    mins = (secs % 3600) // 60
    rem_secs = secs % 60
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{rem_secs:02d}"
    return f"{mins:02d}:{rem_secs:02d}"


def format_eta(seconds: Optional[float]) -> str:
    return format_time(seconds)


def _ensure_valid_certifi():
    """
    Ensures 'certifi' module has a valid callable .where() attribute.
    Protects against broken PEP 420 namespace packages (e.g. empty _internal/certifi dir).
    """
    try:
        import certifi as _certifi
        if not hasattr(_certifi, "where") or not callable(getattr(_certifi, "where", None)):
            import ssl
            _default_ca = ssl.get_default_verify_paths().cafile or ""
            _certifi.where = lambda: _default_ca
    except Exception:
        import sys
        sys.modules.pop("certifi", None)


def sanitize_filename(filename: str, max_stem_len: int = 100) -> str:
    if not filename:
        return "download"
    raw = filename.split("?")[0].split("#")[0].strip()

    # Separate stem and extension first to ensure extension is always preserved
    base, ext = os.path.splitext(raw)
    if not (1 <= len(ext) <= 12 and ext.startswith(".")):
        base = raw
        ext = ""

    cleaned_base = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', base)
    cleaned_base = re.sub(r'[\\/*?:"<>|]', '_', cleaned_base)
    cleaned_base = re.sub(r'\.{2,}', '_', cleaned_base)
    cleaned_base = cleaned_base.strip(" ._")

    cleaned_ext = re.sub(r'[\\/*?:"<>|]', '', ext).strip()

    # Prevent Windows MAX_PATH (>260 chars) failure by limiting file stem
    if len(cleaned_base) > max_stem_len:
        cleaned_base = cleaned_base[:max_stem_len].rstrip(" ._")

    cleaned = f"{cleaned_base}{cleaned_ext}" if cleaned_base else f"download{cleaned_ext}"

    reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    }
    stem_check = cleaned_base.split(".")[0].upper()
    if stem_check in reserved_names:
        cleaned = f"_{cleaned}"

    return cleaned


CATEGORY_EXTENSIONS: Dict[str, Set[str]] = {
    'compressed': {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.iso', '.tgz'},
    'documents': {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv', '.epub', '.rtf', '.odt'},
    'music': {'.mp3', '.flac', '.wav', '.aac', '.m4a', '.ogg', '.wma', '.opus', '.alac'},
    'programs': {'.exe', '.msi', '.bat', '.cmd', '.apk', '.dmg', '.iso', '.sh', '.appx', '.msix', '.deb', '.rpm'},
    'video': {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.ts', '.m3u8', '.m4v', '.3gp'}
}


def get_category_from_ext(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    for cat, exts in CATEGORY_EXTENSIONS.items():
        if ext in exts:
            return cat.capitalize()
    return 'Documents'


def get_category_from_filename(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    for cat, extensions in CATEGORY_EXTENSIONS.items():
        if ext in extensions:
            return cat.capitalize()
    return "General"


def get_default_download_dir(category: Optional[str] = None) -> str:
    base = os.path.join(os.path.expanduser('~'), 'Downloads')
    if category and category.lower() in CATEGORY_EXTENSIONS:
        cat_folder = os.path.join(base, category.capitalize())
        os.makedirs(cat_folder, exist_ok=True)
        return cat_folder
    os.makedirs(base, exist_ok=True)
    return base


def extract_filename_from_headers(headers, url: str) -> str:
    cd = ""
    if headers and hasattr(headers, "get"):
        cd = headers.get("content-disposition") or headers.get("Content-Disposition") or ""
        if not cd and isinstance(headers, dict):
            for k, v in headers.items():
                if k.lower() == "content-disposition":
                    cd = v
                    break
    if cd:
        match_utf8 = re.search(r"filename\*\s*=\s*UTF-8''([^;\r\n]+)", cd, re.IGNORECASE)
        if match_utf8:
            return sanitize_filename(urllib.parse.unquote(match_utf8.group(1).strip('"\'')))

        match_std = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.IGNORECASE)
        if not match_std:
            match_std = re.search(r'filename\s*=\s*([^;\r\n]+)', cd, re.IGNORECASE)
        if match_std:
            return sanitize_filename(match_std.group(1).strip('"\''))

    if url:
        parsed = urllib.parse.urlparse(url)
        path = urllib.parse.unquote(parsed.path)
        base = os.path.basename(path)
        if base:
            return sanitize_filename(base)
    return "download"


def apply_windows_dark_titlebar(widget):
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
        )
        if res != 0:
            DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:
        pass


def get_app_icon():
    from PyQt6.QtGui import QIcon
    import sys
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ico_candidates = [
        os.path.join(base_dir, "assets", "logo.ico"),
        os.path.join(base_dir, "assets", "app_icon.ico"),
    ]
    if hasattr(sys, "_MEIPASS"):
        ico_candidates.insert(0, os.path.join(sys._MEIPASS, "app", "assets", "logo.ico"))
        ico_candidates.insert(1, os.path.join(sys._MEIPASS, "app", "assets", "app_icon.ico"))
        ico_candidates.insert(2, os.path.join(sys._MEIPASS, "assets", "logo.ico"))

    icon = QIcon()
    for ico_p in ico_candidates:
        if os.path.exists(ico_p):
            icon = QIcon(ico_p)
            break

    # Add individual PNG sizes into the icon collection for razor-sharp DPI scaling
    for sz in (16, 24, 32, 48, 64, 128, 256):
        png_p = os.path.join(base_dir, "assets", f"logo_{sz}.png")
        if os.path.exists(png_p):
            icon.addFile(png_p)
        elif hasattr(sys, "_MEIPASS"):
            m_png = os.path.join(sys._MEIPASS, "app", "assets", f"logo_{sz}.png")
            if os.path.exists(m_png):
                icon.addFile(m_png)

    if not icon.isNull():
        return icon
    return QIcon()


def apply_taskbar_icon(widget):
    """
    Explicitly binds multi-resolution logo.ico to the native Windows HWND via WM_SETICON.
    Ensures Windows Taskbar, Alt+Tab, and Titlebar display the authentic Zero logo
    instead of the generic Windows executable / pythonw document icon.
    """
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = int(widget.winId())

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ico_path = os.path.join(base_dir, "assets", "logo.ico")
        if not os.path.exists(ico_path):
            ico_path = os.path.join(base_dir, "assets", "app_icon.ico")
        if hasattr(sys, "_MEIPASS"):
            m_ico = os.path.join(sys._MEIPASS, "app", "assets", "logo.ico")
            if os.path.exists(m_ico):
                ico_path = m_ico

        if os.path.exists(ico_path):
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010
            WM_SETICON = 0x0080
            ICON_SMALL = 0
            ICON_BIG = 1

            h_icon_sm = user32.LoadImageW(None, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
            h_icon_lg = user32.LoadImageW(None, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
            if h_icon_sm:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_icon_sm)
            if h_icon_lg:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_icon_lg)
    except Exception:
        pass




def detect_file_extension_from_magic(file_path: str) -> Optional[str]:
    """
    Sniffs magic bytes from the header of file_path and returns the appropriate file extension
    (e.g., '.rar', '.zip', '.7z', '.mp4', '.pdf', '.exe', etc.) or None if unrecognized.
    """
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return None
    try:
        with open(file_path, "rb") as f:
            header = f.read(512)
            if not header:
                return None

            # RAR archive
            # RAR 5.0: 52 61 72 21 1a 07 01 00
            # RAR 4.x: 52 61 72 21 1a 07 00
            if header.startswith(b"Rar!\x1a\x07\x01\x00") or header.startswith(b"Rar!\x1a\x07\x00"):
                return ".rar"

            # 7-Zip archive
            # 37 7a bc af 27 1c
            if header.startswith(b"7z\xbc\xaf\x27\x1c"):
                return ".7z"

            # ZIP archive (PK\x03\x04 or empty PK\x05\x06)
            if header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06") or header.startswith(b"PK\x07\x08"):
                return ".zip"

            # GZIP
            if header.startswith(b"\x1f\x8b"):
                return ".gz"

            # BZIP2
            if header.startswith(b"BZh"):
                return ".bz2"

            # XZ
            if header.startswith(b"\xfd7zXZ\x00"):
                return ".xz"

            # PDF document
            if header.startswith(b"%PDF-"):
                return ".pdf"

            # Windows Executable / DLL (PE)
            if header.startswith(b"MZ"):
                return ".exe"

            # PNG image
            if header.startswith(b"\x89PNG\r\n\x1a\n"):
                return ".png"

            # JPEG image
            if header.startswith(b"\xff\xd8\xff"):
                return ".jpg"

            # GIF image
            if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
                return ".gif"

            # WebP / RIFF containers
            if header.startswith(b"RIFF") and len(header) >= 12:
                riff_type = header[8:12]
                if riff_type == b"WEBP":
                    return ".webp"
                if riff_type == b"WAVE":
                    return ".wav"
                if riff_type == b"AVI ":
                    return ".avi"

            # MP4 / MOV / M4V container: offset 4 contains 'ftyp'
            if len(header) >= 8 and header[4:8] == b"ftyp":
                return ".mp4"

            # Matroska / WebM
            if header.startswith(b"\x1aE\xdf\xa3"):
                return ".mkv"

            # FLAC audio
            if header.startswith(b"fLaC"):
                return ".flac"

            # MP3 audio (ID3 tag or sync word)
            if header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xff and (header[1] & 0xe0) == 0xe0):
                return ".mp3"

            # Ogg container
            if header.startswith(b"OggS"):
                return ".ogg"

            # ISO 9660 CD/DVD image (check offset 0x8000 / 32768)
            if os.path.getsize(file_path) > 32774:
                f.seek(32768)
                iso_magic = f.read(6)
                if iso_magic in (b"\x01CD001", b"\x02CD001"):
                    return ".iso"

            # TAR archive (check offset 257 for 'ustar')
            if len(header) >= 262 and header[257:262] == b"ustar":
                return ".tar"
    except Exception:
        pass
    return None
