import time
import threading
from datetime import datetime
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
        self.max_concurrent_active = int(self.db.get_setting("max_concurrent_downloads", "2"))
        
        self.auto_shutdown_enabled = False
        self.auto_shutdown_action = "shutdown"

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
            except Exception as e:
                pass
            time.sleep(2.0)

    def _check_time_schedules(self):
        schedules = self.db.get_schedules()
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")

        for sched in schedules:
            if not sched["enabled"]:
                continue

            start_t = sched.get("start_time")
            stop_t = sched.get("stop_time")
            speed_limit = sched.get("speed_limit_kbps", 0)

            # Bandwidth profile adjustment
            if speed_limit > 0:
                if start_t and stop_t:
                    if start_t <= stop_t:
                        in_range = (start_t <= current_time_str <= stop_t)
                    else:
                        in_range = (current_time_str >= start_t or current_time_str <= stop_t)

                    if in_range:
                        self.speed_limiter.set_limit(speed_limit * 1024)
                    else:
                        global_limit = int(self.db.get_setting("speed_limit_kbps", "0"))
                        self.speed_limiter.set_limit(global_limit * 1024)

    def _manage_queue(self):
        """Sequences queued downloads up to max_concurrent_active."""
        tasks = list(self.engine.tasks.values())
        active_count = sum(1 for t in tasks if t.status in [DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING])

        # If all downloads are finished and auto_shutdown is on
        if self.auto_shutdown_enabled and active_count == 0:
            queued_or_connecting = [t for t in tasks if t.status in [DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING]]
            if len(queued_or_connecting) == 0 and len(tasks) > 0:
                self.auto_shutdown_enabled = False
                PostActionManager.execute(self.auto_shutdown_action)
                return

        # Start queued tasks up to limit
        if active_count < self.max_concurrent_active:
            queued_tasks = [t for t in tasks if t.status == DownloadStatus.QUEUED]
            queued_tasks.sort(key=lambda t: (t.queue_order, t.created_at))

            for task in queued_tasks:
                if active_count >= self.max_concurrent_active:
                    break
                self.engine.start_download(task.id)
                active_count += 1
