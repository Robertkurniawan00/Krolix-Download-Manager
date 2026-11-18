import os
import unittest
import tempfile

from app.core.database import Database
from app.core.license_manager import LicenseManager, LicenseStatus


class TestLicenseManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_license.db")
        self.db = Database(self.db_path)
        # Reset singleton for clean isolated testing
        LicenseManager._instance = None
        self.mgr = LicenseManager(self.db)

    def tearDown(self):
        try:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_initial_trial_state(self):
        status = self.mgr.get_status()
        self.assertEqual(status, LicenseStatus.TRIAL)
        self.assertTrue(self.mgr.is_trial_active())
        self.assertFalse(self.mgr.is_full_version())
        self.assertFalse(self.mgr.is_master_mode())
        self.assertGreaterEqual(self.mgr.get_trial_days_remaining(), 29)

    def test_trial_feature_allowance(self):
        self.assertTrue(self.mgr.is_feature_allowed("site_grabber"))
        self.assertTrue(self.mgr.is_feature_allowed("scheduler"))
        self.assertEqual(self.mgr.get_max_segments_allowed(), 32)
        self.assertEqual(self.mgr.get_max_concurrent_allowed(), 32)

    def test_blacklisted_serial_detection(self):
        """Tests that notoriously leaked serial keys from cracking forums are caught immediately."""
        name = "Pirate User"
        email = "pirate@torrents.ru"
        leaked_key = "7HL92-9F4K2-109KD-84720"

        valid, code, msg = self.mgr.validate_serial_key("Pirate", "User", email, leaked_key)
        self.assertFalse(valid)
        self.assertEqual(code, "FAKE_SERIAL_BLACKLIST")
        self.assertIn("daftar hitam", msg)

    def test_invalid_serial_format(self):
        valid, code, msg = self.mgr.validate_serial_key("User", "Test", "user@test.com", "INVALID-SERIAL-FORMAT")
        self.assertFalse(valid)
        self.assertEqual(code, "INVALID_KEY")

    def test_database_tampering_defense(self):
        """Attacker manually modifies SQLite database to pretend to be Master Mode."""
        self.db.set_setting("license_status", "master_mode")
        self.db.set_setting("license_serial_key", "ZMMST-FAKE1-22222-33333")
        self.db.set_setting("license_user_first_name", "Hacker")
        self.db.set_setting("license_user_last_name", "Crack")
        self.db.set_setting("license_user_email", "hacker@crack.com")

        # get_status() re-verifies cryptographic HMAC and detects the fake
        status = self.mgr.get_status()
        self.assertIn(status, (LicenseStatus.EXPIRED, LicenseStatus.FAKE_SERIAL))
        self.assertFalse(self.mgr.is_master_mode())

    def test_expired_and_restricted_mode(self):
        self.mgr.set_trial_expired_for_testing()
        self.assertEqual(self.mgr.get_status(), LicenseStatus.EXPIRED)
        self.assertFalse(self.mgr.is_full_version())
        self.assertFalse(self.mgr.is_trial_active())
        self.assertEqual(self.mgr.get_trial_days_remaining(), 0)

        # Restricted features
        self.assertFalse(self.mgr.is_feature_allowed("site_grabber"))
        self.assertFalse(self.mgr.is_feature_allowed("scheduler"))
        self.assertEqual(self.mgr.get_max_segments_allowed(), 4)
        self.assertEqual(self.mgr.get_max_concurrent_allowed(), 2)


if __name__ == "__main__":
    unittest.main()
