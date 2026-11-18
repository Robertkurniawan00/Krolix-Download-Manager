import os
import tempfile
import unittest
from app.core.torrent_downloader import TorrentWorker
from app.core.downloader import DownloadEngine


def bencode(val):
    if isinstance(val, int):
        return f"i{val}e".encode("ascii")
    elif isinstance(val, bytes):
        return f"{len(val)}:".encode("ascii") + val
    elif isinstance(val, str):
        b = val.encode("utf-8")
        return f"{len(b)}:".encode("ascii") + b
    elif isinstance(val, list):
        return b"l" + b"".join(bencode(x) for x in val) + b"e"
    elif isinstance(val, dict):
        items = []
        for k in sorted(val.keys()):
            items.append(bencode(k))
            items.append(bencode(val[k]))
        return b"d" + b"".join(items) + b"e"
    raise TypeError(f"Unsupported type: {type(val)}")


class TestTorrentAndFileSizeDetection(unittest.TestCase):
    def test_single_file_torrent_bencode_and_info(self):
        torrent_dict = {
            "announce": "http://tracker.example.com/announce",
            "info": {
                "name": "Ubuntu-24.04-Desktop-amd64.iso",
                "length": 4831838208,
                "piece length": 262144,
                "pieces": b"\x00" * 20
            }
        }
        with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as f:
            f.write(bencode(torrent_dict))
            tpath = f.name

        try:
            info = TorrentWorker.get_torrent_info(tpath)
            self.assertEqual(info["name"], "Ubuntu-24.04-Desktop-amd64.iso")
            self.assertEqual(info["total_bytes"], 4831838208)
            self.assertFalse(info["is_multi_file"])
            self.assertEqual(len(info["files"]), 1)
            self.assertEqual(info["files"][0]["size"], 4831838208)
            self.assertEqual(info["files"][0]["ext"], "iso")
        finally:
            if os.path.exists(tpath):
                os.unlink(tpath)

    def test_multi_file_torrent_bencode_and_filelist(self):
        torrent_dict = {
            "announce": "http://tracker.example.com/announce",
            "info": {
                "name": "Collection_Pack_2026",
                "piece length": 262144,
                "pieces": b"\x00" * 20,
                "files": [
                    {"length": 150000000, "path": ["Video", "Episode_01.mkv"]},
                    {"length": 250000000, "path": ["Video", "Episode_02.mkv"]},
                    {"length": 45000, "path": ["Subtitles", "English.srt"]},
                ]
            }
        }
        with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as f:
            f.write(bencode(torrent_dict))
            tpath = f.name

        try:
            files = TorrentWorker.get_file_list(tpath)
            self.assertEqual(len(files), 3)
            self.assertEqual(files[0]["name"], "Episode_01.mkv")
            self.assertEqual(files[0]["size"], 150000000)
            self.assertEqual(files[1]["name"], "Episode_02.mkv")
            self.assertEqual(files[1]["size"], 250000000)
            self.assertEqual(files[2]["name"], "English.srt")
            self.assertEqual(files[2]["size"], 45000)

            info = TorrentWorker.get_torrent_info(tpath)
            self.assertEqual(info["name"], "Collection_Pack_2026")
            self.assertEqual(info["total_bytes"], 400045000)
            self.assertTrue(info["is_multi_file"])
        finally:
            if os.path.exists(tpath):
                os.unlink(tpath)

    def test_magnet_exact_length_detection(self):
        magnet = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=Sample+Movie+1080p.mp4&xl=2147483648"
        info = TorrentWorker.get_torrent_info(magnet)
        self.assertEqual(info["name"], "Sample Movie 1080p.mp4")
        self.assertEqual(info["total_bytes"], 2147483648)

    def test_engine_probe_and_create_task_preserves_torrent_size(self):
        from app.core.database import Database
        tmp_save_dir = tempfile.mkdtemp()
        db_path = os.path.join(tmp_save_dir, "test_zero.db")
        engine = DownloadEngine(Database(db_path))
        torrent_dict = {
            "info": {
                "name": "Archive_Data.zip",
                "length": 987654321,
                "piece length": 16384,
                "pieces": b"\x00" * 20
            }
        }
        with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as f:
            f.write(bencode(torrent_dict))
            tpath = f.name

        tmp_save_dir = tempfile.mkdtemp()
        try:
            probe_res = engine.probe_url(tpath)
            self.assertTrue(probe_res["success"])
            self.assertEqual(probe_res["total_bytes"], 987654321)
            self.assertEqual(probe_res["filename"], "Archive_Data.zip")

            task = engine.create_task(url=tpath, save_dir=tmp_save_dir, zero_log=True)
            self.assertEqual(task.total_bytes, 987654321)
            self.assertEqual(task.category, "Torrents")
        finally:
            if os.path.exists(tpath):
                os.unlink(tpath)
            import shutil
            shutil.rmtree(tmp_save_dir, ignore_errors=True)


    def test_torrent_worker_initialization(self):
        worker = TorrentWorker(
            source="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
            save_dir=tempfile.gettempdir()
        )
        self.assertEqual(worker.seed_duration_days, 3)
        self.assertEqual(worker.seed_ratio, 2.0)

        worker_custom = TorrentWorker(
            source="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
            save_dir=tempfile.gettempdir(),
            seed_duration_days=7,
            seed_ratio=1.5
        )
        self.assertEqual(worker_custom.seed_duration_days, 7)
        self.assertEqual(worker_custom.seed_ratio, 1.5)

        worker_header = TorrentWorker(
            source="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
            save_dir=tempfile.gettempdir(),
            headers={"seed_duration_days": "14", "seed_ratio": "3.0"}
        )
        self.assertEqual(worker_header.seed_ratio, 3.0)

    def test_bdecode_and_parse_torrent_or_magnet(self):
        from app.core.torrent_downloader import bdecode, parse_torrent_or_magnet
        data = b"d4:name11:test_sample6:lengthi9999ee"
        dec = bdecode(data)
        self.assertEqual(dec["length"], 9999)
        self.assertEqual(dec["name"], b"test_sample")

        mag = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=Sample+Film&xl=50000000"
        parsed = parse_torrent_or_magnet(mag)
        self.assertEqual(parsed["info_hash"], "0123456789abcdef0123456789abcdef01234567")
        self.assertEqual(parsed["name"], "Sample Film")
        self.assertEqual(parsed["total_size"], 50000000)


if __name__ == "__main__":
    unittest.main()
