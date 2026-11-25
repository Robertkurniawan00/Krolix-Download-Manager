"""
Zero Download Assistant - Live Stream Watchlist & Auto-Recorder Engine
Monitors favorite streamers/channels across Chaturbate, Stripchat, Twitch, YouTube,
Kick, and direct HLS feeds, automatically capturing streams when they go live.
"""

import os
import re
import time
import threading
import urllib.parse
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from .database import Database
from .downloader import DownloadEngine
from .media_grabber import MediaGrabber
from .models import DownloadStatus, DownloadTask
from ..utils.helpers import sanitize_filename


PLATFORM_RULES: List[Tuple[str, str, re.Pattern]] = [
    ("Chaturbate", "chaturbate", re.compile(r'(?:chaturbate\.(?:com|eu|global)/(?:b/)?|cb\.live/|chaturbate:)([a-zA-Z0-9_\-]+)', re.I)),
    ("Stripchat", "stripchat", re.compile(r'(?:stripchat\.(?:com|org|me)/(?:b/)?|stripchat:)([a-zA-Z0-9_\-]+)', re.I)),
    ("Twitch", "twitch", re.compile(r'twitch\.tv/([a-zA-Z0-9_\-]+)', re.I)),
    ("YouTube", "youtube", re.compile(r'(?:youtube\.com/(?:@|c/|channel/|user/)?|youtu\.be/)([a-zA-Z0-9_\-@]+)', re.I)),
    ("Kick", "kick", re.compile(r'kick\.com/([a-zA-Z0-9_\-]+)', re.I)),
]

QUALITY_HEIGHT_MAP = {
    "best": 99999,
    "4k": 2160,
    "2160p": 2160,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}

ACTIVE_TASK_STATES = (
    DownloadStatus.DOWNLOADING,
    DownloadStatus.CONNECTING,
    DownloadStatus.QUEUED,
)


def parse_stream_target(raw_input: str) -> Tuple[str, str, str]:
    """
    Normalize a URL or shorthand (e.g. 'chaturbate:name') into
    (normalized_url, platform_display, default_channel_name).
    """
    raw = (raw_input or "").strip()
    if not raw:
        return "", "Custom", "Stream"

    normalized = MediaGrabber.normalize_url(raw)
    lower_u = normalized.lower()

    for platform_label, _, pattern in PLATFORM_RULES:
        m = pattern.search(raw) or pattern.search(normalized)
        if m:
            channel = m.group(1).lstrip("@")
            return normalized, platform_label, channel or platform_label

    if ".m3u8" in lower_u:
        base = os.path.basename(urllib.parse.urlparse(normalized).path) or "hls_stream"
        name = os.path.splitext(base)[0] or "HLS Stream"
        return normalized, "HLS Feed", name

    parsed = urllib.parse.urlparse(normalized)
    host = (parsed.netloc or "").replace("www.", "")
    slug = (parsed.path or "").strip("/").split("/")[-1]
    name = slug or host or "Stream"
    return normalized, (host or "Web Stream"), name


def select_format_for_quality(formats: List[dict], quality_pref: str = "best") -> Optional[dict]:
    """
    Choose the optimal format dictionary matching quality_pref from pre-sorted
    (highest quality first) formats. Falls back to the highest available stream.
    """
    if not formats:
        return None

    pref = (quality_pref or "best").lower().strip()
    if pref == "best":
        return formats[0]

    max_h = QUALITY_HEIGHT_MAP.get(pref)
    if max_h is None:
        m = re.search(r'(\d{3,4})', pref)
        max_h = int(m.group(1)) if m else 99999

    video_formats = [f for f in formats if f.get("has_video", True)] or formats
    for fmt in video_formats:
        h = int(fmt.get("height") or 0)
        if 0 < h <= max_h:
            return fmt

    # If all detected variants exceed cap, pick the lowest resolution video variant
    return video_formats[-1]


