"""
Zero Download Assistant - Dynamic BitTorrent Public Tracker Manager
Automatically fetches, validates, and caches the freshest high-speed public trackers
from curated community repositories (ngosang/trackerslist, XIU2/TrackersListCollection).
Significantly boosts torrent download speeds, peer discovery, and seeder connections.
"""

import os
import json
import time
import ssl
import threading
import urllib.request
from typing import List, Optional, Callable


DEFAULT_TIER1_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "udp://explodie.org:6969/announce",
    "udp://tracker.tiny-vps.com:6969/announce",
    "udp://p4p.arenabg.com:1337/announce",
    "udp://retracker.lanta-net.ru:2710/announce",
    "http://tracker.dler.org:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://tracker.dump.cl:6969/announce",
    "udp://tracker.bittor.pw:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.pomf.se:80/announce",
    "udp://newton.its-a-tree.org:6969/announce",
]

UPSTREAM_TRACKER_SOURCES = [
    "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt",
    "https://cdn.jsdelivr.net/gh/ngosang/trackerslist@master/trackers_best.txt",
    "https://raw.githubusercontent.com/XIU2/TrackersListCollection/master/best.txt",
]

CACHE_EXPIRY_SECONDS = 86400  # 24 Hours


class TrackerManager:
    _instance: Optional["TrackerManager"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "TrackerManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = TrackerManager()
            return cls._instance

    def __init__(self):
        self._cache_dir = os.path.join(os.path.expanduser("~"), ".zero_download")
        os.makedirs(self._cache_dir, exist_ok=True)
        self._cache_file = os.path.join(self._cache_dir, "trackers_cache.json")
        self._trackers: List[str] = list(DEFAULT_TIER1_TRACKERS)
        self._last_updated: float = 0.0
        self._is_updating = False

        self._load_cache()
        # Auto refresh if cache is expired
        if time.time() - self._last_updated > CACHE_EXPIRY_SECONDS:
            self.update_trackers_async()

    def _load_cache(self):
        try:
            if os.path.exists(self._cache_file):
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cached_trackers = data.get("trackers", [])
                    cached_time = float(data.get("last_updated", 0.0))
                    if cached_trackers and len(cached_trackers) >= 5:
                        self._trackers = cached_trackers
                        self._last_updated = cached_time
        except Exception as e:
            print(f"[TrackerManager] Warning loading cache: {e}")

    def _save_cache(self):
        try:
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump({
                    "last_updated": self._last_updated,
                    "trackers": self._trackers
                }, f, indent=2)
        except Exception as e:
            print(f"[TrackerManager] Warning saving cache: {e}")

    def get_trackers(self) -> List[str]:
        """Returns the list of high-tier validated tracker announce URLs."""
        if not self._trackers:
            return list(DEFAULT_TIER1_TRACKERS)
        return list(self._trackers)

    def get_trackers_string(self) -> str:
        """Returns comma-separated tracker URLs suitable for aria2c --bt-tracker argument."""
        return ",".join(self.get_trackers())

    def get_status_info(self) -> dict:
        """Returns metadata about the cached tracker list."""
        return {
            "count": len(self._trackers),
            "last_updated": self._last_updated,
            "is_updating": self._is_updating,
            "sample": self._trackers[:3] if self._trackers else []
        }

    def update_trackers_async(self, force: bool = False, on_completed: Optional[Callable[[bool, int, str], None]] = None):
        """Asynchronously updates public tracker list in a background thread."""
        if self._is_updating:
            return

        def _worker():
            self._is_updating = True
            success = False
            new_trackers = set(DEFAULT_TIER1_TRACKERS)
            msg = ""

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            headers = {
                "User-Agent": "ZeroDownloadAssistant/2.8 TrackerUpdater (+https://github.com/)"
            }

            for url in UPSTREAM_TRACKER_SOURCES:
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                        if resp.status == 200:
                            content = resp.read().decode("utf-8", errors="ignore")
                            found_count = 0
                            for line in content.splitlines():
                                line = line.strip()
                                if line and (line.startswith("udp://") or line.startswith("http://") or line.startswith("https://") or line.startswith("wss://")):
                                    new_trackers.add(line)
                                    found_count += 1
                            if found_count > 0:
                                success = True
                                break
                except Exception as e:
                    msg = str(e)
                    continue

            if success and new_trackers:
                # Deduplicate while keeping high-tier first
                ordered = []
                for t in DEFAULT_TIER1_TRACKERS:
                    if t in new_trackers and t not in ordered:
                        ordered.append(t)
                for t in sorted(new_trackers):
                    if t not in ordered:
                        ordered.append(t)

                self._trackers = ordered
                self._last_updated = time.time()
                self._save_cache()
                msg = f"Berhasil memperbarui {len(self._trackers)} tracker publik."
            else:
                msg = f"Gagal memperbarui dari remote. Menggunakan {len(self._trackers)} tracker bawaan."

            self._is_updating = False
            if on_completed:
                try:
                    on_completed(success, len(self._trackers), msg)
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True, name="ZeroTrackerUpdater").start()
