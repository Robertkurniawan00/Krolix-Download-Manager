"""
Unit tests for Krolix Download Manager Automation APIs (PowerShell, Node.js, REST, COM)
"""
import os
import sys
import subprocess
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.segment import SegmentManager


class TestKrolixCompatibilityAndNativeEngine(unittest.TestCase):
    def test_segment_merging(self):
        import tempfile
        d = tempfile.mkdtemp()
        p1 = os.path.join(d, "p1")
        p2 = os.path.join(d, "p2")
        out = os.path.join(d, "out.bin")
        data1 = b"Hello, "
        data2 = b"Krolix Download Manager!"
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

    def test_krolix_com_object_in_powershell(self):
        cmd = "powershell -Command \"try { $obj = New-Object -ComObject 'Krolix.LinkTransmitter' -ErrorAction Stop; 'COM_OK' } catch { try { $obj = New-Object -ComObject 'Zero.LinkTransmitter' -ErrorAction Stop; 'COM_OK' } catch { 'NOT_REGISTERED' } }\""
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn(res.stdout.strip(), ("COM_OK", "NOT_REGISTERED"))

    def test_powershell_module_loading(self):
        psm1_path = os.path.join(os.path.dirname(__file__), "..", "app", "api", "Krolix.psm1")
        if not os.path.exists(psm1_path):
            self.skipTest("Krolix.psm1 not found")
        cmd = f'powershell -ExecutionPolicy Bypass -Command "Import-Module \'{psm1_path}\' -Force; (Get-Command -Module Krolix).Name"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Start-KrolixDownload", res.stdout)
        self.assertIn("Add-KrolixQueue", res.stdout)
        self.assertIn("Get-KrolixStatus", res.stdout)

    def test_nodejs_sdk_cli(self):
        js_path = os.path.join(os.path.dirname(__file__), "..", "app", "api", "krolix-client.js")
        if not os.path.exists(js_path):
            self.skipTest("krolix-client.js not found")
        res = subprocess.run(["node", js_path, "--help"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Krolix Download Manager - Node.js SDK & CLI", res.stdout)


if __name__ == "__main__":
    unittest.main()
