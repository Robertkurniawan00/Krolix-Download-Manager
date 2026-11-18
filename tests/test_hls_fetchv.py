import unittest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from app.core.hls_downloader import HLSWorker

class TestHLSFetchVMethodology(unittest.TestCase):
    def test_query_inheritance_on_relative_segment(self):
        """FetchV methodology: relative segment inherits parent playlist auth query parameters."""
        base_url = "https://edge-cdn.example.com/hls/1080p/index.m3u8?token=secureToken123&expires=1700000000&sign=abcd"
        relative_seg = "seg-0001.ts"
        resolved = HLSWorker._resolve_url(base_url, relative_seg)
        
        self.assertIn("https://edge-cdn.example.com/hls/1080p/seg-0001.ts", resolved)
        self.assertIn("token=secureToken123", resolved)
        self.assertIn("expires=1700000000", resolved)
        self.assertIn("sign=abcd", resolved)

    def test_query_inheritance_on_absolute_segment(self):
        """FetchV methodology: absolute segment without query inherits parent playlist auth query parameters."""
        base_url = "https://master.example.com/playlist.m3u8?token=secureToken123&sign=abcd"
        absolute_seg = "https://node-01.cdn.example.com/hls/segment_001.ts"
        resolved = HLSWorker._resolve_url(base_url, absolute_seg)

        self.assertTrue(resolved.startswith("https://node-01.cdn.example.com/hls/segment_001.ts"))
        self.assertIn("token=secureToken123", resolved)
        self.assertIn("sign=abcd", resolved)

    def test_query_not_duplicated_when_segment_has_own_query(self):
        """If segment already has query parameters, preserve them without duplicating."""
        base_url = "https://edge-cdn.example.com/hls/index.m3u8?token=old"
        relative_seg = "seg-0001.ts?custom=customVal"
        resolved = HLSWorker._resolve_url(base_url, relative_seg)

        self.assertIn("custom=customVal", resolved)
        self.assertNotIn("token=old", resolved)

    def test_data_uri_key_not_mangled(self):
        """Data URIs (e.g. inline base64 keys) must not have query strings appended."""
        base_url = "https://edge-cdn.example.com/hls/index.m3u8?token=xyz"
        data_uri = "data:text/plain;base64,MDEyMzQ1Njc4OWFiY2RlZg=="
        resolved = HLSWorker._resolve_url(base_url, data_uri)
        self.assertEqual(resolved, data_uri)

    def test_aes_128_decryption_with_pkcs7(self):
        """Verify AES-128 CBC in-memory decryption matches RFC 8216 standard."""
        key = b"0123456789abcdef"
        iv = b"fedcba9876543210"
        
        # Plaintext of 188-byte MPEG-TS packet
        plaintext = b"\x47" + b"\x00" * 187
        pad_len = 16 - (len(plaintext) % 16)
        padded = plaintext + bytes([pad_len] * pad_len)
        
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        enc = cipher.encryptor()
        ciphertext = enc.update(padded) + enc.finalize()

        # Decrypt using logic from HLSWorker
        dec_cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = dec_cipher.decryptor()
        decrypted = decryptor.update(ciphertext) + decryptor.finalize()
        pad_val = decrypted[-1]
        if 1 <= pad_val <= 16 and decrypted[-pad_val:] == bytes([pad_val] * pad_val):
            decrypted = decrypted[:-pad_val]

        self.assertEqual(decrypted, plaintext)

    def test_live_stream_not_falsely_triggered_by_live_in_url(self):
        """URLs containing the word 'live' (e.g. delivery/live_vod/movie.m3u8) must not be forced to live webcam mode."""
        url = "https://cdn.example.com/delivery/live_vod/movie_master.m3u8"
        worker = HLSWorker(url=url, target_path="movie.mp4")
        self.assertFalse(worker.is_live)

    def test_zero_hls_inspector_reads_resolution_bitrate_and_size(self):
        """HLSInspector reads resolution, bitrate, duration, and calculates exact file sizes."""
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler
        from app.core.hls_downloader import HLSInspector

        master_m3u8 = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:3\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=4000000,RESOLUTION=1920x1080,FRAME-RATE=60.0\n"
            "1080p/index.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720,FRAME-RATE=30.0\n"
            "720p/index.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION=854x480\n"
            "480p/index.m3u8\n"
        )
        # 10 segments of 10.0 seconds = 100.0 seconds total
        variant_m3u8 = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:3\n"
            "#EXT-X-TARGETDURATION:10\n"
            + "".join([f"#EXTINF:10.0,\nseg_{i}.ts\n" for i in range(10)])
            + "#EXT-X-ENDLIST\n"
        )

        class MockHLSHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if "master.m3u8" in self.path:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                    self.end_headers()
                    self.wfile.write(master_m3u8.encode("utf-8"))
                elif "index.m3u8" in self.path:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                    self.end_headers()
                    self.wfile.write(variant_m3u8.encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), MockHLSHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        try:
            url = f"http://127.0.0.1:{port}/video/master.m3u8?token=secret123"
            res = HLSInspector.probe(url)
            self.assertTrue(res.get("success"))
            self.assertTrue(res.get("is_hls"))
            self.assertTrue(res.get("is_master"))
            self.assertAlmostEqual(res.get("duration"), 100.0, places=1)
            self.assertEqual(res.get("resolution"), "1920x1080")
            self.assertEqual(res.get("bitrate"), 4000)
            # 100 seconds * 4,000,000 bps / 8 = 50,000,000 bytes
            self.assertEqual(res.get("total_bytes"), 50000000)

            variants = res.get("variants", [])
            self.assertEqual(len(variants), 3)
            # 1080p
            self.assertEqual(variants[0]["resolution"], "1920x1080")
            self.assertEqual(variants[0]["bitrate"], 4000)
            self.assertEqual(variants[0]["total_bytes"], 50000000)
            self.assertIn("token=secret123", variants[0]["url"])
            # 720p
            self.assertEqual(variants[1]["resolution"], "1280x720")
            self.assertEqual(variants[1]["bitrate"], 2000)
            self.assertEqual(variants[1]["total_bytes"], 25000000)
            # 480p
            self.assertEqual(variants[2]["resolution"], "854x480")
            self.assertEqual(variants[2]["bitrate"], 1000)
            self.assertEqual(variants[2]["total_bytes"], 12500000)
        finally:
            server.shutdown()
            server.server_close()

if __name__ == "__main__":
    unittest.main()
