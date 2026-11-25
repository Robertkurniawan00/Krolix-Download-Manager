"""
Zero Download Assistant - C++ (aria2c) Engine Adapter
Harnesses the high-throughput C++ multi-connection aria2c binary.
"""

import os
import re
import sys
import time
import subprocess
import threading
from PyQt6.QtCore import QObject, pyqtSignal

from .models import DownloadTask

class Aria2Worker(QObject):
    progress_updated = pyqtSignal(str, int, int, float, int) # task_id, downloaded, total, speed, eta
    segment_progress = pyqtSignal(str, int, int, int)         # task_id, seg_idx, downloaded, total
    task_completed = pyqtSignal(str)
    task_failed = pyqtSignal(str, str)

    def __init__(self, task: DownloadTask, parent=None):
        super().__init__(parent)
        self.task = task
        self._proc = None
        self._thread = None
        self._is_paused = False
        self._is_cancelled = False
        self._aria2_bin = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "assets", "bin", "aria2c.exe")
        )

    def is_available(self) -> bool:
        return os.path.exists(self._aria2_bin)

    def start(self):
        self._is_paused = False
        self._is_cancelled = False
        self.task.status = 'downloading'
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def wait(self, timeout_ms: int = None):
        if self._thread and self._thread.is_alive():
            timeout_sec = (timeout_ms / 1000.0) if timeout_ms is not None else None
            self._thread.join(timeout=timeout_sec)

    def pause(self):
        self._is_paused = True
        self.task.status = 'paused'
        self._terminate()

    def cancel(self):
        self._is_cancelled = True
        self.task.status = 'canceled'
        self._terminate()

    def _terminate(self):
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _run(self):
        if not self.is_available():
            self.task.status = 'error'
            self.task_failed.emit(self.task.id, "aria2c.exe tidak ditemukan di folder assets/bin")
            return

        dest_dir = self.task.save_path if os.path.isdir(self.task.save_path) else os.path.dirname(os.path.abspath(self.task.save_path))
        dest_filename = self.task.filename or os.path.basename(self.task.save_path)
        os.makedirs(dest_dir, exist_ok=True)

        cmd = [
            self._aria2_bin,
            f"--dir={dest_dir}",
            f"--out={dest_filename}",
            f"--max-connection-per-server={self.task.connections_count or 16}",
            f"--split={self.task.connections_count or 16}",
            "--min-split-size=1M",
            "--summary-interval=1",
            "--file-allocation=trunc",
            "--allow-overwrite=true",
            "--auto-file-renaming=false",
            "--no-want-digest-header=true",
            self.task.url
        ]

        try:
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0 # SW_HIDE

            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                startupinfo=startupinfo
            )

            # Regex for aria2 progress line: [#6f8272 2.3MiB/10MiB(23%) CN:8 DL:1.2MiB ETA:6s]
            prog_re = re.compile(r'\[#\w+\s+([\d\.]+)([A-Za-z]+)/([\d\.]+)([A-Za-z]+)\((\d+)%\)\s+CN:(\d+)\s+DL:([\d\.]+)([A-Za-z]+)(?:\s+ETA:(\d+m?\d*s))?\]')

            for line in self._proc.stdout:
                if self._is_paused or self._is_cancelled:
                    break

                match = prog_re.search(line)
                if match:
                    d_val, d_unit, t_val, t_unit, pct, cn, sp_val, sp_unit, eta_str = match.groups()
                    downloaded = self._to_bytes(float(d_val), d_unit)
                    total = self._to_bytes(float(t_val), t_unit)
                    speed = self._to_bytes(float(sp_val), sp_unit)
                    eta = self._parse_eta(eta_str) if eta_str else 0

                    self.task.downloaded_bytes = downloaded
                    self.task.total_bytes = total
                    self.task.speed = speed
                    self.task.eta = eta

                    self.progress_updated.emit(self.task.id, downloaded, total, speed, eta)

            self._proc.wait()

            if self._is_paused:
                return

            if self._is_cancelled:
                self.task_failed.emit(self.task.id, "Unduhan dibatalkan")
                return

            if self._proc.returncode == 0:
                self.task.status = 'completed'
                self.task.completed_at = time.time()
                self.task_completed.emit(self.task.id)
            else:
                self.task.status = 'error'
                self.task_failed.emit(self.task.id, f"aria2c gagal dengan kode {self._proc.returncode}")

        except Exception as e:
            self.task.status = 'error'
            self.task_failed.emit(self.task.id, str(e))

    def _to_bytes(self, val: float, unit: str) -> int:
        unit = unit.upper()
        multipliers = {'B': 1, 'KIB': 1024, 'KB': 1000, 'MIB': 1048576, 'MB': 1000000, 'GIB': 1073741824, 'GB': 1000000000}
        return int(val * multipliers.get(unit, 1024))

    def _parse_eta(self, s: str) -> int:
        total_sec = 0
        if 'm' in s:
            parts = s.split('m')
            total_sec += int(parts[0]) * 60
            s = parts[1]
        if 's' in s:
            total_sec += int(s.replace('s', ''))
        return total_sec