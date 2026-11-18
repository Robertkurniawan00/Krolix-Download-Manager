"""
Zero Download Assistant - Queue & Concurrency Manager
"""

import os
from PyQt6.QtCore import QObject, pyqtSignal
from .models import DownloadTask, DownloadStatus
from .downloader import DownloadWorker
from .native_downloader import NativeDownloadWorker
from .aria2_downloader import Aria2Worker
from .speed_limiter import SpeedLimiter
from .database import Database
from ..utils.win32_native import Win32Native

class QueueManager(QObject):
    task_added = pyqtSignal(DownloadTask)
    task_progress = pyqtSignal(str, int, int, float, int)
    segment_progress = pyqtSignal(str, int, int, int)
    task_status_changed = pyqtSignal(str, str) # task_id, status

    def __init__(self, engine=None, db=None, parent=None):
        if isinstance(engine, QObject) and db is None and parent is None:
            parent = engine
            engine = None
        super().__init__(parent)
        self.engine = engine
        self.db = db or (Database.get_instance() if hasattr(Database, 'get_instance') else Database())
        self.speed_limiter = getattr(engine, 'speed_limiter', None) or SpeedLimiter(0)
        self.workers = {} # task_id -> Worker
        self.tasks = {}   # task_id -> DownloadTask
        self.max_concurrent = 3
        self.is_queue_running = True
        self.load_tasks_from_db()

    def start_queue(self, queue_name: str = "Main Queue"):
        if self.engine:
            for tid, t in list(self.engine.tasks.items()):
                if t.status in [DownloadStatus.QUEUED, DownloadStatus.PAUSED]:
                    self.engine.start_download(tid)
        else:
            self.resume_all()

    def stop_queue(self, queue_name: str = "Main Queue"):
        if self.engine:
            for tid, t in list(self.engine.tasks.items()):
                if t.status == DownloadStatus.DOWNLOADING:
                    self.engine.pause_download(tid)
        else:
            self.pause_all()

    def load_tasks_from_db(self):
        saved = self.db.get_all_tasks()
        for t in saved:
            if t.status == 'downloading':
                t.status = 'paused'
            self.tasks[t.id] = t

    def add_download(self, url: str, filename: str, save_path: str, category: str = 'documents', auto_start: bool = True) -> DownloadTask:
        task = DownloadTask(url, filename, save_path)
        task.category = category
        self.tasks[task.id] = task
        self.db.save_task(task)
        self.task_added.emit(task)
        
        if auto_start:
            self.start_task(task.id)
        return task

    def start_task(self, task_id: str):
        if task_id not in self.tasks:
            return
        task = self.tasks[task_id]
        
        # Don't exceed concurrency
        active_count = sum(1 for t in self.tasks.values() if t.status == 'downloading')
        if active_count >= self.max_concurrent:
            task.status = 'queued'
            self.db.save_task(task)
            self.task_status_changed.emit(task.id, 'queued')
            return

        # Engine selection: C# Turbo (Default) -> C++ aria2 -> Python Fallback
        engine_type = self.db.get_setting('engine', 'turbo')

        if engine_type == 'turbo' and NativeDownloadWorker.is_available():
            worker = NativeDownloadWorker(task, self.speed_limiter.max_bytes_per_sec, self)
        elif engine_type == 'aria2' and Aria2Worker(task).is_available():
            worker = Aria2Worker(task, self)
        else:
            worker = DownloadWorker(task, self.speed_limiter, self)

        worker.progress_updated.connect(self._on_worker_progress)
        worker.segment_progress.connect(self.segment_progress.emit)
        worker.task_completed.connect(self._on_worker_completed)
        worker.task_failed.connect(self._on_worker_failed)
        
        self.workers[task_id] = worker
        worker.start()
        self.task_status_changed.emit(task.id, 'downloading')
        self.db.save_task(task)
        
        # Prevent Windows PC from sleeping during active downloads
        Win32Native.prevent_sleep(True)

    def pause_task(self, task_id: str):
        if task_id in self.workers:
            self.workers[task_id].pause()
            del self.workers[task_id]
        if task_id in self.tasks:
            self.tasks[task_id].status = 'paused'
            self.tasks[task_id].speed = 0.0
            self.db.save_task(self.tasks[task_id])
            self.task_status_changed.emit(task_id, 'paused')
        self._check_queue()

    def resume_task(self, task_id: str):
        self.start_task(task_id)

    def pause_all(self):
        for tid in list(self.workers.keys()):
            self.pause_task(tid)

    def resume_all(self):
        for t in self.tasks.values():
            if t.status in ['paused', 'queued', 'error']:
                self.start_task(t.id)

    def delete_task(self, task_id: str, delete_file: bool = False):
        if task_id in self.workers:
            self.workers[task_id].cancel()
            del self.workers[task_id]
        
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if delete_file and os.path.exists(task.save_path):
                try:
                    os.remove(task.save_path)
                except Exception:
                    pass
            del self.tasks[task_id]
            self.db.delete_task(task_id)
            self.task_status_changed.emit(task_id, 'deleted')
        self._check_queue()

    def set_speed_limit_kbps(self, kbps: int):
        bps = kbps * 1024 if kbps > 0 else 0
        self.speed_limiter.set_limit(bps)

    def _on_worker_progress(self, *args):
        if len(args) == 1 and hasattr(args[0], 'id'):
            task = args[0]
            self.task_progress.emit(task.id, task.downloaded_bytes, task.total_bytes, getattr(task, 'speed', 0.0), getattr(task, 'eta', 0))
        elif len(args) >= 5:
            self.task_progress.emit(args[0], args[1], args[2], args[3], args[4])

    def _on_worker_completed(self, task_id):
        if task_id in self.workers:
            del self.workers[task_id]
        if task_id in self.tasks:
            t = self.tasks[task_id]
            t.status = 'completed'
            t.speed = 0.0
            self.db.save_task(t)
            self.task_status_changed.emit(task_id, 'completed')
        self._check_queue()

    def _on_worker_failed(self, task_id, err_msg):
        if task_id in self.workers:
            del self.workers[task_id]
        if task_id in self.tasks:
            t = self.tasks[task_id]
            t.status = 'error'
            t.error_message = err_msg
            t.speed = 0.0
            self.db.save_task(t)
            self.task_status_changed.emit(task_id, 'error')
        self._check_queue()

    def _check_queue(self):
        if not self.is_queue_running:
            return
        active_count = sum(1 for t in self.tasks.values() if t.status == 'downloading')
        if active_count == 0:
            Win32Native.prevent_sleep(False)

        slots = self.max_concurrent - active_count
        if slots > 0:
            for t in self.tasks.values():
                if t.status == 'queued':
                    self.start_task(t.id)
                    slots -= 1
                    if slots <= 0:
                        break