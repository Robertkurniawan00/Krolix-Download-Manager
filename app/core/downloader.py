"""
Zero Download Assistant - Core Download Engine & Multi-threaded Controller
"""

import os
import shutil
import time
import uuid
import threading
import urllib.request
import urllib.parse
import ssl
from typing import Dict, Optional, Callable, List, Any
from PyQt6.QtCore import QObject, pyqtSignal
from .models import DownloadTask, DownloadStatus, SegmentModel
from .segment import SegmentWorker
from .speed_limiter import SpeedLimiter
from .database import Database
from ..utils.helpers import extract_filename_from_headers, get_category_from_filename, sanitize_filename, detect_file_extension_from_magic
from urllib.parse import urlparse
import base64
from .hasher import FileHasher
from .archive_extractor import ArchiveExtractor
from .post_actions import PostActionManager, AntivirusScanner
from .hls_downloader import HLSWorker
from .audio_feedback import SoundManager
from .torrent_downloader import TorrentWorker
from .link_resolver import CloudLinkResolver
from .duplicate_detector import DuplicateDetector
from ..utils.win32_native import Win32Native



class DownloadEngine:
    active_refresh_dialog: Any = None
    active_refresh_task_id: Optional[str] = None

    def __init__(self, db: Database, speed_limiter: Optional[SpeedLimiter] = None):
        self.db = db
        self.speed_limiter = speed_limiter or SpeedLimiter()
        self.sound_manager = SoundManager(self.db)
        self.active_refresh_dialog: Any = None
        self.active_refresh_task_id: Optional[str] = None
        self.tasks: Dict[str, DownloadTask] = {}
        self.workers: Dict[str, List[SegmentWorker]] = {}
        self.hls_workers: Dict[str, HLSWorker] = {}
        self.torrent_workers: Dict[str, TorrentWorker] = {}
        self.ytdlp_workers: Dict[str, Any] = {}
        self.pause_events: Dict[str, threading.Event] = {}
        self.cancel_events: Dict[str, threading.Event] = {}
        self.lock = threading.Lock()

        # Listeners / Callbacks
        self.on_task_updated: Optional[Callable[[DownloadTask], None]] = None
        self.on_task_completed: Optional[Callable[[DownloadTask], None]] = None
        self.on_task_failed: Optional[Callable[[DownloadTask, str], None]] = None

        # Speed monitor
        self._speed_tracker: Dict[str, List[int]] = {}
        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._speed_monitor_loop, daemon=True)
        self._monitor_thread.start()

        # Load existing tasks from DB
        self._load_from_db()

    def _save_task_if_needed(self, task: DownloadTask):
        """Save task to DB only if zero_log mode is not active for this task."""
        if not getattr(task, "zero_log", False):
            self.db.save_task(task)


    def _load_from_db(self):
        saved = self.db.get_all_tasks()
        for t in saved:
            if t.status in [DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING]:
                t.status = DownloadStatus.PAUSED
            is_torrent = getattr(t, "is_torrent", False) or t.url.startswith("magnet:") or t.url.lower().endswith(".torrent")
            is_hls = (
                ".m3u8" in t.url.lower() or
                ".mpd" in t.url.lower() or
                ".urlset/" in t.url.lower() or
                (t.headers and t.headers.get("is_hls") in ["true", True, 1, "1"])
            )
            is_ytdlp = bool(t.headers and (t.headers.get("is_ytdlp") in ["true", True, 1, "1"]))
            if not is_torrent and not is_hls and not is_ytdlp and not t.segments:
                end_b = (t.total_bytes - 1) if (t.total_bytes and t.total_bytes > 0) else -1
                t.segments = [SegmentModel(index=0, start_byte=0, end_byte=end_b, downloaded_bytes=t.downloaded_bytes or 0, status="Idle")]
                t.connections = 1
                self.db.save_task(t)
            self.tasks[t.id] = t

    def _apply_credentials_and_proxy(self, url: str, headers: dict, proxy: Optional[str]) -> tuple:
        parsed = urlparse(url)
        domain = parsed.netloc.split(":")[0].lower()
        new_headers = dict(headers)
        
        # Check DB for site credentials if Authorization not explicitly provided
        if "Authorization" not in new_headers and "authorization" not in new_headers:
            cred = self.db.get_credential(domain)
            if cred:
                username, password = cred
                b64_auth = base64.b64encode(f"{username}:{password}".encode()).decode()
                new_headers["Authorization"] = f"Basic {b64_auth}"

        # Global proxy fallback if not provided per-task
        final_proxy = proxy
        if not final_proxy:
            global_proxy = self.db.get_setting("proxy_url", "")
            if global_proxy:
                final_proxy = global_proxy

        return new_headers, final_proxy

    def probe_url(self, url: str, headers: Optional[dict] = None, proxy: Optional[str] = None) -> dict:
        url = CloudLinkResolver.resolve(url)
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Range": "bytes=0-0"
        }
        if headers:
            req_headers.update(headers)

        req_headers, final_proxy = self._apply_credentials_and_proxy(url, req_headers, proxy)
        req_headers = CloudLinkResolver.fix_headers(url, req_headers)

        # Check if URL is a PikPak public share link
        try:
            from .pikpak_resolver import PikPakResolver
            if PikPakResolver.is_pikpak_url(url):
                pikpak_items = PikPakResolver.resolve_public_share(url)
                if pikpak_items:
                    first = pikpak_items[0]
                    is_multi = len(pikpak_items) > 1
                    total_s = sum(it.get("size", 0) for it in pikpak_items) if is_multi else first.get("size", -1)
                    return {
                        "success": True,
                        "filename": sanitize_filename(first.get("name") if not is_multi else f"{first.get('name', 'PikPak')}_bundle"),
                        "total_bytes": total_s,
                        "resumable": True,
                        "category": get_category_from_filename(first.get("name")),
                        "direct_url": first.get("url"),
                        "headers": first.get("headers"),
                        "pikpak_files": pikpak_items,
                        "is_pikpak": True
                    }
        except Exception as e_pik:
            return {
                "success": False,
                "error": f"PikPak Share Error: {e_pik}"
            }

        # Check if URL is a BitTorrent Magnet link or .torrent file
        is_torrent = url.startswith("magnet:") or url.lower().endswith(".torrent") or (os.path.isfile(url) and url.lower().endswith(".torrent"))
        if is_torrent:
            from .torrent_downloader import TorrentWorker
            t_info = TorrentWorker.get_torrent_info(url)
            fn = t_info.get("name") or "torrent_download"
            total_bytes = t_info.get("total_bytes", -1)
            return {
                "success": True,
                "filename": sanitize_filename(fn),
                "total_bytes": total_bytes,
                "resumable": True,
                "category": "Torrents",
                "torrent_files": t_info.get("files", [])
            }

        # Check if URL is an HLS (.m3u8 / .urlset / disguised .txt) or DASH (.mpd) stream
        is_hls = (
            ".m3u8" in url.lower() or 
            ".mpd" in url.lower() or
            ".urlset/" in url.lower() or
            (headers and (headers.get("is_hls") in ["true", True, 1, "1"] or "mpegurl" in str(headers.get("content-type", "")).lower()))
        )
        if is_hls:
            if ".mpd" not in url.lower():
                try:
                    from .hls_downloader import HLSInspector
                    hls_info = HLSInspector.probe(url, headers=req_headers, proxy=final_proxy)
                    if hls_info.get("success"):
                        return hls_info
                except Exception:
                    pass

            fn = extract_filename_from_headers({}, url) or "stream.mp4"
            if not fn.lower().endswith(".mp4"):
                base_f, _ = os.path.splitext(fn)
                fn = f"{base_f}.mp4"
            return {
                "success": True,
                "filename": sanitize_filename(fn),
                "total_bytes": -1,
                "resumable": True,
                "category": "Video",
                "is_hls": True
            }

        handlers = []
        if final_proxy:
            handlers.append(urllib.request.ProxyHandler({'http': final_proxy, 'https': final_proxy}))
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        except Exception:
            pass
        opener = urllib.request.build_opener(*handlers)

        req_probe = dict(req_headers)
        req_probe["Range"] = "bytes=0-0"
        req = urllib.request.Request(url, headers=req_probe)
        try:
            with opener.open(req, timeout=15) as res:
                filename = extract_filename_from_headers(res.headers, url)
                resumable = False
                total_bytes = -1

                status_code = getattr(res, "status", getattr(res, "code", 200))
                if status_code == 206:
                    resumable = True

                cr = res.headers.get("Content-Range")
                if cr and "/" in cr:
                    total_str = cr.split("/")[-1].strip()
                    if total_str.isdigit():
                        total_bytes = int(total_str)
                        resumable = True

                if total_bytes <= 0:
                    cl = res.headers.get("Content-Length")
                    if cl and cl.isdigit():
                        val = int(cl)
                        # Guard: on 206 Partial Content for Range: bytes=0-0, Content-Length is 1 byte (the chunk size), NOT total size
                        if not (status_code == 206 and val <= 1):
                            total_bytes = val

                # If Range probe returned 206 without Content-Range total size, query HEAD without Range
                if total_bytes <= 0:
                    try:
                        req_head = dict(req_headers)
                        req_head.pop("Range", None)
                        head_req = urllib.request.Request(url, headers=req_head, method="HEAD")
                        with opener.open(head_req, timeout=8) as head_res:
                            head_cl = head_res.headers.get("Content-Length")
                            if head_cl and head_cl.isdigit() and int(head_cl) > 0:
                                total_bytes = int(head_cl)
                    except Exception:
                        pass

                if "bytes" in (res.headers.get("Accept-Ranges") or "").lower():
                    resumable = True

                ct = (res.headers.get("Content-Type") or "").lower()
                if "mpegurl" in ct or "m3u8" in ct:
                    if not filename.lower().endswith(".mp4"):
                        base_f, _ = os.path.splitext(filename)
                        filename = f"{base_f or 'stream'}.mp4"
                    return {
                        "success": True,
                        "filename": sanitize_filename(filename),
                        "total_bytes": -1,
                        "resumable": True,
                        "category": "Videos",
                        "is_hls": True
                    }

                category = get_category_from_filename(filename)
                return {
                    "success": True,
                    "filename": filename,
                    "total_bytes": total_bytes,
                    "resumable": resumable,
                    "category": category
                }
        except Exception as e:
            # Auto-recovery for 401/403/410 expired CDN stream tokens
            if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 410):
                try:
                    fresh_url, fresh_hdrs = CloudLinkResolver.resolve_stream_url(url, req_headers)
                    if fresh_url != url or fresh_hdrs != req_headers:
                        return self.probe_url(fresh_url, headers=fresh_hdrs, proxy=proxy)
                except Exception:
                    pass

            # Fallback probe without Range header in case server rejects bytes=0-0 (e.g. 400 or 416)
            try:
                req_fallback = dict(req_headers)
                req_fallback.pop("Range", None)
                req_no_range = urllib.request.Request(url, headers=req_fallback)
                with opener.open(req_no_range, timeout=15) as res:
                    filename = extract_filename_from_headers(res.headers, url)
                    total_bytes = -1
                    cl = res.headers.get("Content-Length")
                    if cl and cl.isdigit():
                        total_bytes = int(cl)
                    ct = (res.headers.get("Content-Type") or "").lower()
                    if "mpegurl" in ct or "m3u8" in ct or "dash+xml" in ct:
                        if not filename.lower().endswith(".mp4"):
                            base_f, _ = os.path.splitext(filename)
                            filename = f"{base_f or 'stream'}.mp4"
                        return {
                            "success": True,
                            "filename": sanitize_filename(filename),
                            "total_bytes": -1,
                            "resumable": True,
                            "category": "Videos",
                            "is_hls": True
                        }

                    resumable = "bytes" in (res.headers.get("Accept-Ranges") or "").lower()
                    category = get_category_from_filename(filename)
                    return {
                        "success": True,
                        "filename": filename,
                        "total_bytes": total_bytes,
                        "resumable": resumable,
                        "category": category
                    }
            except Exception:
                pass

            fallback_filename = extract_filename_from_headers({}, url)
            return {
                "success": False,
                "error": str(e),
                "filename": fallback_filename,
                "total_bytes": -1,
                "resumable": False,
                "category": get_category_from_filename(fallback_filename)
            }


    def _auto_detect_and_fix_extension(self, task: DownloadTask):
        """
        If task.save_path has no extension (e.g. downloaded from an API slug like /file/SaHbWTcR),
        inspects file magic bytes. If a known signature is found, renames the file to include
        the correct extension, and updates the task and database records.
        """
        if not task.save_path or not os.path.exists(task.save_path) or not os.path.isfile(task.save_path):
            return

        _, ext = os.path.splitext(task.save_path)
        if ext:
            return

        detected_ext = detect_file_extension_from_magic(task.save_path)
        if detected_ext:
            dir_name = os.path.dirname(task.save_path)
            base_name = os.path.basename(task.save_path)
            new_filename = f"{base_name}{detected_ext}"
            new_save_path = os.path.join(dir_name, new_filename)
            counter = 1
            while os.path.exists(new_save_path):
                new_filename = f"{base_name}_{counter}{detected_ext}"
                new_save_path = os.path.join(dir_name, new_filename)
                counter += 1
            try:
                os.rename(task.save_path, new_save_path)
                task.save_path = new_save_path
                task.filename = new_filename
                task.category = get_category_from_filename(task.filename)
                self.db.save_task(task)
            except Exception as e:
                print(f"[Engine] Could not rename file with detected extension: {e}")

    def create_task(
        self,
        url: str,
        save_dir: str,
        filename: Optional[str] = None,
        connections: int = 8,
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        checksum: Optional[str] = None,
        checksum_type: str = "SHA-256",
        auto_extract: bool = False,
        post_action: str = "none",
        total_bytes: Optional[int] = None,
        resumable: Optional[bool] = None,
        task_id: Optional[str] = None,
        zero_log: bool = False,
        on_duplicate_found: Optional[Callable] = None,
        description: str = ""
    ) -> DownloadTask:
        task_id = task_id or str(uuid.uuid4())
        # Auto-resolve PikPak share link to direct CDN download stream
        try:
            from .pikpak_resolver import PikPakResolver
            if PikPakResolver.is_pikpak_url(url):
                pik_first = PikPakResolver.resolve_single_or_first(url)
                if pik_first and pik_first.get("url"):
                    if not filename or filename in ("download.bin", "auto_detected_filename.ext"):
                        filename = sanitize_filename(pik_first.get("name", filename))
                    if total_bytes is None or total_bytes <= 0:
                        total_bytes = pik_first.get("size", total_bytes)
                    url = pik_first["url"]
                    if not headers:
                        headers = {}
                    headers.update(pik_first.get("headers", {}))
        except Exception as e_pik_task:
            print(f"[DownloadEngine] PikPak task resolution warning: {e_pik_task}")
        url = CloudLinkResolver.resolve(url)
        req_headers, final_proxy = self._apply_credentials_and_proxy(url, headers or {}, proxy)
        req_headers = CloudLinkResolver.fix_headers(url, req_headers)

        # Zero Log: override from global setting if not explicitly set
        if not zero_log:
            zero_log = str(self.db.get_setting("zero_log_mode", "false")).lower() in ("true", "1", "yes")

        # Duplicate detection (skip for zero_log tasks)
        if not zero_log and filename:
            try:
                dup = DuplicateDetector.check(url, filename, save_dir, self.db)
                if dup and dup.is_duplicate and on_duplicate_found:
                    on_duplicate_found(dup)
                    # Don't auto-cancel — let caller decide based on dup result
            except Exception as e:
                print(f"[!] Warning checking duplicate: {e}")


        # Check if URL is an HLS (.m3u8) or DASH (.mpd) stream
        is_hls = (
            ".m3u8" in url.lower() or 
            ".mpd" in url.lower() or
            (headers and (headers.get("is_hls") in ["true", True, 1, "1"] or "mpegurl" in str(headers.get("content-type", "")).lower()))
        )

        # Check if URL is a BitTorrent Magnet link or .torrent file
        is_torrent = url.startswith("magnet:") or url.lower().endswith(".torrent") or (os.path.isfile(url) and url.lower().endswith(".torrent"))
        if is_torrent:
            from .torrent_downloader import TorrentWorker
            t_info = None
            if not filename or total_bytes is None or total_bytes <= 0:
                t_info = TorrentWorker.get_torrent_info(url)
            raw_filename = filename or (t_info.get("name") if t_info else None) or "torrent_download"
            if total_bytes is None or total_bytes <= 0:
                total_bytes = t_info.get("total_bytes", -1) if t_info else -1
            resumable = True
            category = "Torrents"
        # Check if URL is an HLS (.m3u8) or DASH (.mpd) stream
        elif is_hls:
            req_headers["is_hls"] = "true"
            raw_filename = filename
            if not raw_filename or any(raw_filename.lower().startswith(x) for x in ("index", "master", "playlist", "stream", "video_stream")):
                try:
                    from .av01_resolver import AV01Resolver
                    if AV01Resolver.is_av01_url(url):
                        vid = AV01Resolver.extract_video_id(url, req_headers)
                        if vid:
                            meta = AV01Resolver.get_video_metadata(vid)
                            if meta:
                                dvd_id = meta.get("dvd_id") or ""
                                en_t = (
                                    (meta.get("seo_titles") or {}).get("en")
                                    or (meta.get("title_translations") or {}).get("en")
                                    or meta.get("title")
                                    or ""
                                )
                                full_t = f"{dvd_id}•{en_t}".strip("• ") if dvd_id else en_t
                                if full_t:
                                    raw_filename = f"{sanitize_filename(full_t)}.mp4"
                except Exception:
                    pass
            if not raw_filename:
                raw_filename = extract_filename_from_headers({}, url) or "stream.mp4"
            if not raw_filename.lower().endswith(".mp4"):
                base_f, _ = os.path.splitext(raw_filename)
                raw_filename = f"{base_f}.mp4"
            total_bytes = -1
            resumable = True # REAL RESUME CAPABILITY!
            category = "Videos"
        # Check if URL is a yt-dlp media task
        elif headers and (headers.get("is_ytdlp") in ["true", True, 1, "1"]):
            req_headers["is_ytdlp"] = "true"
            raw_filename = filename or "media_download.mp4"
            total_bytes = -1
            resumable = True
            category = "Music" if headers.get("download_mode") == "audio" else "Videos"
        else:
            # Check if filename was provided and whether it has an extension
            _, given_ext = os.path.splitext(filename or "")
            # If total_bytes is already known (> 0) and filename has an extension, probe can be bypassed
            if total_bytes is not None and total_bytes > 0 and given_ext:
                raw_filename = filename
                resumable = True if resumable is None else resumable
                category = get_category_from_filename(raw_filename)
            else:
                probe = self.probe_url(url, headers=req_headers, proxy=final_proxy)
                probe_name = probe.get("filename")
                _, probe_ext = os.path.splitext(probe_name or "")
                if filename:
                    # If given filename has no extension, but probe discovered one, prefer probe filename
                    if not given_ext and probe_ext:
                        raw_filename = probe_name
                    else:
                        raw_filename = filename
                else:
                    raw_filename = probe_name or "download"
                if total_bytes is None or total_bytes <= 0:
                    total_bytes = probe.get("total_bytes", -1)
                if resumable is None:
                    resumable = probe.get("resumable", False)
                category = probe.get("category", get_category_from_filename(raw_filename))

        final_filename = sanitize_filename(os.path.basename(raw_filename))
        abs_save_dir = os.path.abspath(save_dir)

        # Smart Category Subfolder Auto-Routing
        auto_subfolders = self.db.get_setting("category_subfolders", "true") == "true"
        if auto_subfolders and category and category != "General":
            cat_key = f"category_dir_{category.lower()}"
            custom_cat_dir = self.db.get_setting(cat_key, "").strip()
            if custom_cat_dir and os.path.isdir(custom_cat_dir):
                abs_save_dir = custom_cat_dir
            elif not abs_save_dir.lower().endswith(category.lower()):
                abs_save_dir = os.path.join(abs_save_dir, category)

        os.makedirs(abs_save_dir, exist_ok=True)
        target_path = os.path.abspath(os.path.join(abs_save_dir, final_filename))

        # Path Traversal Guard: Ensure target_path stays strictly inside save_dir
        if not target_path.startswith(abs_save_dir + os.sep) and target_path != abs_save_dir:
            final_filename = sanitize_filename(os.path.basename(final_filename))
            target_path = os.path.join(abs_save_dir, final_filename)

        # Handle file name conflict (skip for torrents to allow piece verification & resume)
        if not is_torrent:
            base_name, ext = os.path.splitext(final_filename)
            counter = 1
            while os.path.exists(target_path):
                target_path = os.path.join(abs_save_dir, f"{base_name}_{counter}{ext}")
                final_filename = f"{base_name}_{counter}{ext}"
                counter += 1

        from .license_manager import LicenseManager
        lic_mgr = LicenseManager.get_instance(self.db)
        max_lic_conns = lic_mgr.get_max_segments_allowed()
        if max_lic_conns > 4:
            tok = lic_mgr.get_feature_session_token("high_connections")
            if not lic_mgr.verify_feature_token("high_connections", tok):
                max_lic_conns = 4

        # Create segments
        segments = []
        if is_torrent:
            actual_conn = min(connections or 16, max_lic_conns, 32)
            for i in range(actual_conn):
                segments.append(SegmentModel(index=i, start_byte=0, end_byte=1000000, downloaded_bytes=0, status="Connecting to Swarm..."))
        elif is_hls or (headers and (headers.get("is_ytdlp") in ["true", True, 1, "1"])):
            actual_conn = min(connections or 8, max_lic_conns, 8)
            for i in range(actual_conn):
                segments.append(SegmentModel(index=i, start_byte=0, end_byte=1000000, downloaded_bytes=0, status="Connecting..."))
        elif resumable and total_bytes > 0:
            actual_conn = min(connections, max_lic_conns, max(1, total_bytes // (128 * 1024)))
            chunk_size = total_bytes // actual_conn
            for i in range(actual_conn):
                start = i * chunk_size
                end = (start + chunk_size - 1) if i < actual_conn - 1 else (total_bytes - 1)
                segments.append(SegmentModel(index=i, start_byte=start, end_byte=end))
        else:
            # Single stream download (non-resumable or unknown/chunked size)
            end_b = (total_bytes - 1) if (total_bytes and total_bytes > 0) else -1
            segments.append(SegmentModel(index=0, start_byte=0, end_byte=end_b, downloaded_bytes=0, status="Connecting"))

        task = DownloadTask(
            id=task_id,
            url=url,
            filename=final_filename,
            save_path=target_path,
            total_bytes=total_bytes,
            downloaded_bytes=0,
            status=DownloadStatus.QUEUED,
            category=category,
            connections=len(segments) if segments else 1,
            resumable=resumable,
            segments=segments,
            headers=req_headers,
            proxy=final_proxy,
            checksum=checksum,
            checksum_type=checksum_type,
            auto_extract=auto_extract,
            post_action=post_action,
            is_torrent=is_torrent,
            zero_log=zero_log,
            description=description
        )

        with self.lock:
            self.tasks[task.id] = task
            if not zero_log:
                self.db.save_task(task)

        return task


    def start_download(self, task_id: str):
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return

            has_active_worker = False
            if task.id in self.workers and self.workers[task.id]:
                has_active_worker = any(w.is_alive() for w in self.workers[task.id])
            elif task.id in self.hls_workers and self.hls_workers[task.id].is_alive():
                has_active_worker = True
            elif task.id in self.torrent_workers and self.torrent_workers[task.id].is_alive():
                has_active_worker = True
            elif task.id in self.ytdlp_workers and self.ytdlp_workers[task.id].is_alive():
                has_active_worker = True

            if task.status == DownloadStatus.DOWNLOADING and has_active_worker:
                return

            from .license_manager import LicenseManager
            license_mgr = LicenseManager.get_instance(self.db)
            tok_conc = license_mgr.get_feature_session_token("unlimited_concurrent")
            is_conc_ok = license_mgr.is_feature_allowed("unlimited_concurrent") and license_mgr.verify_feature_token("unlimited_concurrent", tok_conc)
            if not is_conc_ok:
                active_count = sum(1 for t in self.tasks.values() if t.status in [DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING] and t.id != task_id)
                if active_count >= license_mgr.get_max_concurrent_allowed():
                    task.status = DownloadStatus.QUEUED
                    task.error_message = f"Maksimal {license_mgr.get_max_concurrent_allowed()} unduhan aktif simultan pada Versi Terbatas. Daftarkan Full Version untuk unduhan tanpa batas."
                    self.db.save_task(task)
                    if self.on_task_updated:
                        self.on_task_updated(task)
                    return

            task.status = DownloadStatus.CONNECTING
            self.db.save_task(task)

        self.sound_manager.play_start()

        try:
            self._start_download_internal(task)
        except Exception as e:
            import traceback
            traceback.print_exc()
            with self.lock:
                task.status = DownloadStatus.ERROR
                task.error_message = f"Gagal memulai unduhan: {e}"
                task.speed = 0.0
                self.db.save_task(task)
            self.sound_manager.play_error()
            if self.on_task_failed:
                self.on_task_failed(task, task.error_message)
            if self.on_task_updated:
                self.on_task_updated(task)

    def _start_download_internal(self, task: DownloadTask):
        # Check if URL is a BitTorrent Magnet link or .torrent file
        is_torrent_task = getattr(task, "is_torrent", False) or task.url.startswith("magnet:") or task.url.lower().endswith(".torrent")
        if is_torrent_task:
            if not self.db.is_torrent_enabled():
                task.status = DownloadStatus.ERROR
                task.error_message = "Unduhan BitTorrent dinonaktifkan dalam Pengaturan."
                self.db.save_task(task)
                if self.on_task_failed:
                    self.on_task_failed(task, task.error_message)
                return

            pause_event = threading.Event()
            pause_event.set()
            cancel_event = threading.Event()
            self.pause_events[task.id] = pause_event
            self.cancel_events[task.id] = cancel_event

            if not task.segments:
                actual_conn = min(task.connections or 16, 32)
                task.segments = [
                    SegmentModel(index=i, start_byte=0, end_byte=1000000, downloaded_bytes=0, status="Connecting...")
                    for i in range(actual_conn)
                ]

            def on_torrent_progress(dl_b, tot_b, dl_spd, ul_spd, seeds, peers, eta_s, tracker_status=""):
                with self.lock:
                    if task.id not in self.tasks:
                        return
                    task.downloaded_bytes = dl_b
                    if tot_b > 0:
                        task.total_bytes = tot_b
                    task.speed = dl_spd
                    task.upload_speed = ul_spd
                    task.torrent_seeds = seeds
                    task.torrent_peers = peers
                    task.eta = eta_s
                    is_seeding = bool((tot_b > 0 and dl_b >= tot_b) or "seeding" in tracker_status.lower())
                    task.is_seeding = is_seeding
                    if is_seeding:
                        now = time.time()
                        last_t = getattr(task, "_last_ul_calc", now)
                        dt = max(0.0, min(2.0, now - last_t))
                        task.uploaded_bytes = getattr(task, "uploaded_bytes", 0) + int(ul_spd * dt)
                        task._last_ul_calc = now
                    if tracker_status:
                        task.tracker_status = tracker_status
                    elif is_seeding:
                        task.tracker_status = f"Seeding (Swarm: {peers}P)" if peers > 0 else "Seeding"
                    elif seeds > 0 or peers > 0:
                        task.tracker_status = ""
                    # Update virtual segment slots for visual telemetry
                    if task.segments:
                        n_slots = max(1, len(task.segments))
                        per_dl = dl_b // n_slots
                        rem_dl = dl_b % n_slots
                        eff_tot = tot_b if tot_b > 0 else max(dl_b * 2, n_slots * 1024 * 1024)
                        per_tot = max(1, eff_tot // n_slots)
                        pct = min(100.0, (dl_b * 100.0) / eff_tot) if eff_tot > 0 else 0.0
                        slot_status = "Receiving data" if dl_spd > 0 else (task.tracker_status if (task.tracker_status and seeds == 0 and peers == 0) else f"Swarm: {seeds}S/{peers}P")
                        for idx_s, seg in enumerate(task.segments):
                            seg.start_byte = 0
                            seg.end_byte = per_tot
                            seg.downloaded_bytes = per_dl + (rem_dl if idx_s == 0 else 0)
                            seg.progress = pct
                            seg.status = slot_status
                if self.on_task_updated:
                    self.on_task_updated(task)

            def on_torrent_finished(success, err, final_path):
                with self.lock:
                    if task.id not in self.tasks:
                        return
                    self.torrent_workers.pop(task.id, None)
                    if success:
                        task.status = DownloadStatus.COMPLETED
                        if final_path and os.path.exists(final_path):
                            base_final = os.path.basename(final_path).lower()
                            if base_final not in ("torrents", "downloads", "general"):
                                task.save_path = final_path
                                task.filename = os.path.basename(final_path)
                            if os.path.isfile(final_path):
                                task.downloaded_bytes = os.path.getsize(final_path)
                                task.total_bytes = task.downloaded_bytes
                            elif os.path.isdir(final_path):
                                total_dir_size = sum(
                                    os.path.getsize(os.path.join(r, f))
                                    for r, _, fs in os.walk(final_path)
                                    for f in fs
                                    if not f.endswith(".aria2")
                                )
                                if total_dir_size > 0:
                                    task.downloaded_bytes = total_dir_size
                                    task.total_bytes = total_dir_size
                        if task.segments and task.downloaded_bytes > 0:
                            n_s = max(1, len(task.segments))
                            p_dl = task.downloaded_bytes // n_s
                            for s in task.segments:
                                s.start_byte = 0
                                s.end_byte = max(1, p_dl)
                                s.downloaded_bytes = p_dl
                                s.progress = 100.0
                                s.status = "Completed"
                        task.speed = 0.0
                        task.upload_speed = 0.0
                        task.eta = 0.0
                        task.completed_at = time.time()
                        task.is_seeding = False
                        task.tracker_status = "Complete (Seeding Finished)"
                        self.db.save_task(task)
                        if hasattr(self.db, "record_seeder_session") and getattr(task, "uploaded_bytes", 0) > 0:
                            dur_s = max(1.0, float(task.completed_at - (task.created_at or task.completed_at)))
                            self.db.record_seeder_session(
                                session_id=task.id,
                                name=task.filename or "Torrent",
                                info_hash=getattr(task, "info_hash", "") or "",
                                total_bytes_reported=task.uploaded_bytes,
                                duration_s=dur_s,
                                started_at=task.created_at or time.time(),
                                completed_at=task.completed_at
                            )
                    else:
                        if task.status == DownloadStatus.PAUSED:
                            task.speed = 0.0
                            task.upload_speed = 0.0
                            self.db.save_task(task)
                        elif self.cancel_events.get(task.id) and self.cancel_events[task.id].is_set():
                            task.status = DownloadStatus.CANCELED
                            task.speed = 0.0
                            task.upload_speed = 0.0
                            self.db.save_task(task)
                        else:
                            task.status = DownloadStatus.ERROR
                            task.error_message = err or "BitTorrent swarm download failed"
                            task.speed = 0.0
                            task.upload_speed = 0.0
                            self.db.save_task(task)

                if success:
                    self.sound_manager.play_complete()
                    if self.on_task_completed:
                        self.on_task_completed(task)
                elif not success and task.status != DownloadStatus.PAUSED:
                    self.sound_manager.play_error()
                    if self.on_task_failed:
                        self.on_task_failed(task, err or "Failed")
                elif self.on_task_updated:
                    self.on_task_updated(task)

            target_dir = os.path.dirname(task.save_path) if task.save_path else os.path.expanduser("~/Downloads")
            selected_files = None
            if task.headers and task.headers.get("selected_files"):
                try:
                    sf = task.headers["selected_files"]
                    if isinstance(sf, list):
                        selected_files = [int(x) for x in sf]
                    elif isinstance(sf, str):
                        selected_files = [int(x) for x in sf.split(",") if x.strip().isdigit()]
                except Exception:
                    pass

            seed_days = 3
            if task.headers and "seed_duration_days" in task.headers:
                try:
                    seed_days = int(task.headers["seed_duration_days"])
                except Exception:
                    pass

            torrent_worker = TorrentWorker(
                source=task.url,
                save_dir=target_dir,
                task_id=task.id,
                headers=task.headers,
                pause_event=pause_event,
                cancel_event=cancel_event,
                on_progress=on_torrent_progress,
                on_finished=on_torrent_finished,
                download_rate_limit=self.speed_limiter.max_bytes_per_sec if (self.speed_limiter and self.speed_limiter.enabled) else 0,
                selected_files=selected_files,
                seed_duration_days=seed_days
            )
            self.torrent_workers[task.id] = torrent_worker
            task.status = DownloadStatus.DOWNLOADING
            self.db.save_task(task)
            torrent_worker.start()

            if self.on_task_updated:
                self.on_task_updated(task)
            return

        # Check if URL is an HLS (.m3u8 / .urlset) or DASH (.mpd) stream
        is_hls = (
            ".m3u8" in task.url.lower() or 
            ".mpd" in task.url.lower() or
            ".urlset/" in task.url.lower() or
            (task.headers and (
                task.headers.get("is_hls") in ["true", True, 1, "1"] or
                task.headers.get("is_dash") in ["true", True, 1, "1"] or
                "mpegurl" in str(task.headers.get("content-type", "")).lower() or
                "dash+xml" in str(task.headers.get("content-type", "")).lower()
            ))
        )

        if is_hls:
            pause_event = threading.Event()
            pause_event.set()
            cancel_event = threading.Event()
            self.pause_events[task.id] = pause_event
            self.cancel_events[task.id] = cancel_event

            _last_hls_db_save = [0.0]
            def on_hls_progress(dl_bytes, total_b, spd, eta):
                now_t = time.time()
                should_save = False
                with self.lock:
                    if task.id not in self.tasks:
                        return
                    task.downloaded_bytes = dl_bytes
                    if total_b > 0:
                        task.total_bytes = total_b
                    task.speed = spd
                    task.eta = eta
                    if now_t - _last_hls_db_save[0] >= 3.0:
                        _last_hls_db_save[0] = now_t
                        should_save = True
                if should_save:
                    try:
                        self._save_task_if_needed(task)
                    except Exception:
                        pass
                if self.on_task_updated:
                    self.on_task_updated(task)

            def on_hls_finished(success, err):
                with self.lock:
                    if task.id not in self.tasks:
                        return
                    worker_ref = self.hls_workers.pop(task.id, None)
                    if worker_ref and getattr(worker_ref, "target_path", None) and worker_ref.target_path != task.save_path:
                        if os.path.exists(worker_ref.target_path):
                            task.save_path = worker_ref.target_path
                            task.filename = os.path.basename(worker_ref.target_path)
                    if success:
                        HLSWorker.cleanup_temp_fragments(task.save_path)
                        task.status = DownloadStatus.COMPLETED
                        if os.path.exists(task.save_path):
                            task.downloaded_bytes = os.path.getsize(task.save_path)
                            task.total_bytes = task.downloaded_bytes
                        task.speed = 0.0
                        task.eta = 0
                        self.db.save_task(task)
                        AntivirusScanner.scan_file_async(task.save_path, db=self.db)
                    else:
                        if task.status == DownloadStatus.PAUSED:
                            task.speed = 0.0
                            self.db.save_task(task)
                        elif self.cancel_events.get(task.id) and self.cancel_events[task.id].is_set():
                            task.status = DownloadStatus.CANCELED
                            task.speed = 0.0
                            self.db.save_task(task)
                        else:
                            task.status = DownloadStatus.ERROR
                            task.error_message = err or "HLS stream download failed"
                            task.speed = 0.0
                            self.db.save_task(task)

                if success:
                    self.sound_manager.play_complete()
                    if self.on_task_completed:
                        self.on_task_completed(task)
                elif not success and task.status != DownloadStatus.PAUSED:
                    self.sound_manager.play_error()
                    if self.on_task_failed:
                        self.on_task_failed(task, err or "Failed")
                elif self.on_task_updated:
                    self.on_task_updated(task)

            is_live_task = bool(
                (task.headers and (
                    task.headers.get("is_live") in ["true", True, 1, "1"] or
                    any(d in str(task.headers.get("Referer", "")).lower() for d in ("chaturbate", "stripchat")) or
                    any(d in str(task.headers.get("master_url", "")).lower() for d in ("chaturbate", "stripchat", "mmcdn", "doppiocdn"))
                )) or
                any(d in task.url.lower() for d in ("chaturbate.com", "stripchat.com", "cb.live", "mmcdn.com", "highwebmedia.com", "doppiocdn", "stripcdn"))
            )
            def on_hls_url_renewed(new_url, new_headers):
                with self.lock:
                    task.url = new_url
                    if new_headers:
                        if not task.headers:
                            task.headers = {}
                        task.headers.update(new_headers)
                    self.db.save_task(task)
                if self.on_task_updated:
                    self.on_task_updated(task)

            if not task.segments:
                actual_conn = min(task.connections or 8, 8)
                slot_dl = (task.downloaded_bytes // actual_conn) if (task.downloaded_bytes and task.downloaded_bytes > 0) else 0
                task.segments = [
                    SegmentModel(index=i, start_byte=0, end_byte=1000000, downloaded_bytes=slot_dl, status="Connecting...")
                    for i in range(actual_conn)
                ]
            hls_worker = HLSWorker(
                url=task.url,
                target_path=task.save_path,
                task_id=task.id,
                segment_slots=task.segments,
                connections=task.connections or 16,
                speed_limiter=self.speed_limiter,
                pause_event=pause_event,
                cancel_event=cancel_event,
                on_progress=on_hls_progress,
                on_finished=on_hls_finished,
                headers=task.headers,
                proxy=task.proxy,
                is_live=is_live_task,
                on_url_renewed=on_hls_url_renewed
            )
            self.hls_workers[task.id] = hls_worker
            task.status = DownloadStatus.DOWNLOADING
            self.db.save_task(task)
            hls_worker.start()

            if self.on_task_updated:
                self.on_task_updated(task)
            return

        # Check if URL is a yt-dlp task
        is_ytdlp_task = bool(getattr(task, "is_ytdlp", False) or (task.headers and (task.headers.get("is_ytdlp") in ["true", True, 1, "1"])))
        if is_ytdlp_task:
            from .ytdlp_worker import YtdlpWorker
            pause_event = threading.Event()
            pause_event.set()
            cancel_event = threading.Event()
            self.pause_events[task.id] = pause_event
            self.cancel_events[task.id] = cancel_event

            _last_ytdlp_db_save = [0.0]
            def on_ytdlp_progress(dl_b, tot_b, spd, eta):
                now_t = time.time()
                should_save = False
                with self.lock:
                    if task.id not in self.tasks:
                        return
                    task.downloaded_bytes = dl_b
                    if tot_b > 0:
                        task.total_bytes = tot_b
                    task.speed = spd
                    task.eta = eta
                    if task.segments:
                        n_slots = max(1, len(task.segments))
                        per_dl = dl_b // n_slots
                        rem_dl = dl_b % n_slots
                        eff_tot = tot_b if tot_b > 0 else max(dl_b * 2, n_slots * 1024 * 1024)
                        per_tot = max(1, eff_tot // n_slots)
                        pct = min(100.0, (dl_b * 100.0) / eff_tot) if eff_tot > 0 else 0.0
                        slot_status = "Mengunduh..." if spd > 0 else "Menunggu data..."
                        for idx_s, seg in enumerate(task.segments):
                            seg.start_byte = 0
                            seg.end_byte = per_tot
                            seg.downloaded_bytes = per_dl + (rem_dl if idx_s == 0 else 0)
                            seg.progress = pct
                            seg.status = slot_status
                    if now_t - _last_ytdlp_db_save[0] >= 3.0:
                        _last_ytdlp_db_save[0] = now_t
                        should_save = True
                if should_save:
                    try:
                        self._save_task_if_needed(task)
                    except Exception:
                        pass
                if self.on_task_updated:
                    self.on_task_updated(task)

            def on_ytdlp_finished(success, err, final_path):
                with self.lock:
                    if task.id not in self.tasks:
                        return
                    self.ytdlp_workers.pop(task.id, None)
                    if success:
                        task.status = DownloadStatus.COMPLETED
                        if final_path and os.path.exists(final_path):
                            task.save_path = final_path
                            task.filename = os.path.basename(final_path)
                            if os.path.isfile(final_path):
                                task.downloaded_bytes = os.path.getsize(final_path)
                                task.total_bytes = task.downloaded_bytes
                        if task.segments:
                            for s in task.segments:
                                s.progress = 100.0
                                s.status = "Selesai"
                        task.speed = 0.0
                        task.eta = 0
                        task.completed_at = time.time()
                        self.db.save_task(task)
                    else:
                        if task.status == DownloadStatus.PAUSED:
                            task.speed = 0.0
                            self.db.save_task(task)
                        elif self.cancel_events.get(task.id) and self.cancel_events[task.id].is_set():
                            task.status = DownloadStatus.CANCELED
                            task.speed = 0.0
                            self.db.save_task(task)
                        else:
                            task.status = DownloadStatus.ERROR
                            task.error_message = err or "Unduhan YT-DLP gagal"
                            task.speed = 0.0
                            self.db.save_task(task)

                if success:
                    self.sound_manager.play_complete()
                    if self.on_task_completed:
                        self.on_task_completed(task)
                elif not success and task.status != DownloadStatus.PAUSED:
                    self.sound_manager.play_error()
                    if self.on_task_failed:
                        self.on_task_failed(task, err or "Failed")
                elif self.on_task_updated:
                    self.on_task_updated(task)

            hdrs = task.headers or {}
            target_dir = os.path.dirname(task.save_path) if task.save_path else os.path.expanduser("~/Downloads")
            ytdlp_worker = YtdlpWorker(
                url=task.url,
                format_id=hdrs.get("format_id", "best"),
                save_dir=target_dir,
                filename=task.filename,
                task_id=task.id,
                pause_event=pause_event,
                cancel_event=cancel_event,
                on_progress=on_ytdlp_progress,
                on_finished=on_ytdlp_finished,
                download_mode=hdrs.get("download_mode", "video"),
                video_quality=hdrs.get("video_quality", "best"),
                container_format=hdrs.get("container_format", "mp4"),
                audio_format=hdrs.get("audio_format", "mp3"),
                audio_bitrate=hdrs.get("audio_bitrate", "320"),
                embed_subtitles=str(hdrs.get("embed_subtitles", "false")).lower() in ("true", "1"),
                embed_thumbnail=str(hdrs.get("embed_thumbnail", "true")).lower() in ("true", "1"),
                embed_metadata=str(hdrs.get("embed_metadata", "true")).lower() in ("true", "1"),
                concurrent_fragments=8,
                use_aria2=True,
                cookies_browser=hdrs.get("cookies_browser") or None,
                proxy=task.proxy
            )
            self.ytdlp_workers[task.id] = ytdlp_worker
            task.status = DownloadStatus.DOWNLOADING
            self.db.save_task(task)
            ytdlp_worker.start()

            if self.on_task_updated:
                self.on_task_updated(task)
            return

        # Direct file download: ensure at least one segment exists
        if not task.segments:
            end_b = (task.total_bytes - 1) if (task.total_bytes and task.total_bytes > 0) else -1
            task.segments = [SegmentModel(index=0, start_byte=0, end_byte=end_b, downloaded_bytes=task.downloaded_bytes or 0, status="Connecting")]
            task.connections = 1
            self.db.save_task(task)

        # Pre-allocate contiguous physical clusters on NTFS/ReFS using low-level Win32 API
        save_dir = os.path.dirname(task.save_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
        else:
            task.save_path = os.path.abspath(task.save_path or task.filename or "download_file")
            save_dir = os.path.dirname(task.save_path)
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
        if task.total_bytes and task.total_bytes > 0:
            Win32Native.preallocate_disk_space(task.save_path, task.total_bytes)
        elif not os.path.exists(task.save_path):
            with open(task.save_path, "wb") as f:
                pass

        pause_event = threading.Event()
        pause_event.set()
        cancel_event = threading.Event()

        self.pause_events[task.id] = pause_event
        self.cancel_events[task.id] = cancel_event

        # Apply cloud link resolver (auto-redirects legacy/decommissioned domains like speed.hetzner.de)
        task.url = CloudLinkResolver.resolve(task.url)
        task.headers = CloudLinkResolver.fix_headers(task.url, task.headers or {})

        workers = []
        for seg in task.segments:
            worker = SegmentWorker(
                url=task.url,
                target_path=task.save_path,
                segment=seg,
                speed_limiter=self.speed_limiter,
                pause_event=pause_event,
                cancel_event=cancel_event,
                on_bytes_received=lambda b, tid=task.id: self._on_bytes_received(tid, b),
                on_finished=lambda idx, success, err, tid=task.id: self._on_segment_finished(tid, idx, success, err),
                headers=task.headers,
                proxy=task.proxy,
                on_total_bytes_discovered=lambda tot, tid=task.id: self._on_total_bytes_discovered(tid, tot),
                on_url_refreshed=lambda nu, nh, tid=task.id: self._on_worker_url_refreshed(tid, nu, nh)
            )
            workers.append(worker)

        self.workers[task.id] = workers
        task.status = DownloadStatus.DOWNLOADING
        self.db.save_task(task)

        for w in workers:
            w.start()

        if self.on_task_updated:
            self.on_task_updated(task)

    def resume_task(self, task_id: str):
        """Resume / start download for a task."""
        self.start_download(task_id)

    def pause_download(self, task_id: str):
        with self.lock:
            task = self.tasks.get(task_id)
            if not task or task.status != DownloadStatus.DOWNLOADING:
                return

            if task_id in self.hls_workers:
                worker = self.hls_workers.get(task_id)
                is_live_worker = bool(
                    (worker and worker.is_live) or
                    (task.headers and task.headers.get("is_live") in ["true", True, 1, "1"])
                )
                if is_live_worker and worker:
                    # For a live stream, clicking Pause / "Selesai & Simpan" finalizes & remuxes the recorded stream into MP4/WebM!
                    worker.finish_live_recording()
                    event = self.pause_events.get(task_id)
                    if event:
                        event.clear()
                    return

            event = self.pause_events.get(task_id)
            if event:
                event.clear()

            if task_id in self.workers:
                workers = self.workers.pop(task_id, [])
                for w in workers:
                    try:
                        w.pause()
                    except Exception:
                        pass

            if task_id in self.torrent_workers:
                worker = self.torrent_workers.pop(task_id, None)
                if worker:
                    worker.stop()


            if task_id in self.hls_workers:
                worker = self.hls_workers.get(task_id)
                if worker:
                    worker.stop()

            task.status = DownloadStatus.PAUSED
            task.speed = 0.0
            task.upload_speed = 0.0
            self.db.save_task(task)

        if self.on_task_updated:
            self.on_task_updated(task)

    def pause_all(self):
        with self.lock:
            active_ids = [tid for tid, t in self.tasks.items() if t.status == DownloadStatus.DOWNLOADING]
        for tid in active_ids:
            self.pause_download(tid)

    def stop(self):
        self._monitor_running = False
        self.pause_all()
        for worker in list(self.hls_workers.values()):
            try:
                worker.stop()
            except Exception:
                pass

    def cancel_download(self, task_id: str, delete_file: bool = False):
        if not delete_file:
            with self.lock:
                task = self.tasks.get(task_id)
                worker = self.hls_workers.get(task_id) if task_id in self.hls_workers else None
                if task and worker and (worker.is_live or (task.headers and task.headers.get("is_live") in ["true", True, 1, "1"])) and (worker._downloaded_bytes > 0 or task.downloaded_bytes > 0):
                    # If user clicked Stop (without deleting file) on an active live recording, finalize and save the recorded MP4/WebM
                    worker.finish_live_recording()
                    event = self.pause_events.get(task_id)
                    if event:
                        event.clear()
                    return

        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return

            event = self.cancel_events.get(task_id)
            if event:
                event.set()

            if task_id in self.workers:
                workers = self.workers.pop(task_id, [])
                for w in workers:
                    try:
                        w.stop()
                    except Exception:
                        pass

            if task_id in self.torrent_workers:
                worker = self.torrent_workers.pop(task_id, None)
                if worker:
                    worker.stop()


            if task_id in self.hls_workers:
                worker = self.hls_workers.pop(task_id, None)
                if worker:
                    worker.stop()

            if task_id in self.ytdlp_workers:
                self.ytdlp_workers.pop(task_id, None)

            task.status = DownloadStatus.CANCELED
            task.speed = 0.0
            task.upload_speed = 0.0
            self.db.save_task(task)

            if delete_file:
                if os.path.exists(task.save_path):
                    try:
                        if os.path.isdir(task.save_path):
                            shutil.rmtree(task.save_path, ignore_errors=True)
                        else:
                            os.remove(task.save_path)
                    except Exception:
                        pass
                aria2_meta = task.save_path + ".aria2"
                if os.path.exists(aria2_meta):
                    try:
                        os.remove(aria2_meta)
                    except Exception:
                        pass
                import tempfile
                cache_dir = os.path.join(tempfile.gettempdir(), f"zero_hls_{task_id}")
                if os.path.exists(cache_dir):
                    shutil.rmtree(cache_dir, ignore_errors=True)

        if self.on_task_updated:
            self.on_task_updated(task)

    def delete_task(self, task_id: str, delete_file: bool = False):
        try:
            self.cancel_download(task_id, delete_file=delete_file)
        except Exception as e:
            print(f"[Engine] Warning cancelling task {task_id} during delete: {e}")
        with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
            self.db.delete_task(task_id)
            if task_id in self.workers:
                del self.workers[task_id]
            if task_id in self.torrent_workers:
                del self.torrent_workers[task_id]
            if task_id in self.hls_workers:
                del self.hls_workers[task_id]
            if task_id in self.ytdlp_workers:
                del self.ytdlp_workers[task_id]
            if task_id in self.pause_events:
                del self.pause_events[task_id]
            if task_id in self.cancel_events:
                del self.cancel_events[task_id]
            if task_id in self._speed_tracker:
                del self._speed_tracker[task_id]

    def _on_bytes_received(self, task_id: str, count: int):
        with self.lock:
            task = self.tasks.get(task_id)
            if task and task.status == DownloadStatus.DOWNLOADING:
                task.downloaded_bytes = sum(s.downloaded_bytes for s in task.segments)
                if task.total_bytes > 0:
                    task.downloaded_bytes = min(task.total_bytes, task.downloaded_bytes)
                if task_id not in self._speed_tracker:
                    self._speed_tracker[task_id] = []
                self._speed_tracker[task_id].append(count)

    def _on_total_bytes_discovered(self, task_id: str, total_b: int):
        with self.lock:
            task = self.tasks.get(task_id)
            if task and task.total_bytes <= 0 and total_b > 0:
                task.total_bytes = total_b
                self.db.save_task(task)
        if self.on_task_updated and task:
            self.on_task_updated(task)

    def _on_worker_url_refreshed(self, task_id: str, new_url: str, new_headers: dict):
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                task.url = new_url
                task.headers.update(new_headers)
                self.db.save_task(task)
                if task_id in self.workers:
                    for w in self.workers[task_id]:
                        w.url = new_url
                        w.headers.update(new_headers)
        if self.on_task_updated and task:
            self.on_task_updated(task)

    def _on_segment_finished(self, task_id: str, index: int, success: bool, error: Optional[str]):
        with self.lock:
            task = self.tasks.get(task_id)
            if not task or task.status != DownloadStatus.DOWNLOADING:
                return

            all_done = all(s.status == "Completed" for s in task.segments)
            any_error = any(s.status == "Error" for s in task.segments)

            if all_done:
                # Clean up workers and cancel events to release all OS file locks immediately
                cancel_ev = self.cancel_events.pop(task_id, None)
                if cancel_ev:
                    cancel_ev.set()
                self.pause_events.pop(task_id, None)
                workers = self.workers.pop(task_id, [])
                for w in workers:
                    try:
                        w.stop()
                    except Exception:
                        pass

                HLSWorker.cleanup_temp_fragments(task.save_path)
                task.status = DownloadStatus.COMPLETED
                task.completed_at = time.time()
                task.speed = 0.0
                task.eta = 0.0
                if os.path.exists(task.save_path):
                    actual_sz = os.path.getsize(task.save_path)
                    if task.total_bytes <= 0 or task.downloaded_bytes != actual_sz:
                        task.total_bytes = actual_sz
                        task.downloaded_bytes = actual_sz
                else:
                    task.downloaded_bytes = task.total_bytes if task.total_bytes > 0 else task.downloaded_bytes

                # Automatically detect and fix file extension from magic bytes if missing
                self._auto_detect_and_fix_extension(task)

                # Checksum verification if requested
                if task.checksum:
                    try:
                        valid, actual_hash = FileHasher.verify_hash(task.save_path, task.checksum, task.checksum_type)
                        if not valid:
                            task.error_message = f"Checksum mismatch! Expected: {task.checksum[:8]}..., Got: {actual_hash[:8]}..."
                    except Exception as he:
                        task.error_message = f"Checksum error: {str(he)}"

                # Auto Extract if requested
                if task.auto_extract and ArchiveExtractor.is_archive(task.save_path):
                    threading.Thread(target=ArchiveExtractor.extract, args=(task.save_path,), daemon=True).start()

                self.db.save_task(task)

                # Antivirus Auto-Scan
                AntivirusScanner.scan_file_async(task.save_path, db=self.db)

                # Post action on completion (shutdown, sleep, etc.)
                if task.post_action and task.post_action != "none":
                    PostActionManager.execute(task.post_action)

                self.sound_manager.play_complete()
                if self.on_task_completed:
                    self.on_task_completed(task)
            elif any_error:
                cancel_ev = self.cancel_events.pop(task_id, None)
                if cancel_ev:
                    cancel_ev.set()
                self.pause_events.pop(task_id, None)
                workers = self.workers.pop(task_id, [])
                for w in workers:
                    try:
                        w.stop()
                    except Exception:
                        pass
                task.status = DownloadStatus.ERROR
                err_clean = error or "Segment download error"
                if "11001" in err_clean or "getaddrinfo" in err_clean:
                    err_clean = "Server / Host tidak ditemukan (Domain offline / DNS Error)"
                task.error_message = err_clean
                self.db.save_task(task)
                self.sound_manager.play_error()
                if self.on_task_failed:
                    self.on_task_failed(task, task.error_message)
            elif not any_error and task.resumable and task.total_bytes > 0:
                # Zero Dynamic Work-Stealing: Re-allocate finished connection to steal largest remaining chunk
                self._try_split_largest_segment(task)

        if self.on_task_updated:
            self.on_task_updated(task)


    def _try_split_largest_segment(self, task: DownloadTask):
        """
        Zero Dynamic Work-Stealing Algorithm:
        When a connection finishes its assigned byte range early, scans for the active
        segment with the largest remaining byte range. If significant (>= 1.5 MB),
        splits it in half dynamically and immediately launches a new worker.
        """
        if not task.resumable or task.total_bytes <= 0 or task.status != DownloadStatus.DOWNLOADING:
            return

        from .license_manager import LicenseManager
        lic_mgr = LicenseManager.get_instance(self.db)
        max_allowed_segs = lic_mgr.get_max_segments_allowed()
        if max_allowed_segs > 4:
            tok = lic_mgr.get_feature_session_token("high_connections")
            if not lic_mgr.verify_feature_token("high_connections", tok):
                max_allowed_segs = 4
        if len(task.segments) >= max_allowed_segs:
            return

        pause_event = self.pause_events.get(task.id)
        cancel_event = self.cancel_events.get(task.id)
        if not pause_event or not cancel_event or cancel_event.is_set():
            return

        donor_seg = None
        max_remaining = 0
        min_split_threshold = int(1.5 * 1024 * 1024)  # 1.5 MB threshold

        for seg in task.segments:
            if seg.status in ("Downloading", "Receiving data") and seg.end_byte > 0:
                curr_pos = seg.start_byte + seg.downloaded_bytes
                rem = seg.end_byte - curr_pos + 1
                if rem > max_remaining:
                    max_remaining = rem
                    donor_seg = seg

        if donor_seg and max_remaining >= min_split_threshold:
            curr_pos = donor_seg.start_byte + donor_seg.downloaded_bytes
            split_point = curr_pos + (max_remaining // 2)

            if split_point > curr_pos + 512 * 1024 and split_point < donor_seg.end_byte:
                orig_end = donor_seg.end_byte
                donor_seg.end_byte = split_point

                new_idx = len(task.segments)
                new_seg = SegmentModel(
                    index=new_idx,
                    start_byte=split_point + 1,
                    end_byte=orig_end,
                    downloaded_bytes=0,
                    status="Connecting"
                )
                task.segments.append(new_seg)
                task.connections = len(task.segments)

                worker = SegmentWorker(
                    url=task.url,
                    target_path=task.save_path,
                    segment=new_seg,
                    speed_limiter=self.speed_limiter,
                    pause_event=pause_event,
                    cancel_event=cancel_event,
                    on_bytes_received=lambda b, tid=task.id: self._on_bytes_received(tid, b),
                    on_finished=lambda idx, s_ok, err, tid=task.id: self._on_segment_finished(tid, idx, s_ok, err),
                    headers=task.headers,
                    proxy=task.proxy,
                    on_total_bytes_discovered=lambda tot, tid=task.id: self._on_total_bytes_discovered(tid, tot),
                    on_url_refreshed=lambda nu, nh, tid=task.id: self._on_worker_url_refreshed(tid, nu, nh)
                )
                if task.id in self.workers:
                    self.workers[task.id].append(worker)
                else:
                    self.workers[task.id] = [worker]

                worker.start()
                self.db.save_task(task)

    def refresh_task_url(self, task_id: str, new_url: str, new_headers: Optional[dict] = None, auto_start: bool = False) -> tuple[bool, str]:
        """
        Refreshes the download URL and headers for an existing task (e.g. when CDN or file host token expired).
        Validates the new URL supports byte-resumption and matches the expected file size.
        If auto_start is True, immediately starts/resumes the download.
        """
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return False, "Task not found"
            if task.status == DownloadStatus.DOWNLOADING:
                self.pause_download(task_id)

        # Probe the new URL
        try:
            is_hls_task = bool(
                (task.headers and (task.headers.get("is_hls") in ["true", True, 1, "1"]))
                or (".m3u8" in (task.url or "").lower())
                or (".m3u8" in (new_url or "").lower())
            )

            info = self.probe_url(new_url, headers=new_headers or task.headers, proxy=task.proxy)
            if not is_hls_task:
                if not info.get("success", True):
                    err_msg = info.get("error", "")
                    if err_msg and ("403" in err_msg or "401" in err_msg):
                        return False, f"Server menolak tautan baru ({err_msg}). Periksa kembali otentikasi atau cookie."
                    elif not info.get("resumable") and task.downloaded_bytes > 0:
                        return False, "Tautan baru tidak mendukung kelanjutan unduhan (Range request tidak didukung)."
                elif not info.get("resumable") and task.downloaded_bytes > 0:
                    return False, "Tautan baru tidak mendukung kelanjutan unduhan (Range request tidak didukung)."

                new_size = info.get("total_bytes", 0)
                if task.total_bytes > 0 and new_size > 0 and new_size != task.total_bytes:
                    return False, f"Ukuran file tidak cocok! File asli: {task.total_bytes} byte, Tautan baru: {new_size} byte."
            else:
                if not info.get("success", False) and not (".m3u8" in new_url.lower()):
                    return False, "Manifest stream baru tidak dapat diakses."

            with self.lock:
                task.url = new_url
                if new_headers:
                    task.headers = new_headers
                if info.get("headers"):
                    task.headers.update(info["headers"])

                # If HLS stream, purge stale inline playlist content and disk cache so fresh CDN tokens take effect
                if is_hls_task:
                    if task.headers:
                        task.headers.pop("m3u8_content", None)
                    try:
                        from .hls_downloader import HLSInspector
                        HLSInspector.cache_playlist(new_url, "")
                        import tempfile
                        cache_dir = os.path.join(tempfile.gettempdir(), f"zero_hls_{task.id}")
                        cached_pl = os.path.join(cache_dir, "playlist.m3u8")
                        if os.path.exists(cached_pl):
                            os.remove(cached_pl)
                    except Exception:
                        pass
                
                # Clear previous error state
                if task.status in [DownloadStatus.ERROR, DownloadStatus.PAUSED]:
                    task.status = DownloadStatus.PAUSED
                    task.error_message = ""

                self.db.save_task(task)

            if self.on_task_updated:
                self.on_task_updated(task)

            if auto_start:
                try:
                    self.start_download(task_id)
                except Exception as e:
                    print(f"[DownloadEngine] Error auto-starting refreshed task {task_id}: {e}")

            return True, "Alamat unduhan berhasil diperbarui dan unduhan langsung dilanjutkan."
        except Exception as e:
            return False, f"Failed to probe new URL: {str(e)}"

    def _speed_monitor_loop(self):
        while self._monitor_running:
            time.sleep(1.0)
            with self.lock:
                for task_id, task in list(self.tasks.items()):
                    if task.status == DownloadStatus.DOWNLOADING:
                        # Skip HLS and Torrent tasks: they manage their own smoothed speed and ETA callbacks
                        if task_id in self.hls_workers or task_id in self.torrent_workers:
                            continue

                        bytes_list = self._speed_tracker.pop(task_id, [])
                        total_sec = sum(bytes_list)
                        task.speed = float(total_sec)
                        
                        remaining = max(0, task.total_bytes - task.downloaded_bytes)
                        if task.speed > 0 and task.total_bytes > 0:
                            task.eta = remaining / task.speed
                        else:
                            task.eta = 0.0
                        
                        self.db.save_task(task)
                        if self.on_task_updated:
                            self.on_task_updated(task)


class DownloadWorker(QObject):
    progress_updated = pyqtSignal(object)
    segment_progress = pyqtSignal(str, int, int, int)  # task_id, seg_idx, downloaded, total
    task_completed = pyqtSignal(str)                   # task_id
    task_failed = pyqtSignal(str, str)                 # task_id, error

    def __init__(self, task: DownloadTask, speed_limiter: Optional[Any] = None, parent=None):
        super().__init__(parent)
        self.task = task
        if isinstance(speed_limiter, SpeedLimiter):
            self.speed_limiter = speed_limiter
        elif isinstance(speed_limiter, (int, float)) and speed_limiter > 0:
            self.speed_limiter = SpeedLimiter(int(speed_limiter))
        else:
            self.speed_limiter = SpeedLimiter(0)

        self._thread = None
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancel_event = threading.Event()
        self._segment_workers: List[SegmentWorker] = []
        self._lock = threading.Lock()
        self._last_sample_time = time.time()
        self._last_sample_bytes = 0

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def wait(self, timeout_ms: Optional[int] = None):
        if self._thread:
            timeout_sec = (timeout_ms / 1000.0) if timeout_ms is not None and timeout_ms > 0 else None
            self._thread.join(timeout=timeout_sec)

    def pause(self):
        self._pause_event.clear()
        self.task.status = DownloadStatus.PAUSED

    def resume(self):
        self._pause_event.set()
        self.task.status = DownloadStatus.DOWNLOADING

    def cancel(self):
        self._cancel_event.set()
        self._pause_event.set()
        self.task.status = DownloadStatus.CANCELED

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self):
        try:
            dest_path = self.task.save_path
            if os.path.isdir(dest_path):
                dest_path = os.path.join(dest_path, self.task.filename)
                self.task.save_path = dest_path
            
            parent_dir = os.path.dirname(os.path.abspath(dest_path))
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            req_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Range": "bytes=0-0"
            }
            if self.task.headers:
                req_headers.update(self.task.headers)

            if self.task.total_bytes <= 0:
                try:
                    req = urllib.request.Request(self.task.url, headers=req_headers)
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        cr = resp.headers.get("Content-Range")
                        if cr and "/" in cr:
                            self.task.total_bytes = int(cr.split("/")[-1])
                            self.task.resumable = True
                        elif resp.headers.get("Content-Length"):
                            self.task.total_bytes = int(resp.headers.get("Content-Length"))
                            self.task.resumable = (resp.status == 206 or resp.headers.get("Accept-Ranges") == "bytes")
                except Exception:
                    try:
                        req2 = urllib.request.Request(self.task.url, headers={"User-Agent": req_headers["User-Agent"]})
                        with urllib.request.urlopen(req2, timeout=10) as resp2:
                            if resp2.headers.get("Content-Length"):
                                self.task.total_bytes = int(resp2.headers.get("Content-Length"))
                    except Exception:
                        pass

            num_conns = self.task.connections_count or self.task.connections or 4
            if not self.task.resumable or self.task.total_bytes <= 0:
                num_conns = 1

            if not self.task.segments:
                from .segment import SegmentManager
                self.task.segments = SegmentManager.create_segments(self.task.total_bytes, num_conns)

            # Pre-allocate file if total_bytes > 0
            if self.task.total_bytes > 0:
                with open(dest_path, "r+b" if os.path.exists(dest_path) else "wb") as f:
                    f.seek(self.task.total_bytes - 1)
                    f.write(b"\0")
            elif not os.path.exists(dest_path):
                with open(dest_path, "wb") as f:
                    pass

            finished_count = 0
            total_segments = len(self.task.segments)
            completed_lock = threading.Lock()
            finished_event = threading.Event()
            has_error = []

            def on_bytes(b_len: int):
                with self._lock:
                    self.task.downloaded_bytes += b_len
                    now = time.time()
                    dt = now - self._last_sample_time
                    if dt >= 0.2:
                        diff = self.task.downloaded_bytes - self._last_sample_bytes
                        self.task.speed = max(0.0, diff / dt)
                        remaining = max(0, self.task.total_bytes - self.task.downloaded_bytes)
                        self.task.eta = int(remaining / self.task.speed) if self.task.speed > 0 else 0
                        self._last_sample_time = now
                        self._last_sample_bytes = self.task.downloaded_bytes
                self.progress_updated.emit(self.task)

            def on_seg_finished(idx: int, success: bool, err_msg: Optional[str]):
                nonlocal finished_count
                with completed_lock:
                    finished_count += 1
                    if not success and err_msg and err_msg not in ("Canceled", "Paused"):
                        has_error.append(err_msg)
                    if finished_count >= total_segments:
                        finished_event.set()

            self.task.status = DownloadStatus.DOWNLOADING
            self._segment_workers = []

            for seg in self.task.segments:
                sw = SegmentWorker(
                    url=self.task.url,
                    target_path=dest_path,
                    segment=seg,
                    speed_limiter=self.speed_limiter,
                    pause_event=self._pause_event,
                    cancel_event=self._cancel_event,
                    on_bytes_received=on_bytes,
                    on_finished=on_seg_finished,
                    headers=self.task.headers,
                    proxy=self.task.proxy
                )
                self._segment_workers.append(sw)
                sw.start()

            finished_event.wait()

            if self._cancel_event.is_set():
                self.task.status = DownloadStatus.CANCELED
            elif has_error:
                self.task.status = DownloadStatus.ERROR
                self.task.error_message = has_error[0]
                self.task_failed.emit(self.task.id, has_error[0])
            else:
                self.task.status = DownloadStatus.COMPLETED
                if self.task.total_bytes > 0:
                    self.task.downloaded_bytes = self.task.total_bytes
                elif os.path.exists(dest_path):
                    self.task.total_bytes = os.path.getsize(dest_path)
                    self.task.downloaded_bytes = self.task.total_bytes
                self.progress_updated.emit(self.task)
                self.task_completed.emit(self.task.id)

        except Exception as e:
            self.task.status = DownloadStatus.ERROR
            self.task.error_message = str(e)
            self.task_failed.emit(self.task.id, str(e))