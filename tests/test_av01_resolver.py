import unittest
from unittest.mock import patch, MagicMock
from app.core.av01_resolver import AV01Resolver
from app.core.link_resolver import CloudLinkResolver


class TestAV01Resolver(unittest.TestCase):

    def test_is_av01_url(self):
        self.assertTrue(AV01Resolver.is_av01_url("https://www.av01.media/videos/224550"))
        self.assertTrue(AV01Resolver.is_av01_url("https://www.av01.tv/videos/224550"))
        self.assertTrue(AV01Resolver.is_av01_url("https://customers.iw01.xyz/fmp4/20261103a/init.mp4"))
        self.assertTrue(AV01Resolver.is_av01_url("https://files.iw01.xyz/edge/geo.js?json"))
        self.assertTrue(AV01Resolver.is_av01_url("https://www.av01.media/api/v1/videos/224550/manifest/master.m3u8"))
        self.assertFalse(AV01Resolver.is_av01_url("https://www.youtube.com/watch?v=123"))
        self.assertFalse(AV01Resolver.is_av01_url("https://google.com/file.mp4"))

    def test_extract_video_id(self):
        url1 = "https://www.av01.media/api/v1/videos/224550/manifest/index90-sv3-v1-a1.m3u8?hb=123"
        self.assertEqual(AV01Resolver.extract_video_id(url1), "224550")

        url2 = "https://www.av01.tv/videos/998811"
        self.assertEqual(AV01Resolver.extract_video_id(url2), "998811")

        url3 = "https://customers.iw01.xyz/fmp4/segment.m4s"
        headers = {"Referer": "https://www.av01.media/videos/554433"}
        self.assertEqual(AV01Resolver.extract_video_id(url3, headers), "554433")

    def test_sign_segment_url_mocked(self):
        with patch.object(AV01Resolver, "get_cdn_token", return_value="mock_jwt_token_123"):
            raw_seg = "https://customers.iw01.xyz/fmp4/test/segment.m4s"
            signed = AV01Resolver.sign_segment_url(raw_seg, video_id="224550")
            self.assertIn("access_token=mock_jwt_token_123", signed)

            # Preserves existing parameters
            raw_seg_params = "https://customers.iw01.xyz/fmp4/test/segment.m4s?hb=abc"
            signed_params = AV01Resolver.sign_segment_url(raw_seg_params, video_id="224550")
            self.assertIn("hb=abc", signed_params)
            self.assertIn("access_token=mock_jwt_token_123", signed_params)

            # Non-AV01 urls are not modified
            other_url = "https://example.com/segment.ts"
            self.assertEqual(AV01Resolver.sign_segment_url(other_url, video_id="224550"), other_url)

    def test_fix_headers(self):
        hdrs = CloudLinkResolver.fix_headers("https://customers.iw01.xyz/fmp4/segment.m4s")
        self.assertEqual(hdrs.get("Referer"), "https://www.av01.media/")
        self.assertEqual(hdrs.get("Origin"), "https://www.av01.media")
        self.assertIn("AppleWebKit", hdrs.get("User-Agent"))

    def test_resolve_video_page(self):
        with patch.object(AV01Resolver, "get_video_metadata", return_value={"dvd_id": "ABC-123", "title": "Test Title", "duration": 3600}):
            page_url = "https://www.av01.media/videos/12345"
            info = AV01Resolver.resolve_video_page(page_url)
            self.assertIsNotNone(info)
            self.assertEqual(info["stream_url"], "https://www.av01.media/api/v1/videos/12345/manifest/master.m3u8")
            self.assertIn("ABC-123", info["filename"])
            self.assertIn("Test Title", info["filename"])


if __name__ == "__main__":
    unittest.main()
