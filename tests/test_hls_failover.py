import unittest
from app.core.hls_downloader import HLSWorker
from app.core.link_resolver import CloudLinkResolver

class TestHLSFailoverAndProtection(unittest.TestCase):
    def test_google_cdn_referer_stripped(self):
        # CloudLinkResolver should strip referer for Google UserContent to prevent 429 Too Many Requests
        url = "https://lh3.googleusercontent.com/d/1zSqIDX_CnOdCcKo5IaJr3EABYZpL6UG-=d"
        headers = {
            "Referer": "https://turbovidhls.com/t/684c65701727f",
            "Origin": "https://turbovidhls.com",
            "User-Agent": "Mozilla/5.0"
        }
        fixed = CloudLinkResolver.fix_headers(url, headers)
        self.assertNotIn("Referer", fixed)
        self.assertNotIn("Origin", fixed)
        self.assertIn("User-Agent", fixed)

    def test_turbosplayer_fallback_resolution(self):
        # A dead g249 subdomain with Referer should resolve to working g241
        import socket
        from unittest.mock import patch
        bad_url = "https://g249.turbosplayer.com/file/e715bdba-69d1-4bb1-b268-0d3613ad2a88/master.m3u8"
        working_url = "https://g241.turbosplayer.com/file/f5654dda-3c78-457e-ab22-b6d3907954dd/master.m3u8"
        headers = {
            "Referer": "https://turbovidhls.com/t/684c65701727f",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        worker = HLSWorker(url=bad_url, target_path="test.mp4", headers=headers)

        def fake_fetch(u, *a, **kw):
            if "turbovidhls.com" in u:
                return f"var urlPlay = '{working_url}';".encode("utf-8")
            return b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2500000\nmaster.m3u8\n"

        with patch.object(socket, "gethostbyname", return_value="127.0.0.1"), \
             patch.object(worker, "_fetch_url_data", side_effect=fake_fetch):
            resolved = worker._resolve_working_fallback_stream()
            self.assertIsNotNone(resolved)
            self.assertIn("g241.turbosplayer.com", resolved)
            self.assertIn("master.m3u8", resolved)

    def test_fallback_urls_header_list(self):
        import socket
        from unittest.mock import patch
        bad_url = "https://nonexistent-stream-domain-xyz-987.com/variant.m3u8"
        working_url = "https://g241.turbosplayer.com/file/f5654dda-3c78-457e-ab22-b6d3907954dd/master.m3u8"
        headers = {
            "fallback_urls": [working_url]
        }
        worker = HLSWorker(url=bad_url, target_path="test.mp4", headers=headers)
        with patch.object(socket, "gethostbyname", return_value="127.0.0.1"), \
             patch.object(worker, "_fetch_url_data", return_value=b"#EXTM3U\n#EXT-X-VERSION:3\nseg1.ts"):
            resolved = worker._resolve_working_fallback_stream()
            self.assertEqual(resolved, working_url)

    def test_lulustream_headers_and_origin(self):
        url = "https://cdn1011.cdn-tnmr.org/hls2/04/04697/67jd49o2hzws_h/index-v1-a1.m3u8?t=test"
        headers = {"Referer": "https://luluvdo.com/e/67jd49o2hzws"}
        fixed = CloudLinkResolver.fix_headers(url, headers)
        self.assertEqual(fixed.get("Referer"), "https://luluvdo.com/e/67jd49o2hzws")
        self.assertEqual(fixed.get("Origin"), "https://luluvdo.com")
        self.assertEqual(fixed.get("Accept-Language"), "en-US,en;q=0.9")

    def test_lulustream_stream_auto_renewal(self):
        url = "https://cdn1011.cdn-tnmr.org/hls2/04/04697/67jd49o2hzws_h/index-v1-a1.m3u8?t=expired"
        headers = {"Referer": "https://luluvdo.com/"}
        from unittest.mock import patch, MagicMock
        fake_html = """
        eval(function(p,a,c,k,e,d){while(c--)if(k[c])p=p.replace(new RegExp('\\\\b'+c.toString(a)+'\\\\b','g'),k[c]);return p}('0.1({2:[{3:"4://5.6-7.8/9/a/b/c/d.e?t=f&s=g"}]})',17,17,'jwplayer|setup|sources|file|https|cdn1011|cdn|tnmr|org|hls2|04|04697|67jd49o2hzws_h|master|m3u8|fresh_token|12345'.split('|')))
        """
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_html.encode("utf-8")
        mock_resp.geturl.return_value = "https://luluvdo.com/e/67jd49o2hzws"
        mock_resp.__enter__.return_value = mock_resp
        with patch("urllib.request.urlopen", return_value=mock_resp):
            fresh_url, fresh_hdrs = CloudLinkResolver.resolve_stream_url(url, headers)
            self.assertIn("fresh_token", fresh_url)
            self.assertTrue("master.m3u8" in fresh_url or "index-v1-a1.m3u8" in fresh_url)
            self.assertEqual(fresh_hdrs.get("Accept-Language"), "en-US,en;q=0.9")

    def test_lulustream_resume_with_expired_cached_playlist(self):
        import os
        import tempfile
        import shutil
        from unittest.mock import patch
        task_id = "test_unit_resume_task"
        cache_dir = os.path.join(tempfile.gettempdir(), f"zero_hls_{task_id}")
        shutil.rmtree(cache_dir, ignore_errors=True)
        os.makedirs(cache_dir, exist_ok=True)
        cached_pl = os.path.join(cache_dir, "playlist.m3u8")
        with open(cached_pl, "w", encoding="utf-8") as f:
            f.write('#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://cdn1011.cdn-tnmr.org/hls2/encryption.key?t=expired"\n#EXTINF:10.0,\nseg1.ts\n#EXT-X-ENDLIST\n')

        url = "https://cdn1011.cdn-tnmr.org/hls2/04/04697/67jd49o2hzws_h/index-v1-a1.m3u8?t=expired"
        headers = {"Referer": "https://streamhihi.com/"}
        worker = HLSWorker(url=url, target_path="test.mp4", task_id=task_id, headers=headers)

        fresh_url = "https://cdn1011.cdn-tnmr.org/hls2/04/04697/67jd49o2hzws_h/index-v1-a1.m3u8?t=fresh_renewal_token"
        with patch.object(worker, "_fetch_url_data", side_effect=Exception("Expired token")), \
             patch.object(worker, "_resolve_working_fallback_stream", return_value=fresh_url):
            resolved = worker._resolve_working_fallback_stream()
            self.assertEqual(resolved, fresh_url)
        shutil.rmtree(cache_dir, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
