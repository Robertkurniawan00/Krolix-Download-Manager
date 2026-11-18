"""
Zero Download Assistant - Task Models & Data Types
"""

import time
import uuid
from enum import Enum
from typing import Any, Optional


class DownloadStatus(str, Enum):
    QUEUED = "Queued"
    CONNECTING = "Connecting"
    DOWNLOADING = "Downloading"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    CANCELED = "Canceled"
    ERROR = "Error"

    def __eq__(self, other):
        if isinstance(other, DownloadStatus):
            return self.value == other.value
        if isinstance(other, str):
            return self.value.lower() == other.lower()
        return False

    def __hash__(self):
        return hash(self.value)


class SegmentModel:
    def __init__(self, index: int = 0, start_byte: int = 0, end_byte: int = 0, downloaded_bytes: int = 0, status: str = "Idle"):
        self.index = index
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.downloaded_bytes = downloaded_bytes
        self.status = status
        self.is_finished = False
        self._custom_progress: Optional[float] = None

    @property
    def total_bytes(self) -> int:
        return max(0, self.end_byte - self.start_byte + 1)

    @property
    def progress_percent(self) -> float:
        if self._custom_progress is not None:
            return min(100.0, max(0.0, float(self._custom_progress) * 100.0))
        if self.total_bytes <= 0:
            return 100.0 if self.is_finished or self.status == "Completed" else 0.0
        return min(100.0, (self.downloaded_bytes / self.total_bytes) * 100.0)

    @property
    def progress(self) -> float:
        if self._custom_progress is not None:
            return min(1.0, max(0.0, float(self._custom_progress)))
        return self.progress_percent / 100.0

    @progress.setter
    def progress(self, value: Optional[float]):
        if value is None:
            self._custom_progress = None
        else:
            self._custom_progress = min(1.0, max(0.0, float(value)))

    def to_dict(self) -> dict:
        return {
            'index': self.index,
            'start_byte': self.start_byte,
            'end_byte': self.end_byte,
            'downloaded_bytes': self.downloaded_bytes,
            'status': self.status
        }

    @classmethod
    def from_dict(cls, data: dict):
        seg = cls(
            index=data.get('index', 0),
            start_byte=data.get('start_byte', 0),
            end_byte=data.get('end_byte', 0),
            downloaded_bytes=data.get('downloaded_bytes', 0),
            status=data.get('status', 'Idle')
        )
        seg.is_finished = data.get('is_finished', False)
        return seg


# Alias for backward compatibility
Segment = SegmentModel


