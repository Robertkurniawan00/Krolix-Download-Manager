"""
Zero Download Assistant - SQLite Persistence Layer
"""

import os
import sqlite3
import json
import threading
from contextlib import contextmanager
from typing import List, Dict, Optional, Any
from .models import DownloadTask, DownloadStatus, SegmentModel

DATA_DIR = os.path.join(os.path.expanduser("~"), ".zero_download")
os.makedirs(DATA_DIR, exist_ok=True)
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "downloads.db")


class Database:
    _instance = None
    _singleton_lock = threading.Lock()

    @classmethod
    def get_instance(cls, db_path: str = None):
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = Database(db_path)
            return cls._instance

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        try:
            with self._lock:
                with conn:
                    yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.execute("PRAGMA busy_timeout=30000;")
            except Exception:
                pass
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    save_path TEXT NOT NULL,
                    total_bytes INTEGER,
                    downloaded_bytes INTEGER,
                    status TEXT,
                    category TEXT,
                    connections INTEGER,
                    resumable INTEGER,
                    created_at REAL,
                    completed_at REAL,
                    error_message TEXT,
                    segments_json TEXT,
                    headers_json TEXT,
                    proxy TEXT,
                    checksum TEXT,
                    checksum_type TEXT,
                    auto_extract INTEGER,
                    post_action TEXT,
                    queue_order INTEGER,
                    priority INTEGER,
                    queue_name TEXT DEFAULT 'Main Queue',
                    is_torrent INTEGER DEFAULT 0,
                    description TEXT DEFAULT ''
                )
            """)
            try:
                cursor.execute("ALTER TABLE downloads ADD COLUMN description TEXT DEFAULT ''")
            except Exception:
                pass
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS site_credentials (
                    domain TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    start_time TEXT,
                    stop_time TEXT,
                    speed_limit_kbps INTEGER DEFAULT 0,
                    action_on_complete TEXT DEFAULT 'none'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS download_queues (
                    name TEXT PRIMARY KEY,
                    max_active INTEGER DEFAULT 1,
                    is_running INTEGER DEFAULT 0
                )
            """)
            cursor.execute("INSERT OR IGNORE INTO download_queues (name, max_active, is_running) VALUES ('Main Queue', 1, 0)")

            # Proxies table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proxies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'http',
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT,
                    password TEXT,
                    is_global INTEGER DEFAULT 0,
                    last_latency_ms INTEGER DEFAULT -1
                )
            """)

            # Seeder sessions leaderboard
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS seeder_sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    info_hash TEXT,
                    total_bytes_reported INTEGER DEFAULT 0,
                    duration_s REAL DEFAULT 0,
                    started_at REAL,
                    completed_at REAL
                )
            """)

            # Live stream watchlist & auto-recorder
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stream_watchlist (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    platform TEXT DEFAULT 'auto',
                    enabled INTEGER DEFAULT 1,
                    auto_record INTEGER DEFAULT 1,
                    quality_pref TEXT DEFAULT 'best',
                    save_dir TEXT DEFAULT '',
                    check_interval_sec INTEGER DEFAULT 60,
                    status TEXT DEFAULT 'Offline',
                    last_checked REAL DEFAULT 0,
                    last_recorded REAL DEFAULT 0,
                    active_task_id TEXT DEFAULT '',
                    record_count INTEGER DEFAULT 0,
                    last_error TEXT DEFAULT '',
                    created_at REAL DEFAULT 0
                )
            """)

            conn.commit()


    def save_task(self, task: DownloadTask):
        segments_data = [
            {
                "index": s.index,
                "start_byte": s.start_byte,
                "end_byte": s.end_byte,
                "downloaded_bytes": s.downloaded_bytes,
                "status": s.status
            }
            for s in task.segments
        ]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO downloads (
                    id, url, filename, save_path, total_bytes, downloaded_bytes,
                    status, category, connections, resumable, created_at,
                    completed_at, error_message, segments_json,
                    headers_json, proxy, checksum, checksum_type,
                    auto_extract, post_action, queue_order, priority, queue_name, is_torrent,
                    description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.url, task.filename, task.save_path,
                task.total_bytes, task.downloaded_bytes,
                task.status.value if hasattr(task.status, 'value') else str(task.status),
                task.category, task.connections, 1 if task.resumable else 0,
                task.created_at, task.completed_at, task.error_message,
                json.dumps(segments_data),
                json.dumps(task.headers) if task.headers else None,
                task.proxy, task.checksum, task.checksum_type,
                1 if task.auto_extract else 0, task.post_action,
                task.queue_order, task.priority, getattr(task, "queue_name", "Main Queue"),
                1 if getattr(task, "is_torrent", False) else 0,
                getattr(task, "description", "") or ""
            ))
            conn.commit()

    def get_all_tasks(self) -> List[DownloadTask]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM downloads ORDER BY queue_order ASC, created_at DESC")
            rows = cursor.fetchall()
            tasks = []
            for r in rows:
                segments = []
                if len(r) > 13 and r[13]:
                    try:
                        for s_data in json.loads(r[13]):
                            segments.append(SegmentModel(
                                index=s_data["index"],
                                start_byte=s_data["start_byte"],
                                end_byte=s_data["end_byte"],
                                downloaded_bytes=s_data.get("downloaded_bytes", 0),
                                status=s_data.get("status", "Idle")
                            ))
                    except Exception:
                        pass
                
                headers = {}
                if len(r) > 14 and r[14]:
                    try:
                        headers = json.loads(r[14])
                    except Exception:
                        headers = {}

                task = DownloadTask(
                    id=r[0],
                    url=r[1],
                    filename=r[2],
                    save_path=r[3],
                    total_bytes=r[4],
                    downloaded_bytes=r[5],
                    status=DownloadStatus(r[6]) if r[6] in [s.value for s in DownloadStatus] else DownloadStatus.QUEUED,
                    category=r[7],
                    connections=r[8],
                    resumable=bool(r[9]),
                    created_at=r[10],
                    completed_at=r[11],
                    error_message=r[12] or "",
                    segments=segments,
                    headers=headers,
                    proxy=r[15] if len(r) > 15 else None,
                    checksum=r[16] if len(r) > 16 else None,
                    checksum_type=r[17] if len(r) > 17 and r[17] else "SHA-256",
                    auto_extract=bool(r[18]) if len(r) > 18 and r[18] else False,
                    post_action=r[19] if len(r) > 19 and r[19] else "none",
                    queue_order=r[20] if len(r) > 20 and r[20] is not None else 0,
                    priority=r[21] if len(r) > 21 and r[21] is not None else 0,
                    queue_name=r[22] if len(r) > 22 and r[22] else "Main Queue",
                    is_torrent=bool(r[23]) if len(r) > 23 and r[23] is not None else (str(r[1]).startswith("magnet:") or str(r[1]).lower().endswith(".torrent")),
                    description=r[24] if len(r) > 24 and r[24] is not None else ""
                )
                tasks.append(task)
            return tasks

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM downloads WHERE id = ?", (task_id,))
            r = cursor.fetchone()
            if not r:
                return None
            segments = []
            if len(r) > 13 and r[13]:
                try:
                    for s_data in json.loads(r[13]):
                        segments.append(SegmentModel(
                            index=s_data["index"],
                            start_byte=s_data["start_byte"],
                            end_byte=s_data["end_byte"],
                            downloaded_bytes=s_data.get("downloaded_bytes", 0),
                            status=s_data.get("status", "Idle")
                        ))
                except Exception:
                    pass
            
            headers = {}
            if len(r) > 14 and r[14]:
                try:
                    headers = json.loads(r[14])
                except Exception:
                    headers = {}

            return DownloadTask(
                id=r[0],
                url=r[1],
                filename=r[2],
                save_path=r[3],
                total_bytes=r[4],
                downloaded_bytes=r[5],
                status=DownloadStatus(r[6]) if r[6] in [s.value for s in DownloadStatus] else DownloadStatus.QUEUED,
                category=r[7],
                connections=r[8],
                resumable=bool(r[9]),
                created_at=r[10],
                completed_at=r[11],
                error_message=r[12] or "",
                segments=segments,
                headers=headers,
                proxy=r[15] if len(r) > 15 else None,
                checksum=r[16] if len(r) > 16 else None,
                checksum_type=r[17] if len(r) > 17 and r[17] else "SHA-256",
                auto_extract=bool(r[18]) if len(r) > 18 and r[18] else False,
                post_action=r[19] if len(r) > 19 and r[19] else "none",
                queue_order=r[20] if len(r) > 20 and r[20] is not None else 0,
                priority=r[21] if len(r) > 21 and r[21] is not None else 0,
                queue_name=r[22] if len(r) > 22 and r[22] else "Main Queue",
                is_torrent=bool(r[23]) if len(r) > 23 and r[23] is not None else (str(r[1]).startswith("magnet:") or str(r[1]).lower().endswith(".torrent")),
                description=r[24] if len(r) > 24 and r[24] is not None else ""
            )

    def update_task(self, task: DownloadTask):
        self.save_task(task)

    def delete_task(self, task_id: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM downloads WHERE id = ?", (task_id,))
            conn.commit()

    # --- Queue Database Methods ---
    def get_queues(self) -> List[Dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, max_active, is_running FROM download_queues ORDER BY name ASC")
            return [{"name": r[0], "max_active": r[1], "is_running": bool(r[2])} for r in cursor.fetchall()]

    def add_queue(self, name: str, max_active: int = 1):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO download_queues (name, max_active, is_running) VALUES (?, ?, 0)", (name.strip(), max_active))
            conn.commit()

    def set_queue_state(self, name: str, is_running: bool):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE download_queues SET is_running = ? WHERE name = ?", (1 if is_running else 0, name))
            conn.commit()

    def delete_queue(self, name: str):
        if name == "Main Queue":
            return
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM download_queues WHERE name = ?", (name,))
            cursor.execute("UPDATE downloads SET queue_name = 'Main Queue' WHERE queue_name = ?", (name,))
            conn.commit()


    def get_setting(self, key: str, default: Any = "") -> Any:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row is None:
                return default
            val = row[0]
            if isinstance(default, bool):
                return str(val).lower() in ("true", "1", "yes")
            if isinstance(default, int):
                try:
                    return int(val)
                except ValueError:
                    return default
            if isinstance(default, float):
                try:
                    return float(val)
                except ValueError:
                    return default
            return val

    def set_setting(self, key: str, value: Any):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()

    def is_torrent_enabled(self) -> bool:
        return self.get_setting("enable_torrent", False)

    # --- Site Credentials Manager ---
    def save_credential(self, domain: str, username: str, password: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO site_credentials (domain, username, password) VALUES (?, ?, ?)",
                           (domain.lower().strip(), username.strip(), password.strip()))
            conn.commit()

    def get_credential(self, domain: str) -> Optional[tuple]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, password FROM site_credentials WHERE domain = ?", (domain.lower().strip(),))
            return cursor.fetchone()

    def get_all_credentials(self) -> List[Dict[str, str]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT domain, username, password FROM site_credentials ORDER BY domain ASC")
            return [{"domain": r[0], "username": r[1], "password": r[2]} for r in cursor.fetchall()]

    def delete_credential(self, domain: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM site_credentials WHERE domain = ?", (domain.lower().strip(),))
            conn.commit()

    # --- Schedules Manager ---
    def save_schedule(self, sched_id: str, name: str, enabled: bool, start_time: str, stop_time: str, speed_limit_kbps: int, action_on_complete: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO schedules (id, name, enabled, start_time, stop_time, speed_limit_kbps, action_on_complete)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (sched_id, name, 1 if enabled else 0, start_time, stop_time, speed_limit_kbps, action_on_complete))
            conn.commit()

    def get_schedules(self) -> List[Dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, enabled, start_time, stop_time, speed_limit_kbps, action_on_complete FROM schedules")
            return [
                {
                    "id": r[0], "name": r[1], "enabled": bool(r[2]),
                    "start_time": r[3], "stop_time": r[4],
                    "speed_limit_kbps": r[5], "action_on_complete": r[6]
                }
                for r in cursor.fetchall()
            ]

    def delete_schedule(self, sched_id: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM schedules WHERE id = ?", (sched_id,))
            conn.commit()

    # --- Duplicate Detection Lookups ---
    def get_tasks_by_url(self, url: str) -> List[DownloadTask]:
        """Return all tasks matching this exact URL (any non-cancelled status)."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, url, filename, save_path, status FROM downloads WHERE url = ? AND status NOT IN ('Canceled', 'Error')",
                (url,)
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                t = DownloadTask(id=r[0], url=r[1], filename=r[2], save_path=r[3] or "")
                t.status = DownloadStatus(r[4]) if r[4] in [s.value for s in DownloadStatus] else DownloadStatus.QUEUED
                results.append(t)
            return results

    def get_tasks_by_filename(self, filename: str) -> List[DownloadTask]:
        """Return all tasks matching this filename (any non-cancelled status)."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, url, filename, save_path, status FROM downloads WHERE filename = ? AND status NOT IN ('Canceled', 'Error')",
                (filename,)
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                t = DownloadTask(id=r[0], url=r[1], filename=r[2], save_path=r[3] or "")
                t.status = DownloadStatus(r[4]) if r[4] in [s.value for s in DownloadStatus] else DownloadStatus.QUEUED
                results.append(t)
            return results

    def get_task_by_hash(self, file_hash: str) -> Optional[DownloadTask]:
        """Return a completed task matching the given checksum if recorded."""
        if not file_hash:
            return None
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, url, filename, save_path, status FROM downloads WHERE checksum = ? AND status = 'Completed' LIMIT 1",
                (file_hash,)
            )
            r = cursor.fetchone()
            if not r:
                return None
            t = DownloadTask(id=r[0], url=r[1], filename=r[2], save_path=r[3] or "")
            t.status = DownloadStatus.COMPLETED
            return t

    # --- Proxy Manager ---
    def get_proxies(self) -> List[Dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, type, host, port, username, password, is_global, last_latency_ms FROM proxies ORDER BY name ASC")
            return [
                {"id": r[0], "name": r[1], "type": r[2], "host": r[3], "port": r[4],
                 "username": r[5] or "", "password": r[6] or "",
                 "is_global": bool(r[7]), "last_latency_ms": r[8]}
                for r in cursor.fetchall()
            ]

    def save_proxy(self, proxy: Dict) -> str:
        """Save or update a proxy entry. Returns the proxy id."""
        import uuid as _uuid
        proxy_id = proxy.get("id") or str(_uuid.uuid4())[:8]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO proxies (id, name, type, host, port, username, password, is_global, last_latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                proxy_id, proxy.get("name", "Proxy"), proxy.get("type", "http"),
                proxy.get("host", ""), int(proxy.get("port", 8080)),
                proxy.get("username", "") or None, proxy.get("password", "") or None,
                1 if proxy.get("is_global") else 0,
                int(proxy.get("last_latency_ms", -1))
            ))
            conn.commit()
        return proxy_id

    def delete_proxy(self, proxy_id: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
            conn.commit()

    def get_global_proxy(self) -> Optional[Dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, type, host, port, username, password FROM proxies WHERE is_global = 1 LIMIT 1")
            r = cursor.fetchone()
            if not r:
                return None
            return {"id": r[0], "name": r[1], "type": r[2], "host": r[3], "port": r[4],
                    "username": r[5] or "", "password": r[6] or ""}

    def set_global_proxy(self, proxy_id: Optional[str]):
        """Set a proxy as global (or clear all global proxies if proxy_id is None)."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE proxies SET is_global = 0")
            if proxy_id:
                cursor.execute("UPDATE proxies SET is_global = 1 WHERE id = ?", (proxy_id,))
            conn.commit()

    def update_proxy_latency(self, proxy_id: str, latency_ms: int):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE proxies SET last_latency_ms = ? WHERE id = ?", (latency_ms, proxy_id))
            conn.commit()

    # --- Seeder Sessions Leaderboard ---
    def record_seeder_session(self, session_id: str, name: str, info_hash: str,
                               total_bytes_reported: int, duration_s: float,
                               started_at: float, completed_at: float):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO seeder_sessions
                (id, name, info_hash, total_bytes_reported, duration_s, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session_id, name, info_hash, total_bytes_reported, duration_s, started_at, completed_at))
            conn.commit()

    def get_seeder_leaderboard(self, limit: int = 50) -> List[Dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, info_hash, total_bytes_reported, duration_s, started_at, completed_at
                FROM seeder_sessions
                ORDER BY total_bytes_reported DESC
                LIMIT ?
            """, (limit,))
            return [
                {"id": r[0], "name": r[1], "info_hash": r[2] or "",
                 "total_bytes_reported": r[3], "duration_s": r[4],
                 "started_at": r[5], "completed_at": r[6]}
                for r in cursor.fetchall()
            ]

    def get_total_upload_credit(self) -> int:
        """Return all-time total bytes reported across all seeder sessions."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(total_bytes_reported) FROM seeder_sessions")
            r = cursor.fetchone()
            return int(r[0] or 0)

    # --- Live Stream Watchlist & Auto-Recorder ---
    def get_watchlist(self) -> List[Dict]:
        """Return all monitored live stream channels ordered by creation time."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, url, platform, enabled, auto_record, quality_pref,
                       save_dir, check_interval_sec, status, last_checked, last_recorded,
                       active_task_id, record_count, last_error, created_at
                FROM stream_watchlist
                ORDER BY created_at ASC, name ASC
            """)
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "url": r[2],
                    "platform": r[3] or "auto",
                    "enabled": bool(r[4]),
                    "auto_record": bool(r[5]),
                    "quality_pref": r[6] or "best",
                    "save_dir": r[7] or "",
                    "check_interval_sec": int(r[8] or 60),
                    "status": r[9] or "Offline",
                    "last_checked": float(r[10] or 0),
                    "last_recorded": float(r[11] or 0),
                    "active_task_id": r[12] or "",
                    "record_count": int(r[13] or 0),
                    "last_error": r[14] or "",
                    "created_at": float(r[15] or 0),
                }
                for r in cursor.fetchall()
            ]

    def get_watchlist_item(self, item_id: str) -> Optional[Dict]:
        """Fetch a single watchlist entry by ID."""
        for item in self.get_watchlist():
            if item["id"] == item_id:
                return item
        return None

    def save_watchlist_item(self, item: Dict) -> str:
        """Insert or update a live stream watchlist channel."""
        import uuid
        import time as _time
        item_id = item.get("id") or str(uuid.uuid4())[:12]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO stream_watchlist (
                    id, name, url, platform, enabled, auto_record, quality_pref,
                    save_dir, check_interval_sec, status, last_checked, last_recorded,
                    active_task_id, record_count, last_error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_id,
                item.get("name", "Stream"),
                item.get("url", ""),
                item.get("platform", "auto"),
                1 if item.get("enabled", True) else 0,
                1 if item.get("auto_record", True) else 0,
                item.get("quality_pref", "best"),
                item.get("save_dir", ""),
                max(15, int(item.get("check_interval_sec", 60))),
                item.get("status", "Offline"),
                float(item.get("last_checked", 0)),
                float(item.get("last_recorded", 0)),
                item.get("active_task_id", "") or "",
                int(item.get("record_count", 0)),
                item.get("last_error", "") or "",
                float(item.get("created_at") or _time.time()),
            ))
            conn.commit()
        return item_id

    def update_watchlist_state(
        self,
        item_id: str,
        status: Optional[str] = None,
        active_task_id: Optional[str] = None,
        last_checked: Optional[float] = None,
        last_recorded: Optional[float] = None,
        increment_count: bool = False,
        last_error: Optional[str] = None,
    ):
        """Update runtime status fields of a watchlist entry without overwriting user settings."""
        fields = []
        values = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if active_task_id is not None:
            fields.append("active_task_id = ?")
            values.append(active_task_id)
        if last_checked is not None:
            fields.append("last_checked = ?")
            values.append(float(last_checked))
        if last_recorded is not None:
            fields.append("last_recorded = ?")
            values.append(float(last_recorded))
        if increment_count:
            fields.append("record_count = COALESCE(record_count, 0) + 1")
        if last_error is not None:
            fields.append("last_error = ?")
            values.append(last_error)

        if not fields:
            return
        values.append(item_id)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE stream_watchlist SET {', '.join(fields)} WHERE id = ?", tuple(values))
            conn.commit()

    def delete_watchlist_item(self, item_id: str):
        """Delete a watchlist entry by ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stream_watchlist WHERE id = ?", (item_id,))
            conn.commit()
