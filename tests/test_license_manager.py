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

    def test_idm_pattern_pro_validation(self):
        name = "Pengguna Zero"
        email = "user@zerodownload.com"
        valid_pro_key = self.mgr.DEFAULT_PRO_KEY  # ZR8X9-K7W4Q-H35V4-E1QZG

        # 1. Correct credentials -> Valid Pro
        valid, code, msg = self.mgr.validate_serial_key("Pengguna", "Zero", email, valid_pro_key)
        self.assertTrue(valid, msg)
        self.assertEqual(code, "VALID_PRO")

        # 2. Tampered email -> Invalid
        valid_bad_email, _, _ = self.mgr.validate_serial_key("Pengguna", "Zero", "attacker@evil.com", valid_pro_key)
        self.assertFalse(valid_bad_email)

        # 3. Tampered name -> Invalid
        valid_bad_name, _, _ = self.mgr.validate_serial_key("Hacker", "Pro", email, valid_pro_key)
        self.assertFalse(valid_bad_name)

    def test_advance_master_mode_activation(self):
        name = "Pengguna Zero"
        email = "user@zerodownload.com"
        master_key = self.mgr.DEFAULT_MASTER_KEY  # ZMMST-K7W4Q-R7Z52-W23XM

        valid, code, msg = self.mgr.validate_serial_key("Pengguna", "Zero", email, master_key)
        self.assertTrue(valid, msg)
        self.assertEqual(code, "VALID_MASTER")

        # Perform registration
        ok, reg_msg, reg_code = self.mgr.register("Pengguna", "Zero", email, master_key)
        self.assertTrue(ok)
        self.assertEqual(self.mgr.get_status(), LicenseStatus.MASTER_MODE)
        self.assertTrue(self.mgr.is_master_mode())
        self.assertTrue(self.mgr.is_full_version())

        # Advance Master Mode unlocks 64 segments!
        self.assertEqual(self.mgr.get_max_segments_allowed(), 64)
        self.assertEqual(self.mgr.get_max_concurrent_allowed(), 64)

        # Display info contains master badge
        info = self.mgr.get_license_display_info()
        self.assertTrue(info["is_master"])
        self.assertIn("Advance Master Mode", info["status_title"])

    def test_honeypot_keygen_detection(self):
        """Simulates an attacker using a keygen that reversed the decoy polynomial."""
        name = "Pengguna Zero"
        email = "user@zerodownload.com"
        fake_keygen_key = self.mgr.DEFAULT_KEYGEN_SAMPLE  # ZR8X9-K7W4Q-H35V4-KEY99

        valid, code, msg = self.mgr.validate_serial_key("Pengguna", "Zero", email, fake_keygen_key)
        self.assertFalse(valid)
        self.assertEqual(code, "FAKE_SERIAL_KEYGEN")
        self.assertIn("Keygen", msg)

        # Registering with a keygen key sets status to FAKE_SERIAL
        ok, _, reg_code = self.mgr.register("Pengguna", "Zero", email, fake_keygen_key)
        self.assertFalse(ok)
        self.assertEqual(reg_code, "FAKE_SERIAL_KEYGEN")
        self.assertEqual(self.mgr.get_status(), LicenseStatus.FAKE_SERIAL)

        # Features are immediately restricted
        self.assertFalse(self.mgr.is_feature_allowed("site_grabber"))
        self.assertEqual(self.mgr.get_max_segments_allowed(), 4)

    def test_blacklisted_serial_detection(self):
        """Tests that notoriously leaked serial keys from cracking forums are caught immediately."""
        name = "Pirate User"
        email = "pirate@torrents.ru"
        leaked_key = "7HL92-9F4K2-109KD-84720"

        valid, code, msg = self.mgr.validate_serial_key("Pirate", "User", email, leaked_key)
        self.assertFalse(valid)
        self.assertEqual(code, "FAKE_SERIAL_BLACKLIST")
        self.assertIn("daftar hitam", msg)

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
