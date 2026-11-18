import os
import sys
import time
import shutil
import tempfile
import threading
import subprocess
import urllib.parse
import urllib.request
import queue
import random
import hashlib
import re
import math
import xml.etree.ElementTree as ET
from typing import Optional, Callable, Dict, List, Tuple

from .audio_muxer import AudioMuxer
from .speed_limiter import SpeedLimiter
from .link_resolver import CloudLinkResolver
from ..utils.helpers import format_bytes, sanitize_filename

def _ensure_valid_certifi():
    """
    Ensures 'certifi' module has a valid callable .where() attribute.
    Protects against broken PEP 420 namespace packages (e.g. empty _internal/certifi dir).
    """
    try:
        import certifi as _certifi
        if not hasattr(_certifi, "where") or not callable(getattr(_certifi, "where", None)):
            import ssl
            _default_ca = ssl.get_default_verify_paths().cafile or ""
            _certifi.where = lambda: _default_ca
    except Exception:
        sys.modules.pop("certifi", None)


_ensure_valid_certifi()

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


def _dechunk_http_body(raw_bytes: bytes) -> Tuple[dict, bytes]:
    """
    Splits raw HTTP/1.1 response bytes into (headers_dict_lower, decoded_body_bytes),
    handling Transfer-Encoding: chunked, gzip, and deflate.
    """
    hdr_end = raw_bytes.find(b"\r\n\r\n")
    if hdr_end < 0:
        return {}, raw_bytes

    hdr_text = raw_bytes[:hdr_end].decode("latin1", errors="ignore")
    body = raw_bytes[hdr_end + 4:]
    hdr_dict = {}
    status_code = 200
    lines = hdr_text.splitlines()
    if lines and lines[0].startswith("HTTP/"):
        parts = lines[0].split()
        if len(parts) >= 2 and parts[1].isdigit():
            status_code = int(parts[1])
    hdr_dict["_status_code"] = status_code

    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            hdr_dict[k.strip().lower()] = v.strip()

    if "chunked" in hdr_dict.get("transfer-encoding", "").lower():
        out = bytearray()
        pos = 0
        while pos < len(body):
            rn = body.find(b"\r\n", pos)
            if rn < 0:
                break
            line_hex = body[pos:rn].split(b";")[0].strip()
            if not line_hex:
                pos = rn + 2
                continue
            try:
                chunk_len = int(line_hex, 16)
            except ValueError:
                break
            if chunk_len == 0:
                break
            start = rn + 2
            out.extend(body[start:start + chunk_len])
            pos = start + chunk_len + 2
        body = bytes(out)

    enc = hdr_dict.get("content-encoding", "").lower()
    if "gzip" in enc or (len(body) >= 2 and body[:2] == b"\x1f\x8b"):
        try:
            import gzip
            body = gzip.decompress(body)
        except Exception:
            pass
    elif "deflate" in enc:
        try:
            import zlib
            body = zlib.decompress(body)
        except Exception:
            try:
                import zlib
                body = zlib.decompress(body, -zlib.MAX_WBITS)
            except Exception:
                pass

    return hdr_dict, body


def fetch_url_with_dpi_bypass(url: str, headers: Optional[dict] = None, timeout: int = 14) -> Tuple[bytes, str]:
    """
    Fetches a URL using:
    1) MemoryBIO TLS ClientHello Fragmentation across all resolved A-record IPs
       (bypasses ISP SNI / Deep Packet Inspection firewalls like Indonesian TrustPositif / Kominfo).
    2) Automatic HTTP 301/302/303/307/308 redirect following.
    3) curl_cffi (Chrome TLS impersonation) fallback if available.
    Returns (raw_bytes, effective_url).
    """
    import ssl
    import socket

    current_url = url
    req_headers = dict(headers or {})
    if "User-Agent" not in req_headers and "user-agent" not in req_headers:
        req_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    last_err = None

    for _redirect in range(5):
        parsed = urllib.parse.urlsplit(current_url)
        host = parsed.hostname
        if not host:
            break
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path_query = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")

        # Resolve all IPv4 addresses for failover (e.g., multiple Cloudflare edge IPs)
        ips = []
        try:
            for info in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
                ip = info[4][0]
                if ip not in ips and ip not in ("255.255.255.255", "0.0.0.0", "127.0.0.1"):
                    ips.append(ip)
        except Exception:
            pass
        if not ips:
            # Fallback to DoH (Cloudflare / Google) if ISP DNS poisoned or failed
            try:
                import json as _doh_json
                d_ctx = ssl.create_default_context()
                d_ctx.check_hostname = False
                d_ctx.verify_mode = ssl.CERT_NONE
                for doh_endpoint in [
                    f"https://8.8.8.8/resolve?name={host}&type=A",
                    f"https://1.1.1.1/dns-query?name={host}&type=A"
                ]:
                    try:
                        d_req = urllib.request.Request(doh_endpoint, headers={"Accept": "application/dns-json"})
                        with urllib.request.urlopen(d_req, context=d_ctx, timeout=3) as d_res:
                            d_parsed = _doh_json.loads(d_res.read().decode())
                            for ans in d_parsed.get("Answer", []):
                                if ans.get("type") == 1 and ans.get("data"):
                                    cand = ans["data"].strip()
                                    if cand not in ips and cand not in ("255.255.255.255", "0.0.0.0", "127.0.0.1"):
                                        ips.append(cand)
                        if ips:
                            break
                    except Exception:
                        pass
            except Exception:
                pass
        if not ips:
            ips = [host]

        redirect_next = None
        for ip in ips:
            sock = None
            try:
                per_ip_timeout = max(5, timeout)
                sock = socket.create_connection((ip, port), timeout=per_ip_timeout)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                if parsed.scheme == "https":
                    in_bio = ssl.MemoryBIO()
                    out_bio = ssl.MemoryBIO()
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    sslobj = ctx.wrap_bio(in_bio, out_bio, server_hostname=host)
                    try:
                        sslobj.do_handshake()
                    except ssl.SSLWantReadError:
                        pass

                    # Fragment the TLS ClientHello across 3 small TCP packets to split SNI
                    hello = out_bio.read()
                    if len(hello) > 25:
                        sock.sendall(hello[:2])
                        time.sleep(0.008)
                        sock.sendall(hello[2:25])
                        time.sleep(0.008)
                        sock.sendall(hello[25:])
                    elif hello:
                        sock.sendall(hello)

                    while True:
                        try:
                            sslobj.do_handshake()
                            out = out_bio.read()
                            if out:
                                sock.sendall(out)
                            break
                        except ssl.SSLWantReadError:
                            out = out_bio.read()
                            if out:
                                sock.sendall(out)
                            d = sock.recv(16384)
                            if not d:
                                raise EOFError("TLS handshake closed by remote host")
                            in_bio.write(d)

                    hdr_lines = [
                        f"GET {path_query} HTTP/1.1",
                        f"Host: {host}"
                    ]
                    for k, v in req_headers.items():
                        if k.lower() not in ("host", "connection", "accept-encoding"):
                            hdr_lines.append(f"{k}: {v}")
                    hdr_lines.append("Accept-Encoding: gzip, deflate")
                    hdr_lines.append("Connection: close")
                    http_req = "\r\n".join(hdr_lines) + "\r\n\r\n"

                    sslobj.write(http_req.encode("utf-8"))
                    sock.sendall(out_bio.read())

                    plain = bytearray()
                    header_end = -1
                    content_length = -1
                    is_chunked = False
                    while True:
                        try:
                            chunk = sslobj.read(32768)
                            if not chunk:
                                break
                            plain.extend(chunk)
                            if header_end == -1:
                                idx_sep = plain.find(b"\r\n\r\n")
                                if idx_sep != -1:
                                    header_end = idx_sep + 4
                                    hdr_part = plain[:header_end].decode("latin1", errors="ignore")
                                    m_cl = re.search(r"content-length:\s*(\d+)", hdr_part, re.IGNORECASE)
                                    if m_cl:
                                        content_length = int(m_cl.group(1))
                                    if "transfer-encoding: chunked" in hdr_part.lower():
                                        is_chunked = True
                            if header_end != -1:
                                if content_length != -1:
                                    if len(plain) - header_end >= content_length:
                                        break
                                elif is_chunked:
                                    if plain.endswith(b"0\r\n\r\n"):
                                        break
                        except ssl.SSLWantReadError:
                            d = sock.recv(32768)
                            if not d:
                                break
                            in_bio.write(d)
                        except ssl.SSLWantWriteError:
                            out = out_bio.read()
                            if out:
                                sock.sendall(out)
                else:
                    hdr_lines = [
                        f"GET {path_query} HTTP/1.1",
                        f"Host: {host}"
                    ]
                    for k, v in req_headers.items():
                        if k.lower() not in ("host", "connection", "accept-encoding"):
                            hdr_lines.append(f"{k}: {v}")
                    hdr_lines.append("Accept-Encoding: gzip, deflate")
                    hdr_lines.append("Connection: close")
                    http_req = "\r\n".join(hdr_lines) + "\r\n\r\n"
                    sock.sendall(http_req.encode("utf-8"))
                    plain = bytearray()
                    header_end = -1
                    content_length = -1
                    is_chunked = False
                    while True:
                        d = sock.recv(32768)
                        if not d:
                            break
                        plain.extend(d)
                        if header_end == -1:
                            idx_sep = plain.find(b"\r\n\r\n")
                            if idx_sep != -1:
                                header_end = idx_sep + 4
                                hdr_part = plain[:header_end].decode("latin1", errors="ignore")
                                m_cl = re.search(r"content-length:\s*(\d+)", hdr_part, re.IGNORECASE)
                                if m_cl:
                                    content_length = int(m_cl.group(1))
                                if "transfer-encoding: chunked" in hdr_part.lower():
                                    is_chunked = True
                        if header_end != -1:
                            if content_length != -1:
                                if len(plain) - header_end >= content_length:
                                    break
                            elif is_chunked:
                                if plain.endswith(b"0\r\n\r\n"):
                                    break

                sock.close()
                sock = None

                resp_headers, body = _dechunk_http_body(bytes(plain))
                sc = resp_headers.get("_status_code", 200)
                if sc in (301, 302, 303, 307, 308) and resp_headers.get("location"):
                    loc = resp_headers["location"]
                    if "cdn.tnmr.org" in loc.lower():
                        raise urllib.error.HTTPError(current_url, sc, f"Stream token expired (Redirected to dead sinkhole: {loc})", resp_headers, None)
                    redirect_next = urllib.parse.urljoin(current_url, loc)
                    break
                if sc >= 400:
                    raise urllib.error.HTTPError(current_url, sc, f"HTTP Error {sc}", resp_headers, None)
                if body:
                    return body, current_url
            except Exception as e:
                last_err = e
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass
                continue

        if redirect_next:
            current_url = redirect_next
            continue
        break

    # Fallback: curl_cffi Chrome TLS impersonation if installed
    try:
        import curl_cffi.requests as cr
        resp = cr.get(current_url, headers=req_headers, impersonate="chrome", verify=False, timeout=timeout)
        if resp.status_code < 400 and resp.content:
            return resp.content, str(resp.url or current_url)
    except Exception as ce:
        if not last_err:
            last_err = ce

    raise last_err if last_err else RuntimeError(f"Failed to fetch {url}")


def resolve_hls_url(base_url: str, target: str) -> str:
    """
    Resolves relative URLs against base_url.
    Follows FetchV methodology:
    - Skip data: and skd: URIs (skd: = FairPlay DRM key, data: = inline)
    - If target is already absolute (http/https), return it normalized via urlsplit
    - Otherwise resolve relative to base_url using urljoin
    - Inherit base query string (CDN auth tokens) if segment URL has no query (FetchV methodology)
    """
    if not target:
        return base_url
    target = target.strip()
    if target.startswith("data:") or target.startswith("skd:"):
        return target

    lower_t = target.lower()
    if lower_t.startswith("http://") or lower_t.startswith("https://"):
        try:
            parsed_target = urllib.parse.urlsplit(target)
            if not parsed_target.query:
                parsed_base = urllib.parse.urlsplit(base_url)
                if parsed_base.query:
                    sep = "&" if "?" in target else "?"
                    target = f"{target}{sep}{parsed_base.query}"

            # Auto-sign AV01 / IW01 media segments with CDN access JWT
            if any(k in target.lower() or k in base_url.lower() for k in ["iw01.xyz", "av01.media", "av01.tv", "av01.xyz"]):
                try:
                    from .av01_resolver import AV01Resolver
                    vid = AV01Resolver.extract_video_id(base_url) or AV01Resolver.extract_video_id(target)
                    target = AV01Resolver.sign_segment_url(target, video_id=vid)
                except Exception:
                    pass

            return target
        except Exception:
            return target

    joined = urllib.parse.urljoin(base_url, target)

    # Inherit CDN auth tokens from playlist URL if segment has no query (FetchV methodology)
    parsed_target = urllib.parse.urlsplit(target)
    if not parsed_target.query:
        parsed_base = urllib.parse.urlsplit(base_url)
        if parsed_base.query:
            sep = "&" if "?" in joined else "?"
            joined = f"{joined}{sep}{parsed_base.query}"

    # Auto-sign AV01 / IW01 media segments with CDN access JWT
    if any(k in joined.lower() or k in base_url.lower() for k in ["iw01.xyz", "av01.media", "av01.tv", "av01.xyz"]):
        try:
            from .av01_resolver import AV01Resolver
            vid = AV01Resolver.extract_video_id(base_url) or AV01Resolver.extract_video_id(joined)
            joined = AV01Resolver.sign_segment_url(joined, video_id=vid)
        except Exception:
            pass

    return joined


