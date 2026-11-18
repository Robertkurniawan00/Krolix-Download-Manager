import unittest
import os
import subprocess
import hashlib
import tempfile
from app.core.hasher import FileHasher
from app.core.segment import get_native_engine_path, SegmentManager
from main import parse_standard_cli

class TestZeroCompatibilityAndNativeEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine_path = get_native_engine_path()
        if os.path.exists(engine_path):
            subprocess.run([engine_path, "register"], capture_output=True)
            cls.server_proc = subprocess.Popen([engine_path, "-Embedding"])
            import time
            time.sleep(0.6)
        else:
            cls.server_proc = None

    @classmethod
    def tearDownClass(cls):
        if cls.server_proc:
            try:
                cls.server_proc.kill()
            except Exception:
                pass

    def test_standard_cli_parsing(self):
        # Test standard flags: /d URL /p path /f filename /n /a /s
        argv = [
            "Zero.exe",
            "/d", "https://example.com/test.zip",
            "/p", "C:\\Downloads",
            "/f", "my_custom_name.zip",
            "/n",
            "/a"
        ]
        parsed = parse_standard_cli(argv)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["url"], "https://example.com/test.zip")
        self.assertEqual(parsed["save_dir"], "C:\\Downloads")
        self.assertEqual(parsed["filename"], "my_custom_name.zip")
        self.assertTrue(parsed["silent"])
        self.assertTrue(parsed["queue_only"])

    def test_standard_cli_start_queue(self):
        argv = ["Zero.exe", "/s"]
        parsed = parse_standard_cli(argv)
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["start_queue"])

    def test_native_engine_exists(self):
        engine_path = get_native_engine_path()
        self.assertTrue(os.path.exists(engine_path), f"Native engine not found at {engine_path}")
        
        # Test ping
        res = subprocess.run([engine_path, "ping"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("ZERO_NATIVE_OK", res.stdout)

    def test_native_engine_hash_matches_python(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Zero Download Assistant Accelerated Hashing Content 1234567890!@#$%^&*()")
            tmp_path = f.name

        try:
            for algo in ["md5", "sha1", "sha256"]:
                with open(tmp_path, "rb") as rf:
                    h_py = getattr(hashlib, algo)(rf.read()).hexdigest()
                h_zero = FileHasher.calculate_hash(tmp_path, algo)
                self.assertEqual(h_zero, h_py, f"{algo} hash mismatch between native C# engine and python hashlib")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_native_engine_merge_chunks(self):
        temp_dir = tempfile.mkdtemp()
        p1 = os.path.join(temp_dir, "chunk1.bin")
        p2 = os.path.join(temp_dir, "chunk2.bin")
        out = os.path.join(temp_dir, "merged.bin")

        data1 = b"CHUNK_1_DATA_" * 1000
        data2 = b"CHUNK_2_DATA_" * 1000

        with open(p1, "wb") as f:
            f.write(data1)
        with open(p2, "wb") as f:
            f.write(data2)

        merged = SegmentManager.merge_files([p1, p2], out)
        self.assertTrue(merged)
        self.assertTrue(os.path.exists(out))
        self.assertEqual(os.path.getsize(out), len(data1) + len(data2))

        with open(out, "rb") as f:
            self.assertEqual(f.read(), data1 + data2)

    def test_zero_com_object_in_powershell(self):
        # Verify that Zero.LinkTransmitter can be instantiated by Windows COM
        cmd = "powershell -Command \"$zero = New-Object -ComObject 'Zero.LinkTransmitter'; if ($zero) { 'ZERO_COM_OK' } else { 'FAIL' }\""
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("ZERO_COM_OK", res.stdout)

    def test_powershell_module_loading(self):
        psm1_path = os.path.join(os.path.dirname(__file__), "..", "app", "api", "Zero.psm1")
        cmd = f'powershell -ExecutionPolicy Bypass -Command "Import-Module \'{psm1_path}\' -Force; (Get-Command -Module Zero).Name"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Start-ZeroDownload", res.stdout)
        self.assertIn("Add-ZeroQueue", res.stdout)
        self.assertIn("Get-ZeroStatus", res.stdout)

    def test_nodejs_sdk_cli(self):
        js_path = os.path.join(os.path.dirname(__file__), "..", "app", "api", "zero-client.js")
        res = subprocess.run(["node", js_path, "--help"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Zero Download Assistant - Node.js SDK & CLI", res.stdout)

    def test_ef2_format_roundtrip(self):
        import re
        sample_ef2 = "<\r\nhttps://example.com/movie.mp4\r\nfile=movie.mp4\r\npath=C:\\Downloads\r\nreferer=https://site.com\r\n>\r\n<\r\nhttps://example.com/archive.zip\r\nfile=archive.zip\r\n>\r\n"
        blocks = re.findall(r'<\s*(.*?)\s*>', sample_ef2, re.DOTALL)
        self.assertEqual(len(blocks), 2)
        
        b1_lines = [l.strip() for l in blocks[0].splitlines() if l.strip()]
        self.assertEqual(b1_lines[0], "https://example.com/movie.mp4")
        self.assertIn("file=movie.mp4", b1_lines)
        self.assertIn("path=C:\\Downloads", b1_lines)
        self.assertIn("referer=https://site.com", b1_lines)

        b2_lines = [l.strip() for l in blocks[1].splitlines() if l.strip()]
        self.assertEqual(b2_lines[0], "https://example.com/archive.zip")
        self.assertIn("file=archive.zip", b2_lines)

if __name__ == "__main__":
    unittest.main()
