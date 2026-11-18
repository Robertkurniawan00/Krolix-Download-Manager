import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app.core.database import Database
from app.core.models import DownloadStatus, DownloadTask
from app.core.stream_watchlist import (
    StreamWatchlistManager,
    parse_stream_target,
    select_format_for_quality,
)


class _DummyEngine:
    def __init__(self, db: Database, default_dir: str):
        self.db = db
        self.default_dir = default_dir
        self.tasks = {}
        self.started_ids = []
        self.paused_ids = []
        self._counter = 0

    def create_task(self, url: str, save_dir: str = "", filename: str = "", headers=None, category: str = "Video"):
        self._counter += 1
        tid = f"task_{self._counter}"
        sdir = save_dir or self.default_dir
        os.makedirs(sdir, exist_ok=True)
        task = DownloadTask(
            id=tid,
            url=url,
            filename=filename or f"live_{self._counter}.mp4",
            save_path=os.path.join(sdir, filename or f"live_{self._counter}.mp4"),
            category=category,
            headers=dict(headers or {}),
            status=DownloadStatus.QUEUED,
        )
        self.tasks[tid] = task
        self.db.save_task(task)
        return task

    def start_download(self, task_id: str):
        self.started_ids.append(task_id)
        if task_id in self.tasks:
            self.tasks[task_id].status = DownloadStatus.DOWNLOADING
            self.db.save_task(self.tasks[task_id])

    def pause_download(self, task_id: str):
        self.paused_ids.append(task_id)
        if task_id in self.tasks:
            self.tasks[task_id].status = DownloadStatus.PAUSED
            self.db.save_task(self.tasks[task_id])


