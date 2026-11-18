"""
Comprehensive Automated Test Suite for Zero Download Assistant
"""
import os
import sys
import time
import json
import tempfile
import unittest
import urllib.request

# Ensure app root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.helpers import (
    format_bytes, format_speed, format_time, sanitize_filename, get_category_from_ext
)
from app.core.models import DownloadTask
from app.core.database import Database
from app.core.segment import SegmentManager
from app.core.speed_limiter import SpeedLimiter
from app.services.api_server import ApiServer


class TestHelpers(unittest.TestCase):
    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500.0 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1024 * 1024), "1.00 MB")
        self.assertEqual(format_bytes(1024 * 1024 * 1024 * 2.5), "2.50 GB")

    def test_format_speed(self):
        self.assertEqual(format_speed(1024 * 500), "500.0 KB/s")
        self.assertEqual(format_speed(1024 * 1024 * 3.2), "3.2 MB/s")

    def test_format_time(self):
        self.assertEqual(format_time(45), "00:45")
        self.assertEqual(format_time(3665), "01:01:05")

    def test_sanitize_filename(self):
        raw = 'my<cool>:file*"name"?|test.mp4'
        clean = sanitize_filename(raw)
        self.assertNotIn('<', clean)
        self.assertNotIn('>', clean)
        self.assertNotIn(':', clean)
        self.assertNotIn('"', clean)
        self.assertNotIn('*', clean)
        self.assertNotIn('?', clean)
        self.assertNotIn('|', clean)

    def test_category(self):
        self.assertEqual(get_category_from_ext("video.mp4"), "Video")
        self.assertEqual(get_category_from_ext("music.mp3"), "Music")
        self.assertEqual(get_category_from_ext("doc.pdf"), "Documents")
        self.assertEqual(get_category_from_ext("app.exe"), "Programs")
        self.assertEqual(get_category_from_ext("archive.zip"), "Compressed")


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = Database(self.db_path)

    def test_task_crud(self):
        task = DownloadTask(
            url="https://example.com/testfile.bin",
            filename="testfile.bin",
            save_path=self.temp_dir,
            total_size=1024 * 1024,
            status="downloading"
        )
        self.db.save_task(task)

        retrieved = self.db.get_task(task.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.filename, "testfile.bin")
        self.assertEqual(retrieved.total_size, 1024 * 1024)

        # Update
        task.status = "completed"
        task.downloaded_size = task.total_size
        self.db.update_task(task)

        updated = self.db.get_task(task.id)
        self.assertEqual(updated.status, "completed")
        self.assertEqual(updated.downloaded_size, 1024 * 1024)

        # Delete
        self.db.delete_task(task.id)
        self.assertIsNone(self.db.get_task(task.id))


class TestSegmentManager(unittest.TestCase):
    def test_segment_split(self):
        total_size = 1000
        num_segments = 4
        segments = SegmentManager.create_segments(total_size, num_segments)
        self.assertEqual(len(segments), 4)
        self.assertEqual(segments[0].start_byte, 0)
        self.assertEqual(segments[-1].end_byte, 999)

        # Ensure contiguous coverage
        for i in range(len(segments) - 1):
            self.assertEqual(segments[i].end_byte + 1, segments[i + 1].start_byte)

    def test_merge_parts(self):
        temp_dir = tempfile.mkdtemp()
        part1 = os.path.join(temp_dir, "file.part0")
        part2 = os.path.join(temp_dir, "file.part1")
        output = os.path.join(temp_dir, "file.final")

        with open(part1, "wb") as f:
            f.write(b"HELLO ")
        with open(part2, "wb") as f:
            f.write(b"WORLD!")

        SegmentManager.merge_files([part1, part2], output)
        with open(output, "rb") as f:
            content = f.read()

        self.assertEqual(content, b"HELLO WORLD!")


class TestSpeedLimiter(unittest.TestCase):
    def test_throttle(self):
        limiter = SpeedLimiter(max_bytes_per_sec=10000)
        self.assertEqual(limiter.max_bytes_per_sec, 10000)
        limiter.set_limit(50000)
        self.assertEqual(limiter.max_bytes_per_sec, 50000)


class TestApiServer(unittest.TestCase):
    def test_api_endpoints(self):
        received_downloads = []

        def on_download(url, filename, category):
            received_downloads.append((url, filename, category))

        server = ApiServer(host="127.0.0.1", port=9699)
        server.on_download_request = on_download
        server.start()
        time.sleep(0.5)

        try:
            # 1. Status endpoint
            req = urllib.request.Request("http://127.0.0.1:9699/api/status")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                self.assertTrue(data.get("online"))

            # 2. Download endpoint
            post_data = json.dumps({
                "url": "https://example.com/test_video.mp4",
                "filename": "test_video.mp4"
            }).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:9699/api/download",
                data=post_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                self.assertTrue(data.get("ok"))

            time.sleep(0.3)
            self.assertEqual(len(received_downloads), 1)
            self.assertEqual(received_downloads[0][0], "https://example.com/test_video.mp4")

        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()