import time
import threading
from datetime import datetime
from typing import Optional
from .downloader import DownloadEngine
from .database import Database
from .models import DownloadStatus
from .speed_limiter import SpeedLimiter
from .post_actions import PostActionManager

class DownloadScheduler:
    def __init__(self, engine: DownloadEngine, db: Database, speed_limiter: SpeedLimiter):
        self.engine = engine
        self.db = db
        self.speed_limiter = speed_limiter
        self.running = True
        try:
            self.max_concurrent_active = max(1, int(self.db.get_setting("max_concurrent_downloads", "2") or "2"))
        except (ValueError, TypeError):
            self.max_concurrent_active = 2
        
        self.auto_shutdown_enabled = False
        self.auto_shutdown_action = "shutdown"
        self._last_applied_limit_bps: Optional[int] = None

        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()

    def set_max_concurrent(self, value: int):
        self.max_concurrent_active = max(1, value)
        self.db.set_setting("max_concurrent_downloads", str(self.max_concurrent_active))

    def _scheduler_loop(self):
        while self.running:
            try:
                self._check_time_schedules()
                self._manage_queue()
            except Exception:
                pass
            time.sleep(2.0)

    def _check_time_schedules(self):
        schedules = self.db.get_schedules()
        if not schedules:
            return
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")

        matched_limit_kbps: Optional[int] = None
        any_bw_schedule = False
        for sched in schedules:
            if not sched["enabled"]:
                continue

            start_t = sched.get("start_time")
            stop_t = sched.get("stop_time")
            speed_limit = sched.get("speed_limit_kbps", 0) or 0

            if speed_limit > 0 and start_t and stop_t:
                any_bw_schedule = True
                if start_t <= stop_t:
                    in_range = (start_t <= current_time_str <= stop_t)
                else:
                    in_range = (current_time_str >= start_t or current_time_str <= stop_t)

                if in_range:
                    matched_limit_kbps = speed_limit
                    break

        if not any_bw_schedule:
            return

        if matched_limit_kbps is not None:
            target_bps = matched_limit_kbps * 1024
        else:
            try:
                global_limit = int(self.db.get_setting("speed_limit_kbps", "0") or "0")
            except (ValueError, TypeError):
                global_limit = 0
            target_bps = max(0, global_limit * 1024)

        if self._last_applied_limit_bps != target_bps:
            self.speed_limiter.set_limit(target_bps)
            self._last_applied_limit_bps = target_bps

    def _manage_queue(self):
        """Sequences queued downloads up to max_concurrent_active."""
        with self.engine.lock:
            tasks = list(self.engine.tasks.values())
        active_count = sum(1 for t in tasks if t.status in [DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING])

        # Only trigger post-completion action if no tasks are still downloading/connecting/queued/paused
        if self.auto_shutdown_enabled and active_count == 0:
            incomplete = [t for t in tasks if t.status in [DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING, DownloadStatus.PAUSED]]
            if len(incomplete) == 0 and len(tasks) > 0:
                self.auto_shutdown_enabled = False
                PostActionManager.execute(self.auto_shutdown_action)
                return

        # Start queued tasks only if not previously rejected by concurrency license cap
        if active_count < self.max_concurrent_active:
            queued_tasks = [t for t in tasks if t.status == DownloadStatus.QUEUED and not (t.error_message and "Versi Terbatas" in t.error_message)]
            queued_tasks.sort(key=lambda t: (t.queue_order, t.created_at))

            for task in queued_tasks:
                if active_count >= self.max_concurrent_active:
                    break
                self.engine.start_download(task.id)
                if task.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING):
                    active_count += 1
