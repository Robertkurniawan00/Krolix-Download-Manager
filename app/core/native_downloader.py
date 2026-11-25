"""
Zero Download Assistant - Native C# Turbo Core Downloader Worker
"""

import os
import sys
import time
import json
import subprocess
import threading
from PyQt6.QtCore import QObject, pyqtSignal
from .models import DownloadTask


class NativeDownloadWorker(QObject):
    progress_updated = pyqtSignal(str, int, int, float, int)  # task_id, downloaded, total, speed, eta
    segment_progress = pyqtSignal(str, int, int, int)          # task_id, seg_idx, downloaded, total
    task_completed = pyqtSignal(str)
    task_failed = pyqtSignal(str, str)

    _zero_core_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "core_bin", "ZeroCore.exe")

    @classmethod
    def is_available(cls) -> bool:
        return os.path.isfile(cls._zero_core_bin) and os.access(cls._zero_core_bin, os.X_OK)

    def __init__(self, task: DownloadTask, speed_limit_bps: int = 0, parent=None):
        super().__init__(parent)
        self.task = task
        self.speed_limit_bps = speed_limit_bps
        self._thread = None
        self._proc = None
        self._is_paused = False
        self._is_cancelled = False

    def start(self):
        self._thread = threading.Thread(target=self._run_download, daemon=True)
        self._thread.start()

    def pause(self):
        self._is_paused = True
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def cancel(self):
        self._is_cancelled = True
        if self._proc:
            try:
                self._proc.kill()
            except Exception:
                pass

    def _run_download(self):
        dest_file = self.task.save_path
        if os.path.isdir(dest_file):
            dest_file = os.path.join(dest_file, self.task.filename)
            self.task.save_path = dest_file

        parent_dir = os.path.dirname(os.path.abspath(dest_file))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        cmd = [
            self._zero_core_bin,
            "--url", self.task.url,
            "--file", dest_file,
            "--connections", str(self.task.connections_count or 8),
            "--json"
        ]
        if self.speed_limit_bps > 0:
            cmd.extend(["--limit", str(self.speed_limit_bps)])

        try:
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE

            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                startupinfo=startupinfo
            )

            for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except Exception:
                    continue

                event = data.get("event")
                if event == "init":
                    total = data.get("total", 0)
                    if total > 0:
                        self.task.total_bytes = total
                    self.task.is_resumable = data.get("resumable", True)

                elif event == "progress":
                    downloaded = data.get("downloaded", 0)
                    total = data.get("total", self.task.total_bytes)
                    speed = float(data.get("speed", 0.0))
                    eta = int(data.get("eta", 0))

                    self.task.downloaded_bytes = downloaded
                    self.task.total_bytes = total
                    self.task.speed = speed
                    self.task.eta = eta

                    self.progress_updated.emit(self.task.id, downloaded, total, speed, eta)

                    # Sub-segment breakdown
                    for seg_dict in data.get("segments", []):
                        s_idx = seg_dict.get("index", 0)
                        s_down = seg_dict.get("downloaded", 0)
                        s_tot = seg_dict.get("total", 0)
                        self.segment_progress.emit(self.task.id, s_idx, s_down, s_tot)

                elif event == "completed":
                    self.task.status = 'completed'
                    self.task.completed_at = time.time()
                    self.task_completed.emit(self.task.id)

                elif event == "error":
                    err_msg = data.get("message", "Terjadi kesalahan unduhan")
                    if not self._is_paused and not self._is_cancelled:
                        self.task.status = 'error'
                        self.task.error_message = err_msg
                        self.task_failed.emit(self.task.id, err_msg)

            self._proc.wait()

            if self._is_paused or self._is_cancelled:
                return

            if self._proc.returncode != 0 and self.task.status != 'completed':
                if not self.task.error_message:
                    self.task.status = 'error'
                    self.task_failed.emit(self.task.id, f"ZeroCore berhenti dengan kode {self._proc.returncode}")

        except Exception as e:
            if not self._is_paused and not self._is_cancelled:
                self.task.status = 'error'
                self.task_failed.emit(self.task.id, str(e))