class TestStreamWatchlist(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_watchlist.db")
        self.db = Database(self.db_path)
        self.db.set_setting("default_save_path", self.temp_dir)
        self.engine = _DummyEngine(self.db, self.temp_dir)
        self.events_updated = []
        self.events_started = []
        self.mgr = StreamWatchlistManager(
            engine=self.engine,
            db=self.db,
            on_item_updated=lambda it: self.events_updated.append(it),
            on_recording_started=lambda it, t: self.events_started.append((it, t)),
            start_thread=False,
        )

    def tearDown(self):
        self.mgr.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_stream_target_platforms(self):
        url, plat, name = parse_stream_target("chaturbate:alice_cam")
        self.assertEqual(url, "https://chaturbate.com/alice_cam/")
        self.assertEqual(plat, "Chaturbate")
        self.assertEqual(name, "alice_cam")

        url2, plat2, name2 = parse_stream_target("https://stripchat.com/bob_live")
        self.assertEqual(url2, "https://stripchat.com/bob_live")
        self.assertEqual(plat2, "Stripchat")
        self.assertEqual(name2, "bob_live")

        url3, plat3, name3 = parse_stream_target("https://www.twitch.tv/shroud")
        self.assertEqual(plat3, "Twitch")
        self.assertEqual(name3, "shroud")

        url4, plat4, name4 = parse_stream_target("https://cdn.example.com/live/feed.m3u8?token=1")
        self.assertEqual(plat4, "HLS Feed")
        self.assertEqual(name4, "feed")

    def test_select_format_for_quality(self):
        formats = [
            {"format_id": "1080p", "height": 1080, "bitrate": 4500000, "url": "https://cdn/1080.m3u8"},
            {"format_id": "720p", "height": 720, "bitrate": 2500000, "url": "https://cdn/720.m3u8"},
            {"format_id": "480p", "height": 480, "bitrate": 1200000, "url": "https://cdn/480.m3u8"},
        ]
        self.assertEqual(select_format_for_quality(formats, "best")["height"], 1080)
        self.assertEqual(select_format_for_quality(formats, "720p")["height"], 720)
        self.assertEqual(select_format_for_quality(formats, "480p")["height"], 480)
        # Fallback to lowest variant when cap is below all available heights
        self.assertEqual(select_format_for_quality(formats, "360p")["height"], 480)

    def test_database_crud_watchlist(self):
        item = self.mgr.add_channel("chaturbate:luna_star", quality_pref="720p")
        self.assertEqual(item["name"], "luna_star")
        self.assertEqual(item["platform"], "Chaturbate")
        self.assertEqual(item["quality_pref"], "720p")

        all_items = self.db.get_watchlist()
        self.assertEqual(len(all_items), 1)
        self.assertEqual(all_items[0]["id"], item["id"])

        # Adding same URL updates existing instead of duplicating
        item2 = self.mgr.add_channel("https://chaturbate.com/luna_star/", name="Luna VIP", quality_pref="1080p")
        self.assertEqual(item2["id"], item["id"])
        self.assertEqual(len(self.db.get_watchlist()), 1)
        self.assertEqual(item2["name"], "Luna VIP")

        self.mgr.remove_channel(item["id"])
        self.assertEqual(len(self.db.get_watchlist()), 0)

    @patch("app.core.stream_watchlist.MediaGrabber.get_media_info")
    def test_auto_record_live_and_deduplicate(self, mock_get_media_info):
        item = self.mgr.add_channel("https://chaturbate.com/aria_live/", quality_pref="1080p")

        # 1. Offline probe updates status cleanly without creating task
        mock_get_media_info.return_value = (None, "Model 'aria_live' saat ini OFFLINE.")
        res_off = self.mgr.check_channel(item["id"])
        self.assertEqual(res_off["status"], "Offline")
        self.assertEqual(len(self.engine.tasks), 0)

        # 2. Private probe sets Private Show status
        mock_get_media_info.return_value = (None, "Model 'aria_live' sedang dalam sesi Private Show (berbayar).")
        res_priv = self.mgr.check_channel(item["id"])
        self.assertEqual(res_priv["status"], "Private Show")
        self.assertEqual(len(self.engine.tasks), 0)

        # 3. Live probe launches recording task and increments count
        mock_get_media_info.return_value = (
            {
                "title": "Chaturbate - aria_live (Live)",
                "is_live": True,
                "webpage_url": "https://chaturbate.com/aria_live/",
                "m3u8_url": "https://edge.mmcdn.com/master.m3u8",
                "formats": [
                    {
                        "format_id": "1080p",
                        "height": 1080,
                        "bitrate": 5000000,
                        "ext": "mp4",
                        "url": "https://edge.mmcdn.com/1080.m3u8",
                        "master_url": "https://edge.mmcdn.com/master.m3u8",
                        "audio_url": "https://edge.mmcdn.com/audio.m3u8",
                        "has_video": True,
                        "has_audio": True,
                        "is_live": True,
                    }
                ],
            },
            None,
        )
        res_live = self.mgr.check_channel(item["id"])
        self.assertEqual(res_live["status"], "Recording")
        self.assertEqual(res_live["record_count"], 1)
        self.assertEqual(len(self.engine.tasks), 1)
        self.assertEqual(len(self.events_started), 1)

        created_task = self.engine.tasks[res_live["active_task_id"]]
        self.assertEqual(created_task.headers.get("is_live"), "true")
        self.assertEqual(created_task.headers.get("master_url"), "https://edge.mmcdn.com/master.m3u8")
        self.assertEqual(created_task.headers.get("audio_url"), "https://edge.mmcdn.com/audio.m3u8")

        # 4. Subsequent check while task is active MUST NOT spawn a duplicate recording
        res_again = self.mgr.check_channel(item["id"])
        self.assertEqual(res_again["status"], "Recording")
        self.assertEqual(len(self.engine.tasks), 1)

        # 5. Stopping recording pauses task and triggers cooldown
        self.mgr.stop_channel_recording(item["id"])
        self.assertIn(created_task.id, self.engine.paused_ids)
        stopped_item = self.db.get_watchlist_item(item["id"])
        self.assertEqual(stopped_item["status"], "Paused (Cooldown)")
        self.assertEqual(stopped_item["active_task_id"], "")


if __name__ == "__main__":
    unittest.main()
