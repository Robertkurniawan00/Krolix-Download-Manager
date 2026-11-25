"""
Krolix Download Manager - Local HTTP API Server for Browser Extension Integration
Listens on http://127.0.0.1:9666
"""

import os, re, json, threading, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from PyQt6.QtCore import QObject, pyqtSignal

class ApiHandler(BaseHTTPRequestHandler):
    server_instance = None # Set by ApiServer

    def _is_host_allowed(self) -> bool:
        raw_host = self.headers.get("Host", "").strip().lower()
        if raw_host.startswith("[") and "]" in raw_host:
            host_name = raw_host[1:raw_host.index("]")]
        elif raw_host in ("::1", "127.0.0.1", "localhost"):
            host_name = raw_host
        else:
            host_name = raw_host.split(":")[0]
        return host_name in ["127.0.0.1", "localhost", "::1"]

    def _is_origin_allowed(self) -> bool:
        origin = self.headers.get("Origin", "")
        if not origin:
            # Loopback direct non-browser requests (native messenger, local script, curl)
            sec_fetch = self.headers.get("Sec-Fetch-Site", "").lower()
            if sec_fetch in ("cross-site", "same-site"):
                return False
            return True

        origin_lower = origin.lower()
        # Allow trusted browser extension protocols
        if origin_lower.startswith((
            "chrome-extension://",
            "moz-extension://",
            "edge-extension://",
            "opera-extension://",
            "safari-web-extension://"
        )):
            return True

        # Allow local loopback origins
        import urllib.parse
        try:
            parsed = urllib.parse.urlparse(origin_lower)
            if parsed.hostname in ("127.0.0.1", "localhost", "::1"):
                return True
        except Exception:
            return False

        return False

    @staticmethod
    def _is_safe_save_dir(save_dir: str) -> bool:
        if not save_dir:
            return True
        try:
            norm = save_dir.strip()
            if norm.startswith("\\\\") or norm.startswith("//"):
                return False
            abs_dir = os.path.abspath(norm).lower()
            # Block system directories
            blocked_prefixes = []
            for env_var in ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
                val = os.environ.get(env_var)
                if val:
                    blocked_prefixes.append(os.path.abspath(val).lower())

            # Explicitly block Windows Startup directories
            appdata = os.environ.get("APPDATA")
            if appdata:
                startup_user = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
                blocked_prefixes.append(os.path.abspath(startup_user).lower())

            for blocked in blocked_prefixes:
                if abs_dir == blocked or abs_dir.startswith(blocked + os.sep):
                    return False
            return True
        except Exception:
            return False

    def _set_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        origin = self.headers.get("Origin", "")
        # Strictly restrict Access-Control-Allow-Origin to authorized extensions or loopback
        if origin and self._is_origin_allowed():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, X-Krolix-Client, X-Zero-Client, Access-Control-Request-Private-Network, *")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "86400")
        elif not origin:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()

    def do_OPTIONS(self):
        if not self._is_host_allowed() or not self._is_origin_allowed():
            self.send_response(403)
            self.end_headers()
            return
        self._set_headers(200)
        self.wfile.write(b"")

    @staticmethod
    def _sanitize_filename(raw_name: str, fallback_url: str = "") -> str:
        clean_base = os.path.basename((raw_name or "").replace("\\", "/"))
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', clean_base).strip('. ')
        if not safe and fallback_url:
            if fallback_url.lower().startswith("magnet:"):
                safe = "magnet_download.torrent"
            else:
                url_base = os.path.basename(fallback_url.split('?')[0].split('#')[0])
                safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', url_base).strip('. ')
        return safe or "download_file"

    @staticmethod
    def _is_allowed_url(url: str) -> bool:
        return url.lower().startswith(('http://', 'https://', 'ftp://', 'magnet:'))

    def do_GET(self):
        if not self._is_host_allowed() or not self._is_origin_allowed():
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Forbidden: Origin or Host unauthorized"}).encode('utf-8'))
            return

        req_path = urllib.parse.urlsplit(self.path).path
        if req_path in ['/', '/ping', '/status', '/api/status']:
            self._set_headers(200)
            port_num = self.server.server_address[1] if (self.server and hasattr(self.server, 'server_address')) else 9666

            lic_payload = {
                "is_full": False,
                "is_master": False,
                "status": "trial",
                "registered_name": "",
                "tier": "Trial Mode"
            }
            try:
                from ..core.license_manager import LicenseManager
                db = None
                if ApiHandler.server_instance:
                    p = ApiHandler.server_instance.parent()
                    if p and hasattr(p, 'db'):
                        db = p.db
                    elif hasattr(ApiHandler.server_instance, 'db'):
                        db = ApiHandler.server_instance.db
                lic_info = LicenseManager.get_instance(db).get_license_display_info()
                lic_payload = {
                    "is_full": bool(lic_info.get("is_full")),
                    "is_master": bool(lic_info.get("is_master")),
                    "status": str(lic_info.get("status", "")),
                    "registered_name": lic_info.get("registered_name", ""),
                    "tier": "Advance Master Mode" if lic_info.get("is_master") else ("Full Version" if lic_info.get("is_full") else "Trial Mode")
                }
            except Exception:
                pass

            res = {
                "status": "online",
                "online": True,
                "ok": True,
                "app": "Krolix Download Manager",
                "version": "2.6.0",
                "port": port_num,
                "license": lic_payload
            }
            self.wfile.write(json.dumps(res).encode('utf-8'))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found"}).encode('utf-8'))

    def do_POST(self):
        if not self._is_host_allowed() or not self._is_origin_allowed():
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Forbidden: Origin or Host unauthorized"}).encode('utf-8'))
            return

        try:
            content_length = int(self.headers.get('Content-Length', 0) or 0)
        except (ValueError, TypeError):
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Invalid Content-Length"}).encode('utf-8'))
            return
        if content_length < 0:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Invalid Content-Length"}).encode('utf-8'))
            return
        # Protect against payload flooding DoS while allowing large M3U8 playlist caches (up to 16 MB)
        if content_length > 16 * 1024 * 1024:
            self._set_headers(413)
            self.wfile.write(json.dumps({"error": "Payload too large"}).encode('utf-8'))
            return

        post_data = self.rfile.read(content_length).decode('utf-8', errors='ignore') if content_length > 0 else ""
        
        try:
            data = json.loads(post_data) if post_data else {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}

        req_path = urllib.parse.urlsplit(self.path).path
        origin = self.headers.get('Origin', '')
        origin_trusted_for_silent = (not origin) or origin.lower().startswith((
            'chrome-extension://', 'moz-extension://', 'edge-extension://',
            'http://127.0.0.1', 'http://localhost'
        ))

        if req_path in ('/api/download', '/download'):
            url = str(data.get('url', '') or '').strip()
            # Security: Validate URL scheme
            if not self._is_allowed_url(url):
                self._set_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Skema URL tidak diizinkan"}).encode('utf-8'))
                return

            raw_filename = str(data.get('filename', '') or '').strip()
            safe_filename = self._sanitize_filename(raw_filename, url)

            from ..core.media_grabber import is_ad_or_junk_media
            if is_ad_or_junk_media(url, safe_filename):
                self._set_headers(400)
                self.wfile.write(json.dumps({"success": False, "ok": False, "error": "URL video iklan atau preview diabaikan"}).encode('utf-8'))
                return

            download_payload = dict(data)
            download_payload['url'] = url
            download_payload['filename'] = safe_filename
            headers = dict(download_payload.get('headers') or {}) if isinstance(download_payload.get('headers'), dict) else {}
            if data.get('referer') and 'Referer' not in headers:
                headers['Referer'] = str(data['referer'])
            if data.get('user_agent') and 'User-Agent' not in headers:
                headers['User-Agent'] = str(data['user_agent'])
            if data.get('cookies') and 'Cookie' not in headers:
                headers['Cookie'] = str(data['cookies'])
            download_payload['headers'] = headers
            
            # Security: Validate and sanitize save_dir
            if 'save_dir' in download_payload and not self._is_safe_save_dir(download_payload['save_dir']):
                download_payload['save_dir'] = ''

            # Security: Prevent unauthorized silent downloads from arbitrary origins
            if not origin_trusted_for_silent:
                download_payload['silent'] = False

            if url and ApiHandler.server_instance:
                ApiHandler.server_instance.download_requested.emit(download_payload)
                if hasattr(ApiHandler.server_instance, 'on_download_request') and callable(ApiHandler.server_instance.on_download_request):
                    try:
                        ApiHandler.server_instance.on_download_request(url, safe_filename, data.get('category', 'general'))
                    except Exception:
                        pass
                self._set_headers(200)
                self.wfile.write(json.dumps({"success": True, "ok": True, "message": "Unduhan diterima"}).encode('utf-8'))
            else:
                self._set_headers(400)
                self.wfile.write(json.dumps({"success": False, "ok": False, "error": "URL tidak valid"}).encode('utf-8'))
        
        elif req_path in ('/api/batch-download', '/batch-download'):
            items = data.get('items', [])
            urls = data.get('urls', [])
            if not items and isinstance(urls, list):
                items = [{'url': u} for u in urls if isinstance(u, str)]

            if isinstance(items, list) and items and ApiHandler.server_instance:
                from ..core.media_grabber import is_ad_or_junk_media
                filtered_items = []
                for it in items:
                    if isinstance(it, dict):
                        it_copy = dict(it)
                        it_url = str(it_copy.get('url', '') or '').strip()
                        it_fn_raw = str(it_copy.get('filename', '') or '').strip()
                    elif isinstance(it, str):
                        it_url = it.strip()
                        it_fn_raw = ''
                        it_copy = {'url': it_url}
                    else:
                        continue
                    if not self._is_allowed_url(it_url):
                        continue
                    it_fn = self._sanitize_filename(it_fn_raw, it_url) if it_fn_raw else ''
                    if not is_ad_or_junk_media(it_url, it_fn):
                        it_copy['url'] = it_url
                        if it_fn:
                            it_copy['filename'] = it_fn
                        filtered_items.append(it_copy)

                if not filtered_items:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"success": False, "error": "No valid items provided"}).encode('utf-8'))
                    return

                safe_save = data.get('save_dir', '')
                if safe_save and not self._is_safe_save_dir(safe_save):
                    safe_save = ''

                batch_payload = {
                    'referer': data.get('referer', ''),
                    'user_agent': data.get('user_agent', ''),
                    'cookies': data.get('cookies', ''),
                    'save_dir': safe_save,
                    'items': filtered_items,
                    'silent': bool(data.get('silent', False)) and origin_trusted_for_silent,
                    'queue_only': bool(data.get('queue_only', False))
                }
                ApiHandler.server_instance.batch_requested.emit(batch_payload)
                self._set_headers(200)
                self.wfile.write(json.dumps({"success": True, "count": len(filtered_items)}).encode('utf-8'))
            else:
                self._set_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "No items provided"}).encode('utf-8'))

        elif req_path == '/api/video-detected':
            videos = data.get('videos', [])
            if isinstance(videos, list) and ApiHandler.server_instance:
                from ..core.media_grabber import is_ad_or_junk_media
                # Sanitize video items
                clean_videos = []
                for v in videos[:50]:
                    if isinstance(v, dict) and 'url' in v:
                        v_url = str(v.get('url', '') or '')
                        v_name = v.get('name', '') or v.get('title', '')
                        v_height = v.get('height', 0)
                        if not is_ad_or_junk_media(v_url, v_name, v_height):
                            clean_videos.append(v)
                if clean_videos:
                    ApiHandler.server_instance.video_detected.emit(clean_videos)
            self._set_headers(200)
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))

        elif req_path == '/api/media_info':
            url = str(data.get('url', '') or '').strip()
            if not url.lower().startswith(('http://', 'https://')):
                self._set_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "URL tidak valid"}).encode('utf-8'))
                return
            try:
                from ..core.media_grabber import MediaGrabber
                info, err = MediaGrabber.get_media_info(url)
                self._set_headers(200)
                if info:
                    self.wfile.write(json.dumps(info).encode('utf-8'))
                else:
                    self.wfile.write(json.dumps({"formats": [], "error": err or "Format tidak ditemukan"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(200)
                self.wfile.write(json.dumps({"formats": [], "error": str(e)}).encode('utf-8'))

        elif req_path in ('/api/restore', '/restore'):
            target_hwnd = 0
            if ApiHandler.server_instance:
                ApiHandler.server_instance.restore_requested.emit()
                parent_win = ApiHandler.server_instance.parent()
                if parent_win:
                    target_hwnd = int(getattr(parent_win, "_cached_hwnd", 0) or 0)
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "message": "Window restored",
                "pid": os.getpid(),
                "hwnd": target_hwnd
            }).encode('utf-8'))

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Unknown endpoint"}).encode('utf-8'))

    def log_message(self, format, *args):
        # Suppress console spam
        pass


class ApiServer(QObject):
    download_requested = pyqtSignal(dict) # full download payload dict
    batch_requested = pyqtSignal(dict)    # batch download payload dict
    video_detected = pyqtSignal(list)
    restore_requested = pyqtSignal()

    def __init__(self, port=9666, parent=None, host="127.0.0.1", on_download_requested=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.httpd = None
        self._thread = None
        ApiHandler.server_instance = self
        if on_download_requested:
            self.download_requested.connect(on_download_requested)

    def start(self):
        try:
            ThreadingHTTPServer.daemon_threads = True
            ThreadingHTTPServer.allow_reuse_address = True
            self.httpd = ThreadingHTTPServer((self.host, self.port), ApiHandler)
            self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self._thread.start()
            print(f"[ApiServer] Running on http://{self.host}:{self.port}")
        except Exception as e:
            print(f"[ApiServer] Error starting server: {e}")

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass

LocalAPIServer = ApiServer
