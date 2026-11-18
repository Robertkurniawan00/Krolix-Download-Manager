"""
Integration Test for Zero Downloader Engine: Multi-connection segmented download
"""
import os
import sys
import time
import hashlib
import tempfile
import unittest
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtCore import QCoreApplication
from app.core.models import DownloadTask
from app.core.downloader import DownloadWorker


class RangeHTTPRequestHandler(SimpleHTTPRequestHandler):
    """HTTP server that supports standard HTTP Range requests"""
    def do_HEAD(self):
        super().do_HEAD()

    def do_GET(self):
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().do_GET()

        file_size = os.path.getsize(path)
        range_header = self.headers.get('Range')

        if not range_header:
            return super().do_GET()

        try:
            range_val = range_header.strip().replace('bytes=', '')
            parts = range_val.split('-')
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if parts[1] else file_size - 1

            if start >= file_size or end >= file_size:
                self.send_error(416, "Requested Range Not Satisfiable")
                return

            length = end - start + 1
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
            self.send_header('Content-Length', str(length))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Type', 'application/octet-stream')
            self.end_headers()

            with open(path, 'rb') as f:
                f.seek(start)
                sent = 0
                while sent < length:
                    chunk = f.read(min(32768, length - sent))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    sent += len(chunk)
        except Exception as e:
            pass


class TestDownloadWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication(sys.argv)
        cls.temp_dir = tempfile.mkdtemp()

        # Create a 256 KB test file with pseudo-random content
        cls.test_file_path = os.path.join(cls.temp_dir, "source.bin")
        cls.payload = os.urandom(256 * 1024)
        with open(cls.test_file_path, "wb") as f:
            f.write(cls.payload)
        cls.expected_hash = hashlib.sha256(cls.payload).hexdigest()

        # Start range-enabled HTTP server
        handler = lambda *args, **kwargs: RangeHTTPRequestHandler(*args, directory=cls.temp_dir, **kwargs)
        cls.httpd = HTTPServer(('127.0.0.1', 9797), handler)
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_multi_threaded_segmented_download(self):
        dest_dir = os.path.join(self.temp_dir, "downloads")
        os.makedirs(dest_dir, exist_ok=True)
        task = DownloadTask(
            url="http://127.0.0.1:9797/source.bin",
            filename="downloaded.bin",
            save_path=dest_dir
        )
        task.connections_count = 4

        completed_tasks = []
        progress_events = []

        worker = DownloadWorker(task)
        worker.task_completed.connect(lambda t: completed_tasks.append(t))
        worker.progress_updated.connect(lambda t: progress_events.append(t.progress_percent))

        worker.start()
        worker.wait(5000)

        # Process Qt events
        self.app.processEvents()

        dest_file = os.path.join(dest_dir, "downloaded.bin")
        self.assertTrue(os.path.exists(dest_file), "Downloaded file must exist")
        self.assertEqual(len(completed_tasks), 1, "Task must trigger completed signal")
        self.assertEqual(completed_tasks[0], task.id)
        self.assertEqual(task.status, "completed")

        with open(dest_file, "rb") as f:
            downloaded_bytes = f.read()

        downloaded_hash = hashlib.sha256(downloaded_bytes).hexdigest()
        self.assertEqual(downloaded_hash, self.expected_hash, "Hash must match source exactly")
        self.assertEqual(len(downloaded_bytes), len(self.payload))


if __name__ == "__main__":
    unittest.main()
