import os
import threading
import urllib.request
import time
from typing import Callable, Optional, List
from .models import SegmentModel
from .speed_limiter import SpeedLimiter
from .link_resolver import CloudLinkResolver
from .ssl_manager import SSLManager
from ..utils.win32_native import Win32Native


CHUNK_SIZE = 256 * 1024  # 256 KB High-Throughput Buffer


def get_native_engine_path() -> str:
    candidates = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "native", "KrolixNativeEngine.exe")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "bin", "KrolixNativeEngine.exe")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "KrolixNativeEngine.exe")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "dist", "Zero", "KrolixNativeEngine.exe")),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Krolix Download Manager\KrolixNativeEngine.exe")
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return ""


class SegmentManager:
    @staticmethod
    def create_segments(total_bytes: int, num_segments: int, temp_base_path: str = "") -> List[SegmentModel]:
        if total_bytes <= 0 or num_segments <= 1:
            return [SegmentModel(index=0, start_byte=0, end_byte=max(0, total_bytes - 1))]
        
        segments = []
        chunk_size = total_bytes // num_segments
        
        for i in range(num_segments):
            start = i * chunk_size
            end = total_bytes - 1 if i == num_segments - 1 else (i + 1) * chunk_size - 1
            
            downloaded = 0
            if temp_base_path:
                part_path = f"{temp_base_path}.part{i}"
                if os.path.exists(part_path):
                    downloaded = os.path.getsize(part_path)
            
            seg = SegmentModel(index=i, start_byte=start, end_byte=end, downloaded_bytes=downloaded)
            if downloaded >= (end - start + 1) and (end - start + 1) > 0:
                seg.is_finished = True
            segments.append(seg)
            
        return segments
    @staticmethod
    def merge_files(part_paths: List[str], output_path: str) -> bool:
        valid_parts = [p for p in part_paths if os.path.exists(p)]
        if not valid_parts:
            return False

        native_exe = get_native_engine_path()
        if native_exe and os.path.exists(native_exe):
            try:
                import subprocess
                cmd = [native_exe, "merge", output_path] + valid_parts
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return True
            except Exception as ex:
                print(f"[ZeroNative] Native merge warning, falling back to python: {ex}")

        try:
            if os.path.dirname(output_path):
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'wb') as out_f:
                for p in valid_parts:
                    with open(p, 'rb') as in_f:
                        while True:
                            chunk = in_f.read(1024 * 1024)
                            if not chunk:
                                break
                            out_f.write(chunk)
            return True
        except Exception as e:
            print(f"Error merging files: {e}")
            return False

    @staticmethod
    def recombine_segments(segments: list, temp_base_path: str, final_save_path: str) -> bool:
        part_paths = [f"{temp_base_path}.part{seg.index}" for seg in segments]
        success = SegmentManager.merge_files(part_paths, final_save_path)
        if success:
            for p in part_paths:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        return success