class HLSInspector:
    """
    Zero High-Precision HLS / M3U8 Stream Inspector.
    Parses Master and Media playlists to extract:
    - Available resolutions (e.g. 1080p, 720p, 480p, 360p)
    - Bitrates / bandwidth (kbps / Mbps)
    - Exact or estimated duration (by summing #EXTINF tags)
    - Calculated file size per variant (duration * bandwidth / 8 or segment sampling)
    - Live vs VOD detection (#EXT-X-ENDLIST)
    - Query/token inheritance for CDN authentication
    """
    _playlist_cache: Dict[str, str] = {}
    _cache_lock = threading.Lock()

    @classmethod
    def cache_playlist(cls, url: str, content: str):
        if not url or not content or "#EXTM3U" not in content:
            return
        with cls._cache_lock:
            if len(cls._playlist_cache) > 100:
                cls._playlist_cache.clear()
            cls._playlist_cache[url] = content
            clean_u = url.split("?")[0].split("#")[0]
            cls._playlist_cache[clean_u] = content

    @classmethod
    def get_cached_playlist(cls, url: str) -> Optional[str]:
        if not url:
            return None
        with cls._cache_lock:
            if url in cls._playlist_cache:
                return cls._playlist_cache[url]
            clean_u = url.split("?")[0].split("#")[0]
            return cls._playlist_cache.get(clean_u)

    @staticmethod
    def probe(url: str, headers: Optional[dict] = None, proxy: Optional[str] = None, timeout: int = 10) -> dict:
        url = CloudLinkResolver.resolve(url)
        req_headers = CloudLinkResolver.fix_headers(url, headers or {})

        parsed = urllib.parse.urlsplit(url)
        ref = req_headers.get("Referer") or req_headers.get("referer") or req_headers.get("page_url") or f"{parsed.scheme}://{parsed.netloc}/"
        origin = req_headers.get("Origin") or req_headers.get("origin")
        if not origin and ref:
            p_ref = urllib.parse.urlsplit(ref)
            if p_ref.scheme and p_ref.netloc:
                origin = f"{p_ref.scheme}://{p_ref.netloc}"
        if not origin:
            origin = f"{parsed.scheme}://{parsed.netloc}"

        headers_to_send = {
            "User-Agent": req_headers.get("User-Agent") or req_headers.get("user-agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Referer": ref,
            "Origin": origin
        }
        for k, v in req_headers.items():
            k_low = k.lower()
            if k_low == "cookie":
                headers_to_send["Cookie"] = v
            elif k_low == "authorization":
                headers_to_send["Authorization"] = v

        handlers = []
        if proxy:
            handlers.append(urllib.request.ProxyHandler({'http': proxy, 'https': proxy}))
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        except Exception:
            pass

        class HLSSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                if "cdn.tnmr.org" in newurl.lower():
                    return None
                return super().redirect_request(req, fp, code, msg, hdrs, newurl)

        handlers.append(HLSSafeRedirectHandler())
        opener = urllib.request.build_opener(*handlers)

        def _fetch(fetch_url: str, fetch_timeout: int = timeout) -> Tuple[str, str]:
            cached = HLSInspector.get_cached_playlist(fetch_url)
            if cached and "#EXTM3U" in cached:
                return cached, fetch_url
            try:
                req = urllib.request.Request(fetch_url, headers=headers_to_send)
                with opener.open(req, timeout=min(fetch_timeout, 6)) as resp:
                    data = resp.read()
                    eff_url = resp.geturl() or fetch_url
                    enc = resp.headers.get("Content-Encoding", "").lower()
                    if "gzip" in enc or (len(data) >= 2 and data[:2] == b"\x1f\x8b"):
                        import gzip
                        data = gzip.decompress(data)
                    elif "deflate" in enc:
                        import zlib
                        try:
                            data = zlib.decompress(data)
                        except Exception:
                            data = zlib.decompress(data, -zlib.MAX_WBITS)
                    text = data.decode("utf-8", errors="ignore")
                    if "#EXTM3U" in text:
                        HLSInspector.cache_playlist(fetch_url, text)
                        HLSInspector.cache_playlist(eff_url, text)
                    return text, eff_url
            except Exception:
                # Fallback to DPI-bypass (fragmented TLS ClientHello + multi-IP failover + curl_cffi)
                raw_b, eff_url = fetch_url_with_dpi_bypass(fetch_url, headers=headers_to_send, timeout=max(fetch_timeout, 12))
                text = raw_b.decode("utf-8", errors="ignore")
                if "#EXTM3U" in text:
                    HLSInspector.cache_playlist(fetch_url, text)
                    HLSInspector.cache_playlist(eff_url, text)
                return text, eff_url

        # Check if m3u8_content was already provided by browser extension
        inline_m3u8 = req_headers.get("m3u8_content") or ""
        if inline_m3u8 and "#EXTM3U" in inline_m3u8:
            HLSInspector.cache_playlist(url, inline_m3u8)
            content, effective_url = inline_m3u8, url
        else:
            try:
                content, effective_url = _fetch(url)
            except Exception as e:
                # Automatic recovery for expired stream tokens via CloudLinkResolver
                try:
                    fresh_url, fresh_hdrs = CloudLinkResolver.resolve_stream_url(url, req_headers)
                    if fresh_url and fresh_url != url:
                        url = fresh_url
                        headers_to_send.update(fresh_hdrs)
                        content, effective_url = _fetch(fresh_url)
                except Exception:
                    pass
                if not content or "#EXTM3U" not in content:
                    return {"success": False, "error": f"Failed to fetch M3U8: {str(e)}"}

        if not content or "#EXTM3U" not in content:
            return {"success": False, "error": "Not a valid M3U8 playlist"}

        HLSInspector.cache_playlist(url, content)
        HLSInspector.cache_playlist(effective_url, content)

        # Extract title from URL basename
        base_name = os.path.basename(parsed.path or "video_stream")
        if base_name.lower().endswith(".m3u8"):
            base_name = base_name[:-5]
        if not base_name or base_name.lower() in ["index", "master", "playlist", "live", "manifest"]:
            base_name = "Video_Stream"
        suggested_title = sanitize_filename(base_name)
        if any(d in url.lower() for d in ["av01.media", "av01.tv", "av01.xyz", "iw01.xyz"]):
            try:
                from .av01_resolver import AV01Resolver
                vid = AV01Resolver.extract_video_id(url, req_headers)
                if vid:
                    meta = AV01Resolver.get_video_metadata(vid)
                    if meta:
                        dvd_id = meta.get("dvd_id") or ""
                        en_t = (
                            (meta.get("seo_titles") or {}).get("en")
                            or (meta.get("title_translations") or {}).get("en")
                            or meta.get("title")
                            or ""
                        )
                        full_t = f"{dvd_id}•{en_t}".strip("• ") if dvd_id else en_t
                        if full_t:
                            suggested_title = sanitize_filename(full_t)
            except Exception:
                pass

        # 1. Master Playlist with Multiple Quality Variants
        if "#EXT-X-STREAM-INF" in content:
            raw_variants = []
            audio_renditions = {}
            lines = content.splitlines()
            # First pass: map audio renditions (#EXT-X-MEDIA:TYPE=AUDIO)
            for l_item in lines:
                l_s = l_item.strip()
                if l_s.startswith("#EXT-X-MEDIA:") and "TYPE=AUDIO" in l_s:
                    grp_m = re.search(r'GROUP-ID="([^"]+)"', l_s)
                    uri_m = re.search(r'URI="([^"]+)"', l_s)
                    if grp_m and uri_m:
                        a_rend_url = resolve_hls_url(effective_url, uri_m.group(1))
                        if "?" not in a_rend_url and "?" in effective_url:
                            a_rend_url = f"{a_rend_url}?{ urllib.parse.urlsplit(effective_url).query }"
                        audio_renditions[grp_m.group(1)] = a_rend_url

            for i, line in enumerate(lines):
                line_s = line.strip()
                if line_s.startswith("#EXT-X-STREAM-INF"):
                    bw = 0
                    width = 0
                    height = 0
                    frame_rate = 0.0

                    bw_m = re.search(r'AVERAGE-BANDWIDTH=(\d+)', line_s) or re.search(r'BANDWIDTH=(\d+)', line_s)
                    if bw_m:
                        bw = int(bw_m.group(1))

                    res_m = re.search(r'RESOLUTION=(\d+)x(\d+)', line_s)
                    if res_m:
                        width = int(res_m.group(1))
                        height = int(res_m.group(2))

                    fps_m = re.search(r'FRAME-RATE=([\d.]+)', line_s)
                    if fps_m:
                        try:
                            frame_rate = float(fps_m.group(1))
                        except Exception:
                            pass

                    m_ag = re.search(r'AUDIO="([^"]+)"', line_s)
                    ag_id = m_ag.group(1) if m_ag else None
                    matched_audio = audio_renditions.get(ag_id) or (list(audio_renditions.values())[0] if audio_renditions else None)

                    # Next non-empty, non-comment line is the variant URI
                    for j in range(i + 1, len(lines)):
                        next_line = lines[j].strip()
                        if next_line and not next_line.startswith("#"):
                            v_url = resolve_hls_url(effective_url, next_line)
                            if "?" not in v_url and "?" in effective_url:
                                v_url = f"{v_url}?{ urllib.parse.urlsplit(effective_url).query }"
                            if any(d in v_url.lower() for d in ("doppiocdn", "stripcdn", "stripchat")) and "pkey=" not in v_url.lower():
                                sep = "&" if "?" in v_url else "?"
                                v_url = f"{v_url}{sep}pkey=B0p93vi8Uj6AYyZb"
                            raw_variants.append({
                                "url": v_url,
                                "master_url": effective_url,
                                "audio_url": matched_audio,
                                "bandwidth": bw,
                                "width": width,
                                "height": height,
                                "frame_rate": frame_rate,
                                "label": f"{height}p" if height else (f"{width}x{height}" if width else "Stream")
                            })
                            break

            if raw_variants:
                # Sort: total pixel count (width * height), then highest bandwidth
                raw_variants.sort(
                    key=lambda x: (
                        (x["width"] * x["height"]) if (x["width"] and x["height"]) else (x["height"] * 1000),
                        x["bandwidth"]
                    ),
                    reverse=True
                )

                # Fetch the top variant's media playlist to determine exact duration & segment count
                total_duration = 0.0
                total_segments = 0
                is_live = False

                for cand in raw_variants[:2]:
                    try:
                        v_content, _ = _fetch(cand["url"], fetch_timeout=8)
                        if "#EXTINF" in v_content:
                            is_ad = "#EXT-X-MOUFLON-ADVERT" in v_content
                            is_live = ("#EXT-X-ENDLIST" not in v_content) or is_ad
                            if not is_live:
                                HLSInspector.cache_playlist(cand["url"], v_content)
                                cand["m3u8_content"] = v_content
                            durations = [float(m.group(1)) for m in re.finditer(r'#EXTINF:([\d.]+)', v_content)]
                            if durations:
                                total_duration = 0.0 if is_live else sum(durations)
                                total_segments = len(durations)
                                break
                    except Exception:
                        continue

                # Format human-friendly numbers for all variants
                processed_variants = []
                for v in raw_variants:
                    bw = v["bandwidth"]
                    dur = 0.0 if is_live else total_duration
                    if not is_live and dur > 0 and bw > 0:
                        est_bytes = round((dur * bw) / 8)
                    else:
                        est_bytes = -1

                    bitrate_kbps = round(bw / 1000) if bw else 0
                    w = v["width"]
                    h = v["height"]
                    res_str = f"{w}x{h}" if (w and h) else (f"{h}p" if h else "Auto")

                    # Formatted display: "1080p (1920x1080) • 3.5 Mbps • ~450 MB"
                    parts = []
                    if h:
                        parts.append(f"{h}p ({res_str})" if (w and h) else f"{h}p")
                    elif res_str != "Auto":
                        parts.append(res_str)
                    
                    if bitrate_kbps > 0:
                        if bitrate_kbps >= 1000:
                            parts.append(f"{bitrate_kbps/1000:.1f} Mbps")
                        else:
                            parts.append(f"{bitrate_kbps} kbps")

                    if is_live:
                        parts.append("Live Stream")
                    elif est_bytes > 0:
                        parts.append(f"~{format_bytes(est_bytes)}")

                    display_name = " • ".join(parts) if parts else "HLS Stream"

                    processed_variants.append({
                        "url": v["url"],
                        "master_url": v["master_url"],
                        "audio_url": v.get("audio_url"),
                        "resolution": res_str,
                        "width": w,
                        "height": h,
                        "bitrate": bitrate_kbps,
                        "bandwidth": bw,
                        "total_bytes": est_bytes,
                        "filesize": est_bytes,
                        "duration": dur,
                        "is_live": is_live,
                        "label": v["label"],
                        "display_name": display_name,
                        "filename": sanitize_filename(f"{suggested_title} [{v['label']}].mp4"),
                        "m3u8_content": "" if is_live else (v.get("m3u8_content") or HLSInspector.get_cached_playlist(v["url"]) or "")
                    })

                best = processed_variants[0]
                return {
                    "success": True,
                    "is_hls": True,
                    "is_master": True,
                    "is_live": is_live,
                    "duration": total_duration,
                    "total_segments": total_segments,
                    "variants": processed_variants,
                    "selected_variant": best,
                    "total_bytes": best["total_bytes"],
                    "filesize": best["total_bytes"],
                    "bitrate": best["bitrate"],
                    "resolution": best["resolution"],
                    "height": best["height"],
                    "width": best["width"],
                    "filename": best["filename"],
                    "m3u8_content": "" if is_live else (best.get("m3u8_content") or content),
                    "resumable": True,
                    "category": "Video"
                }

        # 2. Single Media Playlist (Direct Segments with #EXTINF)
        durations = [float(m.group(1)) for m in re.finditer(r'#EXTINF:([\d.]+)', content)]
        is_ad = "#EXT-X-MOUFLON-ADVERT" in content
        is_live = ("#EXT-X-ENDLIST" not in content) or is_ad
        total_duration = 0.0 if is_live else (sum(durations) if durations else 0.0)
        total_segments = len(durations)

        # Estimate segment bytes by sampling the first segment
        estimated_bytes = -1
        bitrate_kbps = 0
        if total_segments > 0 and not is_live:
            first_seg = None
            for line in content.splitlines():
                line_s = line.strip()
                if line_s and not line_s.startswith("#"):
                    first_seg = resolve_hls_url(effective_url, line_s)
                    break
            
            if first_seg:
                try:
                    seg_req = urllib.request.Request(first_seg, headers=dict(headers_to_send, Range="bytes=0-0"))
                    with opener.open(seg_req, timeout=5) as s_resp:
                        cr = s_resp.headers.get("Content-Range")
                        if cr and "/" in cr:
                            total_seg_sz = int(cr.split("/")[-1])
                            estimated_bytes = total_segments * total_seg_sz
                        elif s_resp.headers.get("Content-Length"):
                            cl = int(s_resp.headers.get("Content-Length"))
                            if cl > 1:
                                estimated_bytes = total_segments * cl
                except Exception:
                    pass

        if estimated_bytes > 0 and total_duration > 0:
            bitrate_kbps = round((estimated_bytes * 8 / total_duration) / 1000)

        # Determine display name
        parts = ["Original"]
        if bitrate_kbps > 0:
            if bitrate_kbps >= 1000:
                parts.append(f"{bitrate_kbps/1000:.1f} Mbps")
            else:
                parts.append(f"{bitrate_kbps} kbps")
        if estimated_bytes > 0:
            parts.append(f"~{format_bytes(estimated_bytes)}")
        elif is_live:
            parts.append("Live Stream")
        display_name = " • ".join(parts)

        return {
            "success": True,
            "is_hls": True,
            "is_master": False,
            "is_live": is_live,
            "duration": total_duration,
            "total_segments": total_segments,
            "variants": [{
                "url": effective_url,
                "master_url": effective_url,
                "resolution": "Original",
                "width": 0,
                "height": 0,
                "bitrate": bitrate_kbps,
                "bandwidth": bitrate_kbps * 1000 if bitrate_kbps else 0,
                "total_bytes": estimated_bytes,
                "filesize": estimated_bytes,
                "duration": total_duration,
                "is_live": is_live,
                "label": "Original",
                "display_name": display_name,
                "filename": sanitize_filename(f"{suggested_title}.mp4"),
                "m3u8_content": content
            }],
            "total_bytes": estimated_bytes,
            "filesize": estimated_bytes,
            "bitrate": bitrate_kbps,
            "resolution": "Original",
            "m3u8_content": content,
            "height": 0,
            "width": 0,
            "filename": sanitize_filename(f"{suggested_title}.mp4"),
            "resumable": True,
            "category": "Video"
        }


class HLSWorker(threading.Thread):
    """
    High-Performance Resumable Multi-Threaded HLS/DASH Stream Downloader.
    
    Features:
    - Resumable Disk Cache: Segments stored deterministically per task/URL, allowing pause and resume without data loss.
    - Persistent HTTP Keep-Alive & Adaptive Stream Pooling (8 threads): Eliminates connection resets and CDN 429 throttling.
    - Live Connection Slot Tracking: Updates UI connection table with actual KB received and chunk status (no more 'Send GET...').
    - Robust Exponential Backoff & Secondary Retry Pass: Recovers from temporary network hiccups without aborting the download.
    - In-Memory AES-128 Decryption (RFC 8216 standard).
    - 2-Second Rolling Window Speed Smoothing (consistent, accurate throughput without oscillations).
    - Dynamic Total Size & ETA Estimation.
    - Instant Lossless Remuxing to Seekable MP4 via FFmpeg (-c copy in 2 seconds).
    - Multi-stage Fallback: Resumable Native ThreadPool -> yt-dlp -> FFmpeg Direct.
    """
    def __init__(
        self,
        url: str,
        target_path: str,
        task_id: Optional[str] = None,
        segment_slots: Optional[list] = None,
        connections: int = 8,
        speed_limiter: Optional[SpeedLimiter] = None,
        pause_event: Optional[threading.Event] = None,
        cancel_event: Optional[threading.Event] = None,
        on_progress: Optional[Callable[[int, int, float, float], None]] = None,
        on_finished: Optional[Callable[[bool, Optional[str]], None]] = None,
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        is_live: bool = False,
        on_url_renewed: Optional[Callable[[str, dict], None]] = None
    ):
        super().__init__(daemon=True)
        self.url = url
        base, ext = os.path.splitext(target_path)
        self.target_path = target_path if ext.lower() in (".mp4", ".webm") else f"{base}.mp4"
        self.task_id = task_id
        self.segment_slots = segment_slots or []
        self.connections = max(2, min(connections or 16, 64))
        self.speed_limiter = speed_limiter
        self.pause_event = pause_event
        self.cancel_event = cancel_event
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.on_url_renewed = on_url_renewed
        self.headers = CloudLinkResolver.fix_headers(self.url, headers or {})
        self.proxy = proxy
        self.is_live = is_live or (self.headers and (self.headers.get("is_live") in [True, "true", "True", 1, "1"]))
        self._proc: Optional[subprocess.Popen] = None
        self._is_cancelled = False
        self._stop_recording_requested = False

        # Speed smoothing state
        self._lock = threading.Lock()
        self._downloaded_bytes = 0
        self._completed_segments = 0
        self._total_segments = 0
        self._speed_history: List[Tuple[float, int]] = []
        self._last_smoothed_speed = 0.0
        self._last_error = ""

        # Separate audio rendition URL (from #EXT-X-MEDIA AUDIO tag in master playlist)
        # Populated during master playlist parsing; used after video segments are merged.
        self._audio_rendition_url: Optional[str] = None

        # AV01 / IW01 Video ID tracking
        self._video_id = None
        try:
            from .av01_resolver import AV01Resolver
            if AV01Resolver.is_av01_url(self.url) or (self.headers and AV01Resolver.is_av01_url(self.headers.get("Referer", ""))):
                self._video_id = AV01Resolver.extract_video_id(self.url, self.headers)
        except Exception:
            pass

        # Shared opener with Keep-Alive
        self._opener = None
        self._init_network()

    def _update_task_url(self, new_url: str, new_headers: Optional[dict] = None):
        """Persists the resolved working variant URL and headers back to the task database."""
        if not self.task_id:
            return
        try:
            from .database import Database
            db = Database()
            task = db.get_task(self.task_id)
            if task:
                task.url = new_url
                task.error_message = ""
                if new_headers:
                    if not task.headers:
                        task.headers = {}
                    task.headers.update(new_headers)
                if task.headers:
                    task.headers.pop("m3u8_content", None)
                db.save_task(task)
        except Exception:
            pass

        if self.on_url_renewed:
            try:
                self.on_url_renewed(new_url, new_headers or {})
            except Exception as e_ren:
                print(f"[HLSWorker] Note on_url_renewed callback: {e_ren}")

    def _resolve_working_fallback_stream(self) -> Optional[str]:
        """
        Intelligently resolves an alternative working quality variant or mirror stream
        when the requested URL suffers from DNS failure (NXDOMAIN / getaddrinfo failed),
        HTTP 404, or server timeouts (e.g. g249.turbosplayer.com -> g241.turbosplayer.com).
        """
        import socket
        import re

        def can_resolve_host(u: str) -> bool:
            try:
                p = urllib.parse.urlsplit(u)
                if not p.netloc:
                    return False
                host = p.netloc.split(":")[0]
                try:
                    socket.gethostbyname(host)
                    return True
                except Exception:
                    # DNS failover to DoH for Indonesian ISP DNS filtering / poisoning
                    for doh in ["8.8.8.8", "1.1.1.1"]:
                        try:
                            d_ctx = ssl.create_default_context()
                            d_ctx.check_hostname = False
                            d_ctx.verify_mode = ssl.CERT_NONE
                            d_req = urllib.request.Request(f"https://{doh}/dns-query?name={host}&type=A", headers={"Accept": "application/dns-json"})
                            with urllib.request.urlopen(d_req, context=d_ctx, timeout=3) as d_resp:
                                d_data = json.loads(d_resp.read().decode())
                                for a in d_data.get("Answer", []):
                                    if a.get("type") == 1:
                                        return True
                        except Exception:
                            pass
                    return False
            except Exception:
                return False

        candidates = []

        # 0. Check CloudLinkResolver to auto-resolve a fresh stream link if the host or token expired
        try:
            from .link_resolver import CloudLinkResolver
            fresh_url, fresh_hdrs = CloudLinkResolver.resolve_stream_url(self.url, self.headers)
            if fresh_url and fresh_url != self.url and can_resolve_host(fresh_url):
                if self.headers and fresh_hdrs:
                    self.headers.update(fresh_hdrs)
                return fresh_url
        except Exception:
            pass

        # 1. Check explicit fallback_urls list in headers
        if self.headers:
            f_urls = self.headers.get("fallback_urls")
            if isinstance(f_urls, list):
                candidates.extend(f_urls)
            elif isinstance(f_urls, str) and f_urls:
                candidates.extend([x.strip() for x in f_urls.split("|||") if x.strip()])

        # 2. Check master_url in headers
        master_url = None
        if self.headers:
            master_url = self.headers.get("master_url")

        # 3. Check Referer or page_url for embedded player scripts (turbovidhls, turboviplay, jwplayer, etc.)
        if not master_url and self.headers:
            ref = self.headers.get("Referer") or self.headers.get("page_url") or ""
            if ref and any(k in ref.lower() for k in ["turbovid", "turboviplay", "jwplayer", "stream"]):
                try:
                    ref_data = self._fetch_url_data(ref, timeout=8).decode("utf-8", errors="ignore")
                    m = re.search(r'urlPlay\s*=\s*[\'"](https?://[^\'"]+)[\'"]', ref_data)
                    if m:
                        master_url = m.group(1)
                except Exception:
                    pass

        # 4. If master_url discovered, fetch it to extract all variant URLs
        if master_url and can_resolve_host(master_url):
            try:
                m_data = self._fetch_url_data(master_url, timeout=10).decode("utf-8", errors="ignore")
                lines = m_data.splitlines()
                v_list = []
                for i, l in enumerate(lines):
                    if l.startswith("#EXT-X-STREAM-INF"):
                        bw = 0
                        if "BANDWIDTH=" in l:
                            try:
                                bw = int(l.split("BANDWIDTH=")[1].split(",")[0].split(":")[0])
                            except Exception:
                                pass
                        for next_idx in range(i + 1, len(lines)):
                            cand_line = lines[next_idx].strip()
                            if cand_line and not cand_line.startswith("#"):
                                resolved_cand = urllib.parse.urljoin(master_url, cand_line)
                                v_list.append((bw, resolved_cand))
                                break
                if v_list:
                    v_list.sort(key=lambda x: x[0], reverse=True)
                    for _, v_url in v_list:
                        if v_url not in candidates:
                            candidates.append(v_url)
            except Exception:
                pass

        # 5. Test each candidate: return first resolvable variant that returns valid playlist
        for cand in candidates:
            if cand != self.url and can_resolve_host(cand):
                try:
                    sample = self._fetch_url_data(cand, timeout=6)
                    if b"#EXTM3U" in sample:
                        return cand
                except Exception:
                    continue

        return None

    def finish_live_recording(self):
        """Gracefully stops live stream capture so recorded segments are finalized and remuxed to MP4/WebM."""
        self._stop_recording_requested = True
        if self._proc:
            try:
                if self._proc.stdin:
                    self._proc.stdin.write("q\n")
                    self._proc.stdin.flush()
            except Exception:
                pass

    def request_stop_live(self):
        """Alias for finish_live_recording."""
        self.finish_live_recording()

    def stop(self):
        """Cleanly stops recording or downloading."""
        if self.is_live and self._downloaded_bytes > 0:
            self.finish_live_recording()
            return
        self._is_cancelled = True
        self._stop_recording_requested = True
        if self._proc:
            try:
                if self._proc.stdin:
                    self._proc.stdin.write("q\n")
                    self._proc.stdin.flush()
            except Exception:
                pass
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _init_network(self):
        handlers = []
        if self.proxy:
            handlers.append(urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy}))
        try:
            import ssl
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=ssl_ctx))
        except Exception:
            pass

        class HLSSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                if "cdn.tnmr.org" in newurl.lower():
                    return None
                return super().redirect_request(req, fp, code, msg, hdrs, newurl)

        handlers.append(HLSSafeRedirectHandler())
        self._opener = urllib.request.build_opener(*handlers)

    def run(self):
        try:
            # Only treat as live stream if explicitly requested (e.g. Chaturbate, Stripchat, live webcam broadcast)
            is_live_stream = bool(
                self.is_live or
                (self.headers and (
                    self.headers.get("is_live") in [True, "true", "True", 1, "1"] or
                    any(d in str(self.headers.get("Referer", "")).lower() for d in ("chaturbate", "stripchat")) or
                    any(d in str(self.headers.get("master_url", "")).lower() for d in ("chaturbate", "stripchat", "mmcdn", "doppiocdn"))
                )) or
                any(d in self.url.lower() for d in ("chaturbate.com", "stripchat.com", "cb.live", "mmcdn.com", "highwebmedia.com", "doppiocdn", "stripcdn"))
            )

            is_dash = bool(
                (".mpd" in self.url.lower()) or
                (self.headers and (
                    self.headers.get("is_dash") in [True, "true", "True", 1, "1"] or
                    "dash+xml" in str(self.headers.get("content-type", "")).lower()
                ))
            )

            if is_live_stream:
                success = self._run_as_live_stream()
            elif is_dash:
                print(f"[HLSWorker] Processing MPEG-DASH stream: {self.url}")
                # Stage 1: Native High-Speed Concurrent MPEG-DASH Engine
                success = self._run_with_dash_engine()

                # Stage 2: yt-dlp Fallback (built-in DASH support)
                if not success and not self._is_cancelled:
                    print(f"[HLSWorker] Native DASH engine returned False; falling back to yt-dlp...")
                    success = self._run_with_ytdlp()

                # Stage 3: Direct FFmpeg Fallback
                if not success and not self._is_cancelled:
                    print(f"[HLSWorker] Falling back to FFmpeg for DASH stream...")
                    success = self._run_with_ffmpeg()
            else:
                # Stage 1: High-Speed Resumable Native Multi-Threaded Concurrent HLS Engine
                success = self._run_with_concurrent_engine()

                # Stage 2: Smart Stream Renewal & Fallback Variant before heavy external tools
                is_av01_stream = bool(self._video_id or any(d in self.url.lower() for d in ("iw01.xyz", "av01")))
                if not success and not self._is_cancelled and not is_av01_stream:
                    fb_url = self._resolve_working_fallback_stream()
                    if fb_url and fb_url != self.url:
                        print(f"[HLSWorker] Fallback Stage 2: Retrying with renewed working variant: {fb_url}")
                        self.url = fb_url
                        self._update_task_url(fb_url)
                        success = self._run_with_concurrent_engine()

                is_token_expired = bool(
                    "kedaluwarsa" in (self._last_error or "").lower() or
                    "expired" in (self._last_error or "").lower() or
                    "refresh url" in (self._last_error or "").lower()
                )

                # Stage 3: Concurrent Fragment yt-dlp Fallback (if native encountered unsupported format)
                # Note: Skip yt-dlp / direct FFmpeg fallback for AV01/IW01 streams or expired tokens
                if not success and not self._is_cancelled and not is_av01_stream and not is_token_expired:
                    success = self._run_with_ytdlp()

                # Stage 4: Robust Reconnecting Direct FFmpeg Fallback
                if not success and not self._is_cancelled and not is_av01_stream and not is_token_expired:
                    success = self._run_with_ffmpeg()

            if success:
                # Ensure if target_path is still a raw MPEG-TS disguised as .mp4 (0x47 sync byte), normalize it to seekable MP4
                # (Skipped for live stream recordings to prevent discontinuity truncation)
                try:
                    if not self.is_live and os.path.exists(self.target_path) and os.path.getsize(self.target_path) > 1024:
                        with open(self.target_path, "rb") as _fh:
                            _hdr = _fh.read(16)
                        if _hdr and (_hdr[0] == 0x47 or b"ftyp" not in _hdr):
                            self.fix_media_seek_and_container(self.target_path)
                except Exception:
                    pass
                self.cleanup_temp_fragments(self.target_path)
                if self.on_finished:
                    self.on_finished(True, None)
            else:
                if self._is_cancelled:
                    self.cleanup_temp_fragments(self.target_path)
                err = "Cancelled by user" if self._is_cancelled else (self._last_error or "Failed to download HLS stream")
                if self.on_finished:
                    self.on_finished(False, err)
        except Exception as e:
            if self.on_finished:
                self.on_finished(False, str(e))

    def _calculate_rolling_speed(self, current_bytes: int) -> float:
        now = time.time()
        self._speed_history.append((now, current_bytes))
        while self._speed_history and (now - self._speed_history[0][0]) > 2.0:
            self._speed_history.pop(0)

        if len(self._speed_history) >= 2:
            dt = self._speed_history[-1][0] - self._speed_history[0][0]
            db = self._speed_history[-1][1] - self._speed_history[0][1]
            if dt > 0.01:
                self._last_smoothed_speed = max(0.0, db / dt)

        return self._last_smoothed_speed

    @staticmethod
    def _strip_stream_obfuscation(data: bytes) -> bytes:
        """
        Deobfuscates fake image wrappers (e.g. 1x1 PNG/JPEG headers used by anti-scraping CDN/sites).
        Locates the genuine MPEG-TS sync pattern (0x47 every 188 bytes) or fMP4 box headers.
        """
        if not data or len(data) < 188:
            return data

        # Fast path: already clean MPEG-TS
        if data[0] == 0x47 and (len(data) < 189 or data[188] == 0x47):
            return data

        # Check for MPEG-TS sync pattern (0x47 ... 188 bytes ... 0x47 ... 188 bytes ... 0x47)
        search_limit = min(8192, len(data) - 564)
        for offset in range(search_limit):
            if data[offset] == 0x47 and data[offset + 188] == 0x47 and data[offset + 376] == 0x47:
                return data[offset:]

        # Check for fMP4 boxes (ftyp, moof, styp) within first 8192 bytes
        for box in (b"ftyp", b"moof", b"styp"):
            bidx = data[:8192].find(box)
            if bidx >= 4:
                return data[bidx - 4:]

        return data

    def _validate_media_file(self, file_path: str) -> bool:
        """
        Validates that the output file contains a legitimate, playable video stream
        and was not corrupted or tricked into a 1x1 image / 0-duration container.
        """
        if not os.path.exists(file_path) or os.path.getsize(file_path) < 1024:
            return False

        if self.headers and self.headers.get("estimated_size"):
            try:
                est = int(self.headers["estimated_size"])
                if est > 10 * 1024 * 1024 and os.path.getsize(file_path) < int(est * 0.5):
                    print(f"[HLSWorker] Validation rejected: file size {os.path.getsize(file_path)} is far below estimated {est}")
                    return False
            except Exception:
                pass

        ffmpeg_bin = AudioMuxer.get_ffmpeg_path()
        if not ffmpeg_bin:
            return os.path.getsize(file_path) > 1024

        flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
        sinfo = None
        if sys.platform == "win32":
            sinfo = subprocess.STARTUPINFO()
            sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            sinfo.wShowWindow = 0

        try:
            probe_cmd = [ffmpeg_bin, "-i", file_path]
            p_res = subprocess.run(
                probe_cmd,
                capture_output=True,
                text=True,
                errors="ignore",
                creationflags=flag,
                startupinfo=sinfo
            )
            probe_out = p_res.stderr or ""

            # Check for Video stream
            has_video = False
            is_fake_image = False
            for line in probe_out.splitlines():
                if "Stream #" in line and "Video:" in line:
                    has_video = True
                    lower_line = line.lower()
                    if "video: png" in lower_line or "video: mjpeg" in lower_line or " 1x1" in lower_line:
                        is_fake_image = True
                    break

            if is_fake_image:
                return False

            if not has_video:
                has_audio = any("Stream #" in line and "Audio:" in line for line in probe_out.splitlines())
                return has_audio

            # Validate duration if file is non-trivial (>10MB)
            import re
            dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", probe_out)
            if dur_match:
                hours = int(dur_match.group(1))
                minutes = int(dur_match.group(2))
                seconds = float(dur_match.group(3))
                total_duration = hours * 3600 + minutes * 60 + seconds
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if file_size_mb > 10.0 and total_duration < 2.0:
                    return False

            return True
        except Exception:
            return os.path.getsize(file_path) > 1024

    @staticmethod
    def _resolve_url(base_url: str, target: str) -> str:
        return resolve_hls_url(base_url, target)

    def _fetch_url_with_info(self, url: str, extra_headers: Optional[dict] = None, timeout: int = 15, bypass_cache: bool = False) -> Tuple[bytes, str]:
        """
        Fetches URL data, automatically tracking redirected edge URLs and handling gzip/deflate responses.
        Uses in-memory M3U8 cache when available (for static VOD only) and falls back to DPI-bypass
        (fragmented TLS ClientHello) when standard urllib times out or is blocked by ISP DPI / Cloudflare.
        Returns (data_bytes, final_effective_url).
        """
        if not bypass_cache and not self.is_live:
            cached_m3u8 = HLSInspector.get_cached_playlist(url)
            if cached_m3u8 and "#EXTM3U" in cached_m3u8 and "#EXT-X-ENDLIST" in cached_m3u8:
                return cached_m3u8.encode("utf-8"), url

        parsed = urllib.parse.urlsplit(url)
        default_referer = f"{parsed.scheme}://{parsed.netloc}/"

        ref = None
        if self.headers:
            ref = self.headers.get("Referer") or self.headers.get("referer") or self.headers.get("page_url")
        if not ref:
            if any(d in url.lower() for d in ("doppiocdn", "stripcdn", "stripchat")):
                ref = "https://stripchat.com/"
            else:
                ref = default_referer

        origin = None
        if self.headers:
            origin = self.headers.get("Origin") or self.headers.get("origin")
        if not origin and ref:
            p_ref = urllib.parse.urlsplit(ref)
            if p_ref.scheme and p_ref.netloc:
                origin = f"{p_ref.scheme}://{p_ref.netloc}"
        if not origin:
            if any(d in url.lower() for d in ("doppiocdn", "stripcdn", "stripchat")):
                origin = "https://stripchat.com"
            else:
                origin = f"{parsed.scheme}://{parsed.netloc}"

        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, identity",
            "Connection": "keep-alive",
            "Referer": ref,
            "Origin": origin
        }
        if self.headers:
            for k, v in self.headers.items():
                k_low = k.lower()
                if k_low == "user-agent":
                    req_headers["User-Agent"] = v
                elif k_low == "cookie":
                    req_headers["Cookie"] = v
                elif k_low in ["authorization"]:
                    req_headers[k] = v

        if extra_headers:
            req_headers.update(extra_headers)

        req_headers = CloudLinkResolver.fix_headers(url, req_headers)
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with self._opener.open(req, timeout=min(timeout, 7)) as resp:
                data = resp.read()
                final_url = resp.geturl() or url

                # Decompress if server sent gzip or deflate
                content_encoding = resp.headers.get("Content-Encoding", "").lower()
                if "gzip" in content_encoding or (len(data) >= 2 and data[:2] == b"\x1f\x8b"):
                    try:
                        import gzip
                        data = gzip.decompress(data)
                    except Exception:
                        pass
                elif "deflate" in content_encoding:
                    try:
                        import zlib
                        data = zlib.decompress(data)
                    except Exception:
                        try:
                            import zlib
                            data = zlib.decompress(data, -zlib.MAX_WBITS)
                        except Exception:
                            pass

                if not bypass_cache and not self.is_live and b"#EXTM3U" in data[:1024] and b"#EXT-X-ENDLIST" in data:
                    HLSInspector.cache_playlist(url, data.decode("utf-8", errors="ignore"))
                    HLSInspector.cache_playlist(final_url, data.decode("utf-8", errors="ignore"))
                return data, final_url
        except Exception:
            # Automatic fallback to DPI-bypass (fragmented TLS ClientHello + multi-IP failover + curl_cffi)
            data, final_url = fetch_url_with_dpi_bypass(url, headers=req_headers, timeout=max(timeout, 14))
            if b"#EXTM3U" in data[:1024]:
                HLSInspector.cache_playlist(url, data.decode("utf-8", errors="ignore"))
                HLSInspector.cache_playlist(final_url, data.decode("utf-8", errors="ignore"))
            return data, final_url

    def _fetch_url_data(self, url: str, extra_headers: Optional[dict] = None, timeout: int = 15) -> bytes:
        data, _ = self._fetch_url_with_info(url, extra_headers=extra_headers, timeout=timeout)
        return data

    def _run_with_concurrent_engine(self) -> bool:
        """
        Fast, Resumable Multi-Threaded HLS Downloader.
        Downloads segments concurrently using persistent workers with resume support.
        Supports standard MPEG-TS, fMP4/CMAF (#EXT-X-MAP), Byte-Range, and AES-128.
        """
        ffmpeg_bin = AudioMuxer.get_ffmpeg_path()
        if not ffmpeg_bin:
            return False

        # Deterministic cache directory per task so downloads can be cleanly resumed
        cache_id = self.task_id if self.task_id else hashlib.md5(self.url.encode("utf-8")).hexdigest()
        cache_dir = os.path.join(tempfile.gettempdir(), f"zero_hls_{cache_id}")
        os.makedirs(cache_dir, exist_ok=True)
        cached_playlist_file = os.path.join(cache_dir, "playlist.m3u8")

        # Pre-scan existing chunk fragments on disk immediately so UI reflects accurate downloaded_bytes upon resume
        existing_cached_bytes = 0
        existing_cached_count = 0
        try:
            for fname in os.listdir(cache_dir):
                if fname.startswith("chunk_") and fname.endswith(".ts"):
                    f_sz = os.path.getsize(os.path.join(cache_dir, fname))
                    if f_sz > 0:
                        existing_cached_bytes += f_sz
                        existing_cached_count += 1
            if existing_cached_bytes > 0:
                with self._lock:
                    self._downloaded_bytes = existing_cached_bytes
                    self._completed_segments = existing_cached_count
                if self.on_progress:
                    est_init = -1
                    if self.headers and self.headers.get("estimated_size"):
                        try:
                            est_init = int(self.headers["estimated_size"])
                        except Exception:
                            pass
                    self.on_progress(existing_cached_bytes, est_init, 0.0, 0)
        except Exception:
            pass

        try:
            # 1. Check disk cache, in-memory cache, or extension-provided m3u8_content first!
            raw_playlist = ""
            media_url = self.url

            if os.path.exists(cached_playlist_file) and os.path.getsize(cached_playlist_file) > 16:
                try:
                    with open(cached_playlist_file, "r", encoding="utf-8", errors="ignore") as pf:
                        disk_pl = pf.read()
                    if "#EXTM3U" in disk_pl and "#EXTINF" in disk_pl:
                        raw_playlist = disk_pl
                except Exception:
                    pass

            if not raw_playlist and self.headers and self.headers.get("m3u8_content"):
                inline_pl = str(self.headers.get("m3u8_content"))
                if "#EXTM3U" in inline_pl and "#EXTINF" in inline_pl:
                    raw_playlist = inline_pl

            if not raw_playlist:
                mem_pl = HLSInspector.get_cached_playlist(self.url)
                if mem_pl and "#EXTM3U" in mem_pl and "#EXTINF" in mem_pl:
                    raw_playlist = mem_pl

            # Verify validity of cached/saved playlist before proceeding.
            # If the token has expired (common after pause/resume or delay), probe key or first chunk.
            if raw_playlist:
                is_expired = False
                key_probe_m = re.search(r'#EXT-X-KEY:[^,\n]*,URI="([^"]+)"', raw_playlist)
                if key_probe_m:
                    probe_key_uri = self._resolve_url(media_url, key_probe_m.group(1))
                    if not probe_key_uri.startswith("data:"):
                        try:
                            self._fetch_url_data(probe_key_uri, timeout=5)
                        except Exception as e_kprobe:
                            print(f"[HLSWorker] Cached playlist encryption key expired or unreachable ({e_kprobe}). Triggering renewal...")
                            is_expired = True
                else:
                    for l in raw_playlist.splitlines():
                        l_s = l.strip()
                        if l_s and not l_s.startswith("#"):
                            probe_seg_url = self._resolve_url(media_url, l_s)
                            try:
                                self._fetch_url_data(probe_seg_url, extra_headers={"Range": "bytes=0-0"}, timeout=5)
                            except Exception as e_sprobe:
                                print(f"[HLSWorker] Cached playlist segment expired or unreachable ({e_sprobe}). Triggering renewal...")
                                is_expired = True
                            break

                if is_expired:
                    raw_playlist = ""
                    HLSInspector.cache_playlist(self.url, "")
                    try:
                        if os.path.exists(cached_playlist_file):
                            os.remove(cached_playlist_file)
                    except Exception:
                        pass
                    if self.headers:
                        self.headers.pop("m3u8_content", None)

            if not raw_playlist:
                try:
                    if self.segment_slots and len(self.segment_slots) > 0:
                        self.segment_slots[0].status = "Connecting to stream..."
                    raw_bytes, media_url = self._fetch_url_with_info(self.url, timeout=10)
                    raw_playlist = raw_bytes.decode("utf-8", errors="ignore")
                except Exception as e_fetch:
                    print(f"[HLSWorker] Initial playlist fetch error on {self.url}: {e_fetch}. Searching fallback variant...")
                    if self.segment_slots and len(self.segment_slots) > 0:
                        self.segment_slots[0].status = "Refreshing stream link..."
                    fb_url = self._resolve_working_fallback_stream()
                    if fb_url and fb_url != self.url:
                        print(f"[HLSWorker] Successfully switched to working fallback: {fb_url}")
                        self.url = fb_url
                        self._update_task_url(fb_url, self.headers)
                        if self.segment_slots and len(self.segment_slots) > 0:
                            self.segment_slots[0].status = "Connecting..."
                        try:
                            raw_bytes, media_url = self._fetch_url_with_info(self.url, timeout=12)
                            raw_playlist = raw_bytes.decode("utf-8", errors="ignore")
                        except Exception as e_fb:
                            print(f"[HLSWorker] Fallback playlist fetch error: {e_fb}")
                            self._last_error = "Token stream video telah kedaluwarsa. Silakan refresh halaman video di browser dan gunakan tombol Refresh URL (Ctrl+U)."
                            return False
                    else:
                        self._last_error = f"Token stream video telah kedaluwarsa atau server tidak merespons ({e_fetch}). Silakan refresh halaman di browser dan perbarui URL (Ctrl+U)."
                        return False

            # Check if Master Playlist: pick highest resolution / bandwidth variant
            # m3u8.dev logic: resolve URI in #EXT-X-MEDIA, #EXT-X-SESSION-KEY, #EXT-X-I-FRAME-STREAM-INF
            if "#EXT-X-STREAM-INF" in raw_playlist:
                variants = []
                # Also capture EXT-X-MEDIA renditions (separate audio tracks) — m3u8.dev approach
                media_renditions: Dict[str, List[dict]] = {}  # group_id -> list of {uri, type, language}
                lines = raw_playlist.splitlines()
                for i, line in enumerate(lines):
                    line_strip = line.strip()

                    # Parse #EXT-X-MEDIA renditions (audio/subtitle tracks)
                    if line_strip.startswith("#EXT-X-MEDIA:"):
                        attrs = {}
                        for m_attr in re.finditer(r'([A-Z0-9-]+)=("([^"]*)"|([^,]*))', line_strip[len("#EXT-X-MEDIA:"):]):
                            k = m_attr.group(1).upper()
                            v = (m_attr.group(3) if m_attr.group(3) is not None else m_attr.group(4) or "").strip()
                            attrs[k] = v
                        media_type = attrs.get("TYPE", "")
                        group_id = attrs.get("GROUP-ID", "")
                        uri = attrs.get("URI", "")
                        if group_id and uri and media_type in ("AUDIO", "SUBTITLE"):
                            abs_uri = self._resolve_url(media_url, uri)
                            if group_id not in media_renditions:
                                media_renditions[group_id] = []
                            media_renditions[group_id].append({
                                "uri": abs_uri,
                                "type": media_type,
                                "language": attrs.get("LANGUAGE", ""),
                                "default": attrs.get("DEFAULT", "NO").upper() == "YES"
                            })
                        continue

                    if line_strip.startswith("#EXT-X-STREAM-INF"):
                        bw = 0
                        audio_group = None
                        if "BANDWIDTH=" in line_strip:
                            try:
                                bw_part = line_strip.split("BANDWIDTH=")[1].split(",")[0].split(":")[0]
                                bw = int(bw_part)
                            except Exception:
                                bw = 0
                        # Capture AUDIO group-id for matching with EXT-X-MEDIA renditions
                        ag_match = re.search(r'AUDIO="([^"]*)"', line_strip)
                        if ag_match:
                            audio_group = ag_match.group(1)
                        for next_idx in range(i + 1, len(lines)):
                            cand = lines[next_idx].strip()
                            if cand and not cand.startswith("#"):
                                v_url = self._resolve_url(media_url, cand)
                                variants.append((bw, v_url, audio_group))
                                break

                if variants:
                    variants.sort(key=lambda x: x[0], reverse=True)
                    # Verify reachability of candidates so broken hosts don't crash the download
                    new_media_url = None
                    selected_audio_group = None
                    for _, cand_url, ag in variants:
                        try:
                            cand_bytes, cand_eff_url = self._fetch_url_with_info(cand_url, timeout=8)
                            cand_data = cand_bytes.decode("utf-8", errors="ignore")
                            if "#EXTM3U" in cand_data:
                                new_media_url = cand_eff_url
                                raw_playlist = cand_data
                                selected_audio_group = ag
                                break
                        except Exception as cand_err:
                            print(f"[HLSWorker] Variant {cand_url} failed probe ({cand_err}), testing next quality...")
                            continue

                    if not new_media_url:
                        first_v, first_ag = variants[0][1], variants[0][2]
                        raw_bytes, media_url = self._fetch_url_with_info(first_v, timeout=15)
                        raw_playlist = raw_bytes.decode("utf-8", errors="ignore")
                        selected_audio_group = first_ag
                    else:
                        media_url = new_media_url

                    # Store audio rendition URL for post-processing merge (m3u8.dev approach)
                    self._audio_rendition_url = None
                    if selected_audio_group and selected_audio_group in media_renditions:
                        renditions = media_renditions[selected_audio_group]
                        # Prefer default audio track, then first
                        default_r = next((r for r in renditions if r["default"]), renditions[0] if renditions else None)
                        if default_r and default_r["type"] == "AUDIO":
                            self._audio_rendition_url = default_r["uri"]
                            print(f"[HLSWorker] Found separate audio rendition (GROUP-ID={selected_audio_group}): {self._audio_rendition_url}")

            # Auto-detect Live Stream if Media Playlist has no #EXT-X-ENDLIST!
            if "#EXTINF" in raw_playlist and "#EXT-X-ENDLIST" not in raw_playlist:
                print(f"[HLSWorker] Detected live HLS broadcast (no #EXT-X-ENDLIST) at {media_url}. Switching to continuous live stream recorder...")
                self.is_live = True
                if self.headers is not None:
                    self.headers["is_live"] = "true"
                self.url = media_url
                shutil.rmtree(cache_dir, ignore_errors=True)
                return self._run_as_live_stream()

            # Persist resolved Media Playlist to disk cache so Pause/Resume never needs to re-fetch playlist!
            if "#EXTM3U" in raw_playlist and "#EXTINF" in raw_playlist:
                HLSInspector.cache_playlist(self.url, raw_playlist)
                HLSInspector.cache_playlist(media_url, raw_playlist)
                try:
                    with open(cached_playlist_file, "w", encoding="utf-8") as pf:
                        pf.write(raw_playlist)
                except Exception:
                    pass


            # 2. Parse Media Playlist
            segments: List[dict] = []
            init_segment: Optional[dict] = None
            current_key = None
            current_iv = None
            key_cache: Dict[str, bytes] = {}
            lines = raw_playlist.splitlines()
            media_sequence = 0
            current_byte_offset = 0
            pending_byte_range = None

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
                    try:
                        media_sequence = int(line.split(":")[1].strip())
                    except Exception:
                        pass

                elif line.startswith("#EXT-X-MAP:"):
                    # fMP4 / CMAF initialization segment
                    map_parts = line[len("#EXT-X-MAP:"):].split(",")
                    init_uri = None
                    init_range = None
                    for p in map_parts:
                        if "=" in p:
                            k, v = p.split("=", 1)
                            k = k.strip().upper()
                            v = v.strip().strip('"')
                            if k == "URI":
                                init_uri = self._resolve_url(media_url, v)
                            elif k == "BYTERANGE":
                                init_range = v
                    if init_uri:
                        init_segment = {
                            "url": init_uri,
                            "byte_range": init_range,
                            "key": current_key,
                            "iv": current_iv
                        }

                elif line.startswith("#EXT-X-BYTERANGE:"):
                    # Format: #EXT-X-BYTERANGE:length[@offset]
                    range_val = line[len("#EXT-X-BYTERANGE:"):].strip()
                    if "@" in range_val:
                        length_str, offset_str = range_val.split("@", 1)
                        length = int(length_str.strip())
                        offset = int(offset_str.strip())
                        current_byte_offset = offset + length
                        pending_byte_range = f"bytes={offset}-{offset + length - 1}"
                    else:
                        length = int(range_val)
                        offset = current_byte_offset
                        current_byte_offset += length
                        pending_byte_range = f"bytes={offset}-{offset + length - 1}"

                elif line.startswith("#EXT-X-KEY:"):
                    parts = line[len("#EXT-X-KEY:"):].split(",")
                    method = None
                    key_uri = None
                    iv_hex = None
                    for p in parts:
                        if "=" in p:
                            k, v = p.split("=", 1)
                            k = k.strip().upper()
                            v = v.strip().strip('"')
                            if k == "METHOD":
                                method = v
                            elif k == "URI":
                                key_uri = self._resolve_url(media_url, v)
                            elif k == "IV":
                                iv_hex = v

                    if method == "AES-128" and key_uri:
                        if key_uri not in key_cache:
                            try:
                                if key_uri.startswith("data:"):
                                    import base64
                                    b64_data = key_uri.split(",", 1)[-1]
                                    key_cache[key_uri] = base64.b64decode(b64_data)
                                else:
                                    key_cache[key_uri] = self._fetch_url_data(key_uri)
                            except Exception as k_err:
                                print(f"[HLSWorker] Key fetch failed on {key_uri}: {k_err}")
                                try:
                                    fb_url = self._resolve_working_fallback_stream()
                                    if fb_url and fb_url != self.url:
                                        print(f"[HLSWorker] Recovering key via fallback: {fb_url}")
                                        self.url = fb_url
                                        self._update_task_url(fb_url, self.headers)
                                        parsed_fb = urllib.parse.urlsplit(fb_url)
                                        p_k = urllib.parse.urlsplit(key_uri)
                                        new_k_uri = urllib.parse.urlunsplit((parsed_fb.scheme, parsed_fb.netloc, p_k.path, parsed_fb.query, p_k.fragment))
                                        key_cache[key_uri] = self._fetch_url_data(new_k_uri)
                                except Exception as e_krec:
                                    print(f"[HLSWorker] Key recovery failed: {e_krec}")
                        current_key = key_cache.get(key_uri)
                        if iv_hex:
                            raw_hex = iv_hex[2:] if iv_hex.lower().startswith("0x") else iv_hex
                            try:
                                current_iv = bytes.fromhex(raw_hex)
                            except Exception:
                                current_iv = None
                        else:
                            current_iv = None
                    elif method == "NONE":
                        current_key = None
                        current_iv = None

                elif line.startswith("#EXT-X-SESSION-KEY:"):
                    # m3u8.dev: treat EXT-X-SESSION-KEY exactly like EXT-X-KEY.
                    # Pre-declared in master playlist for session-level key caching.
                    sess_parts = line[len("#EXT-X-SESSION-KEY:"):].split(",")
                    sess_method = None
                    sess_key_uri = None
                    sess_iv_hex = None
                    for p in sess_parts:
                        if "=" in p:
                            k, v = p.split("=", 1)
                            k = k.strip().upper()
                            v = v.strip().strip('"')
                            if k == "METHOD":
                                sess_method = v
                            elif k == "URI":
                                sess_key_uri = self._resolve_url(media_url, v)
                            elif k == "IV":
                                sess_iv_hex = v
                    if sess_method == "AES-128" and sess_key_uri and not sess_key_uri.startswith("skd:"):
                        if sess_key_uri not in key_cache:
                            try:
                                if sess_key_uri.startswith("data:"):
                                    import base64
                                    b64_data = sess_key_uri.split(",", 1)[-1]
                                    key_cache[sess_key_uri] = base64.b64decode(b64_data)
                                else:
                                    key_cache[sess_key_uri] = self._fetch_url_data(sess_key_uri)
                            except Exception as sk_err:
                                print(f"[HLSWorker] Session key fetch failed: {sk_err}")

                elif not line.startswith("#"):
                    seg_url = self._resolve_url(media_url, line)
                    seq_num = media_sequence + len(segments)
                    seg_iv = current_iv if current_iv else seq_num.to_bytes(16, byteorder="big")
                    segments.append({
                        "index": len(segments),
                        "url": seg_url,
                        "byte_range": pending_byte_range,
                        "key": current_key,
                        "iv": seg_iv
                    })
                    pending_byte_range = None

            if not segments:
                return False

            self._total_segments = len(segments)
            self._downloaded_bytes = 0
            self._completed_segments = 0
            self._speed_history.clear()
            seg_file_paths = [None] * len(segments)

            # 3. Check for existing chunks on disk (Resume capability!)
            for item in segments:
                idx = item["index"]
                chunk_file = os.path.join(cache_dir, f"chunk_{idx:06d}.ts")
                if os.path.exists(chunk_file) and os.path.getsize(chunk_file) > 0:
                    # Sanitize any previously saved chunk if it contained obfuscated headers
                    try:
                        with open(chunk_file, "rb") as cf:
                            c_data = cf.read()
                        clean_c = self._strip_stream_obfuscation(c_data)
                        if len(clean_c) != len(c_data):
                            with open(chunk_file, "wb") as cf:
                                cf.write(clean_c)
                    except Exception:
                        pass
                    sz = os.path.getsize(chunk_file)
                    seg_file_paths[idx] = chunk_file
                    self._completed_segments += 1
                    self._downloaded_bytes += sz

            # Report initial progress immediately so UI updates
            if self.on_progress:
                if self._completed_segments > 0:
                    avg_sz = self._downloaded_bytes / self._completed_segments
                    est_init_total = int(avg_sz * self._total_segments)
                    self.on_progress(self._downloaded_bytes, est_init_total, 0.0, 0)
                else:
                    est_init = -1
                    if self.headers and self.headers.get("estimated_size"):
                        try:
                            est_init = int(self.headers["estimated_size"])
                        except Exception:
                            pass
                    self.on_progress(0, est_init, 0.0, 0)

            missing_items = [item for item in segments if seg_file_paths[item["index"]] is None]

            # If stream has fMP4 init segment (#EXT-X-MAP), download it first so concat succeeds
            init_file_path = None
            if init_segment:
                init_file_path = os.path.join(cache_dir, "init.mp4")
                if not os.path.exists(init_file_path) or os.path.getsize(init_file_path) == 0:
                    try:
                        init_headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                            "Accept": "*/*",
                            "Connection": "keep-alive"
                        }
                        if self.headers:
                            for k, v in self.headers.items():
                                if k.lower() in ["referer", "user-agent", "cookie", "authorization"]:
                                    init_headers[k] = v
                        if any(g in init_segment["url"].lower() for g in ["googleusercontent.com", "storage.googleapis.com"]):
                            init_headers.pop("Referer", None)
                            init_headers.pop("Origin", None)
                        elif any(d in init_segment["url"].lower() for d in ["iw01.xyz", "av01"]):
                            init_headers["Referer"] = "https://www.av01.media/"
                            init_headers["Origin"] = "https://www.av01.media"
                            if self._video_id:
                                try:
                                    from .av01_resolver import AV01Resolver
                                    init_segment["url"] = AV01Resolver.sign_segment_url(init_segment["url"], video_id=self._video_id)
                                except Exception:
                                    pass

                        if any(d in init_segment["url"].lower() for d in ["iw01.xyz", "av01"]):
                            init_headers["Connection"] = "close"
                        if init_segment.get("byte_range"):
                            init_headers["Range"] = init_segment["byte_range"]
                        init_req = urllib.request.Request(init_segment["url"], headers=init_headers)
                        with self._opener.open(init_req, timeout=25) as resp:
                            expected_init_len = int(resp.headers.get("Content-Length", 0))
                            init_raw = bytearray()
                            while True:
                                b_init = resp.read(64 * 1024)
                                if not b_init:
                                    break
                                init_raw.extend(b_init)
                            if expected_init_len > 0 and len(init_raw) < expected_init_len:
                                range_hdrs = dict(init_headers, Range=f"bytes={len(init_raw)}-{expected_init_len - 1}")
                                req_r = urllib.request.Request(init_segment["url"], headers=range_hdrs)
                                with self._opener.open(req_r, timeout=15) as resp_r:
                                    init_raw.extend(resp_r.read())
                            init_clean = self._strip_stream_obfuscation(bytes(init_raw))
                            with open(init_file_path, "wb") as f_init:
                                f_init.write(init_clean)
                    except Exception as e:
                        print(f"[!] Note: Could not download init segment: {e}")

            # 4. Multi-Stream Worker Pool
            # TikTok CDN hard-blocks >3 simultaneous connections per IP (returns 403/timeout for extras).
            # Auto-detect TikTok CDN segments and cap at 3 workers to avoid stall-at-0-bytes.
            CDN_THROTTLE_PATTERNS = ["tiktokcdn.com", "tiktok.com/ad-site", "tiktokv.com"]
            first_seg_url = (segments[0]["url"] if segments else "").lower()
            is_tiktok_cdn = any(p in first_seg_url for p in CDN_THROTTLE_PATTERNS)
            max_connections = self.connections or 16
            if is_tiktok_cdn and max_connections > 3:
                max_connections = 3
                print(f"[HLSWorker] TikTok CDN detected - capping concurrent connections at 3 to avoid rate limiting")
            num_workers = min(max_connections, max(2, len(missing_items))) if missing_items else 1
            if self.segment_slots:
                # Trim excess slots if CDN throttle reduced num_workers below initial slot count
                if len(self.segment_slots) > num_workers:
                    del self.segment_slots[num_workers:]
                while len(self.segment_slots) < num_workers:
                    from .models import SegmentModel
                    self.segment_slots.append(SegmentModel(
                        index=len(self.segment_slots),
                        start_byte=0,
                        end_byte=1000000,
                        downloaded_bytes=0,
                        status="Connecting..."
                    ))
                if self.segment_slots:
                    for s_obj in self.segment_slots:
                        s_obj.status = "Connecting..."

            work_queue = queue.Queue()
            for item in missing_items:
                work_queue.put(item)

            unresolved_chunks = []
            unresolved_lock = threading.Lock()
            consecutive_failures = 0
            circuit_breaker_tripped = threading.Event()

            def download_single_chunk(item: dict, slot_id: int) -> bool:
                if self.cancel_event and self.cancel_event.is_set():
                    return False
                if self.pause_event:
                    self.pause_event.wait()

                idx = item["index"]
                url = item["url"]
                key = item["key"]
                iv = item["iv"]
                chunk_file = os.path.join(cache_dir, f"chunk_{idx:06d}.ts")

                # Double check resume
                if os.path.exists(chunk_file) and os.path.getsize(chunk_file) > 0:
                    with self._lock:
                        seg_file_paths[idx] = chunk_file
                    return True

                parsed = urllib.parse.urlsplit(url)
                default_referer = f"{parsed.scheme}://{parsed.netloc}/"

                ref = None
                if self.headers:
                    ref = self.headers.get("Referer") or self.headers.get("referer") or self.headers.get("page_url")
                if not ref:
                    ref = default_referer

                origin = None
                if self.headers:
                    origin = self.headers.get("Origin") or self.headers.get("origin")
                if not origin and ref:
                    p_ref = urllib.parse.urlsplit(ref)
                    if p_ref.scheme and p_ref.netloc:
                        origin = f"{p_ref.scheme}://{p_ref.netloc}"
                if not origin:
                    origin = f"{parsed.scheme}://{parsed.netloc}"

                req_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "*/*",
                    "Accept-Encoding": "gzip, deflate, identity",
                    "Connection": "keep-alive",
                    "Referer": ref,
                    "Origin": origin
                }
                if self.headers:
                    for k, v in self.headers.items():
                        k_low = k.lower()
                        if k_low == "user-agent":
                            req_headers["User-Agent"] = v
                        elif k_low == "cookie":
                            req_headers["Cookie"] = v
                        elif k_low in ["authorization"]:
                            req_headers[k] = v

                # Public Object Storage / Ad-Site CDN check:
                # Do NOT forward third-party embed referers or cookies to Google/TikTok/ByteImg CDNs
                # or their WAF immediately drops/rejects with HTTP 403 / 429 / Timeout!
                seg_lower = url.lower()
                NO_REFERER_CDNS = (
                    "googleusercontent.com",
                    "storage.googleapis.com",
                    "tiktokcdn.com",
                    "tiktokv.com",
                    "tiktok.com/ad-site",
                    "ibyteimg.com",
                    "byteimg.com",
                    "fbcdn.net",
                )
                if any(g in seg_lower for g in NO_REFERER_CDNS):
                    req_headers.pop("Referer", None)
                    req_headers.pop("Origin", None)
                    req_headers.pop("Cookie", None)
                else:
                    # Do not leak top-level website cookies to unrelated segment CDN domains
                    ref_host = urllib.parse.urlsplit(ref).netloc.lower() if ref else ""
                    seg_host = parsed.netloc.lower()
                    if ref_host and seg_host and (ref_host != seg_host) and not seg_host.endswith("." + ref_host):
                        req_headers.pop("Cookie", None)

                if item.get("byte_range"):
                    req_headers["Range"] = item["byte_range"]

                # Retry up to 5 times (or at most 2 for 401/403/404) with exponential backoff & jitter
                for attempt in range(5):
                    if self.cancel_event and self.cancel_event.is_set():
                        return False
                    if circuit_breaker_tripped.is_set():
                        return False
                    if self.pause_event:
                        self.pause_event.wait()

                    # Self-healing header rotation: if attempt 0 failed, strip third-party Referer/Origin/Cookie
                    attempt_headers = dict(req_headers)
                    is_av01_host = ("iw01.xyz" in seg_lower or "av01" in seg_lower)
                    if attempt >= 1 and not is_av01_host:
                        attempt_headers.pop("Cookie", None)
                        if attempt >= 2:
                            attempt_headers.pop("Referer", None)
                            attempt_headers.pop("Origin", None)
                    elif is_av01_host:
                        attempt_headers["Referer"] = "https://www.av01.media/"
                        attempt_headers["Origin"] = "https://www.av01.media"

                    partial_bytes_this_attempt = 0
                    try:
                        if self.segment_slots and slot_id < len(self.segment_slots):
                            self.segment_slots[slot_id].status = f"Connecting #{idx+1}..."

                        # For Cloudflare edge / AV01 / IW01 endpoints, force Connection: close
                        # to prevent socket stalls and premature stream truncation
                        if is_av01_host:
                            attempt_headers["Connection"] = "close"

                        req = urllib.request.Request(url, headers=attempt_headers)
                        raw_data = bytearray()
                        expected_chunk_len = -1
                        content_encoding = ""

                        try:
                            with self._opener.open(req, timeout=20) as resp:
                                content_encoding = resp.headers.get("Content-Encoding", "").lower()
                                cl_hdr = resp.headers.get("Content-Length")
                                if cl_hdr:
                                    try:
                                        expected_chunk_len = int(cl_hdr.strip())
                                    except Exception:
                                        pass

                                while True:
                                    if self.cancel_event and self.cancel_event.is_set():
                                        return False
                                    if self.pause_event:
                                        self.pause_event.wait()

                                    block = resp.read(64 * 1024)
                                    if not block:
                                        break

                                    raw_data.extend(block)
                                    b_len = len(block)
                                    partial_bytes_this_attempt += b_len

                                    if self.speed_limiter:
                                        self.speed_limiter.acquire(b_len)

                                    with self._lock:
                                        self._downloaded_bytes += b_len
                                        if self.segment_slots and slot_id < len(self.segment_slots):
                                            self.segment_slots[slot_id].downloaded_bytes += b_len
                                            self.segment_slots[slot_id].status = "Receiving data"
                                            self.segment_slots[slot_id].progress = min(1.0, self._completed_segments / max(1, self._total_segments))

                                        smoothed_spd = self._calculate_rolling_speed(self._downloaded_bytes)
                                        if self._completed_segments >= 1:
                                            avg_chunk = self._downloaded_bytes / max(1, self._completed_segments)
                                            est_total = int(avg_chunk * self._total_segments)
                                        else:
                                            est_total = -1
                                            if self.headers and self.headers.get("estimated_size"):
                                                try:
                                                    est_total = int(self.headers["estimated_size"])
                                                except Exception:
                                                    pass

                                        eta = int((est_total - self._downloaded_bytes) / smoothed_spd) if (smoothed_spd > 0 and est_total > self._downloaded_bytes) else 0

                                        if self.on_progress:
                                            self.on_progress(self._downloaded_bytes, est_total, smoothed_spd, eta)

                        except http.client.IncompleteRead as inc_err:
                            if inc_err.partial:
                                raw_data.extend(inc_err.partial)
                                b_len = len(inc_err.partial)
                                partial_bytes_this_attempt += b_len
                                with self._lock:
                                    self._downloaded_bytes += b_len
                                    if self.segment_slots and slot_id < len(self.segment_slots):
                                        self.segment_slots[slot_id].downloaded_bytes += b_len

                        # Partial read recovery: If expected Content-Length was not fully received
                        # (common on Cloudflare edge terminating TCP with Connection: close),
                        # resume and recover missing tail bytes using HTTP Range header!
                        if expected_chunk_len > 0 and len(raw_data) < expected_chunk_len:
                            range_headers = dict(attempt_headers)
                            range_headers["Range"] = f"bytes={len(raw_data)}-{expected_chunk_len - 1}"
                            range_headers["Connection"] = "close"
                            req_range = urllib.request.Request(url, headers=range_headers)
                            try:
                                with self._opener.open(req_range, timeout=15) as resp_range:
                                    while True:
                                        if self.cancel_event and self.cancel_event.is_set():
                                            return False
                                        block = resp_range.read(64 * 1024)
                                        if not block:
                                            break
                                        raw_data.extend(block)
                                        b_len = len(block)
                                        partial_bytes_this_attempt += b_len
                                        with self._lock:
                                            self._downloaded_bytes += b_len
                                            if self.segment_slots and slot_id < len(self.segment_slots):
                                                self.segment_slots[slot_id].downloaded_bytes += b_len
                            except Exception as e_range:
                                print(f"[HLSWorker] Range recovery notice on chunk #{idx}: {e_range}")

                        # Strict byte verification: never accept a truncated chunk
                        if expected_chunk_len > 0 and len(raw_data) < expected_chunk_len:
                            raise Exception(f"Chunk #{idx+1} truncated: got {len(raw_data)}/{expected_chunk_len} bytes")

                        if not raw_data:
                            raise Exception("Empty chunk received")

                        data = bytes(raw_data)
                        if "gzip" in content_encoding or (len(data) >= 2 and data[:2] == b"\x1f\x8b"):
                            try:
                                import gzip
                                data = gzip.decompress(data)
                            except Exception:
                                pass
                        elif "deflate" in content_encoding:
                            try:
                                import zlib
                                data = zlib.decompress(data)
                            except Exception:
                                try:
                                    import zlib
                                    data = zlib.decompress(data, -zlib.MAX_WBITS)
                                except Exception:
                                    pass

                        if key and HAS_CRYPTOGRAPHY:
                            try:
                                cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
                                decryptor = cipher.decryptor()
                                if len(data) % 16 == 0:
                                    dec = decryptor.update(data) + decryptor.finalize()
                                    pad_len = dec[-1]
                                    if 1 <= pad_len <= 16 and dec[-pad_len:] == bytes([pad_len] * pad_len):
                                        data = dec[:-pad_len]
                                    else:
                                        data = dec
                            except Exception as e_dec:
                                print(f"[HLSWorker] Decrypt error on chunk #{idx}: {e_dec}")

                        # Deobfuscate fake image wrappers (e.g. 1x1 PNG/JPEG headers used by anti-scraping CDN/sites)
                        data = self._strip_stream_obfuscation(data)

                        if not data or len(data) == 0:
                            raise ValueError(f"Empty chunk #{idx+1} received (0 bytes)")

                        with open(chunk_file, "wb") as cf:
                            cf.write(data)

                        with self._lock:
                            self._completed_segments += 1
                            seg_file_paths[idx] = chunk_file

                        return True

                    except Exception as exc:
                        # Revert partial bytes from failed attempt to maintain accurate byte counters
                        if partial_bytes_this_attempt > 0:
                            with self._lock:
                                self._downloaded_bytes = max(0, self._downloaded_bytes - partial_bytes_this_attempt)
                                if self.segment_slots and slot_id < len(self.segment_slots):
                                    self.segment_slots[slot_id].downloaded_bytes = max(0, self.segment_slots[slot_id].downloaded_bytes - partial_bytes_this_attempt)

                        if self.segment_slots and slot_id < len(self.segment_slots):
                            self.segment_slots[slot_id].status = f"Retrying #{idx+1}..."

                        exc_str = str(exc)
                        self._last_error = f"Chunk #{idx+1} failed: {exc_str}"

                        # Auto-refresh token on 401 / 403 Forbidden for AV01 CDN
                        if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403):
                            if "iw01.xyz" in url.lower() or "av01" in url.lower():
                                try:
                                    from .av01_resolver import AV01Resolver
                                    new_signed_url = AV01Resolver.sign_segment_url(url, video_id=self._video_id, force_refresh=True)
                                    if new_signed_url != url:
                                        url = new_signed_url
                                        item["url"] = new_signed_url
                                        time.sleep(0.5)
                                        continue
                                except Exception:
                                    pass

                        # If redirect/auth failure or 404: do not waste endless retries (fail fast)
                        is_auth_or_404 = (
                            isinstance(exc, urllib.error.HTTPError) and (
                                exc.code in (301, 302, 303, 307, 308, 401, 403, 404, 410)
                            )
                        )
                        if is_auth_or_404:
                            item["_auth_failed"] = True
                            break

                        is_throttled = (
                            "429" in exc_str or "503" in exc_str or
                            "403" in exc_str or
                            isinstance(exc, TimeoutError) or
                            "timed out" in exc_str.lower() or
                            "connectionreset" in exc_str.lower() or
                            "connection reset" in exc_str.lower()
                        )
                        if attempt < 4:
                            if is_throttled:
                                backoff = 1.5 + random.uniform(0.3, 1.2)
                            else:
                                backoff = min(4.0, 0.3 * (1.5 ** attempt) + random.uniform(0.1, 0.3))
                            time.sleep(backoff)

                return False

            def worker_loop(slot_id: int):
                nonlocal consecutive_failures
                while not work_queue.empty() and not circuit_breaker_tripped.is_set():
                    if self.cancel_event and self.cancel_event.is_set():
                        break
                    if self.pause_event:
                        self.pause_event.wait()

                    try:
                        item = work_queue.get_nowait()
                    except queue.Empty:
                        break

                    succ = download_single_chunk(item, slot_id)
                    with unresolved_lock:
                        if succ:
                            consecutive_failures = 0
                        else:
                            if not (self.cancel_event and self.cancel_event.is_set()):
                                unresolved_chunks.append(item)
                                consecutive_failures += 1
                                # Circuit Breaker:
                                # Fast trip on redirect/auth failure (consecutive_failures >= 3),
                                # or general consecutive failures >= 16
                                auth_failed = item.get("_auth_failed", False)
                                if (auth_failed and consecutive_failures >= 3) or (self._completed_segments == 0 and consecutive_failures >= 6) or consecutive_failures >= max(16, num_workers * 2):
                                    print(f"[HLSWorker] Circuit breaker tripped: {consecutive_failures} consecutive chunk failures (auth_failed={auth_failed}). Auto-renewing stream link...")
                                    circuit_breaker_tripped.set()
                    work_queue.task_done()

            if missing_items:
                threads = []
                for s_id in range(num_workers):
                    t = threading.Thread(target=worker_loop, args=(s_id,), daemon=True)
                    threads.append(t)
                    t.start()
                    # Stagger thread startup for CDN-throttled hosts (e.g. TikTok) to avoid
                    # simultaneous connection bursts triggering rate limiting on all workers at once.
                    if is_tiktok_cdn and s_id < num_workers - 1:
                        time.sleep(0.2)

                for t in threads:
                    t.join()

                # If circuit breaker was tripped, attempt automatic stream URL renewal before falling back
                if circuit_breaker_tripped.is_set():
                    print("[HLSWorker] Circuit breaker tripped! Attempting automatic stream URL refresh...")
                    try:
                        from .link_resolver import CloudLinkResolver
                        fresh_url, fresh_hdrs = CloudLinkResolver.resolve_stream_url(self.url, self.headers)
                        if not fresh_url or fresh_url == self.url:
                            fresh_url = self._resolve_working_fallback_stream()
                        if fresh_url and fresh_url != self.url:
                            print(f"[HLSWorker] Successfully auto-renewed expired stream URL: {fresh_url}")
                            self.url = fresh_url
                            if self.headers and fresh_hdrs:
                                self.headers.update(fresh_hdrs)
                            self._update_task_url(fresh_url, self.headers)
                            self.headers.pop("m3u8_content", None)
                            HLSInspector.cache_playlist(self.url, "")
                            raw_bytes, media_url = self._fetch_url_with_info(self.url, timeout=15, bypass_cache=True)
                            raw_new_text = raw_bytes.decode("utf-8", errors="ignore")

                            # If fresh_url was master, resolve variant
                            if "#EXT-X-STREAM-INF" in raw_new_text:
                                lines = raw_new_text.splitlines()
                                for i, l in enumerate(lines):
                                    if l.startswith("#EXT-X-STREAM-INF"):
                                        for nxt in range(i + 1, len(lines)):
                                            c_line = lines[nxt].strip()
                                            if c_line and not c_line.startswith("#"):
                                                media_url = self._resolve_url(media_url, c_line)
                                                raw_bytes, media_url = self._fetch_url_with_info(media_url, timeout=15, bypass_cache=True)
                                                raw_new_text = raw_bytes.decode("utf-8", errors="ignore")
                                                break
                                        break

                            # Save fresh playlist to disk cache
                            try:
                                with open(cached_playlist_file, "w", encoding="utf-8") as pf:
                                    pf.write(raw_new_text)
                            except Exception:
                                pass

                            parsed_fresh = urllib.parse.urlsplit(media_url)
                            fresh_query = parsed_fresh.query

                            # Re-extract AES key from fresh playlist
                            fresh_key_bytes = None
                            if "#EXT-X-KEY:" in raw_new_text:
                                for l in raw_new_text.splitlines():
                                    if l.startswith("#EXT-X-KEY:"):
                                        k_m = re.search(r'URI="([^"]+)"', l)
                                        if k_m:
                                            new_key_uri = self._resolve_url(media_url, k_m.group(1))
                                            try:
                                                fresh_key_bytes = self._fetch_url_data(new_key_uri)
                                                key_cache[new_key_uri] = fresh_key_bytes
                                                break
                                            except Exception as k_e:
                                                print(f"[HLSWorker] Key fetch on renewal failed: {k_e}")

                            # Build fresh segment URLs list
                            fresh_seg_urls = []
                            for l in raw_new_text.splitlines():
                                l_s = l.strip()
                                if l_s and not l_s.startswith("#"):
                                    fresh_seg_urls.append(self._resolve_url(media_url, l_s))

                            for item in missing_items:
                                idx = item["index"]
                                if idx < len(fresh_seg_urls):
                                    item["url"] = fresh_seg_urls[idx]
                                elif fresh_query:
                                    p_u = urllib.parse.urlsplit(item["url"])
                                    item["url"] = urllib.parse.urlunsplit((parsed_fresh.scheme, parsed_fresh.netloc, p_u.path, fresh_query, p_u.fragment))
                                if fresh_key_bytes:
                                    item["key"] = fresh_key_bytes

                            circuit_breaker_tripped.clear()
                            consecutive_failures = 0
                            for item in unresolved_chunks:
                                work_queue.put(item)
                            unresolved_chunks.clear()
                            retry_threads = []
                            for s_id in range(num_workers):
                                t = threading.Thread(target=worker_loop, args=(s_id,), daemon=True)
                                retry_threads.append(t)
                                t.start()
                            for t in retry_threads:
                                t.join()
                    except Exception as e_renew:
                        print(f"[HLSWorker] Auto-renewal failed: {e_renew}")

                if circuit_breaker_tripped.is_set():
                    print("[HLSWorker] Native Concurrent Engine aborted via circuit breaker. Proceeding to fallback...")
                    self._last_error = "Token sesi stream video telah kedaluwarsa (HTTP 401/403/Redirect). Silakan buka halaman video di browser lalu perbarui URL (Ctrl+U)."
                    return False

                # Multi-pass retry for any missing chunks (up to 3 passes)
                retry_pass = 0
                while None in seg_file_paths and retry_pass < 3 and not self._is_cancelled and not (self.cancel_event and self.cancel_event.is_set()):
                    retry_pass += 1
                    missing = [item for item in segments if seg_file_paths[item["index"]] is None]
                    if not missing:
                        break
                    print(f"[HLSWorker] Missing {len(missing)} chunks after pass. Starting retry round {retry_pass}/3...")
                    circuit_breaker_tripped.clear()
                    consecutive_failures = 0
                    time.sleep(1.0)
                    for item in missing:
                        # Auto-refresh CDN token for AV01/IW01 on retry rounds
                        if self._video_id and any(k in item["url"].lower() for k in ("iw01.xyz", "av01")):
                            try:
                                from .av01_resolver import AV01Resolver
                                item["url"] = AV01Resolver.sign_segment_url(item["url"], video_id=self._video_id, force_refresh=(retry_pass > 1))
                            except Exception:
                                pass
                        work_queue.put(item)

                    retry_threads = []
                    for s_id in range(min(num_workers, len(missing))):
                        t = threading.Thread(target=worker_loop, args=(s_id,), daemon=True)
                        retry_threads.append(t)
                        t.start()

                    for t in retry_threads:
                        t.join()

            if self.cancel_event and self.cancel_event.is_set():
                self._is_cancelled = True
                return False

            if None in seg_file_paths:
                return False

            # 5. Direct Binary Concatenation + Lossless Remuxing (FetchV methodology)
            merged_ts_path = os.path.join(cache_dir, "merged.ts")
            try:
                with open(merged_ts_path, "wb") as f_out:
                    if init_file_path and os.path.exists(init_file_path) and os.path.getsize(init_file_path) > 0:
                        with open(init_file_path, "rb") as f_in:
                            shutil.copyfileobj(f_in, f_out)
                    for sp in seg_file_paths:
                        if sp and os.path.exists(sp):
                            with open(sp, "rb") as f_in:
                                shutil.copyfileobj(f_in, f_out)
            except Exception as e_merge:
                print(f"[HLSWorker] Binary TS merge notice: {e_merge}")

            concat_path = os.path.join(cache_dir, "concat.txt")
            with open(concat_path, "w", encoding="utf-8") as f:
                if init_file_path and os.path.exists(init_file_path) and os.path.getsize(init_file_path) > 0:
                    clean_init = init_file_path.replace(os.sep, "/").replace("'", r"'\''")
                    f.write(f"file '{clean_init}'\n")
                for sp in seg_file_paths:
                    if sp and os.path.exists(sp):
                        clean_sp = sp.replace(os.sep, "/").replace("'", r"'\''")
                        f.write(f"file '{clean_sp}'\n")

            dir_name = os.path.dirname(os.path.abspath(self.target_path))
            os.makedirs(dir_name, exist_ok=True)

            flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
            sinfo = None
            if sys.platform == "win32":
                sinfo = subprocess.STARTUPINFO()
                sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                sinfo.wShowWindow = 0

            remux_success = False

            # Strategy A: Direct remux of merged.ts with Universal M3U8 Seek Fixer flags
            # Input flags (-fflags +genpts+igndts) MUST precede -i; output flags (-avoid_negative_ts, -max_interleave_delta, -movflags) MUST follow -i.
            merged_size = os.path.getsize(merged_ts_path) if os.path.exists(merged_ts_path) else 0
            min_acceptable_size = int(merged_size * 0.7) if merged_size > (10 * 1024 * 1024) else 1024

            if ffmpeg_bin and os.path.exists(merged_ts_path) and merged_size > 1024:
                extra_out_flags = ["-movflags", "+faststart"] if self.target_path.lower().endswith(".mp4") else []
                cmd_a = [
                    ffmpeg_bin, "-y",
                    "-fflags", "+genpts+igndts",
                    "-i", merged_ts_path,
                    "-map", "0:v?",
                    "-map", "0:a?",
                    "-map", "0:s?",
                    "-c", "copy",
                    "-bsf:a", "aac_adtstoasc",
                    "-avoid_negative_ts", "make_zero",
                    "-max_interleave_delta", "0",
                    *extra_out_flags,
                    self.target_path
                ]
                res_a = subprocess.run(cmd_a, capture_output=True, creationflags=flag, startupinfo=sinfo)
                if res_a.returncode == 0 and os.path.exists(self.target_path) and os.path.getsize(self.target_path) >= min_acceptable_size:
                    remux_success = True
                else:
                    if os.path.exists(self.target_path) and os.path.getsize(self.target_path) < min_acceptable_size:
                        print(f"[HLSWorker] Strategy A produced truncated output ({os.path.getsize(self.target_path)} vs merged {merged_size}). Retrying...")
                        try:
                            os.remove(self.target_path)
                        except Exception:
                            pass
                    # Retry without -bsf:a (for MP3/Opus/AC3 audio tracks in HLS)
                    cmd_b = [
                        ffmpeg_bin, "-y",
                        "-fflags", "+genpts+igndts",
                        "-i", merged_ts_path,
                        "-map", "0:v?",
                        "-map", "0:a?",
                        "-map", "0:s?",
                        "-c", "copy",
                        "-avoid_negative_ts", "make_zero",
                        "-max_interleave_delta", "0",
                        *extra_out_flags,
                        self.target_path
                    ]
                    res_b = subprocess.run(cmd_b, capture_output=True, creationflags=flag, startupinfo=sinfo)
                    if res_b.returncode == 0 and os.path.exists(self.target_path) and os.path.getsize(self.target_path) >= min_acceptable_size:
                        remux_success = True
                    elif os.path.exists(self.target_path) and os.path.getsize(self.target_path) < min_acceptable_size:
                        try:
                            os.remove(self.target_path)
                        except Exception:
                            pass

            # Strategy B: Concat demuxer with Universal Seek Fixer flags
            if not remux_success and ffmpeg_bin and os.path.exists(concat_path):
                extra_out_flags = ["-movflags", "+faststart"] if self.target_path.lower().endswith(".mp4") else []
                cmd_c = [
                    ffmpeg_bin, "-y",
                    "-fflags", "+genpts+igndts",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_path,
                    "-map", "0:v?",
                    "-map", "0:a?",
                    "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    "-max_interleave_delta", "0",
                    *extra_out_flags,
                    self.target_path
                ]
                res_c = subprocess.run(cmd_c, capture_output=True, creationflags=flag, startupinfo=sinfo)
                if res_c.returncode == 0 and os.path.exists(self.target_path) and os.path.getsize(self.target_path) >= min_acceptable_size:
                    remux_success = True
                elif os.path.exists(self.target_path) and os.path.getsize(self.target_path) < min_acceptable_size:
                    try:
                        os.remove(self.target_path)
                    except Exception:
                        pass

            # Strategy C (FetchV Fallback): If FFmpeg is missing or remux fails, preserve merged stream then run seek fixer
            if not remux_success and os.path.exists(merged_ts_path) and merged_size > 1024:
                try:
                    shutil.copy2(merged_ts_path, self.target_path)
                    self.fix_media_seek_and_container(self.target_path)
                    remux_success = (os.path.exists(self.target_path) and os.path.getsize(self.target_path) >= min_acceptable_size)
                except Exception:
                    pass

            if remux_success and os.path.exists(self.target_path) and os.path.getsize(self.target_path) > 1024:
                # m3u8.dev approach: if master playlist had a separate audio rendition (EXT-X-MEDIA AUDIO),
                # download and mux it into the final MP4 (common for TV/streaming sites with video+audio split)
                if self._audio_rendition_url and ffmpeg_bin and not self._is_cancelled:
                    try:
                        print(f"[HLSWorker] Downloading separate audio track: {self._audio_rendition_url}")
                        audio_target = os.path.join(cache_dir, "audio_track.mp4")
                        # Re-run the concurrent engine concept for just the audio rendition
                        # Use HLSWorker sub-instance to download audio playlist
                        audio_worker = HLSWorker(
                            url=self._audio_rendition_url,
                            target_path=audio_target,
                            task_id=None,
                            connections=3,
                            headers=self.headers,
                            proxy=self.proxy,
                        )
                        audio_worker.start()
                        audio_worker.join(timeout=300)  # Wait up to 5 min for audio
                        if not audio_worker._is_cancelled and os.path.exists(audio_target) and os.path.getsize(audio_target) > 0:
                            # Mux video + audio into final output
                            muxed_path = self.target_path + ".muxed.mp4"
                            cmd_mux = [
                                ffmpeg_bin, "-y",
                                "-i", self.target_path,
                                "-i", audio_target,
                                "-c", "copy",
                                "-map", "0:v:0",
                                "-map", "1:a:0",
                                "-movflags", "+faststart",
                                muxed_path
                            ]
                            res_mux = subprocess.run(cmd_mux, capture_output=True, creationflags=flag, startupinfo=sinfo)
                            if res_mux.returncode == 0 and os.path.exists(muxed_path) and os.path.getsize(muxed_path) > 1024:
                                os.replace(muxed_path, self.target_path)
                                print(f"[HLSWorker] Audio track muxed successfully into {self.target_path}")
                            else:
                                print(f"[HLSWorker] Audio mux failed (returncode={res_mux.returncode}), keeping video-only output")
                                try:
                                    os.remove(muxed_path)
                                except Exception:
                                    pass
                        else:
                            print(f"[HLSWorker] Audio track download failed or produced empty file, keeping video-only output")
                    except Exception as audio_err:
                        print(f"[HLSWorker] Audio track mux error (non-fatal): {audio_err}")

                final_sz = os.path.getsize(self.target_path)
                if self.segment_slots:
                    for s in self.segment_slots:
                        s.status = "Completed"
                if self.on_progress:
                    self.on_progress(final_sz, final_sz, 0.0, 0)
                shutil.rmtree(cache_dir, ignore_errors=True)
                self.cleanup_temp_fragments(self.target_path)
                return True

            return False
        except Exception as e_engine:
            print(f"[HLSWorker] Concurrent engine error: {e_engine}")
            self._last_error = f"Engine error: {e_engine}"
            return False

    @staticmethod
    def cleanup_temp_fragments(target_path: str):
        """
        Deletes all temporary fragment/part files (.part-Frag*, .part*, .ytdl, .temp*)
        associated with target_path or orphaned in its destination directory.
        """
        if not target_path:
            return
        try:
            abs_target = os.path.abspath(target_path)
            dir_name = os.path.dirname(abs_target)
            if not os.path.isdir(dir_name):
                return
            base_name = os.path.basename(abs_target)
            base_stem, _ = os.path.splitext(base_name)

            for fname in os.listdir(dir_name):
                if fname == base_name:
                    continue
                is_target_temp = (
                    fname.startswith(base_name + ".part") or
                    fname.startswith(base_stem + ".part") or
                    fname.startswith(base_name + ".temp") or
                    fname.startswith(base_stem + ".temp") or
                    fname.startswith(base_name + ".ytdl") or
                    fname.startswith(base_stem + ".ytdl") or
                    (fname.startswith(base_stem + ".f") and (".part" in fname or fname.endswith(".m4a") or fname.endswith(".mp4") or fname.endswith(".webm"))) or
                    ".part-Frag" in fname or
                    fname.endswith(".ytdl")
                )
                if is_target_temp:
                    full_f = os.path.join(dir_name, fname)
                    try:
                        if os.path.isfile(full_f):
                            os.remove(full_f)
                    except Exception:
                        pass
        except Exception:
            pass

    @staticmethod
    def fix_media_seek_and_container(file_path: str) -> bool:
        """
        Universal M3U8/MP4/MKV Seek Fixer & Container Normalizer:
        Works on ANY .mp4 or .mkv file—including M3U8 downloads that were already saved as .mp4
        (even if internally raw MPEG-TS from external downloaders/yt-dlp or fragmented MP4 with broken PTS/DTS).
        Performs lossless stream copy (-c copy) with:
          - Input:  -fflags +genpts+igndts
          - Output: -map 0:v? -map 0:a? -map 0:s? -c copy [-bsf:a aac_adtstoasc]
                    -avoid_negative_ts make_zero -max_interleave_delta 0 [-movflags +faststart]
        Replaces file_path atomically in-place.
        """
        if not file_path or not os.path.exists(file_path) or os.path.getsize(file_path) < 1024:
            return False

        ffmpeg_bin = AudioMuxer.get_ffmpeg_path()
        if not ffmpeg_bin:
            return False

        flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
        sinfo = None
        if sys.platform == "win32":
            sinfo = subprocess.STARTUPINFO()
            sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            sinfo.wShowWindow = 0

        base_no_ext, ext = os.path.splitext(file_path)
        if not ext:
            ext = ".mp4"
        temp_out = f"{base_no_ext}._seekfix{ext}"
        extra_flags = ["-movflags", "+faststart"] if ext.lower() == ".mp4" else []

        # Attempt 1: Full remux with AAC ADTS-to-ASC filter (essential when .mp4 is actually raw MPEG-TS)
        cmd_1 = [
            ffmpeg_bin, "-y",
            "-fflags", "+genpts+igndts",
            "-i", file_path,
            "-map", "0:v?",
            "-map", "0:a?",
            "-map", "0:s?",
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-avoid_negative_ts", "make_zero",
            "-max_interleave_delta", "0",
            *extra_flags,
            temp_out
        ]
        orig_sz = os.path.getsize(file_path)
        # For fMP4/live streams, container remuxing safely merges metadata and overhead (can be 45-70% of raw)
        min_safe_sz = max(1024, int(orig_sz * 0.45))

        try:
            res = subprocess.run(cmd_1, capture_output=True, creationflags=flag, startupinfo=sinfo)
            if res.returncode != 0 or not os.path.exists(temp_out) or os.path.getsize(temp_out) < min_safe_sz:
                # Attempt 2: Without -bsf:a aac_adtstoasc (for MP3/Opus/AC3 audio or already-ASC MP4)
                cmd_2 = [
                    ffmpeg_bin, "-y",
                    "-merge_pmt_versions", "1",
                    "-scan_all_pmts", "1",
                    "-fflags", "+genpts+igndts+discardcorrupt",
                    "-err_detect", "ignore_err",
                    "-i", file_path,
                    "-map", "0:v?",
                    "-map", "0:a?",
                    "-map", "0:s?",
                    "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    "-max_interleave_delta", "0",
                    *extra_flags,
                    temp_out
                ]
                res = subprocess.run(cmd_2, capture_output=True, creationflags=flag, startupinfo=sinfo)

            # Attempt 3: General tolerant stream copy if previous attempts failed
            if res.returncode != 0 or not os.path.exists(temp_out) or os.path.getsize(temp_out) < min_safe_sz:
                cmd_3 = [
                    ffmpeg_bin, "-y",
                    "-fflags", "+genpts+igndts+discardcorrupt",
                    "-err_detect", "ignore_err",
                    "-i", file_path,
                    "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    "-max_interleave_delta", "0",
                    *extra_flags,
                    temp_out
                ]
                res = subprocess.run(cmd_3, capture_output=True, creationflags=flag, startupinfo=sinfo)

            if res.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) >= min_safe_sz:
                os.replace(temp_out, file_path)
                return True
        except Exception as e:
            print(f"[HLSWorker] Seek fixer error on {file_path}: {e}")
        finally:
            if os.path.exists(temp_out):
                try:
                    os.remove(temp_out)
                except Exception:
                    pass
        return False

    def _run_with_ytdlp(self) -> bool:
        """
        Stage 2 Fallback: Multi-threaded yt-dlp with concurrent fragments & rolling speed smoothing.
        """
        temp_ytdlp_dir = os.path.join(tempfile.gettempdir(), f"z_{self.task_id[:8]}")
        try:
            _ensure_valid_certifi()
            import yt_dlp
            ffmpeg_path = AudioMuxer.get_ffmpeg_path()

            dir_name = os.path.dirname(os.path.abspath(self.target_path))
            os.makedirs(dir_name, exist_ok=True)
            os.makedirs(temp_ytdlp_dir, exist_ok=True)

            raw_hdrs = CloudLinkResolver.fix_headers(self.url, dict(self.headers or {}))
            INTERNAL_META_KEYS = {"is_hls", "is_dash", "is_live", "resolution", "bitrate", "estimated_size", "fallback_urls", "master_url", "page_url", "selected_files", "m3u8_content"}
            headers_dict = {k: v for k, v in raw_hdrs.items() if k.lower() not in INTERNAL_META_KEYS and isinstance(v, str)}
            if "User-Agent" not in headers_dict and "user-agent" not in headers_dict:
                headers_dict["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            if "Referer" not in headers_dict and "referer" not in headers_dict:
                page_u = (self.headers or {}).get("page_url")
                if page_u:
                    headers_dict["Referer"] = page_u
                else:
                    parsed_u = urllib.parse.urlsplit(self.url)
                    headers_dict["Referer"] = f"{parsed_u.scheme}://{parsed_u.netloc}/"
            if "Origin" not in headers_dict and "origin" not in headers_dict:
                ref_val = headers_dict.get("Referer") or headers_dict.get("referer")
                if ref_val:
                    parsed_ref = urllib.parse.urlsplit(ref_val)
                    headers_dict["Origin"] = f"{parsed_ref.scheme}://{parsed_ref.netloc}"

            def progress_hook(d):
                if self.cancel_event and self.cancel_event.is_set():
                    self._is_cancelled = True
                    raise Exception("Download cancelled by user")

                status = d.get("status")
                if status == "downloading":
                    dl_bytes = d.get("downloaded_bytes") or 0
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    if total <= 0 and self.headers and self.headers.get("estimated_size"):
                        try:
                            total = int(self.headers["estimated_size"])
                        except Exception:
                            pass
                    speed = self._calculate_rolling_speed(dl_bytes)
                    eta = d.get("eta") or 0
                    if self.segment_slots:
                        n_slots = max(1, len(self.segment_slots))
                        per_slot_dl = int(dl_bytes // n_slots)
                        per_slot_tot = max(per_slot_dl, int(total // n_slots)) if total > 0 else max(per_slot_dl * 2, 1000000)
                        prog_val = min(1.0, dl_bytes / total) if total > 0 else 0.0
                        for idx_s, s in enumerate(self.segment_slots):
                            s.downloaded_bytes = per_slot_dl + (int(dl_bytes % n_slots) if idx_s == 0 else 0)
                            s.start_byte = 0
                            s.end_byte = max(1, per_slot_tot - 1)
                            s.progress = prog_val
                            s.status = "Receiving data"
                    if self.on_progress:
                        self.on_progress(dl_bytes, total, speed, eta)
                elif status == "finished":
                    dl_bytes = d.get("total_bytes") or d.get("downloaded_bytes") or 0
                    if self.on_progress:
                        self.on_progress(dl_bytes, dl_bytes, 0.0, 0)

            base_out, target_ext = os.path.splitext(os.path.basename(self.target_path))
            safe_base_out = base_out[:80].rstrip(" ._") if len(base_out) > 80 else base_out
            outtmpl = f"{safe_base_out}.%(ext)s"

            ydl_opts = {
                'nocheckcertificate': True,
                'paths': {
                    'home': dir_name,
                    'temp': temp_ytdlp_dir
                },
                'outtmpl': outtmpl,
                'format': 'bestvideo+bestaudio/best/all',
                'merge_output_format': 'mp4',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 8,
                'retries': 3,
                'fragment_retries': 3,
                'concurrent_fragment_downloads': 4,
                'hls_use_mpegts': False,
                'postprocessor_args': {
                    'ffmpeg': [
                        '-fflags', '+genpts+igndts',
                        '-avoid_negative_ts', 'make_zero',
                        '-max_interleave_delta', '0',
                        '-movflags', '+faststart'
                    ]
                },
                'downloader': {
                    'default': 'native',
                    'm3u8': 'native',
                    'dash': 'native'
                },
                'buffersize': 1024 * 1024,
                'http_chunk_size': 10485760,
                'progress_hooks': [progress_hook],
                'http_headers': headers_dict,
                'continuedl': True
            }
            if ffmpeg_path:
                ydl_opts['ffmpeg_location'] = ffmpeg_path
            if self.proxy:
                ydl_opts['proxy'] = self.proxy

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])

            if os.path.exists(self.target_path) and os.path.getsize(self.target_path) > 0:
                self.fix_media_seek_and_container(self.target_path)
                if self._validate_media_file(self.target_path):
                    self.cleanup_temp_fragments(self.target_path)
                    shutil.rmtree(temp_ytdlp_dir, ignore_errors=True)
                    return True
                else:
                    try:
                        os.remove(self.target_path)
                    except Exception:
                        pass

            # If yt-dlp output to another extension (e.g. .mkv, .ts) or safe_base_out
            candidates = []
            full_base_out, _ = os.path.splitext(self.target_path)
            for ext in [".mp4", ".mkv", ".ts", ".webm"]:
                candidates.append(full_base_out + ext)
                candidates.append(os.path.join(dir_name, f"{safe_base_out}{ext}"))

            for cand in candidates:
                if os.path.exists(cand) and os.path.getsize(cand) > 0:
                    try:
                        if cand != self.target_path:
                            try:
                                shutil.move(cand, self.target_path)
                            except Exception:
                                self.target_path = cand
                        self.fix_media_seek_and_container(self.target_path)
                        if self._validate_media_file(self.target_path):
                            self.cleanup_temp_fragments(self.target_path)
                            shutil.rmtree(temp_ytdlp_dir, ignore_errors=True)
                            return True
                        else:
                            os.remove(self.target_path)
                    except Exception:
                        pass

            return False
        except Exception as e:
            print(f"[HLSWorker] yt-dlp fallback error: {e}")
            err_str = str(e)
            if "429" in err_str:
                self._last_error = "Server membatasi permintaan (HTTP 429: Too Many Requests) atau token link video telah kedaluwarsa. Silakan refresh halaman video di browser dan gunakan tombol Perbarui URL (Ctrl+U)."
            elif "403" in err_str:
                self._last_error = "Akses ditolak server CDN (HTTP 403: Forbidden). Token sesi video mungkin telah kedaluwarsa. Silakan refresh halaman video dan perbarui URL (Ctrl+U)."
            elif "404" in err_str:
                self._last_error = "Tautan video tidak ditemukan atau sudah kedaluwarsa (HTTP 404: Not Found). Silakan refresh halaman video dan perbarui URL (Ctrl+U)."
            else:
                self._last_error = f"yt-dlp error: {e}"
            if "cancelled" in str(e).lower() or self._is_cancelled:
                self._is_cancelled = True
                self.cleanup_temp_fragments(self.target_path)
                shutil.rmtree(temp_ytdlp_dir, ignore_errors=True)
            return False

    def _run_with_ffmpeg(self) -> bool:
        """
        Stage 3 Fallback: Direct FFmpeg with reconnect flags and stdout progress tracking.
        """
        ffmpeg_bin = AudioMuxer.get_ffmpeg_path()
        if not ffmpeg_bin:
            return False

        header_lines = []
        for k, v in self.headers.items():
            if k.lower() in ["referer", "user-agent", "authorization", "origin", "cookie"]:
                header_lines.append(f"{k}: {v}")

        headers_str = "\r\n".join(header_lines) + "\r\n" if header_lines else ""

        cmd = [
            ffmpeg_bin, "-y",
            "-fflags", "+genpts+igndts",
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "2",
            "-timeout", "10000000"
        ]
        if headers_str:
            cmd.extend(["-headers", headers_str])
        cmd.extend([
            "-i", self.url,
            "-map", "0:v?",
            "-map", "0:a?",
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-avoid_negative_ts", "make_zero",
            "-max_interleave_delta", "0",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            self.target_path
        ])

        flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
        sinfo = None
        if sys.platform == "win32":
            sinfo = subprocess.STARTUPINFO()
            sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            sinfo.wShowWindow = 0

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=flag,
                startupinfo=sinfo
            )

            total_bytes_dl = 0
            for line in self._proc.stdout:
                if self.cancel_event and self.cancel_event.is_set():
                    self._proc.terminate()
                    self._is_cancelled = True
                    return False
                line = line.strip()
                if line.startswith("total_size="):
                    try:
                        total_bytes_dl = int(line.split("=")[1])
                        speed = self._calculate_rolling_speed(total_bytes_dl)
                        est_tot = -1
                        if self.headers and self.headers.get("estimated_size"):
                            try:
                                est_tot = int(self.headers["estimated_size"])
                            except Exception:
                                pass
                        if self.segment_slots:
                            n_slots = max(1, len(self.segment_slots))
                            per_slot_dl = int(total_bytes_dl // n_slots)
                            prog_val = min(1.0, total_bytes_dl / est_tot) if est_tot > 0 else 0.0
                            for idx_s, s in enumerate(self.segment_slots):
                                s.downloaded_bytes = per_slot_dl + (int(total_bytes_dl % n_slots) if idx_s == 0 else 0)
                                s.progress = prog_val
                                s.status = "Receiving data"
                        if self.on_progress:
                            self.on_progress(total_bytes_dl, est_tot, speed, 0)
                    except Exception:
                        pass

            est_tot = -1
            if self.headers and self.headers.get("estimated_size"):
                try:
                    est_tot = int(self.headers["estimated_size"])
                except Exception:
                    pass

            min_ff_size = int(est_tot * 0.5) if est_tot > (10 * 1024 * 1024) else 1024

            self._proc.wait()
            if self._proc.returncode == 0 and os.path.exists(self.target_path) and os.path.getsize(self.target_path) >= min_ff_size:
                if self._validate_media_file(self.target_path):
                    return True
                else:
                    try:
                        os.remove(self.target_path)
                    except Exception:
                        pass
            elif os.path.exists(self.target_path) and os.path.getsize(self.target_path) < min_ff_size:
                try:
                    os.remove(self.target_path)
                except Exception:
                    pass

            # If stream has non-AAC audio or no audio, retry without bitstream filter
            if not self._is_cancelled:
                cmd_no_bsf = [
                    ffmpeg_bin, "-y",
                    "-reconnect", "1",
                    "-reconnect_at_eof", "1",
                    "-reconnect_streamed", "1",
                    "-reconnect_delay_max", "5"
                ]
                if headers_str:
                    cmd_no_bsf.extend(["-headers", headers_str])
                cmd_no_bsf.extend([
                    "-i", self.url,
                    "-c", "copy",
                    "-movflags", "+faststart",
                    self.target_path
                ])
                res = subprocess.run(cmd_no_bsf, capture_output=True, creationflags=flag, startupinfo=sinfo)
                if res.returncode == 0 and os.path.exists(self.target_path) and os.path.getsize(self.target_path) > 0:
                    return self._validate_media_file(self.target_path)

            return False
        except Exception:
            return False

    def _should_stop_live(self) -> bool:
        if self._stop_recording_requested or self._is_cancelled:
            return True
        if self.cancel_event and self.cancel_event.is_set():
            return True
        if self.pause_event and not self.pause_event.is_set():
            return True
        return False

    @staticmethod
    def _decode_stripchat_mouflon(mouflon_val: str, seg_url: str) -> str:
        """
        Decodes Stripchat #EXT-X-MOUFLON:FILE:<b64> or #EXT-X-MOUFLON:URI:<b64> obfuscated segment URLs.
        """
        if not mouflon_val or not seg_url:
            return seg_url
        import base64
        for static_key in ("QueB4cai9boJa5a", "Zokee2OhPh9kugh4"):
            try:
                rev = mouflon_val.strip()[::-1]
                pad = len(rev) % 4
                if pad:
                    rev += "=" * (4 - pad)
                raw = base64.b64decode(rev)
                key_hash = hashlib.sha256(static_key.encode("utf-8")).digest()
                dec_bytes = bytes(b ^ key_hash[i % len(key_hash)] for i, b in enumerate(raw))
                decoded_part = dec_bytes.decode("utf-8")
                if decoded_part and all(32 <= ord(c) < 127 for c in decoded_part):
                    if "media.mp4" in seg_url:
                        return seg_url.replace("media.mp4", decoded_part)
                    elif decoded_part.startswith("http"):
                        return decoded_part
            except Exception:
                continue
        return seg_url

    def _parse_live_m3u8(self, playlist_text: str, base_url: str) -> dict:
        """
        Parses a live HLS media playlist (including LL-HLS #EXT-X-MAP, #EXT-X-PART, #EXT-X-KEY, and #EXT-X-MOUFLON).
        """
        target_duration = 2.0
        media_sequence = 0
        is_ad = "#EXT-X-MOUFLON-ADVERT" in playlist_text
        is_ended = ("#EXT-X-ENDLIST" in playlist_text) and not is_ad
        init_url = None
        current_key = None
        pending_mouflon = None
        segments = []
        partial_segments = []

        base_parsed = urllib.parse.urlsplit(base_url)
        base_query = base_parsed.query

        def inherit_query(u: str) -> str:
            if not base_query or "?" in u:
                return u
            return f"{u}?{base_query}"

        lines = playlist_text.splitlines()
        seq_counter = 0
        current_extinf_dur = 2.0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("#EXT-X-TARGETDURATION:"):
                try:
                    target_duration = float(line.split(":", 1)[1].strip())
                except Exception:
                    pass
            elif line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
                try:
                    media_sequence = int(line.split(":", 1)[1].strip())
                    seq_counter = media_sequence
                except Exception:
                    pass
            elif line.startswith("#EXT-X-MAP:"):
                m_uri = re.search(r'URI="([^"]+)"', line)
                if m_uri:
                    candidate_init = inherit_query(self._resolve_url(base_url, m_uri.group(1)))
                    if not is_ad and "/cpa/" not in candidate_init and "/advert/" not in candidate_init:
                        init_url = candidate_init
            elif line.startswith("#EXT-X-KEY:"):
                if "METHOD=AES-128" in line:
                    m_k = re.search(r'URI="([^"]+)"', line)
                    m_iv = re.search(r'IV=0x([0-9a-fA-F]+)', line)
                    if m_k:
                        k_url = inherit_query(self._resolve_url(base_url, m_k.group(1)))
                        iv_bytes = bytes.fromhex(m_iv.group(1).zfill(32)) if m_iv else None
                        current_key = {"url": k_url, "iv": iv_bytes}
                elif "METHOD=NONE" in line:
                    current_key = None
            elif line.startswith("#EXT-X-MOUFLON:"):
                parts_m = line.split(":")
                if len(parts_m) >= 3:
                    pending_mouflon = ":".join(parts_m[2:])
            elif line.startswith("#EXT-X-PART:"):
                m_part_uri = re.search(r'URI="([^"]+)"', line)
                if m_part_uri:
                    p_url = inherit_query(self._resolve_url(base_url, m_part_uri.group(1)))
                    if pending_mouflon:
                        p_url = self._decode_stripchat_mouflon(pending_mouflon, p_url)
                    if not is_ad and "/cpa/" not in p_url and "/advert/" not in p_url:
                        partial_segments.append({
                            "seq": f"part_{len(partial_segments)}_{p_url.split('?')[0]}",
                            "url": p_url,
                            "duration": 0.5,
                            "key": current_key
                        })
            elif line.startswith("#EXTINF:"):
                try:
                    current_extinf_dur = float(line.split(":", 1)[1].split(",")[0].strip())
                except Exception:
                    current_extinf_dur = target_duration
            elif not line.startswith("#"):
                seg_url = inherit_query(self._resolve_url(base_url, line))
                if pending_mouflon:
                    seg_url = self._decode_stripchat_mouflon(pending_mouflon, seg_url)
                    pending_mouflon = None
                # Skip preroll ad segments so recording contains pure live stream
                if is_ad or "/cpa/" in seg_url or "/advert/" in seg_url or "/mouflon-advert/" in seg_url:
                    continue
                clean_seg_key = seg_url.split("?")[0]
                segments.append({
                    "seq": f"{seq_counter}_{clean_seg_key}",
                    "seq_num": seq_counter,
                    "url": seg_url,
                    "duration": current_extinf_dur,
                    "key": current_key
                })
                seq_counter += 1

        if not segments and partial_segments:
            segments = partial_segments

        return {
            "target_duration": target_duration,
            "media_sequence": media_sequence,
            "is_ended": is_ended,
            "is_ad": is_ad,
            "init_url": init_url,
            "segments": segments
        }

    def _finalize_live_recording(
        self,
        raw_video_path: str,
        raw_audio_path: Optional[str] = None,
        concat_list_path: Optional[str] = None
    ) -> bool:
        """
        Losslessly remuxes captured live stream data into a standard, seekable MP4 container.
        Automatically differentiates between MPEG-TS and fMP4 (fragmented MP4) streams:
        - For fMP4 (Chaturbate, Stripchat, modern Webcams): losslessly remuxes fMP4 video & audio tracks
          with MP4 demuxer and +faststart flag without invalid MPEG-TS PMT options.
        - For MPEG-TS (Classic Live Streams): uses PMT version merging & concat demuxer.
        """
        if not os.path.exists(raw_video_path) or os.path.getsize(raw_video_path) < 1024:
            return False

        dir_name = os.path.dirname(os.path.abspath(self.target_path))
        os.makedirs(dir_name, exist_ok=True)

        base, ext = os.path.splitext(self.target_path)
        if ext.lower() not in (".mp4", ".webm", ".mkv", ".ts"):
            self.target_path = f"{base}.mp4"
            ext = ".mp4"

        raw_size = os.path.getsize(raw_video_path)
        # For fMP4 and live streams, merging thousands of duplicate moof/sidx fragments into
        # a standard single moov container safely deduplicates overhead by 30-55%.
        min_safe_size = max(1024, int(raw_size * 0.45))
        remux_timeout = max(300, int(raw_size / (4 * 1024 * 1024)))

        if self.segment_slots:
            for s in self.segment_slots:
                s.status = f"Remuxing {ext.upper()[1:]}..."

        ffmpeg_bin = AudioMuxer.get_ffmpeg_path()
        if not ffmpeg_bin:
            shutil.copy2(raw_video_path, self.target_path)
            return os.path.exists(self.target_path) and os.path.getsize(self.target_path) > 1024

        flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
        sinfo = None
        if sys.platform == "win32":
            sinfo = subprocess.STARTUPINFO()
            sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            sinfo.wShowWindow = 0

        has_audio_file = bool(raw_audio_path and os.path.exists(raw_audio_path) and os.path.getsize(raw_audio_path) > 512)
        has_concat_list = bool(concat_list_path and os.path.exists(concat_list_path) and os.path.getsize(concat_list_path) > 10)
        temp_out = f"{base}.remux_temp{ext}"
        temp_mkv = f"{base}.remux_temp.mkv"

        # Check if the stream is MPEG-TS (starts with 0x47 sync byte) or fMP4 (ftyp / moov / moof)
        is_raw_ts = False
        try:
            with open(raw_video_path, "rb") as _chk:
                first_byte = _chk.read(1)
                is_raw_ts = (first_byte == b"\x47")
        except Exception:
            pass

        # -------------------------------------------------------------
        # BRANCH A: fMP4 Fragmented MP4 Stream (Chaturbate & Stripchat)
        # -------------------------------------------------------------
        if not is_raw_ts:
            print(f"[HLSWorker] Detected fMP4 fragmented live stream (raw_size={raw_size}, has_audio={has_audio_file}). Finalizing...")
            # Stage A1: Direct lossless remux with faststart moov atom indexing & zeroed baseline PTS/DTS
            cmd_fmp4_1 = [
                ffmpeg_bin, "-y",
                "-fflags", "+genpts+igndts+discardcorrupt",
                "-err_detect", "ignore_err",
                "-i", raw_video_path
            ]
            if has_audio_file:
                cmd_fmp4_1.extend(["-i", raw_audio_path])
                cmd_fmp4_1.extend(["-map", "0:v:0?", "-map", "1:a:0?", "-c", "copy"])
            else:
                cmd_fmp4_1.extend(["-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy"])

            cmd_fmp4_1.extend(["-avoid_negative_ts", "make_zero", "-max_interleave_delta", "0"])
            if ext.lower() == ".webm":
                cmd_fmp4_1.append(temp_out)
            else:
                cmd_fmp4_1.extend(["-movflags", "+faststart", temp_out])

            try:
                res = subprocess.run(cmd_fmp4_1, capture_output=True, creationflags=flag, startupinfo=sinfo, timeout=remux_timeout)
                if res.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) >= min_safe_size:
                    os.replace(temp_out, self.target_path)
                    print(f"[HLSWorker] fMP4 lossless remux succeeded: {os.path.getsize(self.target_path)} bytes.")
                    return True
                else:
                    if os.path.exists(temp_out):
                        print(f"[HLSWorker] fMP4 Stage A1 output size {os.path.getsize(temp_out)} < safe {min_safe_size}, rejecting.")
                        os.remove(temp_out)
            except Exception as e_f1:
                print(f"[HLSWorker] fMP4 Stage A1 warning: {e_f1}")

            # Stage A2: Fallback remux without explicit stream mapping
            cmd_fmp4_2 = [
                ffmpeg_bin, "-y",
                "-fflags", "+genpts+igndts+discardcorrupt",
                "-err_detect", "ignore_err",
                "-i", raw_video_path
            ]
            if has_audio_file:
                cmd_fmp4_2.extend(["-i", raw_audio_path, "-c", "copy", "-avoid_negative_ts", "make_zero", "-max_interleave_delta", "0", "-movflags", "+faststart", temp_out])
            else:
                cmd_fmp4_2.extend(["-c", "copy", "-avoid_negative_ts", "make_zero", "-max_interleave_delta", "0", "-movflags", "+faststart", temp_out])

            try:
                res = subprocess.run(cmd_fmp4_2, capture_output=True, creationflags=flag, startupinfo=sinfo, timeout=remux_timeout)
                if res.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) >= min_safe_size:
                    os.replace(temp_out, self.target_path)
                    print(f"[HLSWorker] fMP4 Stage A2 succeeded: {os.path.getsize(self.target_path)} bytes.")
                    return True
                else:
                    if os.path.exists(temp_out):
                        os.remove(temp_out)
            except Exception as e_f2:
                print(f"[HLSWorker] fMP4 Stage A2 warning: {e_f2}")

            # Stage A3: Remux to MKV if MP4 container rejected variable streams
            cmd_fmp4_mkv = [
                ffmpeg_bin, "-y",
                "-fflags", "+genpts+igndts+discardcorrupt",
                "-err_detect", "ignore_err",
                "-i", raw_video_path
            ]
            if has_audio_file:
                cmd_fmp4_mkv.extend(["-i", raw_audio_path, "-map", "0:v:0?", "-map", "1:a:0?"])
            cmd_fmp4_mkv.extend(["-c", "copy", "-avoid_negative_ts", "make_zero", temp_mkv])

            try:
                res = subprocess.run(cmd_fmp4_mkv, capture_output=True, creationflags=flag, startupinfo=sinfo, timeout=remux_timeout)
                if res.returncode == 0 and os.path.exists(temp_mkv) and os.path.getsize(temp_mkv) >= min_safe_size:
                    mkv_target = f"{base}.mkv"
                    os.replace(temp_mkv, mkv_target)
                    self.target_path = mkv_target
                    print(f"[HLSWorker] fMP4 Stage A3 to MKV succeeded: {os.path.getsize(self.target_path)} bytes.")
                    return True
                else:
                    if os.path.exists(temp_mkv):
                        os.remove(temp_mkv)
            except Exception as e_f3:
                print(f"[HLSWorker] fMP4 Stage A3 warning: {e_f3}")

        # -------------------------------------------------------------
        # BRANCH B: MPEG-TS Stream (Classic Live Feeds)
        # -------------------------------------------------------------
        if has_concat_list:
            cmd_c1 = [
                ffmpeg_bin, "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_list_path
            ]
            if has_audio_file:
                cmd_c1.extend(["-i", raw_audio_path])
            if ext.lower() == ".webm":
                cmd_c1.extend(["-c", "copy", "-avoid_negative_ts", "make_zero", temp_out])
            else:
                cmd_c1.extend(["-c", "copy", "-bsf:a", "aac_adtstoasc", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", temp_out])

            try:
                res = subprocess.run(cmd_c1, capture_output=True, creationflags=flag, startupinfo=sinfo, timeout=remux_timeout)
                if res.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) >= min_safe_size:
                    os.replace(temp_out, self.target_path)
                    print(f"[HLSWorker] TS Concat demuxer remux succeeded: {os.path.getsize(self.target_path)} bytes.")
                    return True
                else:
                    if os.path.exists(temp_out):
                        os.remove(temp_out)
            except Exception as e_c1:
                print(f"[HLSWorker] TS Concat Stage 1A notice: {e_c1}")

        # Stage B2: Direct Linear TS Remux with PMT Version Merging
        cmd_l1 = [
            ffmpeg_bin, "-y",
            "-merge_pmt_versions", "1",
            "-scan_all_pmts", "1",
            "-fflags", "+genpts+igndts+discardcorrupt",
            "-err_detect", "ignore_err",
            "-i", raw_video_path
        ]
        if has_audio_file:
            cmd_l1.extend(["-i", raw_audio_path])
        if ext.lower() == ".webm":
            cmd_l1.extend(["-c", "copy", "-avoid_negative_ts", "make_zero", temp_out])
        else:
            cmd_l1.extend(["-c", "copy", "-bsf:a", "aac_adtstoasc", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", temp_out])

        try:
            res = subprocess.run(cmd_l1, capture_output=True, creationflags=flag, startupinfo=sinfo, timeout=remux_timeout)
            if res.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) >= min_safe_size:
                os.replace(temp_out, self.target_path)
                print(f"[HLSWorker] Linear TS remux succeeded: {os.path.getsize(self.target_path)} bytes.")
                return True
            else:
                if os.path.exists(temp_out):
                    os.remove(temp_out)
        except Exception:
            pass

        # -------------------------------------------------------------
        # STAGE 3: Absolute Safe Fallback - Preserve 100% of Raw Data
        # -------------------------------------------------------------
        for tf in (temp_out, temp_mkv):
            if os.path.exists(tf):
                try:
                    os.remove(tf)
                except Exception:
                    pass

        safe_target = f"{base}.ts" if is_raw_ts else self.target_path
        shutil.copy2(raw_video_path, safe_target)
        self.target_path = safe_target
        print(f"[HLSWorker] Preserved 100% captured raw video data ({os.path.getsize(self.target_path)} bytes) as {safe_target}.")
        return os.path.exists(self.target_path) and os.path.getsize(self.target_path) > 1024

    def _run_as_live_stream(self) -> bool:
        """
        Production-Grade Continuous Live Stream Recorder with DPI-Bypass & Lossless MP4/WebM Remuxing.
        1. Automatically resolves webpage URLs (Chaturbate, Stripchat, Twitch, YouTube Live, etc.) to live .m3u8 URLs.
        2. Resolves Master .m3u8 playlists to the highest-resolution working variant Media .m3u8 playlist.
        3. Continuously polls the live Media .m3u8 playlist (bypassing cache & ISP SNI DPI blocks),
           capturing fMP4 init segments (#EXT-X-MAP) and live .ts/.m4s segments in real time.
        4. When the user clicks 'Selesai & Simpan' (Stop/Pause) or when the broadcast ends,
           losslessly remuxes all captured segments into a seekable .mp4 or .webm file.
        """
        self.is_live = True
        if self.headers is not None:
            self.headers["is_live"] = "true"

        temp_live_dir = os.path.join(tempfile.gettempdir(), f"zero_live_{self.task_id or int(time.time())}")
        os.makedirs(temp_live_dir, exist_ok=True)
        segments_dir = os.path.join(temp_live_dir, "segments")
        os.makedirs(segments_dir, exist_ok=True)
        concat_list_path = os.path.join(temp_live_dir, "concat_list.txt")
        raw_video_path = os.path.join(temp_live_dir, "live_video.mp4")
        raw_audio_path = os.path.join(temp_live_dir, "live_audio.mp4")

        try:
            # Step 1: If URL is a webpage URL (not .m3u8 / .mpd), resolve it via MediaGrabber
            live_url = self.url
            if ".m3u8" not in live_url.lower() and ".mpd" not in live_url.lower():
                if self.segment_slots:
                    self.segment_slots[0].status = "Resolving Live URL..."
                try:
                    from .media_grabber import MediaGrabber
                    info, _ = MediaGrabber.get_media_info(live_url)
                    if info and info.get("formats"):
                        for fmt in info["formats"]:
                            f_url = fmt.get("url") or ""
                            if ".m3u8" in f_url.lower() or fmt.get("is_live"):
                                live_url = f_url
                                self.url = live_url
                                self._update_task_url(live_url)
                                break
                except Exception as e_res:
                    print(f"[HLSWorker] Live URL resolution notice: {e_res}")

            # Step 2: Fetch playlist & resolve Master Playlist -> Variant Media Playlist
            master_hint = self.headers.get("master_url") if self.headers else None
            audio_hint = self.headers.get("audio_url") if self.headers else None
            if master_hint:
                live_url = master_hint
            live_audio_url = audio_hint

            if any(d in live_url.lower() for d in ("doppiocdn", "stripcdn", "stripchat")) and "pkey=" not in live_url.lower():
                sep = "&" if "?" in live_url else "?"
                live_url = f"{live_url}{sep}pkey=B0p93vi8Uj6AYyZb"
            live_media_url = live_url
            initial_playlist_text = ""

            try:
                raw_bytes, eff_url = self._fetch_url_with_info(live_url, timeout=12, bypass_cache=True)
                initial_playlist_text = raw_bytes.decode("utf-8", errors="ignore")
                live_media_url = eff_url
            except Exception as e_init:
                fb = self._resolve_working_fallback_stream()
                if fb:
                    live_media_url = fb
                    self.url = fb
                    raw_bytes, eff_url = self._fetch_url_with_info(fb, timeout=12, bypass_cache=True)
                    initial_playlist_text = raw_bytes.decode("utf-8", errors="ignore")
                    live_media_url = eff_url
                else:
                    print(f"[HLSWorker] Initial live playlist fetch failed ({e_init}), trying FFmpeg fallback...")

            if "#EXT-X-STREAM-INF" in initial_playlist_text:
                variants = []
                audio_renditions = {}
                lines = initial_playlist_text.splitlines()
                for i, l in enumerate(lines):
                    l_s = l.strip()
                    if l_s.startswith("#EXT-X-MEDIA:") and "TYPE=AUDIO" in l_s:
                        m_gid = re.search(r'GROUP-ID="([^"]+)"', l_s)
                        m_uri = re.search(r'URI="([^"]+)"', l_s)
                        if m_gid and m_uri:
                            a_rend_url = self._resolve_url(live_media_url, m_uri.group(1))
                            if "?" not in a_rend_url and "?" in live_media_url:
                                a_rend_url = f"{a_rend_url}?{ urllib.parse.urlsplit(live_media_url).query }"
                            audio_renditions[m_gid.group(1)] = a_rend_url
                    elif l_s.startswith("#EXT-X-STREAM-INF"):
                        bw = 0
                        width = 0
                        height = 0
                        m_bw = re.search(r'AVERAGE-BANDWIDTH=(\d+)', l_s) or re.search(r'BANDWIDTH=(\d+)', l_s)
                        if m_bw:
                            bw = int(m_bw.group(1))
                        m_res = re.search(r'RESOLUTION=(\d+)x(\d+)', l_s)
                        if m_res:
                            width = int(m_res.group(1))
                            height = int(m_res.group(2))
                        m_ag = re.search(r'AUDIO="([^"]+)"', l_s)
                        ag = m_ag.group(1) if m_ag else None
                        for nxt in range(i + 1, len(lines)):
                            cand = lines[nxt].strip()
                            if cand and not cand.startswith("#"):
                                v_url = self._resolve_url(live_media_url, cand)
                                # Inherit master query params if variant has none
                                if "?" not in v_url and "?" in live_media_url:
                                    v_url = f"{v_url}?{ urllib.parse.urlsplit(live_media_url).query }"
                                if any(d in v_url.lower() for d in ("doppiocdn", "stripcdn", "stripchat")) and "pkey=" not in v_url.lower():
                                    sep = "&" if "?" in v_url else "?"
                                    v_url = f"{v_url}{sep}pkey=B0p93vi8Uj6AYyZb"
                                variants.append((width, height, bw, v_url, ag))
                                break

                if variants:
                    # Sort variants by total pixel count descending, then bandwidth descending
                    variants.sort(
                        key=lambda x: (
                            (x[0] * x[1]) if (x[0] and x[1]) else (x[1] * 1000),
                            x[2]
                        ),
                        reverse=True
                    )
                    # Check if user requested specific resolution
                    target_res = (self.headers.get("resolution") or "") if self.headers else ""
                    if target_res:
                        for idx_v, (w_val, h_val, bw_val, cand_url, ag_id) in enumerate(variants):
                            if f"{h_val}" in target_res or (w_val and f"{w_val}" in target_res):
                                chosen_item = variants.pop(idx_v)
                                variants.insert(0, chosen_item)
                                break

                    for w_val, h_val, bw_val, cand_url, ag_id in variants:
                        try:
                            v_bytes, v_eff = self._fetch_url_with_info(cand_url, timeout=10, bypass_cache=True)
                            v_txt = v_bytes.decode("utf-8", errors="ignore")
                            if "#EXTM3U" in v_txt:
                                live_media_url = v_eff
                                initial_playlist_text = v_txt
                                matched_a = audio_renditions.get(ag_id) or (list(audio_renditions.values())[0] if audio_renditions else None)
                                if matched_a:
                                    live_audio_url = matched_a
                                break
                        except Exception:
                            continue

            if any(d in live_media_url.lower() for d in ("doppiocdn", "stripcdn", "stripchat")) and "pkey=" not in live_media_url.lower():
                sep = "&" if "?" in live_media_url else "?"
                live_media_url = f"{live_media_url}{sep}pkey=B0p93vi8Uj6AYyZb"

            # Step 3: Continuous Native Python Live HLS Segment Polling Loop
            if "#EXTM3U" in initial_playlist_text:
                seen_segments = set()
                seen_order = []
                downloaded_inits = set()
                key_cache: Dict[str, bytes] = {}
                consecutive_errors = 0
                is_first_poll = True

                with open(raw_video_path, "wb") as f_video, open(concat_list_path, "w", encoding="utf-8") as f_concat:
                    f_audio = open(raw_audio_path, "wb") if live_audio_url else None
                    seen_audio_segments = set()
                    downloaded_audio_inits = set()

                    try:
                        while not self._should_stop_live():
                            try:
                                if is_first_poll and "#EXTINF" in initial_playlist_text:
                                    pl_text = initial_playlist_text
                                    eff_pl_url = live_media_url
                                else:
                                    pl_bytes, eff_pl_url = self._fetch_url_with_info(live_media_url, timeout=10, bypass_cache=True)
                                    pl_text = pl_bytes.decode("utf-8", errors="ignore")
                                    live_media_url = eff_pl_url

                                if "#EXTM3U" not in pl_text:
                                    raise ValueError("Invalid live M3U8 response")

                                parsed = self._parse_live_m3u8(pl_text, live_media_url)
                                consecutive_errors = 0

                                if parsed.get("is_ad"):
                                    if self.segment_slots:
                                        self.segment_slots[0].status = "Menunggu siaran langsung..."

                                # 3a. Download fMP4 Initialization Segment (#EXT-X-MAP) if present
                                init_u = parsed.get("init_url")
                                if init_u and init_u not in downloaded_inits:
                                    try:
                                        init_data, _ = self._fetch_url_with_info(init_u, timeout=10, bypass_cache=True)
                                        init_data = self._strip_stream_obfuscation(init_data)
                                        if init_data:
                                            f_video.write(init_data)
                                            f_video.flush()
                                            downloaded_inits.add(init_u)
                                            with self._lock:
                                                self._downloaded_bytes += len(init_data)
                                            try:
                                                init_filepath = os.path.join(segments_dir, f"init_{len(downloaded_inits):03d}.mp4")
                                                with open(init_filepath, "wb") as _init_f:
                                                    _init_f.write(init_data)
                                                escaped_init = init_filepath.replace("\\", "/").replace("'", r"'\''")
                                                f_concat.write(f"file '{escaped_init}'\n")
                                                f_concat.flush()
                                            except Exception:
                                                pass
                                    except Exception as e_map:
                                        print(f"[HLSWorker] Live init segment error: {e_map}")

                                # 3b. Select new segments to record
                                all_segs = parsed.get("segments") or []
                                if is_first_poll and len(all_segs) > 3:
                                    # Mark older sliding-window segments as seen so we start near live edge (last 3 segments)
                                    for old_s in all_segs[:-3]:
                                        seen_segments.add(old_s["seq"])
                                    all_segs = all_segs[-3:]
                                is_first_poll = False

                                new_segs = [s for s in all_segs if s["seq"] not in seen_segments]

                                if new_segs and not self._should_stop_live():
                                    def _fetch_one_live_seg(seg_item):
                                        if self._should_stop_live():
                                            return seg_item, b""
                                        try:
                                            s_url = seg_item["url"]
                                            sb, _ = self._fetch_url_with_info(s_url, timeout=10, bypass_cache=True)
                                            if not sb:
                                                return seg_item, b""

                                            k_info = seg_item.get("key")
                                            if k_info and k_info.get("url") and HAS_CRYPTOGRAPHY:
                                                k_url = k_info["url"]
                                                with self._lock:
                                                    if k_url not in key_cache:
                                                        kb, _ = self._fetch_url_with_info(k_url, timeout=8, bypass_cache=True)
                                                        key_cache[k_url] = kb[:16]
                                                    aes_key = key_cache.get(k_url)
                                                if aes_key and len(aes_key) == 16:
                                                    iv = k_info.get("iv") or seg_item.get("seq_num", 0).to_bytes(16, byteorder="big")
                                                    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
                                                    decryptor = cipher.decryptor()
                                                    padded_len = (len(sb) // 16) * 16
                                                    dec = decryptor.update(sb[:padded_len]) + decryptor.finalize()
                                                    if dec:
                                                        pad_v = dec[-1]
                                                        if 1 <= pad_v <= 16 and all(b == pad_v for b in dec[-pad_v:]):
                                                            dec = dec[:-pad_v]
                                                        sb = dec

                                            sb = self._strip_stream_obfuscation(sb)
                                            return seg_item, sb
                                        except Exception as e_fetch_one:
                                            print(f"[HLSWorker] Live parallel segment fetch error: {e_fetch_one}")
                                            return seg_item, b""

                                    # Concurrently download live segments across parallel threads for maximum line speed
                                    if len(new_segs) == 1:
                                        batch_results = [_fetch_one_live_seg(new_segs[0])]
                                    else:
                                        import concurrent.futures
                                        max_workers = min(len(new_segs), 8)
                                        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                                            batch_results = list(pool.map(_fetch_one_live_seg, new_segs))

                                    for seg, seg_bytes in batch_results:
                                        if self._should_stop_live():
                                            break
                                        if not seg_bytes:
                                            continue

                                        try:
                                            if self.speed_limiter and self.speed_limiter.is_enabled:
                                                self.speed_limiter.throttle(len(seg_bytes))

                                            f_video.write(seg_bytes)
                                            f_video.flush()

                                            try:
                                                seg_ext = ".m4s" if init_u else ".ts"
                                                seg_filename = f"seg_{self._completed_segments:07d}{seg_ext}"
                                                seg_filepath = os.path.join(segments_dir, seg_filename)
                                                with open(seg_filepath, "wb") as _sf:
                                                    _sf.write(seg_bytes)
                                                escaped_sp = seg_filepath.replace(chr(92), "/").replace("'", "'\\''")
                                                f_concat.write(f"file '{escaped_sp}'\n")
                                                f_concat.flush()
                                            except Exception:
                                                pass

                                            seen_segments.add(seg["seq"])
                                            seen_order.append(seg["seq"])
                                            if len(seen_order) > 2000:
                                                oldest = seen_order.pop(0)
                                                seen_segments.discard(oldest)

                                            with self._lock:
                                                self._downloaded_bytes += len(seg_bytes)
                                                self._completed_segments += 1
                                                cur_dl = self._downloaded_bytes
                                                cur_cnt = self._completed_segments

                                            if self.segment_slots:
                                                s_slot = self.segment_slots[(cur_cnt - 1) % len(self.segment_slots)]
                                                s_slot.downloaded_bytes += len(seg_bytes)
                                                s_slot.status = f"Live Seg #{cur_cnt}"

                                            spd = self._calculate_rolling_speed(cur_dl)
                                            if self.on_progress:
                                                self.on_progress(cur_dl, -1, spd, 0)
                                        except Exception as e_seg:
                                            print(f"[HLSWorker] Live segment write warning: {e_seg}")
                                            continue
                                # 3c. Poll separate audio rendition if present
                                if f_audio and live_audio_url and not self._should_stop_live():
                                    try:
                                        a_pl_bytes, a_eff = self._fetch_url_with_info(live_audio_url, timeout=8, bypass_cache=True)
                                        a_parsed = self._parse_live_m3u8(a_pl_bytes.decode("utf-8", errors="ignore"), a_eff)
                                        a_init = a_parsed.get("init_url")
                                        if a_init and a_init not in downloaded_audio_inits:
                                            ai_bytes, _ = self._fetch_url_with_info(a_init, timeout=8, bypass_cache=True)
                                            if ai_bytes:
                                                f_audio.write(ai_bytes)
                                                f_audio.flush()
                                                downloaded_audio_inits.add(a_init)
                                        for a_seg in (a_parsed.get("segments") or [])[-3:]:
                                            if a_seg["seq"] not in seen_audio_segments and not self._should_stop_live():
                                                ab, _ = self._fetch_url_with_info(a_seg["url"], timeout=8, bypass_cache=True)
                                                if ab:
                                                    f_audio.write(ab)
                                                    f_audio.flush()
                                                    seen_audio_segments.add(a_seg["seq"])
                                    except Exception:
                                        pass

                                if parsed.get("is_ended"):
                                    print("[HLSWorker] Live broadcast reached #EXT-X-ENDLIST.")
                                    break

                                # Responsive wait before next live playlist poll (checks stop signal every 100ms)
                                wait_s = max(0.5, min(parsed.get("target_duration", 2.0) * 0.45, 1.5)) if not new_segs else 0.4
                                elapsed = 0.0
                                while elapsed < wait_s and not self._should_stop_live():
                                    time.sleep(0.1)
                                    elapsed += 0.1

                            except Exception as e_poll:
                                consecutive_errors += 1
                                if consecutive_errors > 8:
                                    print(f"[HLSWorker] Live stream polling ended after {consecutive_errors} retries: {e_poll}")
                                    break
                                elapsed = 0.0
                                while elapsed < 1.0 and not self._should_stop_live():
                                    time.sleep(0.1)
                                    elapsed += 0.1
                    finally:
                        if f_audio:
                            try:
                                f_audio.close()
                            except Exception:
                                pass

                if self._downloaded_bytes > 1024 and os.path.exists(raw_video_path) and os.path.getsize(raw_video_path) > 1024:
                    if self._finalize_live_recording(raw_video_path, raw_audio_path if live_audio_url else None, concat_list_path=concat_list_path):
                        final_sz = os.path.getsize(self.target_path)
                        if self.segment_slots:
                            for s in self.segment_slots:
                                s.status = "Completed"
                        if self.on_progress:
                            self.on_progress(final_sz, final_sz, 0.0, 0)
                        shutil.rmtree(temp_live_dir, ignore_errors=True)
                        return True

            # Step 4: Fallback to Direct FFmpeg Live Capture if non-HLS or 0 bytes recorded
            ffmpeg_bin = AudioMuxer.get_ffmpeg_path()
            if not ffmpeg_bin or self._should_stop_live():
                return False

            header_lines = []
            if self.headers:
                for k, v in self.headers.items():
                    if k.lower() in ["referer", "user-agent", "authorization", "origin", "cookie"]:
                        header_lines.append(f"{k}: {v}")
            if not any(h.lower().startswith("user-agent:") for h in header_lines):
                header_lines.append("User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
            headers_str = "\r\n".join(header_lines) + "\r\n" if header_lines else ""

            ffmpeg_raw_mp4 = os.path.join(temp_live_dir, "ffmpeg_live_capture.mp4")
            cmd = [
                ffmpeg_bin, "-y",
                "-reconnect", "1",
                "-reconnect_at_eof", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5"
            ]
            if headers_str:
                cmd.extend(["-headers", headers_str])
            cmd.extend([
                "-i", live_media_url,
                "-c", "copy",
                "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
                "-progress", "pipe:1",
                ffmpeg_raw_mp4
            ])

            flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
            sinfo = None
            if sys.platform == "win32":
                sinfo = subprocess.STARTUPINFO()
                sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                sinfo.wShowWindow = 0

            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=flag,
                startupinfo=sinfo
            )

            for line in self._proc.stdout:
                if self._should_stop_live():
                    break
                line = line.strip()
                if line.startswith("total_size="):
                    try:
                        total_bytes_dl = int(line.split("=")[1])
                        self._downloaded_bytes = total_bytes_dl
                        speed = self._calculate_rolling_speed(total_bytes_dl)
                        if self.on_progress:
                            self.on_progress(total_bytes_dl, -1, speed, 0)
                    except Exception:
                        pass

            if self._proc and self._proc.poll() is None:
                try:
                    if self._proc.stdin:
                        self._proc.stdin.write("q\n")
                        self._proc.stdin.flush()
                except Exception:
                    pass
                try:
                    self._proc.wait(timeout=6)
                except Exception:
                    try:
                        self._proc.terminate()
                        self._proc.wait(timeout=2)
                    except Exception:
                        pass

            if os.path.exists(ffmpeg_raw_mp4) and os.path.getsize(ffmpeg_raw_mp4) > 1024:
                if self._finalize_live_recording(ffmpeg_raw_mp4):
                    final_sz = os.path.getsize(self.target_path)
                    if self.on_progress:
                        self.on_progress(final_sz, final_sz, 0.0, 0)
                    shutil.rmtree(temp_live_dir, ignore_errors=True)
                    return True

            return False
        except Exception as e_live:
            print(f"[HLSWorker] Live stream recorder error: {e_live}")
            if os.path.exists(raw_video_path) and os.path.getsize(raw_video_path) > 1024:
                if self._finalize_live_recording(raw_video_path):
                    return True
            return False
        finally:
            if self._proc:
                try:
                    self._proc.kill()
                except Exception:
                    pass
                self._proc = None
            shutil.rmtree(temp_live_dir, ignore_errors=True)

    @staticmethod
    def _parse_iso8601_duration(dur_str: str) -> float:
        if not dur_str or not dur_str.startswith("P"):
            return 0.0
        match = re.search(
            r'PT?(?:(?P<hours>\d+(?:\.\d+)?)H)?(?:(?P<minutes>\d+(?:\.\d+)?)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?',
            dur_str
        )
        if not match:
            return 0.0
        hours = float(match.group('hours') or 0.0)
        minutes = float(match.group('minutes') or 0.0)
        seconds = float(match.group('seconds') or 0.0)
        return hours * 3600.0 + minutes * 60.0 + seconds

    @staticmethod
    def _format_dash_template(
        template: str,
        rep_id: Optional[str] = None,
        number: Optional[int] = None,
        time_val: Optional[int] = None,
        bandwidth: Optional[int] = None
    ) -> str:
        res = template.replace("$$", "\x00")
        if rep_id is not None:
            res = res.replace("$RepresentationID$", str(rep_id))
        if bandwidth is not None:
            res = re.sub(
                r'\$Bandwidth(?:%([0-9]+[di]))?\$',
                lambda m: (f"%{m.group(1)}" % int(bandwidth)) if m.group(1) else str(bandwidth),
                res
            )
            res = res.replace("$Bandwidth$", str(bandwidth))
        if number is not None:
            res = re.sub(
                r'\$Number(?:%([0-9]+[di]))?\$',
                lambda m: (f"%{m.group(1)}" % int(number)) if m.group(1) else str(number),
                res
            )
            res = res.replace("$Number$", str(number))
        if time_val is not None:
            res = re.sub(
                r'\$Time(?:%([0-9]+[di]))?\$',
                lambda m: (f"%{m.group(1)}" % int(time_val)) if m.group(1) else str(time_val),
                res
            )
            res = res.replace("$Time$", str(time_val))
        res = res.replace("\x00", "$")
        return res

    def _parse_mpd(self, content: str, mpd_url: str) -> Optional[dict]:
        try:
            root = ET.fromstring(content)
        except Exception as e:
            print(f"[HLSWorker] MPD XML parse error: {e}")
            return None

        def local_tag(elem):
            return elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

        mpd_duration = self._parse_iso8601_duration(root.attrib.get('mediaPresentationDuration', ''))
        base_url = mpd_url
        for child in root:
            if local_tag(child) == 'BaseURL' and child.text:
                base_url = self._resolve_url(base_url, child.text.strip())

        video_info = None
        audio_info = None

        for period in root:
            if local_tag(period) != 'Period':
                continue
            p_duration = self._parse_iso8601_duration(period.attrib.get('duration', '')) or mpd_duration
            period_base = base_url
            for child in period:
                if local_tag(child) == 'BaseURL' and child.text:
                    period_base = self._resolve_url(period_base, child.text.strip())

            for ad_set in period:
                if local_tag(ad_set) != 'AdaptationSet':
                    continue
                ad_base = period_base
                for child in ad_set:
                    if local_tag(child) == 'BaseURL' and child.text:
                        ad_base = self._resolve_url(ad_base, child.text.strip())

                mime = (ad_set.attrib.get('mimeType') or '').lower()
                ct = (ad_set.attrib.get('contentType') or '').lower()
                is_video = 'video' in mime or ct == 'video'
                is_audio = 'audio' in mime or ct == 'audio'
                if not is_video and not is_audio:
                    continue

                tmpl_elem = next((c for c in ad_set if local_tag(c) == 'SegmentTemplate'), None)
                reps = [r for r in ad_set if local_tag(r) == 'Representation']
                reps.sort(key=lambda r: int(r.attrib.get('bandwidth') or 0), reverse=True)
                if not reps:
                    continue

                # Pick representation with highest bandwidth
                best_rep = reps[0]
                rep_id = best_rep.attrib.get('id', '')
                bw = int(best_rep.attrib.get('bandwidth') or 0)
                rep_base = ad_base
                for child in best_rep:
                    if local_tag(child) == 'BaseURL' and child.text:
                        rep_base = self._resolve_url(rep_base, child.text.strip())

                rep_tmpl = next((c for c in best_rep if local_tag(c) == 'SegmentTemplate'), tmpl_elem)
                init_url = None
                segments = []

                if rep_tmpl is not None:
                    init_pat = rep_tmpl.attrib.get('initialization', '')
                    media_pat = rep_tmpl.attrib.get('media', '')
                    timescale = float(rep_tmpl.attrib.get('timescale', 1))
                    duration = float(rep_tmpl.attrib.get('duration', 0))
                    start_num = int(rep_tmpl.attrib.get('startNumber', 1))

                    if init_pat:
                        init_url = self._resolve_url(
                            rep_base,
                            self._format_dash_template(init_pat, rep_id=rep_id, bandwidth=bw)
                        )

                    timeline = next((c for c in rep_tmpl if local_tag(c) == 'SegmentTimeline'), None)
                    if timeline is not None:
                        curr_time = 0
                        curr_num = start_num
                        for s_elem in timeline:
                            if local_tag(s_elem) != 'S':
                                continue
                            t_attr = s_elem.attrib.get('t')
                            if t_attr is not None:
                                curr_time = int(t_attr)
                            d_val = int(s_elem.attrib.get('d', 0))
                            r_val = int(s_elem.attrib.get('r', 0))
                            count = 1 + max(0, r_val)
                            for _ in range(count):
                                s_url = self._resolve_url(
                                    rep_base,
                                    self._format_dash_template(media_pat, rep_id=rep_id, number=curr_num, time_val=curr_time, bandwidth=bw)
                                )
                                segments.append(s_url)
                                curr_time += d_val
                                curr_num += 1
                    elif duration > 0 and timescale > 0 and p_duration > 0:
                        seg_dur = duration / timescale
                        total_segs = math.ceil(p_duration / seg_dur)
                        for n in range(start_num, start_num + total_segs):
                            s_url = self._resolve_url(
                                rep_base,
                                self._format_dash_template(media_pat, rep_id=rep_id, number=n, bandwidth=bw)
                            )
                            segments.append(s_url)
                else:
                    # SegmentList fallback
                    seg_list = next((c for c in best_rep if local_tag(c) == 'SegmentList'), None) or next((c for c in ad_set if local_tag(c) == 'SegmentList'), None)
                    if seg_list is not None:
                        init_elem = next((c for c in seg_list if local_tag(c) == 'Initialization'), None)
                        if init_elem is not None:
                            src = init_elem.attrib.get('sourceURL')
                            if src:
                                init_url = self._resolve_url(rep_base, src)
                        for s_elem in seg_list:
                            if local_tag(s_elem) == 'SegmentURL':
                                m_url = s_elem.attrib.get('media')
                                if m_url:
                                    segments.append(self._resolve_url(rep_base, m_url))

                track_dict = {
                    "init_url": init_url,
                    "segments": segments,
                    "rep_id": rep_id,
                    "bandwidth": bw
                }
                if is_video and not video_info and segments:
                    video_info = track_dict
                elif is_audio and not audio_info and segments:
                    audio_info = track_dict

        if not video_info and not audio_info:
            return None
        return {"video": video_info, "audio": audio_info}

    def _run_with_dash_engine(self) -> bool:
        """
        High-Performance Resumable Multi-Threaded Native MPEG-DASH (.mpd) Downloader.
        Downloads video and audio segment streams concurrently and lossless-muxes via FFmpeg.
        """
        ffmpeg_bin = AudioMuxer.get_ffmpeg_path()
        if not ffmpeg_bin:
            return False

        cache_id = self.task_id if self.task_id else hashlib.md5(self.url.encode("utf-8")).hexdigest()
        cache_dir = os.path.join(tempfile.gettempdir(), f"zero_dash_{cache_id}")
        os.makedirs(cache_dir, exist_ok=True)

        try:
            # 1. Fetch MPD manifest
            try:
                raw_bytes, effective_url = self._fetch_url_with_info(self.url, timeout=15)
                mpd_text = raw_bytes.decode("utf-8", errors="ignore")
            except Exception as e_fetch:
                print(f"[HLSWorker] DASH MPD fetch failed on {self.url}: {e_fetch}")
                return False

            if "<MPD" not in mpd_text and "<mpd" not in mpd_text:
                print(f"[HLSWorker] Manifest at {self.url} is not a valid MPD XML document.")
                return False

            # 2. Parse MPD
            dash_plan = self._parse_mpd(mpd_text, effective_url)
            if not dash_plan:
                print(f"[HLSWorker] Could not parse media representations or segment templates from MPD.")
                return False

            video_info = dash_plan.get("video")
            audio_info = dash_plan.get("audio")

            v_segs = video_info["segments"] if video_info else []
            a_segs = audio_info["segments"] if audio_info else []

            if not v_segs and not a_segs:
                print(f"[HLSWorker] MPD contained 0 discrete segment URLs (may be single-file DASH).")
                return False

            # 3. Download Initialization segments
            def download_init_file(init_url: str, save_path: str):
                if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                    return True
                try:
                    init_data = self._fetch_url_data(init_url, timeout=25)
                    init_data = self._strip_stream_obfuscation(init_data)
                    with open(save_path, "wb") as f_init:
                        f_init.write(init_data)
                    return True
                except Exception as e:
                    print(f"[HLSWorker] Failed to download DASH init segment {init_url}: {e}")
                    return False

            v_init_path = os.path.join(cache_dir, "v_init.mp4") if video_info and video_info.get("init_url") else None
            if v_init_path and video_info.get("init_url"):
                download_init_file(video_info["init_url"], v_init_path)

            a_init_path = os.path.join(cache_dir, "a_init.mp4") if audio_info and audio_info.get("init_url") else None
            if a_init_path and audio_info.get("init_url"):
                download_init_file(audio_info["init_url"], a_init_path)

            # 4. Build work queue of all media segments (video + audio)
            all_items = []
            v_files = []
            for i, u in enumerate(v_segs):
                f_path = os.path.join(cache_dir, f"v_seg_{i:06d}.m4s")
                v_files.append(f_path)
                all_items.append({"track": "video", "index": i, "url": u, "file_path": f_path})

            a_files = []
            for i, u in enumerate(a_segs):
                f_path = os.path.join(cache_dir, f"a_seg_{i:06d}.m4s")
                a_files.append(f_path)
                all_items.append({"track": "audio", "index": i, "url": u, "file_path": f_path})

            self._total_segments = len(all_items)
            self._downloaded_bytes = 0
            self._completed_segments = 0
            self._speed_history.clear()

            # Check existing chunks on disk (Resume capability!)
            for it in all_items:
                fp = it["file_path"]
                if os.path.exists(fp) and os.path.getsize(fp) > 0:
                    sz = os.path.getsize(fp)
                    self._completed_segments += 1
                    self._downloaded_bytes += sz

            if self.on_progress:
                if self._completed_segments > 0:
                    avg_sz = self._downloaded_bytes / self._completed_segments
                    est_init_total = int(avg_sz * self._total_segments)
                    self.on_progress(self._downloaded_bytes, est_init_total, 0.0, 0)
                else:
                    est_init = -1
                    if self.headers and self.headers.get("estimated_size"):
                        try:
                            est_init = int(self.headers["estimated_size"])
                        except Exception:
                            pass
                    self.on_progress(0, est_init, 0.0, 0)

            missing_items = [it for it in all_items if not (os.path.exists(it["file_path"]) and os.path.getsize(it["file_path"]) > 0)]

            # 5. Multi-Worker Pool for Concurrent Segment Downloads
            CDN_THROTTLE_PATTERNS = ["tiktokcdn.com", "tiktok.com/ad-site", "tiktokv.com"]
            first_url = (all_items[0]["url"] if all_items else "").lower()
            is_tiktok = any(p in first_url for p in CDN_THROTTLE_PATTERNS)
            max_connections = self.connections or 16
            if is_tiktok and max_connections > 3:
                max_connections = 3
                print(f"[HLSWorker] TikTok CDN detected - capping DASH workers at 3")

            num_workers = min(max_connections, max(2, len(missing_items))) if missing_items else 1
            if self.segment_slots:
                if len(self.segment_slots) > num_workers:
                    del self.segment_slots[num_workers:]
                while len(self.segment_slots) < num_workers:
                    from .models import SegmentModel
                    self.segment_slots.append(SegmentModel(
                        index=len(self.segment_slots),
                        start_byte=0,
                        end_byte=1000000,
                        downloaded_bytes=0,
                        status="Connecting..."
                    ))

            work_queue = queue.Queue()
            for it in missing_items:
                work_queue.put(it)

            unresolved_chunks = []
            unresolved_lock = threading.Lock()

            def download_dash_chunk(item: dict, slot_id: int) -> bool:
                if self.cancel_event and self.cancel_event.is_set():
                    return False
                if self.pause_event:
                    self.pause_event.wait()

                track = item["track"]
                idx = item["index"]
                url = item["url"]
                file_path = item["file_path"]

                slot = None
                if self.segment_slots and slot_id < len(self.segment_slots):
                    slot = self.segment_slots[slot_id]
                    slot.status = f"Dl {track[:1].upper()}{idx + 1}"

                parsed = urllib.parse.urlsplit(url)
                default_ref = f"{parsed.scheme}://{parsed.netloc}/"
                ref = self.headers.get("Referer") or self.headers.get("referer") or default_ref if self.headers else default_ref

                req_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "Referer": ref
                }
                if self.headers:
                    for k, v in self.headers.items():
                        if k.lower() in ["user-agent", "cookie", "authorization", "origin"]:
                            req_headers[k] = v

                max_retries = 3
                for attempt in range(max_retries):
                    if self.cancel_event and self.cancel_event.is_set():
                        return False
                    if self.pause_event:
                        self.pause_event.wait()

                    try:
                        req = urllib.request.Request(url, headers=req_headers)
                        with self._opener.open(req, timeout=15) as resp:
                            data = resp.read()
                            if len(data) == 0:
                                raise ValueError("Empty response body")

                            data = self._strip_stream_obfuscation(data)

                            if self.speed_limiter and self.speed_limiter.is_enabled:
                                self.speed_limiter.throttle(len(data))

                            tmp_path = file_path + ".tmp"
                            with open(tmp_path, "wb") as f_out:
                                f_out.write(data)
                            os.replace(tmp_path, file_path)

                            with self._lock:
                                self._downloaded_bytes += len(data)
                                self._completed_segments += 1
                                cur_bytes = self._downloaded_bytes
                                cur_comp = self._completed_segments
                                tot_segs = self._total_segments

                            speed = self._calculate_rolling_speed(cur_bytes)
                            if self.on_progress:
                                avg_seg_size = cur_bytes / cur_comp
                                est_total = int(avg_seg_size * tot_segs)
                                remaining_bytes = max(0, est_total - cur_bytes)
                                eta = (remaining_bytes / speed) if speed > 500 else 0
                                self.on_progress(cur_bytes, est_total, speed, eta)

                            if slot:
                                slot.downloaded_bytes += len(data)
                                slot.status = "Idle"
                            return True
                    except Exception as e:
                        err_str = str(e).lower()
                        is_throttled = ("403" in err_str) or ("429" in err_str) or ("timed out" in err_str)
                        if attempt < max_retries - 1:
                            backoff = (2.0 + attempt * 1.5) if is_throttled else (0.5 + attempt * 0.5)
                            time.sleep(backoff)
                        else:
                            with unresolved_lock:
                                unresolved_chunks.append(item)
                            if slot:
                                slot.status = "Error"
                            return False
                return False

            def worker_thread(slot_id: int):
                while not (self.cancel_event and self.cancel_event.is_set()):
                    if self.pause_event:
                        self.pause_event.wait()
                    try:
                        item = work_queue.get_nowait()
                    except queue.Empty:
                        break
                    download_dash_chunk(item, slot_id)
                    work_queue.task_done()

            threads = []
            for s_id in range(num_workers):
                t = threading.Thread(target=worker_thread, args=(s_id,), daemon=True)
                threads.append(t)
                t.start()
                if is_tiktok:
                    time.sleep(0.2)

            for t in threads:
                t.join()

            if self.cancel_event and self.cancel_event.is_set():
                self._is_cancelled = True
                return False

            # Secondary Retry Pass for any intermittent dropped chunks
            if unresolved_chunks:
                print(f"[HLSWorker] Retrying {len(unresolved_chunks)} failed DASH chunks sequentially...")
                time.sleep(1.0)
                still_missing = []
                for item in unresolved_chunks:
                    if not download_dash_chunk(item, slot_id=0):
                        still_missing.append(item)
                if len(still_missing) > len(all_items) * 0.15:
                    print(f"[HLSWorker] DASH download failed: {len(still_missing)} chunks could not be retrieved.")
                    return False

            # 6. Concatenate Video & Audio Streams
            merged_v_path = os.path.join(cache_dir, "merged_video.mp4") if v_files else None
            if merged_v_path:
                with open(merged_v_path, "wb") as f_out:
                    if v_init_path and os.path.exists(v_init_path):
                        with open(v_init_path, "rb") as f_in:
                            shutil.copyfileobj(f_in, f_out)
                    for vf in v_files:
                        if os.path.exists(vf):
                            with open(vf, "rb") as f_in:
                                shutil.copyfileobj(f_in, f_out)

            merged_a_path = os.path.join(cache_dir, "merged_audio.mp4") if a_files else None
            if merged_a_path:
                with open(merged_a_path, "wb") as f_out:
                    if a_init_path and os.path.exists(a_init_path):
                        with open(a_init_path, "rb") as f_in:
                            shutil.copyfileobj(f_in, f_out)
                    for af in a_files:
                        if os.path.exists(af):
                            with open(af, "rb") as f_in:
                                shutil.copyfileobj(f_in, f_out)

            # 7. Mux Video + Audio with FFmpeg
            dir_name = os.path.dirname(os.path.abspath(self.target_path))
            os.makedirs(dir_name, exist_ok=True)

            flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
            sinfo = None
            if sys.platform == "win32":
                sinfo = subprocess.STARTUPINFO()
                sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                sinfo.wShowWindow = 0

            remux_success = False

            if merged_v_path and os.path.exists(merged_v_path) and merged_a_path and os.path.exists(merged_a_path):
                # Mux video + audio
                cmd = [
                    ffmpeg_bin, "-y",
                    "-fflags", "+genpts+igndts",
                    "-avoid_negative_ts", "make_zero",
                    "-i", merged_v_path,
                    "-i", merged_a_path,
                    "-c", "copy",
                    "-movflags", "+faststart",
                    self.target_path
                ]
                res = subprocess.run(cmd, capture_output=True, creationflags=flag, startupinfo=sinfo)
                if res.returncode == 0 and os.path.exists(self.target_path) and os.path.getsize(self.target_path) > 1024:
                    remux_success = True
                else:
                    # Retry without -fflags
                    cmd_alt = [
                        ffmpeg_bin, "-y",
                        "-i", merged_v_path,
                        "-i", merged_a_path,
                        "-c", "copy",
                        "-movflags", "+faststart",
                        self.target_path
                    ]
                    res_alt = subprocess.run(cmd_alt, capture_output=True, creationflags=flag, startupinfo=sinfo)
                    if res_alt.returncode == 0 and os.path.exists(self.target_path) and os.path.getsize(self.target_path) > 1024:
                        remux_success = True
            elif merged_v_path and os.path.exists(merged_v_path):
                # Video only
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", merged_v_path,
                    "-c", "copy",
                    "-movflags", "+faststart",
                    self.target_path
                ]
                res = subprocess.run(cmd, capture_output=True, creationflags=flag, startupinfo=sinfo)
                if res.returncode == 0 and os.path.exists(self.target_path) and os.path.getsize(self.target_path) > 1024:
                    remux_success = True
                else:
                    shutil.copy2(merged_v_path, self.target_path)
                    remux_success = True
            elif merged_a_path and os.path.exists(merged_a_path):
                # Audio only
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", merged_a_path,
                    "-c", "copy",
                    self.target_path
                ]
                res = subprocess.run(cmd, capture_output=True, creationflags=flag, startupinfo=sinfo)
                if res.returncode == 0 and os.path.exists(self.target_path) and os.path.getsize(self.target_path) > 1024:
                    remux_success = True
                else:
                    shutil.copy2(merged_a_path, self.target_path)
                    remux_success = True

            if remux_success and os.path.exists(self.target_path) and os.path.getsize(self.target_path) > 1024:
                final_sz = os.path.getsize(self.target_path)
                if self.segment_slots:
                    for s in self.segment_slots:
                        s.status = "Completed"
                if self.on_progress:
                    self.on_progress(final_sz, final_sz, 0.0, 0)
                shutil.rmtree(cache_dir, ignore_errors=True)
                print(f"[HLSWorker] DASH download & remux completed successfully: {self.target_path} ({final_sz} bytes)")
                return True

            return False
        except Exception as e_dash:
            print(f"[HLSWorker] DASH engine exception: {e_dash}")
            return False
