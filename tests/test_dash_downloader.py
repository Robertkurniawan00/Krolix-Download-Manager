import unittest
import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.hls_downloader import HLSWorker


class TestDASHDownloader(unittest.TestCase):
    """Unit tests for MPEG-DASH (.mpd) parsing, template evaluation, and track selection."""

    def test_iso8601_duration_parsing(self):
        self.assertEqual(HLSWorker._parse_iso8601_duration("PT30S"), 30.0)
        self.assertEqual(HLSWorker._parse_iso8601_duration("PT1M"), 60.0)
        self.assertEqual(HLSWorker._parse_iso8601_duration("PT1H2M30.5S"), 3750.5)
        self.assertEqual(HLSWorker._parse_iso8601_duration(""), 0.0)
        self.assertEqual(HLSWorker._parse_iso8601_duration(None), 0.0)

    def test_dash_template_formatting(self):
        tmpl = "$RepresentationID$/segment_$Number%05d$.m4s"
        formatted = HLSWorker._format_dash_template(tmpl, rep_id="video_1080p", number=42)
        self.assertEqual(formatted, "video_1080p/segment_00042.m4s")

        tmpl_time = "chunk_$RepresentationID$_$Time$.m4s"
        formatted_time = HLSWorker._format_dash_template(tmpl_time, rep_id="audio_aac", time_val=180000)
        self.assertEqual(formatted_time, "chunk_audio_aac_180000.m4s")

        tmpl_bw = "stream_$Bandwidth$_$Number$.m4s"
        formatted_bw = HLSWorker._format_dash_template(tmpl_bw, bandwidth=5000000, number=1)
        self.assertEqual(formatted_bw, "stream_5000000_1.m4s")

    def test_parse_mpd_segment_template_number(self):
        sample_mpd = """<?xml version="1.0"?>
        <MPD xmlns="urn:mpeg:dash:schema:mpd:2011" mediaPresentationDuration="PT12S">
            <Period>
                <AdaptationSet mimeType="video/mp4" contentType="video">
                    <SegmentTemplate duration="4" timescale="1" initialization="v_init.mp4" media="v_$Number$.m4s" startNumber="1"/>
                    <Representation id="v_low" bandwidth="1000000" />
                    <Representation id="v_high" bandwidth="5000000" />
                </AdaptationSet>
                <AdaptationSet mimeType="audio/mp4" contentType="audio">
                    <SegmentTemplate duration="4" timescale="1" initialization="a_init.mp4" media="a_$Number$.m4s" startNumber="1"/>
                    <Representation id="a_main" bandwidth="128000" />
                </AdaptationSet>
            </Period>
        </MPD>
        """
        worker = HLSWorker(url="https://example.com/dash/manifest.mpd", target_path="test.mp4")
        res = worker._parse_mpd(sample_mpd, "https://example.com/dash/manifest.mpd")

        self.assertIsNotNone(res)
        self.assertIn("video", res)
        self.assertIn("audio", res)

        # Should select highest bandwidth representation (v_high = 5Mbps)
        v = res["video"]
        self.assertEqual(v["rep_id"], "v_high")
        self.assertEqual(v["bandwidth"], 5000000)
        self.assertEqual(v["init_url"], "https://example.com/dash/v_init.mp4")
        # 12s total duration / 4s seg duration = 3 segments
        self.assertEqual(len(v["segments"]), 3)
        self.assertEqual(v["segments"][0], "https://example.com/dash/v_1.m4s")
        self.assertEqual(v["segments"][1], "https://example.com/dash/v_2.m4s")
        self.assertEqual(v["segments"][2], "https://example.com/dash/v_3.m4s")

        # Audio
        a = res["audio"]
        self.assertEqual(a["rep_id"], "a_main")
        self.assertEqual(a["init_url"], "https://example.com/dash/a_init.mp4")
        self.assertEqual(len(a["segments"]), 3)

    def test_parse_mpd_segment_timeline(self):
        sample_mpd = """<?xml version="1.0"?>
        <MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
            <Period>
                <AdaptationSet contentType="video">
                    <SegmentTemplate timescale="1000" initialization="init.mp4" media="seg_$Time$.m4s">
                        <SegmentTimeline>
                            <S t="0" d="2000" r="2" />
                            <S d="1000" />
                        </SegmentTimeline>
                    </SegmentTemplate>
                    <Representation id="rep1" bandwidth="2000000" />
                </AdaptationSet>
            </Period>
        </MPD>
        """
        worker = HLSWorker(url="https://example.com/stream/manifest.mpd", target_path="test.mp4")
        res = worker._parse_mpd(sample_mpd, "https://example.com/stream/manifest.mpd")

        self.assertIsNotNone(res)
        v = res["video"]
        # r="2" means 1 initial + 2 repeats = 3 segments of 2000ms: times 0, 2000, 4000
        # next S has d="1000": time 6000
        # Total = 4 segments
        self.assertEqual(len(v["segments"]), 4)
        self.assertEqual(v["segments"][0], "https://example.com/stream/seg_0.m4s")
        self.assertEqual(v["segments"][1], "https://example.com/stream/seg_2000.m4s")
        self.assertEqual(v["segments"][2], "https://example.com/stream/seg_4000.m4s")
        self.assertEqual(v["segments"][3], "https://example.com/stream/seg_6000.m4s")


if __name__ == "__main__":
    unittest.main()