class SegmentWorker(threading.Thread):
    def __init__(
        self,
        url: str,
        target_path: str,
        segment: SegmentModel,
        speed_limiter: SpeedLimiter,
        pause_event: threading.Event,
        cancel_event: threading.Event,
        on_bytes_received: Callable[[int], None],
        on_finished: Callable[[int, bool, Optional[str]], None],
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        max_retries: int = 3,
        on_total_bytes_discovered: Optional[Callable[[int], None]] = None,
        on_url_refreshed: Optional[Callable[[str, dict], None]] = None
    ):
        super().__init__(daemon=True)
        self.url = url
        self.target_path = target_path
        self.segment = segment
        self.speed_limiter = speed_limiter
        self.pause_event = pause_event
        self.cancel_event = cancel_event
        self.on_bytes_received = on_bytes_received
        self.on_finished = on_finished
        self.headers = headers or {}
        self.proxy = proxy
        self.max_retries = max_retries
        self.on_total_bytes_discovered = on_total_bytes_discovered
        self.on_url_refreshed = on_url_refreshed
        self._current_response = None

    def stop(self):
        """Signals worker to terminate and immediately closes any active HTTP socket."""
        self.cancel_event.set()
        self.pause_event.set()
        if hasattr(self, "_current_response") and self._current_response:
            try:
                self._current_response.close()
            except Exception:
                pass

    def pause(self):
        """Signals worker to pause and immediately aborts any blocking HTTP read to release file locks."""
        self.pause_event.clear()
        if hasattr(self, "_current_response") and self._current_response:
            try:
                self._current_response.close()
            except Exception:
                pass

    def _get_opener(self):
        handlers = []
        if self.proxy:
            proxy_clean = self.proxy.strip()
            # Support socks proxies (requires PySocks)
            if proxy_clean.startswith("socks"):
                try:
                    import socks
                    proxy_type = socks.SOCKS5 if "socks5" in proxy_clean else socks.SOCKS4
                    from urllib.parse import urlparse as _up
                    p = _up(proxy_clean)
                    if hasattr(socks, "SocksiPyHandler"):
                        handlers.append(socks.SocksiPyHandler(proxy_type, p.hostname, p.port or 1080, True, p.username, p.password))
                    else:
                        socks.set_default_proxy(proxy_type, p.hostname, p.port or 1080,
                                                username=p.username, password=p.password)
                        import socket
                        socket.socket = socks.socksocket
                except Exception:
                    pass
            else:
                handlers.append(urllib.request.ProxyHandler({
                    'http': proxy_clean,
                    'https': proxy_clean
                }))
        try:
            from urllib.parse import urlparse as _urlp
            host = _urlp(self.url).hostname or ""
            ctx = SSLManager.get_instance().get_ssl_context(host)
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        except Exception:
            pass
        return urllib.request.build_opener(*handlers)


    def run(self):
        self.url = CloudLinkResolver.resolve(self.url)
        retries = 0
        while retries <= self.max_retries:
            curr_start = self.segment.start_byte + self.segment.downloaded_bytes
            if self.segment.end_byte >= self.segment.start_byte and self.segment.end_byte > 0 and curr_start > self.segment.end_byte:
                self.segment.status = "Completed"
                self.on_finished(self.segment.index, True, None)
                return

            if self.cancel_event.is_set():
                self.segment.status = "Canceled"
                self.on_finished(self.segment.index, False, "Canceled")
                return

            self.segment.status = f"Connecting" if retries == 0 else f"Retrying ({retries}/{self.max_retries})"
            req_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Connection": "keep-alive"
            }
            req_headers.update(self.headers)
            req_headers = CloudLinkResolver.fix_headers(self.url, req_headers)

            if self.segment.end_byte > 0 and self.segment.end_byte >= curr_start:
                req_headers["Range"] = f"bytes={curr_start}-{self.segment.end_byte}"
            elif curr_start > 0:
                req_headers["Range"] = f"bytes={curr_start}-"
            else:
                req_headers.pop("Range", None)

            req = urllib.request.Request(self.url, headers=req_headers)
            opener = self._get_opener()

            try:
                with opener.open(req, timeout=30) as response:
                    self._current_response = response
                    # High-throughput socket optimization (SO_RCVBUF & TCP_NODELAY)
                    try:
                        raw_sock = getattr(getattr(response, "fp", None), "raw", None)
                        if hasattr(raw_sock, "_sock") and raw_sock._sock:
                            import socket
                            raw_sock._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                            raw_sock._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
                    except Exception:
                        pass
                    # Dynamically discover Content-Length or Content-Range total size if unknown
                    cr_header = response.headers.get("Content-Range")
                    cl_header = response.headers.get("Content-Length")
                    total_file_discovered = -1

                    if cr_header and "/" in cr_header:
                        tot_part = cr_header.split("/")[-1].strip()
                        if tot_part.isdigit():
                            total_file_discovered = int(tot_part)

                    if total_file_discovered > 0:
                        if self.segment.end_byte <= 0:
                            self.segment.end_byte = total_file_discovered - 1
                        if self.on_total_bytes_discovered:
                            try:
                                self.on_total_bytes_discovered(total_file_discovered)
                            except Exception:
                                pass
                    elif cl_header and cl_header.strip().isdigit():
                        cl = int(cl_header.strip())
                        if self.segment.end_byte <= 0:
                            self.segment.end_byte = max(0, curr_start + cl - 1)
                        if self.on_total_bytes_discovered:
                            try:
                                self.on_total_bytes_discovered(curr_start + cl)
                            except Exception:
                                pass

                    self.segment.status = "Receiving data"
                    
                    if os.path.dirname(self.target_path):
                        os.makedirs(os.path.dirname(self.target_path), exist_ok=True)
                    if not os.path.exists(self.target_path):
                        with open(self.target_path, "wb") as f_init:
                            pass

                    bytes_since_sync = 0
                    with open(self.target_path, "r+b") as f:
                        if curr_start > 0:
                            f.seek(curr_start)

                        while not self.cancel_event.is_set():
                            if not self.pause_event.is_set():
                                break

                            curr_pos = self.segment.start_byte + self.segment.downloaded_bytes
                            if self.segment.end_byte > 0:
                                rem = self.segment.end_byte - curr_pos + 1
                                if rem <= 0:
                                    break
                                read_size = min(CHUNK_SIZE, rem)
                            else:
                                rem = -1
                                read_size = CHUNK_SIZE

                            chunk = response.read(read_size)
                            if not chunk:
                                break

                            # Strictly re-clamp chunk against dynamic work-stealing segment split boundary
                            curr_pos = self.segment.start_byte + self.segment.downloaded_bytes
                            if self.segment.end_byte > 0:
                                max_allowed = self.segment.end_byte - curr_pos + 1
                                if max_allowed <= 0:
                                    break
                                if len(chunk) > max_allowed:
                                    chunk = chunk[:max_allowed]

                            if self.speed_limiter:
                                self.speed_limiter.wait_for_token(len(chunk))

                            f.write(chunk)

                            bytes_since_sync += len(chunk)
                            if bytes_since_sync >= 2 * 1024 * 1024:  # Sync to physical disk every 2 MB
                                f.flush()
                                Win32Native.flush_file_buffers(f)
                                bytes_since_sync = 0

                            self.segment.downloaded_bytes += len(chunk)
                            self.on_bytes_received(len(chunk))

                            # Exact boundary reached check
                            if self.segment.end_byte > 0 and (self.segment.start_byte + self.segment.downloaded_bytes) > self.segment.end_byte:
                                break

                        # Final commit of OS filesystem buffers to disk on exit
                        f.flush()
                        Win32Native.flush_file_buffers(f)
                    self._current_response = None

                if self.cancel_event.is_set():
                    self.segment.status = "Canceled"
                    self.on_finished(self.segment.index, False, "Canceled")
                    return
                elif not self.pause_event.is_set():
                    self.segment.status = "Paused"
                    self.on_finished(self.segment.index, False, "Paused")
                    return
                else:
                    if self.segment.end_byte <= 0:
                        self.segment.end_byte = max(0, self.segment.start_byte + self.segment.downloaded_bytes - 1)
                    self.segment.status = "Completed"
                    self.on_finished(self.segment.index, True, None)
                    return


            except Exception as e:
                if self.cancel_event.is_set():
                    self.segment.status = "Canceled"
                    self.on_finished(self.segment.index, False, "Canceled")
                    return
                if not self.pause_event.is_set():
                    self.segment.status = "Paused"
                    self.on_finished(self.segment.index, False, "Paused")
                    return

                # Auto-recovery for 403 Forbidden / 410 Gone / expired CDN tokens
                if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 410):
                    try:
                        fresh_url, fresh_headers = CloudLinkResolver.resolve_stream_url(self.url, self.headers)
                        if fresh_url != self.url or fresh_headers != self.headers:
                            print(f"[SegmentWorker] Auto-recovered stream URL on HTTP {e.code}: {fresh_url[:60]}...")
                            self.url = fresh_url
                            self.headers.update(fresh_headers)
                            if self.on_url_refreshed:
                                try:
                                    self.on_url_refreshed(fresh_url, fresh_headers)
                                except Exception:
                                    pass
                            time.sleep(1)
                            continue
                    except Exception as res_err:
                        print(f"[SegmentWorker] Failed to auto-recover stream: {res_err}")

                # Auto-recovery for DNS / URLError or domain migration
                if isinstance(e, urllib.error.URLError) or "11001" in str(e):
                    try:
                        resolved_url = CloudLinkResolver.resolve(self.url)
                        if resolved_url != self.url:
                            print(f"[SegmentWorker] Auto-redirected URL: {self.url} -> {resolved_url}")
                            self.url = resolved_url
                            if self.on_url_refreshed:
                                try:
                                    self.on_url_refreshed(resolved_url, self.headers)
                                except Exception:
                                    pass
                            time.sleep(1)
                            continue
                    except Exception:
                        pass

                retries += 1
                if retries <= self.max_retries:
                    time.sleep(1.5 * retries)
                else:
                    self.segment.status = "Error"
                    err_clean = str(e)
                    if "11001" in err_clean or "getaddrinfo" in err_clean:
                        err_clean = "Server / Host tidak ditemukan (Domain offline / DNS Error)"
                    self.on_finished(self.segment.index, False, err_clean)
                    return


