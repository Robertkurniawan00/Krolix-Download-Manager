import threading
import time
import urllib.parse
from typing import Callable

DOWNLOAD_EXTS = (
    ".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".dmg",
    ".exe", ".msi", ".apk", ".bin",
    ".mp4", ".mkv", ".avi", ".mov", ".mp3", ".wav", ".flac",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt",
    ".torrent", ".m3u8", ".mpd"
)

class ClipboardMonitor(threading.Thread):
    def __init__(self, on_url_detected: Callable[[str], None], enabled: bool = True, is_torrent_enabled: Callable[[], bool] = None):
        super().__init__(daemon=True)
        self.on_url_detected = on_url_detected
        self.enabled = enabled
        self.is_torrent_enabled = is_torrent_enabled or (lambda: False)
        self._running = True
        self._last_clip = ""

    def run(self):
        try:
            import pyperclip
            self._last_clip = (pyperclip.paste() or "").strip()
        except Exception:
            self._last_clip = ""

        while self._running:
            if self.enabled:
                try:
                    import pyperclip
                    clip_text = (pyperclip.paste() or "").strip()
                    # Guard against huge buffer strings (e.g. copied log files or database dumps)
                    if clip_text and len(clip_text) <= 4096 and clip_text != self._last_clip:
                        self._last_clip = clip_text
                        if self._is_downloadable_url(clip_text):
                            self.on_url_detected(clip_text)
                except Exception:
                    pass
            time.sleep(1.0)

    def _is_downloadable_url(self, text: str) -> bool:
        if "\n" in text or "\r" in text or " " in text:
            return False
        low = text.lower()
        if low.startswith("magnet:"):
            return self.is_torrent_enabled()
        if not low.startswith(("http://", "https://")):
            return False

        try:
            parsed = urllib.parse.urlparse(text)
        except ValueError:
            return False
        if not parsed.netloc:
            return False

        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in DOWNLOAD_EXTS):
            if path.endswith(".torrent") and not self.is_torrent_enabled():
                return False
            return True

        # Check explicit forced-download query parameters rather than generic substrings
        query_low = parsed.query.lower()
        if any(q in query_low for q in ("response-content-disposition=attachment", "download=1", "download=true", "force_download=1")):
            return True

        return False

    def stop(self):
        self._running = False
