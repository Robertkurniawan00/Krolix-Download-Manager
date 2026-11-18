import json
import logging
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("AV01Resolver")

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

GEO_JSON_URL = "https://files.iw01.xyz/edge/geo.js?json"
PRIMARY_CDN_API = "https://customers.iw01.xyz"
FALLBACK_APIS = [
    "https://www.av01.media",
    "https://www.av01.tv",
    "https://customers.iw01.xyz",
]


class AV01Resolver:
    """
    Automated Link, Token, and CDN Stream Resolver for AV01 (av01.media / av01.tv / iw01.xyz).
    
    Architecture:
    1. Video Page Resolution: Converts web page URLs (e.g. /videos/224550) to the master HLS playlist
       and resolves high-resolution video metadata (DVD ID, Title, Duration).
    2. Geo & Security Token Handshake: Queries files.iw01.xyz/edge/geo.js?json to acquire token_v2
       and client IP with rolling cache.
    3. CDN Access Token Generation: Queries /api/v1/videos/<id>/cdn-access to acquire signed JWT tokens
       with 1-hour expiration.
    4. Seamless Segment URL Signing: Transparently injects ?access_token=<JWT> into CMAF/fMP4 .m4s 
       segment requests and #EXT-X-MAP initialization segments to bypass Cloudflare/Envoy RBAC 403.
    """

    _lock = threading.Lock()
    _geo_cache: Optional[Dict[str, Any]] = None
    _geo_cache_time: float = 0.0
    _geo_cache_ttl: float = 300.0  # 5 minutes

    # Token cache: video_id -> (access_token, expires_at_timestamp)
    _token_cache: Dict[str, Tuple[str, float]] = {}

    # Metadata cache: video_id -> dict
    _metadata_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _create_ssl_context(cls) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    @classmethod
    def is_av01_url(cls, url: str) -> bool:
        """Determines if the URL belongs to AV01 / IW01 streaming ecosystem."""
        if not url:
            return False
        clean = url.strip().lower()
        return any(
            domain in clean
            for domain in [
                "av01.media",
                "av01.tv",
                "av01.xyz",
                "iw01.xyz",
                "customers.iw01.xyz",
                "files.iw01.xyz",
            ]
        ) or bool(re.search(r'/videos/\d+/(?:manifest|token|cdn-access)', clean))

    @classmethod
    def extract_video_id(cls, url: str, headers: Optional[dict] = None) -> Optional[str]:
        """Extracts the numeric video ID from URL or Referer headers."""
        if not url:
            return None

        # 1. Direct path /videos/(\d+)
        m = re.search(r'/(?:videos|video)/(\d+)', url)
        if m:
            return m.group(1)

        # 2. Query param ?video_id=(\d+) or &id=(\d+)
        m_q = re.search(r'[?&](?:video_id|id|v)=(\d+)', url)
        if m_q:
            return m_q.group(1)

        # 3. Check Referer or page_url in headers
        if headers:
            for k in ["Referer", "referer", "page_url", "Origin", "origin"]:
                ref_val = headers.get(k) or ""
                m_ref = re.search(r'/(?:videos|video)/(\d+)', ref_val)
                if m_ref:
                    return m_ref.group(1)

        # 4. In case the URL is a segment URL like .../1sdde00772-lada/...
        # check if we have a known token for any cached video_id whose sub matches the path
        try:
            with cls._lock:
                for vid, (token, _) in cls._token_cache.items():
                    # Quick check if vid is related
                    if f"/videos/{vid}" in url:
                        return vid
        except Exception:
            pass

        return None

    @classmethod
    def get_geo_data(cls, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Fetches client Geo, IP, and security token_v2 from files.iw01.xyz/edge/geo.js?json.
        Thread-safe with TTL caching.
        """
        now = time.time()
        with cls._lock:
            if not force_refresh and cls._geo_cache and (now - cls._geo_cache_time) < cls._geo_cache_ttl:
                return dict(cls._geo_cache)

        try:
            req = urllib.request.Request(
                GEO_JSON_URL,
                headers={
                    "User-Agent": DEFAULT_UA,
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://www.av01.media/",
                    "Origin": "https://www.av01.media",
                },
            )
            ctx = cls._create_ssl_context()
            with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                if data and ("token_v2" in data or "access_token" in data):
                    with cls._lock:
                        cls._geo_cache = data
                        cls._geo_cache_time = now
                    return dict(data)
        except Exception as e:
            logger.warning(f"[AV01Resolver] Failed to fetch geo data: {e}")
            with cls._lock:
                if cls._geo_cache:
                    return dict(cls._geo_cache)

        return None

    @classmethod
    def get_cdn_token(cls, video_id: str, force_refresh: bool = False) -> Optional[str]:
        """
        Obtains or refreshes the CDN access JWT token for a specific video ID.
        Queries /api/v1/videos/<id>/cdn-access with token_v2, expires, and client IP.
        """
        if not video_id:
            return None

        now = time.time()
        with cls._lock:
            if not force_refresh and video_id in cls._token_cache:
                tok, exp_time = cls._token_cache[video_id]
                # If token has >60 seconds of validity left, reuse it
                if exp_time > (now + 60):
                    return tok

        geo = cls.get_geo_data(force_refresh=force_refresh)
        if not geo:
            return None

        token_v2 = geo.get("token_v2", "")
        expires = geo.get("expires", "")
        client_ip = geo.get("ip", "")

        for base_host in FALLBACK_APIS:
            try:
                cdn_url = (
                    f"{base_host}/api/v1/videos/{video_id}/cdn-access"
                    f"?token_v2={urllib.parse.quote(str(token_v2))}"
                    f"&expires={urllib.parse.quote(str(expires))}"
                    f"&ip={urllib.parse.quote(str(client_ip))}"
                )
                req = urllib.request.Request(
                    cdn_url,
                    headers={
                        "User-Agent": DEFAULT_UA,
                        "Accept": "application/json, text/plain, */*",
                        "Referer": f"https://www.av01.media/videos/{video_id}",
                        "Origin": "https://www.av01.media",
                    },
                )
                ctx = cls._create_ssl_context()
                with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    access_token = resp_json.get("access_token")
                    expires_at = resp_json.get("expires_at") or (now + 3600)
                    if access_token:
                        with cls._lock:
                            cls._token_cache[video_id] = (access_token, float(expires_at))
                        logger.info(f"[AV01Resolver] Acquired fresh CDN access token for video {video_id}")
                        return access_token
            except Exception as e:
                logger.debug(f"[AV01Resolver] CDN access request failed on {base_host}: {e}")

        return None

    @classmethod
    def sign_segment_url(
        cls,
        url: str,
        video_id: Optional[str] = None,
        force_refresh: bool = False
    ) -> str:
        """
        Signs an fMP4/CMAF segment or map URL with the CDN access token.
        Preserves existing parameters and seamlessly appends access_token=<JWT>.
        """
        if not url:
            return url

        clean_lower = url.lower()
        # Only customer/files IW01 CDN endpoints require access_token
        if "iw01.xyz" not in clean_lower and "av01" not in clean_lower:
            return url

        # If already signed and not forcing refresh, return as is
        if "access_token=" in url and not force_refresh:
            return url

        vid = video_id or cls.extract_video_id(url)
        if not vid:
            # Check cached tokens for the most recently used video_id
            with cls._lock:
                if cls._token_cache:
                    vid = next(reversed(cls._token_cache))

        if not vid:
            return url

        token = cls.get_cdn_token(vid, force_refresh=force_refresh)
        if not token:
            return url

        parsed = urllib.parse.urlsplit(url)
        query_dict = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        query_dict["access_token"] = [token]

        # Flatten query dict back
        new_query_pairs = []
        for k, v_list in query_dict.items():
            for v in v_list:
                new_query_pairs.append(f"{k}={urllib.parse.quote(str(v), safe='')}")
        new_query = "&".join(new_query_pairs)

        return urllib.parse.urlunsplit((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            new_query,
            parsed.fragment
        ))

    @classmethod
    def get_video_metadata(cls, video_id: str) -> Optional[Dict[str, Any]]:
        """Fetches detailed video metadata (DVD ID, title, duration, cover) from API."""
        if not video_id:
            return None

        with cls._lock:
            if video_id in cls._metadata_cache:
                return dict(cls._metadata_cache[video_id])

        for base_host in FALLBACK_APIS:
            try:
                meta_url = f"{base_host}/api/v1/videos/{video_id}"
                req = urllib.request.Request(
                    meta_url,
                    headers={
                        "User-Agent": DEFAULT_UA,
                        "Accept": "application/json",
                        "Referer": "https://www.av01.media/",
                    },
                )
                ctx = cls._create_ssl_context()
                with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    if data and "id" in data:
                        with cls._lock:
                            cls._metadata_cache[video_id] = data
                        return dict(data)
            except Exception:
                pass

        return None

    @classmethod
    def resolve_video_page(cls, url: str) -> Optional[Dict[str, Any]]:
        """
        Resolves a user-provided video page URL (e.g. https://www.av01.media/videos/224550)
        into a master HLS stream URL and metadata.
        """
        video_id = cls.extract_video_id(url)
        if not video_id:
            return None

        meta = cls.get_video_metadata(video_id) or {}
        dvd_id = meta.get("dvd_id") or ""
        en_title = (
            (meta.get("seo_titles") or {}).get("en")
            or (meta.get("title_translations") or {}).get("en")
            or meta.get("title")
            or ""
        )
        clean_title = f"{dvd_id}•{en_title}".strip("• ") if dvd_id else en_title
        if not clean_title:
            clean_title = f"AV01_Video_{video_id}"

        # Clean filename for filesystem
        safe_fn = re.sub(r'[\\/*?:"<>|]', "_", clean_title).strip()
        if not safe_fn.lower().endswith(".mp4"):
            safe_fn = f"{safe_fn}.mp4"

        master_url = f"https://www.av01.media/api/v1/videos/{video_id}/manifest/master.m3u8"

        return {
            "stream_url": master_url,
            "filename": safe_fn,
            "video_id": video_id,
            "title": clean_title,
            "duration": meta.get("duration", 0),
            "cover": meta.get("cover"),
            "headers": {
                "User-Agent": DEFAULT_UA,
                "Referer": f"https://www.av01.media/videos/{video_id}",
                "Origin": "https://www.av01.media",
            }
        }
