import unittest
from app.core.pikpak_resolver import PikPakResolver


class TestPikPakResolver(unittest.TestCase):
    def test_is_pikpak_url(self):
        valid_urls = [
            "https://mypikpak.com/s/VN_x98abc",
            "http://mypikpak.net/s/VN_x98abc/parent_123",
            "https://www.mypikpak.com/drive/url/folder999?pwd=123",
            "https://api-drive.mypikpak.com/drive/v1/share?share_id=xyz789",
        ]
        invalid_urls = [
            "https://google.com/search?q=pikpak",
            "https://youtube.com/watch?v=123",
            "https://mediafire.com/file/abc",
        ]
        for u in valid_urls:
            self.assertTrue(PikPakResolver.is_pikpak_url(u), f"Should match: {u}")
        for u in invalid_urls:
            self.assertFalse(PikPakResolver.is_pikpak_url(u), f"Should not match: {u}")

    def test_parse_share_url(self):
        u1 = "https://mypikpak.com/s/VN_ABC123"
        s1, p1, pwd1 = PikPakResolver.parse_share_url(u1)
        self.assertEqual(s1, "VN_ABC123")
        self.assertEqual(p1, "")
        self.assertEqual(pwd1, "")

        u2 = "https://mypikpak.net/s/SHARE999/SUBFOLDER?pwd=pass123&other=val"
        s2, p2, pwd2 = PikPakResolver.parse_share_url(u2)
        self.assertEqual(s2, "SHARE999")
        self.assertEqual(p2, "SUBFOLDER")
        self.assertEqual(pwd2, "pass123")

    def test_compute_captcha_sign_format(self):
        device_id = "0123456789abcdef0123456789abcdef"
        ts = "1731100000000"
        sign = PikPakResolver._compute_captcha_sign(device_id, ts)
        self.assertTrue(sign.startswith("1."))
        self.assertEqual(len(sign), 34)  # "1." + 32-char hex md5

    def test_not_found_handling(self):
        fake_url = "https://mypikpak.com/s/NON_EXISTENT_SHARE_ID_999999"
        with self.assertRaises(ValueError) as ctx:
            PikPakResolver.resolve_public_share(fake_url)
        self.assertIn("tidak ditemukan", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