class DownloadTask:
    def __init__(
        self,
        url: str = "",
        filename: str = "",
        save_path: str = "",
        id: str = None,
        task_id: str = None,
        total_bytes: int = 0,
        total_size: int = None,
        downloaded_bytes: int = 0,
        status: Any = DownloadStatus.QUEUED,
        category: str = "documents",
        connections: int = 8,
        connections_count: int = None,
        resumable: bool = True,
        is_resumable: bool = None,
        segments: list = None,
        headers: dict = None,
        proxy: str = None,
        checksum: str = None,
        checksum_type: str = "SHA-256",
        auto_extract: bool = False,
        post_action: str = "none",
        is_torrent: bool = False,
        queue_order: int = 0,
        priority: int = 0,
        queue_name: str = "Main Queue",
        created_at: float = None,
        completed_at: float = 0.0,
        error_message: str = "",
        speed: float = 0.0,
        eta: int = 0,
        is_hidden: bool = False,
        zero_log: bool = False,
        description: str = ""
    ):
        self.id = id or task_id or str(uuid.uuid4())[:8]
        self.url = url
        self.filename = filename
        self.save_path = save_path
        self.description = description or ""
        self.total_bytes = total_bytes or total_size or 0
        self.downloaded_bytes = downloaded_bytes or 0
        self.speed = speed          # bytes/sec
        self.eta = eta              # seconds
        
        # Handle string or Enum status
        if isinstance(status, str):
            status_map = {s.value.lower(): s for s in DownloadStatus}
            self.status = status_map.get(status.lower(), DownloadStatus.QUEUED)
        else:
            self.status = status or DownloadStatus.QUEUED
            
        self.category = category
        self.connections = connections_count if connections_count is not None else (connections or 8)
        self.resumable = is_resumable if is_resumable is not None else resumable
        self.created_at = created_at or time.time()
        self.completed_at = completed_at or 0.0
        self.error_message = error_message or ""
        self.segments = segments if segments is not None else []
        self.headers = headers or {}
        self.proxy = proxy
        self.checksum = checksum
        self.checksum_type = checksum_type or "SHA-256"
        self.auto_extract = auto_extract
        self.post_action = post_action
        self.is_torrent = is_torrent
        self.queue_order = queue_order
        self.priority = priority
        self.queue_name = queue_name
        self.is_hidden = is_hidden
        self.zero_log = zero_log
        self.torrent_seeds: int = 0
        self.torrent_peers: int = 0
        self.upload_speed: float = 0.0
        self.tracker_status: str = ""

    @property
    def total_size(self) -> int:
        return self.total_bytes

    @total_size.setter
    def total_size(self, val: int):
        self.total_bytes = val

    @property
    def downloaded_size(self) -> int:
        return self.downloaded_bytes

    @downloaded_size.setter
    def downloaded_size(self, val: int):
        self.downloaded_bytes = val

    @property
    def status(self) -> Any:
        return self._status

    @status.setter
    def status(self, val: Any):
        if isinstance(val, str):
            status_map = {s.value.lower(): s for s in DownloadStatus}
            self._status = status_map.get(val.lower(), DownloadStatus.QUEUED)
        elif isinstance(val, DownloadStatus):
            self._status = val
        else:
            self._status = val or DownloadStatus.QUEUED

    @property
    def connections_count(self) -> int:
        return self.connections

    @connections_count.setter
    def connections_count(self, val: int):
        self.connections = val

    @property
    def is_resumable(self) -> bool:
        return self.resumable

    @is_resumable.setter
    def is_resumable(self, val: bool):
        self.resumable = val

    @property
    def progress_percent(self) -> float:
        if self.total_bytes <= 0:
            return 100.0 if self.status == DownloadStatus.COMPLETED else 0.0
        val = (self.downloaded_bytes / self.total_bytes) * 100.0
        return round(min(100.0, max(0.0, val)), 1)

    @property
    def progress(self) -> float:
        return self.progress_percent

    @progress.setter
    def progress(self, val: float):
        if self.total_bytes > 0:
            self.downloaded_bytes = int((val / 100.0) * self.total_bytes)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'url': self.url,
            'filename': self.filename,
            'save_path': self.save_path,
            'total_bytes': self.total_bytes,
            'downloaded_bytes': self.downloaded_bytes,
            'status': self.status.value if isinstance(self.status, DownloadStatus) else str(self.status),
            'category': self.category,
            'connections_count': self.connections,
            'created_at': self.created_at,
            'completed_at': self.completed_at,
            'error_message': self.error_message,
            'is_resumable': self.resumable,
            'description': self.description
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            url=data.get('url', ''),
            filename=data.get('filename', ''),
            save_path=data.get('save_path', ''),
            id=data.get('id'),
            total_bytes=data.get('total_bytes', 0),
            downloaded_bytes=data.get('downloaded_bytes', 0),
            status=data.get('status', DownloadStatus.QUEUED),
            category=data.get('category', 'documents'),
            connections=data.get('connections_count', data.get('connections', 8)),
            created_at=data.get('created_at', time.time()),
            completed_at=data.get('completed_at', 0.0),
            error_message=data.get('error_message', ''),
            resumable=data.get('is_resumable', data.get('resumable', True)),
            description=data.get('description', '')
        )