class StreamWatchlistManager:
    """
    Background monitor that periodically probes enabled watchlist channels
    and launches live recording tasks via DownloadEngine when targets go live.
    """

    def __init__(
        self,
        engine: DownloadEngine,
        db: Database,
        on_item_updated: Optional[Callable[[Dict], None]] = None,
        on_recording_started: Optional[Callable[[Dict, DownloadTask], None]] = None,
        start_thread: bool = True,
    ):
        self.engine = engine
        self.db = db
        self.on_item_updated = on_item_updated
        self.on_recording_started = on_recording_started

        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._lock = threading.RLock()
        self._checking_ids: set = set()
        self._pending_launches: set = set()
        self._cooldown_until: Dict[str, float] = {}
        self._thread: Optional[threading.Thread] = None

        if start_thread:
            self.start()

    def is_enabled(self) -> bool:
        """Return whether global background watchlist monitoring is active."""
        return self.db.get_setting("watchlist_enabled", "true") == "true"

    def set_enabled(self, enabled: bool):
        """Enable or disable background watchlist monitoring globally."""
        self.db.set_setting("watchlist_enabled", "true" if enabled else "false")
        if enabled:
            self._wake_event.set()

    def get_default_interval(self) -> int:
        """Return default global polling interval in seconds (minimum 15s)."""
        try:
            return max(15, int(self.db.get_setting("watchlist_default_interval", "60")))
        except Exception:
            return 60

    def set_default_interval(self, seconds: int):
        """Persist default global polling interval in seconds."""
        self.db.set_setting("watchlist_default_interval", str(max(15, int(seconds))))
        self._wake_event.set()

    def get_max_concurrent_recordings(self) -> int:
        """Return maximum concurrent auto-recordings permitted."""
        try:
            return max(1, int(self.db.get_setting("watchlist_max_concurrent", "3")))
        except Exception:
            return 3

    def start(self):
        """Start the background monitor thread if not already running."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, name="ZeroWatchlistMonitor", daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the background monitor thread to exit cleanly."""
        self._stop_event.set()
        self._wake_event.set()

    def add_channel(
        self,
        url_or_handle: str,
        name: str = "",
        quality_pref: str = "best",
        save_dir: str = "",
        check_interval_sec: Optional[int] = None,
        auto_record: bool = True,
        enabled: bool = True,
    ) -> Dict:
        """Add or update a channel in the watchlist database."""
        norm_url, platform, detected_name = parse_stream_target(url_or_handle)
        if not norm_url:
            raise ValueError("URL atau username channel tidak valid.")

        clean_name = (name or "").strip() or detected_name
        interval = max(15, int(check_interval_sec or self.get_default_interval()))

        # Reuse existing item if same normalized URL is already in watchlist
        existing = next(
            (it for it in self.db.get_watchlist() if it["url"].rstrip("/").lower() == norm_url.rstrip("/").lower()),
            None,
        )
        item = {
            "id": existing["id"] if existing else "",
            "name": clean_name,
            "url": norm_url,
            "platform": platform,
            "enabled": enabled,
            "auto_record": auto_record,
            "quality_pref": quality_pref or "best",
            "save_dir": (save_dir or "").strip(),
            "check_interval_sec": interval,
            "status": existing["status"] if existing else "Queued",
            "last_checked": existing["last_checked"] if existing else 0.0,
            "last_recorded": existing["last_recorded"] if existing else 0.0,
            "active_task_id": existing["active_task_id"] if existing else "",
            "record_count": existing["record_count"] if existing else 0,
            "last_error": "",
            "created_at": existing["created_at"] if existing else time.time(),
        }
        item_id = self.db.save_watchlist_item(item)
        saved = self.db.get_watchlist_item(item_id) or item
        if self.on_item_updated:
            self.on_item_updated(saved)
        self._wake_event.set()
        return saved

    def remove_channel(self, item_id: str):
        """Remove a channel from the watchlist."""
        self.db.delete_watchlist_item(item_id)
        with self._lock:
            self._cooldown_until.pop(item_id, None)

    def _get_engine_task(self, task_id: str) -> Optional[DownloadTask]:
        if not task_id:
            return None
        eng_lock = getattr(self.engine, "lock", None)
        if eng_lock:
            with eng_lock:
                return self.engine.tasks.get(task_id)
        return self.engine.tasks.get(task_id)

    def _is_task_active(self, task_id: str) -> bool:
        """Check whether the given task ID is currently running or queued in DownloadEngine."""
        task = self._get_engine_task(task_id)
        return bool(task and task.status in ACTIVE_TASK_STATES)

    def _count_active_recordings(self, items: List[Dict]) -> int:
        return sum(1 for it in items if self._is_task_active(it.get("active_task_id", "")))

    def _sync_finished_tasks(self, items: List[Dict]):
        """Reconcile watchlist items whose previously active recording task has stopped."""
        now = time.time()
        for it in items:
            task_id = it.get("active_task_id", "")
            if not task_id:
                continue
            task = self._get_engine_task(task_id)
            if not task or task.status not in ACTIVE_TASK_STATES:
                new_status = "Offline"
                if task and task.status in (DownloadStatus.PAUSED, DownloadStatus.CANCELED):
                    # Respect manual user pause/cancel with a 5-minute cooldown before auto-restarting
                    with self._lock:
                        self._cooldown_until[it["id"]] = now + 300.0
                    new_status = "Paused (Cooldown)"
                elif task and task.status == DownloadStatus.COMPLETED:
                    # Brief cooldown after stream ends so offline transitions settle cleanly
                    with self._lock:
                        self._cooldown_until[it["id"]] = now + 45.0
                self.db.update_watchlist_state(it["id"], status=new_status, active_task_id="")
                updated = self.db.get_watchlist_item(it["id"])
                if updated and self.on_item_updated:
                    self.on_item_updated(updated)

    def _monitor_loop(self):
        """Main polling loop checking due watchlist entries."""
        while not self._stop_event.is_set():
            try:
                items = self.db.get_watchlist()
                self._sync_finished_tasks(items)

                if self.is_enabled():
                    now = time.time()
                    for it in items:
                        if self._stop_event.is_set():
                            break
                        if not it.get("enabled"):
                            continue
                        if self._is_task_active(it.get("active_task_id", "")):
                            if it.get("status") != "Recording":
                                self.db.update_watchlist_state(it["id"], status="Recording")
                            continue

                        with self._lock:
                            cd_until = self._cooldown_until.get(it["id"], 0.0)
                        if now < cd_until:
                            continue

                        interval = max(15, int(it.get("check_interval_sec") or self.get_default_interval()))
                        if now - float(it.get("last_checked") or 0) >= interval:
                            self.check_channel(it["id"], force_record=False)
            except Exception:
                pass

            self._wake_event.wait(timeout=5.0)
            self._wake_event.clear()

    def check_all_async(self, force_record: bool = False):
        """Trigger an immediate non-blocking check across all enabled channels."""
        def _run():
            for it in self.db.get_watchlist():
                if self._stop_event.is_set():
                    break
                if it.get("enabled") or force_record:
                    self.check_channel(it["id"], force_record=force_record)

        threading.Thread(target=_run, name="ZeroWatchlistCheckAll", daemon=True).start()

    def check_channel_async(self, item_id: str, force_record: bool = False):
        """Trigger an immediate background check for a single channel."""
        threading.Thread(
            target=self.check_channel,
            args=(item_id, force_record),
            name=f"ZeroWatchlistCheck_{item_id}",
            daemon=True,
        ).start()

    def stop_channel_recording(self, item_id: str):
        """Stop an active auto-recording for the given watchlist item and apply cooldown."""
        item = self.db.get_watchlist_item(item_id)
        if not item:
            return
        task_id = item.get("active_task_id", "")
        if task_id and self._get_engine_task(task_id):
            self.engine.pause_download(task_id)
        with self._lock:
            self._cooldown_until[item_id] = time.time() + 300.0
        self.db.update_watchlist_state(item_id, status="Paused (Cooldown)", active_task_id="")
        updated = self.db.get_watchlist_item(item_id)
        if updated and self.on_item_updated:
            self.on_item_updated(updated)

    def probe_channel(self, url: str, quality_pref: str = "best") -> Dict:
        """
        Probe target URL using MediaGrabber to detect live status and pick best stream format.
        Returns a status dictionary without mutating database state.
        """
        norm_url, platform, _ = parse_stream_target(url)
        info, err = MediaGrabber.get_media_info(norm_url)

        if not info or not info.get("formats"):
            err_low = (err or "").lower()
            if "private" in err_low or "paid" in err_low or "berbayar" in err_low:
                return {"is_live": False, "status": "Private Show", "error": err or ""}
            if "away" in err_low:
                return {"is_live": False, "status": "Away", "error": err or ""}
            return {"is_live": False, "status": "Offline", "error": err or ""}

        is_live = bool(
            info.get("is_live")
            or platform.lower() in ("chaturbate", "stripchat")
            or ".m3u8" in norm_url.lower()
        )
        if not is_live:
            return {"is_live": False, "status": "Offline (VOD Only)", "error": ""}

        chosen = select_format_for_quality(info["formats"], quality_pref)
        if not chosen or not chosen.get("url"):
            return {"is_live": False, "status": "Offline", "error": "No playable stream URL found"}

        return {
            "is_live": True,
            "status": "Live",
            "info": info,
            "selected_format": chosen,
            "error": "",
        }

    def check_channel(self, item_id: str, force_record: bool = False) -> Optional[Dict]:
        """
        Check a single watchlist channel, update its status, and start recording if live
        and permitted by auto_record / force_record & concurrency limits.
        """
        with self._lock:
            if item_id in self._checking_ids:
                return self.db.get_watchlist_item(item_id)
            self._checking_ids.add(item_id)

        try:
            item = self.db.get_watchlist_item(item_id)
            if not item:
                return None

            if force_record:
                with self._lock:
                    self._cooldown_until.pop(item_id, None)

            # Avoid duplicate recording if task is already active
            if self._is_task_active(item.get("active_task_id", "")):
                self.db.update_watchlist_state(item_id, status="Recording", last_checked=time.time())
                updated = self.db.get_watchlist_item(item_id)
                if updated and self.on_item_updated:
                    self.on_item_updated(updated)
                return updated

            probe = self.probe_channel(item["url"], item.get("quality_pref", "best"))
            now = time.time()

            if not probe.get("is_live"):
                self.db.update_watchlist_state(
                    item_id,
                    status=probe.get("status", "Offline"),
                    active_task_id="",
                    last_checked=now,
                    last_error=probe.get("error", ""),
                )
                updated = self.db.get_watchlist_item(item_id)
                if updated and self.on_item_updated:
                    self.on_item_updated(updated)
                return updated

            # Channel is LIVE! Check whether we should record now (reserve slot atomically)
            should_record = bool(item.get("auto_record") or force_record)
            reserved_slot = False
            if should_record:
                with self._lock:
                    if not force_record:
                        all_items = self.db.get_watchlist()
                        active_count = self._count_active_recordings(all_items) + len(self._pending_launches)
                        if active_count >= self.get_max_concurrent_recordings():
                            should_record = False
                    if should_record:
                        self._pending_launches.add(item_id)
                        reserved_slot = True

            if not should_record:
                self.db.update_watchlist_state(
                    item_id,
                    status="Live (Standby)",
                    last_checked=now,
                    last_error="",
                )
                updated = self.db.get_watchlist_item(item_id)
                if updated and self.on_item_updated:
                    self.on_item_updated(updated)
                return updated

            try:
                task = self._launch_recording_task(item, probe)
            finally:
                if reserved_slot:
                    with self._lock:
                        self._pending_launches.discard(item_id)
            if task:
                self.db.update_watchlist_state(
                    item_id,
                    status="Recording",
                    active_task_id=task.id,
                    last_checked=now,
                    last_recorded=now,
                    increment_count=True,
                    last_error="",
                )
                updated = self.db.get_watchlist_item(item_id)
                if updated and self.on_item_updated:
                    self.on_item_updated(updated)
                if updated and self.on_recording_started:
                    self.on_recording_started(updated, task)
                return updated

            self.db.update_watchlist_state(
                item_id,
                status="Live (Start Failed)",
                last_checked=now,
                last_error="Failed to launch recording task",
            )
            updated = self.db.get_watchlist_item(item_id)
            if updated and self.on_item_updated:
                self.on_item_updated(updated)
            return updated
        finally:
            with self._lock:
                self._checking_ids.discard(item_id)

    def _launch_recording_task(self, item: Dict, probe: Dict) -> Optional[DownloadTask]:
        """Create and start a live stream DownloadTask for the probed channel."""
        chosen = probe["selected_format"]
        info = probe["info"]
        stream_url = chosen.get("url", "")
        if not stream_url:
            return None

        default_base = self.db.get_setting(
            "default_save_path",
            os.path.join(os.path.expanduser("~"), "Downloads"),
        )
        safe_channel = sanitize_filename(item.get("name") or "LiveStream")
        save_dir = (item.get("save_dir") or "").strip()
        if not save_dir:
            save_dir = os.path.join(default_base, "LiveCaptures", safe_channel)
        os.makedirs(save_dir, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        res_label = chosen.get("format_id") or (f"{chosen['height']}p" if chosen.get("height") else "live")
        ext = chosen.get("ext") or "mp4"
        filename = sanitize_filename(f"{safe_channel}_{stamp}_{res_label}.{ext}")

        page_url = info.get("webpage_url") or item["url"]
        parsed_page = urllib.parse.urlparse(page_url)
        origin = f"{parsed_page.scheme}://{parsed_page.netloc}" if parsed_page.scheme and parsed_page.netloc else ""

        task_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": page_url,
            "is_live": "true",
            "is_hls": "true",
            "resolution": str(res_label),
            "watchlist_item_id": item["id"],
        }
        if origin:
            task_headers["Origin"] = origin
        if chosen.get("master_url") or info.get("m3u8_url"):
            task_headers["master_url"] = chosen.get("master_url") or info.get("m3u8_url")
        if chosen.get("audio_url"):
            task_headers["audio_url"] = chosen["audio_url"]

        # If non-HLS generic live stream (e.g., Twitch/YouTube without direct .m3u8), mark yt-dlp fallback
        if ".m3u8" not in stream_url.lower() and not task_headers.get("master_url"):
            task_headers["is_ytdlp"] = "true"
            task_headers.pop("is_hls", None)

        task = self.engine.create_task(
            url=stream_url,
            save_dir=save_dir,
            filename=filename,
            headers=task_headers,
            category="Video",
        )
        task.description = f"Auto-Recorded from Live Watchlist ({item.get('platform', 'Live')})"
        self.db.save_task(task)
        self.engine.start_download(task.id)
        return task
