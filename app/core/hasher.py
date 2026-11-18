import hashlib
import os
from typing import Tuple
from PyQt6.QtCore import QThread, pyqtSignal

class FileHasher:
    @staticmethod
    def calculate_hash(file_path: str, hash_type: str = "SHA-256", chunk_size: int = 65536) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        hash_type_upper = hash_type.upper().replace("-", "")
        if hash_type_upper in ("MD5", "SHA1", "SHA256"):
            try:
                from .segment import get_native_engine_path
                import subprocess
                native_exe = get_native_engine_path()
                if native_exe and os.path.exists(native_exe):
                    res = subprocess.run([native_exe, "hash", file_path, hash_type_upper.lower()], capture_output=True, text=True, timeout=60)
                    if res.returncode == 0:
                        val = res.stdout.strip().lower()
                        if val and len(val) >= 32:
                            return val
            except Exception:
                pass

        if hash_type_upper == "MD5":
            hasher = hashlib.md5()
        elif hash_type_upper == "SHA1":
            hasher = hashlib.sha1()
        elif hash_type_upper == "SHA256":
            hasher = hashlib.sha256()
        elif hash_type_upper == "SHA512":
            hasher = hashlib.sha512()
        else:
            hasher = hashlib.sha256()

        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)

        return hasher.hexdigest().lower()

    @staticmethod
    def verify_hash(file_path: str, expected_hash: str, hash_type: str = "SHA-256") -> Tuple[bool, str]:
        expected = expected_hash.strip().lower()
        actual = FileHasher.calculate_hash(file_path, hash_type)
        return (actual == expected), actual


class HashWorker(QThread):
    progress_updated = pyqtSignal(int, int)  # current_bytes, total_bytes
    hash_completed = pyqtSignal(dict)       # {"md5": str, "sha1": str, "sha256": str, "size": int}
    hash_failed = pyqtSignal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            if not os.path.exists(self.file_path):
                self.hash_failed.emit(f"Berkas tidak ditemukan: {self.file_path}")
                return

            total_size = os.path.getsize(self.file_path)
            md5 = hashlib.md5()
            sha1 = hashlib.sha1()
            sha256 = hashlib.sha256()

            processed = 0
            chunk_size = 1024 * 1024  # 1MB buffer

            with open(self.file_path, "rb") as f:
                while True:
                    if self._is_cancelled:
                        return
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    md5.update(chunk)
                    sha1.update(chunk)
                    sha256.update(chunk)
                    processed += len(chunk)
                    self.progress_updated.emit(processed, total_size)

            if not self._is_cancelled:
                self.hash_completed.emit({
                    "md5": md5.hexdigest().lower(),
                    "sha1": sha1.hexdigest().lower(),
                    "sha256": sha256.hexdigest().lower(),
                    "size": total_size
                })
        except Exception as e:
            self.hash_failed.emit(str(e))
