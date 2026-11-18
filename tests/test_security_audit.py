import unittest
import os
from app.services.api_server import ApiHandler
from app.core.post_actions import PostActionManager

class DummyHandler:
    def __init__(self, headers):
        self.headers = headers
    
    _is_host_allowed = ApiHandler._is_host_allowed
    _is_origin_allowed = ApiHandler._is_origin_allowed
    _is_safe_save_dir = ApiHandler._is_safe_save_dir

class TestSecurityPatches(unittest.TestCase):
    def test_host_filtering(self):
        h_good = DummyHandler({"Host": "127.0.0.1:9666"})
        self.assertTrue(h_good._is_host_allowed())

        h_local = DummyHandler({"Host": "localhost:9666"})
        self.assertTrue(h_local._is_host_allowed())

        h_ipv6 = DummyHandler({"Host": "::1"})
        self.assertTrue(h_ipv6._is_host_allowed())

        h_evil = DummyHandler({"Host": "attacker.com:9666"})
        self.assertFalse(h_evil._is_host_allowed())

    def test_origin_filtering(self):
        # Browser extension origins
        h_chrome = DummyHandler({"Origin": "chrome-extension://abcdefghijklmnop"})
        self.assertTrue(h_chrome._is_origin_allowed())

        h_moz = DummyHandler({"Origin": "moz-extension://1234-5678-90ab"})
        self.assertTrue(h_moz._is_origin_allowed())

        h_edge = DummyHandler({"Origin": "edge-extension://abcdefghijklmnop"})
        self.assertTrue(h_edge._is_origin_allowed())

        # Local loopback origins
        h_loop1 = DummyHandler({"Origin": "http://127.0.0.1:8080"})
        self.assertTrue(h_loop1._is_origin_allowed())

        h_loop2 = DummyHandler({"Origin": "http://localhost:3000"})
        self.assertTrue(h_loop2._is_origin_allowed())

        # Malicious external origins
        h_evil = DummyHandler({"Origin": "https://attacker.site"})
        self.assertFalse(h_evil._is_origin_allowed())

        h_evil_cors = DummyHandler({"Origin": "http://evil-drive-by.com"})
        self.assertFalse(h_evil_cors._is_origin_allowed())

        h_null = DummyHandler({"Origin": "null"})
        self.assertFalse(h_null._is_origin_allowed())

        # Direct loopback without Origin header
        h_direct = DummyHandler({})
        self.assertTrue(h_direct._is_origin_allowed())

        # Cross-site probe without Origin header
        h_cross = DummyHandler({"Sec-Fetch-Site": "cross-site"})
        self.assertFalse(h_cross._is_origin_allowed())

    def test_safe_save_dir_filtering(self):
        # Safe paths
        self.assertTrue(ApiHandler._is_safe_save_dir(r"D:\Downloads"))
        self.assertTrue(ApiHandler._is_safe_save_dir(r"C:\Users\Public\Downloads"))
        self.assertTrue(ApiHandler._is_safe_save_dir(""))

        # Unsafe Windows system paths
        win_dir = os.environ.get("SystemRoot", r"C:\Windows")
        self.assertFalse(ApiHandler._is_safe_save_dir(win_dir))
        self.assertFalse(ApiHandler._is_safe_save_dir(os.path.join(win_dir, "System32")))
        self.assertFalse(ApiHandler._is_safe_save_dir(os.path.join(win_dir, "System32", "drivers")))

        # Unsafe Windows startup paths
        appdata = os.environ.get("APPDATA")
        if appdata:
            startup_dir = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
            self.assertFalse(ApiHandler._is_safe_save_dir(startup_dir))
            self.assertFalse(ApiHandler._is_safe_save_dir(os.path.join(startup_dir, "nested")))

    def test_post_action_manager_supported_modes(self):
        # Test abort_shutdown executes without crashing
        try:
            PostActionManager.abort_shutdown()
        except Exception as e:
            self.fail(f"abort_shutdown raised an unexpected exception: {e}")

if __name__ == "__main__":
    unittest.main()
