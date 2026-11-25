import base64
import gzip
import http.client
import json
import os
import sys
import tarfile
import tempfile
import threading
import unittest
import urllib.parse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.archive_extractor import ArchiveExtractor
from app.core.database import Database
from app.core.downloader import DownloadEngine
from app.core.link_resolver import CloudLinkResolver
from app.core.models import DownloadStatus, DownloadTask
from app.core.pikpak_resolver import PikPakResolver
from app.core.speed_limiter import SpeedLimiter
from app.services.api_server import ApiHandler, ApiServer
from app.services.clipboard_service import ClipboardMonitor
from app.utils.browser_integration import decode_protocol_url
from app.utils.helpers import extract_filename_from_headers, sanitize_filename


class TestAuditRegressions(unittest.TestCase):
    def test_speed_limiter_low_limit_and_zero_reset(self):
        # Regression: chunks >= 256KB previously deadlocked when max_bytes_per_sec < 262144
        limiter = SpeedLimiter(max_bytes_per_sec=100 * 1024)
        self.assertTrue(limiter.enabled)

        done = threading.Event()
        errors = []

        def _worker():
            try:
                limiter.acquire(10 * 1024)
                limiter.throttle(5 * 1024)
            except Exception as e:
                errors.append(e)
            finally:
                done.set()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        limiter.set_limit(0)  # Must not trigger ZeroDivisionError in concurrent waiter
        self.assertTrue(done.wait(timeout=2.0), "SpeedLimiter deadlocked on wait or set_limit(0)")
        self.assertEqual(errors, [])

    def test_database_lookup_includes_save_path_and_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path=db_path)

            t = DownloadTask(
                id="task_001",
                url="https://example.com/archive.zip",
                filename="archive.zip",
                save_path=os.path.join(tmpdir, "archive.zip"),
                status=DownloadStatus.COMPLETED,
                checksum="abc123def456",
            )
            db.save_task(t)

            by_url = db.get_tasks_by_url("https://example.com/archive.zip")
            self.assertEqual(len(by_url), 1)
            self.assertEqual(by_url[0].save_path, t.save_path)

            by_name = db.get_tasks_by_filename("archive.zip")
            self.assertEqual(len(by_name), 1)
            self.assertEqual(by_name[0].save_path, t.save_path)

            by_hash = db.get_task_by_hash("abc123def456")
            self.assertIsNotNone(by_hash)
            self.assertEqual(by_hash.id, "task_001")

    def test_engine_rlock_refresh_redownload_and_zero_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(db_path=os.path.join(tmpdir, "engine.db"))
            engine = DownloadEngine(db=db, speed_limiter=SpeedLimiter(0))
            engine.probe_url = lambda *a, **kw: {
                "success": True,
                "filename": "movie.mp4",
                "total_bytes": 1024,
                "resumable": True,
                "is_hls": False,
                "headers": {},
            }
            try:
                task = engine.create_task(
                    url="https://example.com/movie.mp4?token=old",
                    save_dir=tmpdir,
                    filename="movie.mp4",
                    total_bytes=1024,
                    resumable=True,
                    category="Video",
                    zero_log=True,
                )
                # Zero-log task must stay in memory and not persist in SQLite
                self.assertIn(task.id, engine.tasks)
                self.assertEqual(db.get_tasks_by_url(task.url), [])

                # refresh_task_url calls pause_download while holding engine.lock (needs RLock)
                ok, _msg = engine.refresh_task_url(task.id, "https://example.com/movie.mp4?token=new")
                self.assertTrue(ok)
                self.assertEqual(engine.tasks[task.id].url, "https://example.com/movie.mp4?token=new")

                # Simulate completed task and test redownload_task reset (without starting real network)
                t2 = engine.create_task(
                    url="https://example.com/done.bin",
                    save_dir=tmpdir,
                    filename="done.bin",
                    total_bytes=5,
                    resumable=True,
                )
                with open(t2.save_path, "wb") as f:
                    f.write(b"hello")
                t2.status = DownloadStatus.COMPLETED
                t2.downloaded_bytes = 5
                t2.progress = 100.0
                engine.start_download = lambda tid: None  # Prevent actual network thread
                engine.redownload_task(t2.id)
                self.assertEqual(t2.downloaded_bytes, 0)
                self.assertEqual(t2.progress, 0.0)
                self.assertFalse(os.path.exists(t2.save_path))
            finally:
                engine.stop()

    def test_protocol_url_decoding_schemes_and_base64_spaces(self):
        payload = {"url": "https://cdn.example.com/video+1.mp4", "filename": "video 1.mp4"}
        raw_b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        # Append '>' characters whose bits reliably yield '+' in base64
        for pad_len in range(1, 10):
            payload["pad"] = ">" * pad_len
            cand = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
            if "+" in cand:
                raw_b64 = cand
                break
        self.assertIn("+", raw_b64)

        for scheme in ("krolix-dl", "krolix", "zero-dl", "zero"):
            decoded = decode_protocol_url(f"{scheme}://download?data={raw_b64}")
            self.assertIsNotNone(decoded, f"Failed decoding {scheme}")
            self.assertEqual(decoded["url"], payload["url"])

        urlsafe = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
        decoded_u = decode_protocol_url(f"krolix-dl://download?data={urlsafe}")
        self.assertEqual(decoded_u["filename"], payload["filename"])

    def test_archive_extractor_tar_gz_and_standalone_gz(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_txt = os.path.join(tmpdir, "sample.txt")
            with open(src_txt, "wb") as f:
                f.write(b"krolix archive test payload")

            tgz_path = os.path.join(tmpdir, "bundle.tar.gz")
            with tarfile.open(tgz_path, "w:gz") as tf:
                tf.add(src_txt, arcname="sample.txt")

            ok, out_dir = ArchiveExtractor.extract(tgz_path)
            self.assertTrue(ok)
            self.assertEqual(os.path.basename(out_dir), "bundle")
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "sample.txt")))

            gz_path = os.path.join(tmpdir, "notes.txt.gz")
            with gzip.open(gz_path, "wb") as gz:
                gz.write(b"standalone gzip ok")
            ok_gz, out_gz = ArchiveExtractor.extract(gz_path)
            self.assertTrue(ok_gz)
            self.assertTrue(os.path.isfile(os.path.join(out_gz, "notes.txt")))

    def test_packer_unpack_preserves_backslashes_and_rfc5987(self):
        # Backslash escape sequence must not fail re.sub
        res = CloudLinkResolver._unpack_packer("0", 1, 1, r"a\b")
        self.assertEqual(res, r"a\b")

        fname = extract_filename_from_headers(
            {"Content-Disposition": "attachment; filename*=UTF-8'en'hello%20world%2B1.zip"},
            "https://example.com/dl"
        )
        self.assertEqual(fname, "hello world+1.zip")
        self.assertNotIn("\n", sanitize_filename("bad.zip\r\n"))

    def test_clipboard_monitor_avoids_html_false_positives(self):
        mon = ClipboardMonitor(on_url_detected=lambda u: None, is_torrent_enabled=lambda: True)
        self.assertFalse(mon._is_downloadable_url("https://example.com/get/started"))
        self.assertFalse(mon._is_downloadable_url("https://example.com/blog/download-guide"))
        self.assertTrue(mon._is_downloadable_url("HTTP://EXAMPLE.COM/release.zip"))
        self.assertTrue(mon._is_downloadable_url("https://cdn.example.com/dl?response-content-disposition=attachment"))
        self.assertTrue(mon._is_downloadable_url("magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"))

    def test_api_server_edge_cases(self):
        srv = ApiServer(port=0, host="127.0.0.1")
        received_dl = []
        srv.download_requested.connect(received_dl.append)
        srv.start()
        try:
            port = srv.httpd.server_address[1]
            # 1. /ping GET check
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("GET", "/ping?ts=123", headers={"Host": f"127.0.0.1:{port}"})
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, 200)

            # 2. Invalid Content-Length returns 400 cleanly
            conn.request("POST", "/download", body="{}", headers={"Host": f"127.0.0.1:{port}", "Content-Length": "-5"})
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, 400)

            # 3. Query-stripped /api/download accepts magnet: and maps top-level referer/cookies
            body = json.dumps({
                "url": "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
                "referer": "https://tracker.example/",
                "cookies": "sid=xyz",
                "save_dir": r"\\evilserver\share"
            })
            conn.request("POST", "/api/download?src=ext", body=body, headers={
                "Host": f"127.0.0.1:{port}",
                "Content-Type": "application/json",
            })
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 200)
            self.assertTrue(data["success"])
            self.assertFalse(ApiHandler._is_safe_save_dir(r"\\evilserver\share"))
            conn.close()
        finally:
            srv.stop()

    def test_pikpak_captcha_cache_is_action_scoped(self):
        PikPakResolver._captcha_cache["GET:/a"] = ("tok_a", 9999999999.0)
        PikPakResolver._captcha_cache["POST:/b"] = ("tok_b", 9999999999.0)
        self.assertEqual(PikPakResolver.get_captcha_token(action="GET:/a"), "tok_a")
        self.assertEqual(PikPakResolver.get_captcha_token(action="POST:/b"), "tok_b")

    def test_ui_modules_import_cleanly(self):
        modules = [
            "app.ui.main_window",
            "app.ui.add_dialog",
            "app.ui.batch_dialog",
            "app.ui.batch_sniffer_dialog",
            "app.ui.dht_search_dialog",
            "app.ui.grabber_dialog",
            "app.ui.hash_dialog",
            "app.ui.progress_dialog",
            "app.ui.proxy_manager_dialog",
            "app.ui.settings_dialog",
            "app.ui.torrent_add_dialog",
            "app.ui.torrent_file_selector",
            "app.ui.torrent_search_dialog",
            "app.ui.torrent_seeding_dialog",
            "app.ui.watchlist_dialog",
            "app.ui.ytdlp_dialog",
        ]
        for mod_name in modules:
            __import__(mod_name)


if __name__ == "__main__":
    unittest.main()
