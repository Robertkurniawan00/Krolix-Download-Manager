import os
import sys
import tempfile
import unittest

from app.core.database import Database
from app.core.license_manager import LicenseManager, LicenseStatus
from app.utils.security_guard import SecurityGuard


class TestAntiTamperShield(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_shield.db")
        self.db = Database(self.db_path)
        LicenseManager._instance = None
        self.mgr = LicenseManager(self.db)

    def tearDown(self):
        try:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_environment_sanitizer(self):
        os.environ["PYTHONPATH"] = r"C:\attacker\malicious_lib"
        os.environ["PYTHONHOME"] = r"C:\attacker\hacked_python"
        os.environ["PYTHONSTARTUP"] = r"C:\attacker\inject.py"

        SecurityGuard.sanitize_environment()

        self.assertNotIn("PYTHONPATH", os.environ)
        self.assertNotIn("PYTHONHOME", os.environ)
        self.assertNotIn("PYTHONSTARTUP", os.environ)
        self.assertTrue(sys.dont_write_bytecode)

    def test_callable_integrity_guard(self):
        # Genuine method on LicenseManager must pass
        self.assertTrue(SecurityGuard.verify_callable_integrity(self.mgr.is_feature_allowed, "app.core.license_manager"))
        self.assertTrue(SecurityGuard.verify_callable_integrity(self.mgr.get_status, "app.core.license_manager"))

        # Non-callable or string must fail
        self.assertFalse(SecurityGuard.verify_callable_integrity("not_a_func", "app.core.license_manager"))

        # Monkeypatched lambda patch must fail
        fake_lambda = lambda s, f: True
        self.assertFalse(SecurityGuard.verify_callable_integrity(fake_lambda, "app.core.license_manager"))

        # Function belonging to foreign module must fail
        def dummy_foreign():
            return True
        self.assertFalse(SecurityGuard.verify_callable_integrity(dummy_foreign, "app.core.license_manager"))

    def test_cryptographic_feature_session_token(self):
        # Valid active trial must produce a 32-byte cryptographic token
        tok = self.mgr.get_feature_session_token("high_connections")
        self.assertIsNotNone(tok)
        self.assertEqual(len(tok), 32)

        # Verification of authentic token must succeed
        self.assertTrue(self.mgr.verify_feature_token("high_connections", tok))

        # Verification of tampered token must fail
        bad_token = b"\x00" * 32
        self.assertFalse(self.mgr.verify_feature_token("high_connections", bad_token))
        self.assertFalse(self.mgr.verify_feature_token("high_connections", None))

        # Different feature name mismatch must fail
        self.assertFalse(self.mgr.verify_feature_token("unlimited_concurrent", tok))

    def test_honeypot_tampered_state_drops_token(self):
        # Force a fake serial in the database
        self.db.set_setting("license_status", "fake_serial")
        tok = self.mgr.get_feature_session_token("high_connections")
        # Token derivation must fail when license is fake
        self.assertIsNone(tok)
        self.assertFalse(self.mgr.verify_feature_token("high_connections", tok))


if __name__ == "__main__":
    unittest.main()
