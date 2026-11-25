"""
Zero Download Assistant - Social Media & Video Stream Grabber via yt-dlp & Native Resolvers
"""

import os
import sys
import re
import json
import ssl
import shutil
import urllib.request
import urllib.parse
import subprocess
from typing import Tuple, Optional, List
from ..utils.helpers import sanitize_filename

AD_OR_JUNK_PATTERNS = [
    "blurred", "_blur", "-blur", "/blur", "blur.m3u8", "preview_blur",
    "hover_preview", "hover-preview", "hoverpreview", "thumb_preview",
    "thumb-preview", "thumbnail_preview", "trailer_preview", "short_preview",
    "preview.m3u8", "preview.mp4", "teaser.m3u8", "storyboard",
    "storyboard.m3u8", "sprite.m3u8", "spritesheet", "160p_blurred",
    "144p_blurred", "120p_blurred"
]

AD_DOMAINS_AND_KEYWORDS = [
    # Google & YouTube Ads
    "doubleclick.net", "googleads", "googlesyndication.com", "adservice.google",
    "pagead", "g.doubleclick", "video-ad-stats", "adwords",
    "youtube.com/api/stats/ads", "youtube.com/pagead", "youtube.com/ptracking",
    # Amazon Ads
    "amazon-adsystem.com", "aax.amazon-adsystem.com", "aax-us-east.amazon-adsystem.com",
    "advertising.amazon.com", "aps.amazon.com",
    # Microsoft / Xandr / AppNexus
    "adnxs.com", "adnxs-simple.com", "bingads", "bat.bing.com",
    # Major SSPs, DSPs, Exchanges & VAST/VPAID
    "spotx.tv", "spotxchange.com", "springserve.com", "teads.tv",
    "aniview.com", "freewheel.tv", "fwmrm.net", "tremorhub.com",
    "tremormedia.com", "unruly.co", "exponential.com", "innovid.com",
    "videologygroup.com", "brightroll.com", "adkernel.com", "adform.net",
    "smartadserver.com", "bidswitch.net", "rubiconproject.com", "pubmatic.com",
    "openx.net", "criteo.com", "criteo.net", "adroll.com", "casalemedia.com",
    "indexww.com", "contextweb.com", "pulsepoint.com", "yieldmo.com",
    "sharethrough.com", "triplelift.com", "nativo.com", "kargo.com",
    "sovrn.com", "adtech.de", "adtechus.com", "conversantmedia.com",
    # Mobile / In-App Video Ad SDKs
    "applovin.com", "unityads", "vungle.com", "inmobi.com",
    "chartboost.com", "ironsource.com", "fyber.com", "mintegral.com",
    "liftoff.io", "pangleglobal.com", "tapjoy.com", "adcolony.com",
    # Native & Recommendation Video Ads
    "outbrain.com", "taboola.com", "mgid.com", "revcontent.com",
    "content-ad.net", "zemanta.com", "zergnet.com",
    # Video Ad & Pop Ad Networks
    "trafficjunky.com", "trafficjunky.net", "trafficfactory.biz",
    "exoclick.com", "exosrv.com", "exdynsrv.com", "adsterra.com",
    "adsterracdn.com", "adsterratech.com", "popads.net", "popcash.net",
    "juicyads.com", "ero-advertising.com", "hubtraffic.com", "ht-ads.com",
    "stripchat-ads", "chaturbate-ads", "plugrush.com", "clickadu.com",
    "propellerads.com", "propellerclick.com", "adcash.com", "hilltopads.net",
    "evadav.com", "monetag.com", "clickaine.com", "rollerads.com",
    "bidgear.com", "coinhive.com",
    # Verification & Measurement
    "moatads.com", "doubleverify.com", "scorecardresearch.com",
    "iasds01.com", "integralads.com", "meetrics.net", "adloox.com"
]

AD_URL_REGEX = re.compile(
    r'(?:(?:^|[/?&_#.-])(?:vast|vpaid|ima3|imasdk|interactive-media-ads|preroll|midroll|postroll|popunder|interstitial|ad_unit|adunit|ad_banner|ad_video|ad-video|advideo|ad_stream|adstream|ad_system|ad_tag|adtag|video-ad|video_ad|videoad|videoads|advert|advertisement|sponsored|promo_video|promoted|commercial|adformat|ad_format|ad_cpn|ad_type|adurl|ad_network|ad_client|ad_slot|ad_channel|ad_companion|ad_provider)(?:[/?&=_#.-]|$))|'
    r'(?:/(?:ads|ad|advert|advertising|banners?|commercials?|promos?|sponsors?)/(?:video|stream|vast|vpaid|m3u8|mp4|hls|dash|delivery))|'
    r'(?:[?&](?:adformat|ad_format|ad_type|ad_tag|adtag|ad_id|adurl|ad_network|ad_client|ad_slot|ad_channel|ad_companion|ad_provider|ad_cpn|is_ad|isad|ctas|gvi)=)',
    re.IGNORECASE
)

def is_ad_or_junk_media(url: str, name: str = "", height: int = 0) -> bool:
    if not url:
        return False
    u = (url or "").lower()
    n = (name or "").lower()
    full = f"{u} {n}"

    if any(p in full for p in AD_OR_JUNK_PATTERNS):
        return True
    if any(ad in u for ad in AD_DOMAINS_AND_KEYWORDS):
        return True
    if AD_URL_REGEX.search(u) or AD_URL_REGEX.search(n):
        return True
    if height and height <= 180 and ("blur" in full or "preview" in full):
        return True
    return False


class MediaGrabber:
    @staticmethod
    def normalize_url(url: str) -> str:
        u = (url or "").strip()
        if not u:
            return ""

        # Chaturbate profile normalization:
        # e.g. "chaturbate.com/sweet_girl", "chaturbate.com/sweet_girl/", "cb.live/sweet_girl", "chaturbate:sweet_girl"
        if "chaturbate" in u.lower() or u.lower().startswith("cb.live/"):
            m = re.search(r'(?:chaturbate\.(?:com|eu|global)/(?:b/)?|cb\.live/|chaturbate:)([a-zA-Z0-9_\-]+)', u, re.I)
            if m:
                username = m.group(1)
                return f"https://chaturbate.com/{username}/"
            elif not u.startswith("http"):
                return f"https://{u}"
        # Stripchat profile normalization:
        elif "stripchat" in u.lower():
            m = re.search(r'(?:stripchat\.(?:com|org|me)/(?:b/)?|stripchat:)([a-zA-Z0-9_\-]+)', u, re.I)
            if m:
                username = m.group(1)
                return f"https://stripchat.com/{username}"
            elif not u.startswith("http"):
                return f"https://{u}"
        elif not u.startswith("http://") and not u.startswith("https://"):
            if "." in u or "/" in u:
                return f"https://{u}"
        return u

    @staticmethod
    def extract_info(url: str) -> dict:
        info, _ = MediaGrabber.get_media_info(url)
        return info or {}

    @staticmethod
    def parse_m3u8_playlist(m3u8_url: str, default_title: str = "Stream", headers: Optional[dict] = None) -> List[dict]:
        """
        Parses an HLS playlist using HLSInspector. Extracts resolution, bitrate, size, master URL, and audio renditions.
        """
        is_live_hint = bool(headers and (str(headers.get("is_live", "")).lower() == "true" or headers.get("is_live") is True))
        try:
            from .hls_downloader import HLSInspector
            hls_info = HLSInspector.probe(m3u8_url, headers=headers)
            if hls_info.get("success") and hls_info.get("variants"):
                formats = []
                for v in hls_info["variants"]:
                    is_fmt_live = v.get('is_live', False) or is_live_hint
                    formats.append({
                        'format_id': f"{v.get('height')}p" if v.get('height') else v.get('label', 'stream'),
                        'label': v.get('display_name') or f"{v.get('label', 'Stream')} ({v.get('resolution', '')})",
                        'ext': 'mp4',
                        'height': v.get('height', 0),
                        'width': v.get('width', 0),
                        'bitrate': v.get('bitrate', 0),
                        'duration': v.get('duration', 0),
                        'filesize': v.get('total_bytes', v.get('filesize', 0)),
                        'url': v.get('url', m3u8_url),
                        'master_url': v.get('master_url') or m3u8_url,
                        'audio_url': v.get('audio_url'),
                        'has_video': True,
                        'has_audio': True,
                        'codec_desc': 'Live Stream (HLS)' if is_fmt_live else 'HLS Stream',
                        'sort_prio': 3,
                        'companion_audio': None,
                        'is_live': is_fmt_live
                    })
                if formats:
                    # Sort formats: highest resolution total pixels (width * height), then bitrate descending
                    formats.sort(
                        key=lambda x: (
                            (x["width"] * x["height"]) if (x["width"] and x["height"]) else (x["height"] * 1000),
                            x["bitrate"]
                        ),
                        reverse=True
                    )
                    return formats
        except Exception:
            pass

        # Basic fallback format
        return [{
            'format_id': 'original',
            'label': 'Live Stream (Original)' if is_live_hint else 'Stream (Original)',
            'ext': 'mp4',
            'height': 720,
            'bitrate': 0,
            'duration': 0,
            'filesize': 0,
            'url': m3u8_url,
            'master_url': m3u8_url,
            'audio_url': None,
            'has_video': True,
            'has_audio': True,
            'codec_desc': 'Live Stream (HLS)' if is_live_hint else 'HLS Stream',
            'sort_prio': 3,
            'companion_audio': None,
            'is_live': is_live_hint
        }]


    @staticmethod
    def extract_chaturbate_direct(url: str) -> Tuple[Optional[dict], Optional[str]]:
        """
        Direct native Chaturbate edge HLS stream extractor.
        Works fast and independently of external libraries, with DPI-bypass fallback.
        """
        m = re.search(r'chaturbate\.(?:com|eu|global)/(?:b/)?([a-zA-Z0-9_\-]+)', url, re.I)
        if not m:
            return None, None
        username = m.group(1)
        if username.lower() in ["b", "p", "tags", "auth", "accounts", "terms"]:
            return None, None

        data = None
        m3u8_url = None
        status = "offline"
        try:
            post_data = urllib.parse.urlencode({"room_slug": username}).encode("utf-8")
            req = urllib.request.Request(
                "https://chaturbate.com/get_edge_hls_url_ajax/",
                data=post_data,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                    "Referer": f"https://chaturbate.com/{username}/"
                }
            )
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            status = data.get("room_status", "offline")
            m3u8_url = data.get("url")
        except Exception:
            pass

        # Fallback to DPI-bypass room HTML inspection if AJAX failed or returned no URL
        if not m3u8_url:
            try:
                from .hls_downloader import fetch_url_with_dpi_bypass
                raw_html, _ = fetch_url_with_dpi_bypass(
                    f"https://chaturbate.com/{username}/",
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                    timeout=12
                )
                if raw_html:
                    html_str = raw_html.decode("utf-8", errors="ignore")
                    m_dossier = re.search(r'window\.initialRoomDossier\s*=\s*"([^"]+)"', html_str)
                    if m_dossier:
                        unescaped = m_dossier.group(1).encode("utf-8").decode("unicode_escape")
                        dossier = json.loads(unescaped)
                        m3u8_url = dossier.get("hls_source") or m3u8_url
                        status = dossier.get("room_status") or status
                    if not m3u8_url:
                        m_hls = re.search(r'https://[^\s"\'\\]+?\.m3u8[^\s"\'\\]*', html_str)
                        if m_hls:
                            m3u8_url = m_hls.group(0).replace("\\u002D", "-")
                            status = "public"
            except Exception as e:
                if not data:
                    return None, str(e)

        try:
            if not m3u8_url or status != "public":
                if status == "offline":
                    return None, f"Model '{username}' saat ini OFFLINE. Broadcaster belum memulai siaran langsung."
                elif status == "private":
                    return None, f"Model '{username}' sedang dalam sesi Private Show (berbayar)."
                elif status == "away":
                    return None, f"Model '{username}' sedang Away."
                return None, f"Status room '{username}': {status.upper()}"

            cb_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Referer": f"https://chaturbate.com/{username}/",
                "Origin": "https://chaturbate.com",
                "page_url": f"https://chaturbate.com/{username}/",
                "is_live": "true"
            }
            variants = MediaGrabber.parse_m3u8_playlist(m3u8_url, f"Chaturbate Live - {username}", headers=cb_headers)
            return {
                "title": f"Chaturbate - {username} (Live)",
                "thumbnail": f"https://roomimg.stream.highwebmedia.com/ri/{username}.jpg",
                "duration": 0,
                "is_live": True,
                "formats": variants,
                "webpage_url": f"https://chaturbate.com/{username}/",
                "m3u8_url": m3u8_url,
                "best_audio": None
            }, None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def extract_stripchat_direct(url: str) -> Tuple[Optional[dict], Optional[str]]:
        """
        Direct native Stripchat edge HLS stream extractor from webpage preloaded state.
        Fast, resilient, and checks online/offline/private status accurately.
        """
        m = re.search(r'stripchat\.(?:com|org|me)/(?:b/)?([a-zA-Z0-9_\-]+)', url, re.I)
        if not m:
            return None, None
        username = m.group(1)
        if username.lower() in ["tags", "auth", "accounts", "terms", "privacy", "categories", "login", "signup"]:
            return None, None

        try:
            html = ""
            try:
                req = urllib.request.Request(
                    f"https://stripchat.com/{username}",
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    }
                )
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
            except Exception:
                from .hls_downloader import fetch_url_with_dpi_bypass
                raw_html, _ = fetch_url_with_dpi_bypass(
                    f"https://stripchat.com/{username}",
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    },
                    timeout=12
                )
                if raw_html:
                    html = raw_html.decode("utf-8", errors="ignore")

            pos = html.find("window.__PRELOADED_STATE__")
            if pos == -1:
                return None, None
            start = html.find("=", pos) + 1
            end = html.find("</script>", start)
            if end == -1:
                return None, None
            data = json.loads(html[start:end].strip().rstrip(";"))

            view_cam = data.get("viewCam") or {}
            model = view_cam.get("model") or {}
            if not model:
                return None, f"'{username}' bukan broadcaster atau tidak ditemukan."
            is_live = bool(model.get("isLive", False))
            status = model.get("status", "off")
            show = view_cam.get("show")

            # Check if currently inside a private/group/paid show
            is_private = False
            if isinstance(show, dict) and not show.get("endedAt"):
                if show.get("mode") in ("private", "groupShow", "p2p", "ticket"):
                    is_private = True
            if status in ("private", "p2p", "group"):
                is_private = True

            if not is_live:
                return None, f"Model '{username}' saat ini OFFLINE. Broadcaster belum memulai siaran langsung."
            if is_private:
                return None, f"Model '{username}' sedang dalam sesi Private Show (berbayar)."

            model_id = model.get("id")
            if not model_id:
                return None, "Tidak dapat menemukan ID model Stripchat."

            # Find fallbackDomains or hlsStreamHost across config versions
            fallback_domains = []
            cfg_v3 = data.get("configV3") or {}
            init_common = cfg_v3.get("initialCommon") or {}
            static_feat = (cfg_v3.get("static") or {}).get("featureSettings") or {}
            feat_cfg = (data.get("featuresConfig") or {}).get("features") or {}

            common_host = init_common.get("hlsStreamHost") or init_common.get("defaultHlsStreamHost")
            if common_host and common_host not in fallback_domains:
                fallback_domains.append(common_host)

            for h_val in (init_common.get("hlsStreamHosts", {}) or {}).values():
                if h_val and h_val not in fallback_domains:
                    fallback_domains.append(h_val)

            hls_fallback = static_feat.get("hlsFallback", {}) or {}
            for dom in hls_fallback.get("fallbackDomains", []):
                if dom and dom not in fallback_domains:
                    fallback_domains.append(dom)

            for default_host in ["doppiocdn.media", "doppiocdn.com", "doppiocdn.net", "doppiocdn1.com", "doppiocdn2.com", "stripcdn.com", "stripchat.com"]:
                if default_host not in fallback_domains:
                    fallback_domains.append(default_host)

            stream_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Referer": f"https://stripchat.com/{username}",
                "Origin": "https://stripchat.com",
                "page_url": f"https://stripchat.com/{username}",
                "is_live": "true"
            }

            # Construct HLS master URL
            variants = []
            for host in fallback_domains:
                m3u8_url = f"https://edge-hls.{host}/hls/{model_id}/master/{model_id}_auto.m3u8?pkey=B0p93vi8Uj6AYyZb"
                try:
                    v = MediaGrabber.parse_m3u8_playlist(m3u8_url, f"Stripchat Live - {username}", headers=stream_headers)
                    if v:
                        variants = v
                        break
                except Exception:
                    continue

            if not variants:
                m3u8_url = f"https://edge-hls.doppiocdn.com/hls/{model_id}/master/{model_id}_auto.m3u8?pkey=B0p93vi8Uj6AYyZb"
                variants = [{
                    'format_id': 'original',
                    'label': 'Live Stream (Original)',
                    'ext': 'mp4',
                    'height': 720,
                    'bitrate': 0,
                    'duration': 0,
                    'filesize': 0,
                    'url': m3u8_url,
                    'has_video': True,
                    'has_audio': True,
                    'codec_desc': 'Stripchat Live HLS',
                    'sort_prio': 3,
                    'companion_audio': None,
                    'is_live': True
                }]

            thumb = model.get("snapshotUrl") or f"https://img.strpst.com/thumbs/{model_id}/thumb.jpg"
            return {
                "title": f"Stripchat - {username} (Live)",
                "thumbnail": thumb,
                "duration": 0,
                "is_live": True,
                "formats": variants,
                "webpage_url": f"https://stripchat.com/{username}",
                "m3u8_url": m3u8_url,
                "best_audio": None
            }, None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def _sanitize_extractor_error(err_str: str, url: str) -> str:
        if not err_str:
            return "Gagal mengekstrak informasi media dari URL ini."

        low = err_str.lower()
        url_low = (url or "").lower()

        # 1. PhantomJS / iQIYI / Legacy JS engine errors
        if "phantomjs" in low or "iq.com" in url_low or "iqiyi" in url_low:
            return (
                "Video pada situs ini (iQIYI / iq.com) menggunakan enkripsi pemutar dinamis "
                "dan proteksi hak cipta DRM (Digital Rights Management). Konten ini tidak dapat "
                "diekstrak secara langsung dari URL halaman web.\n\n"
                "Catatan: Konten video yang dilindungi hak cipta DRM (seperti iQIYI, Netflix, Disney+) "
                "hanya dapat diputar langsung di dalam browser resmi."
            )

        # 2. DRM protection
        if "drm" in low:
            return (
                "Video ini dilindungi oleh enkripsi DRM (Digital Rights Management) "
                "dan tidak dapat diunduh langsung."
            )

        # 3. Stream / Broadcaster offline
        if "offline" in low:
            return "Siaran langsung / room penyiar saat ini sedang OFFLINE."

        # 4. Age restriction / Login required
        if "sign in to confirm your age" in low or "login" in low or "account" in low:
            return "Video ini memerlukan login akun atau verifikasi batas usia pada platform."

        # 5. Private / Removed video
        if "private video" in low or "video unavailable" in low or "deleted" in low:
            return "Video ini disetel ke pribadi, telah dihapus, atau tidak tersedia lagi."

        # 6. Geo-blocking
        if "not available in your country" in low or "geo-restricted" in low or "geographic" in low:
            return "Video ini dibatasi secara geografis (Geo-restricted) dan tidak tersedia untuk wilayah Anda."

        # 7. Clean up raw CLI error prefixes
        clean = err_str.strip()
        if clean.startswith("ERROR:"):
            clean = clean[6:].strip()
        clean = re.sub(r'^\[[^\]]+\]\s*[^:]*:\s*', '', clean).strip()

        return clean or "Gagal mengekstrak informasi media. Pastikan URL valid dan aktif."

    @staticmethod
    def get_media_info(url: str, headers: Optional[dict] = None):
        clean_url = MediaGrabber.normalize_url(url)
        if is_ad_or_junk_media(clean_url):
            return None, "URL video iklan atau preview tidak didukung."
        last_error = None

        # If direct Chaturbate URL, try high-speed native edge extractor first
        if "chaturbate" in clean_url.lower() or "cb.live" in clean_url.lower():
            cb_info, cb_err = MediaGrabber.extract_chaturbate_direct(clean_url)
            if cb_info:
                return cb_info, None
            elif cb_err and ("offline" in cb_err.lower() or "private" in cb_err.lower()):
                return None, cb_err

        # If direct Stripchat URL, try high-speed native extractor first
        if "stripchat" in clean_url.lower():
            sc_info, sc_err = MediaGrabber.extract_stripchat_direct(clean_url)
            if sc_info:
                return sc_info, None
            elif sc_err:
                return None, sc_err

        # Fast-track direct M3U8 URL with native HLS inspector
        if ".m3u8" in clean_url.lower():
            try:
                from .hls_downloader import HLSInspector
                hls_info = HLSInspector.probe(clean_url, headers=headers)
                if hls_info.get("success"):
                    formats = MediaGrabber.parse_m3u8_playlist(clean_url, headers=headers)
                    if formats:
                        return {
                            'title': hls_info.get("filename", "HLS Stream").replace(".mp4", ""),
                            'thumbnail': None,
                            'duration': hls_info.get("duration", 0),
                            'is_live': hls_info.get("is_live", False),
                            'formats': formats,
                            'webpage_url': clean_url,
                            'best_audio': None
                        }, None
            except Exception:
                pass

        # 1. Try python library yt_dlp directly
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'noplaylist': True,
                'extract_flat': False,
                'socket_timeout': 15,
                'nocheckcertificate': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
                }
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)
                if not info:
                    raise ValueError("yt-dlp returned empty info")

                # If playlist was returned, get first entry
                if 'entries' in info and info['entries']:
                    for entry in info['entries']:
                        if entry:
                            info = entry
                            break

                return MediaGrabber._process_formats(info, clean_url)
        except Exception as e:
            err_str = str(e)
            last_error = MediaGrabber._sanitize_extractor_error(err_str, clean_url)

        # 2. Try standalone binary if available
        ytdlp_bin = shutil.which("yt-dlp")
        if not ytdlp_bin:
            candidate = os.path.join(os.path.dirname(sys.executable), "yt-dlp.exe")
            if os.path.exists(candidate):
                ytdlp_bin = candidate

        if ytdlp_bin:
            try:
                cmd = [ytdlp_bin, "--no-check-certificates", "--dump-json", "--no-warnings", "--no-playlist", clean_url]
                sp_kwargs = {"capture_output": True, "text": True, "timeout": 20}
                if sys.platform == "win32":
                    sp_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                    sinfo = subprocess.STARTUPINFO()
                    sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    sinfo.wShowWindow = 0  # SW_HIDE
                    sp_kwargs["startupinfo"] = sinfo
                res = subprocess.run(cmd, **sp_kwargs)
                if res.returncode == 0 and res.stdout.strip():
                    info = json.loads(res.stdout)
                    return MediaGrabber._process_formats(info, clean_url)
                elif res.stderr:
                    last_error = MediaGrabber._sanitize_extractor_error(res.stderr.strip(), clean_url)
            except Exception as e:
                last_error = MediaGrabber._sanitize_extractor_error(str(e), clean_url)

        # 3. Direct m3u8 fallback if URL is an HLS playlist
        if ".m3u8" in clean_url.lower():
            variants = MediaGrabber.parse_m3u8_playlist(clean_url)
            if variants:
                return {
                    'title': sanitize_filename(os.path.basename(clean_url.split("?")[0]) or "HLS Stream"),
                    'thumbnail': None,
                    'duration': 0,
                    'is_live': True,
                    'formats': variants,
                    'webpage_url': clean_url,
                    'best_audio': None
                }, None

        err_msg = last_error or "Could not extract media info. Ensure URL is online and accessible."
        return None, err_msg

    @staticmethod
    def _process_formats(info: dict, url: str):
        duration = info.get('duration') or 0
        is_live = bool(info.get('is_live', False))
        raw_formats = info.get('formats', [])
        if not raw_formats:
            if info.get('url'):
                raw_formats = [info]

        video_candidates = []
        audio_candidates = []

        for f in raw_formats:
            ext = (f.get('ext') or 'mp4').lower()
            fid = str(f.get('format_id', ''))
            f_url = f.get('url')
            if not f_url or ext in ['mhtml', 'none'] or fid.startswith('sb'):
                continue

            height = f.get('height') or 0
            format_note = (f.get('format_note') or '').strip()
            if is_ad_or_junk_media(f_url, f"{fid} {format_note}", height):
                continue

            vcodec = f.get('vcodec', 'none')
            acodec = f.get('acodec', 'none')
            has_v = (vcodec is not None and vcodec != 'none')
            has_a = (acodec is not None and acodec != 'none')

            # Handle HLS streams where codecs might be None or unknown in manifest
            is_hls_stream = (
                f.get('protocol', '').startswith('m3u8') or
                '.m3u8' in f_url.lower() or
                is_live
            )
            if is_hls_stream and not has_v and not has_a:
                has_v = True
                has_a = True

            if not has_v and not has_a:
                continue

            height = f.get('height') or 0
            tbr = f.get('tbr') or 0
            abr = f.get('abr') or 0
            vbr = f.get('vbr') or 0
            fs = f.get('filesize') or f.get('filesize_approx') or 0

            # If filesize is missing, compute from bitrate and duration
            if not fs and duration:
                eff_rate = tbr or (vbr + abr)
                if eff_rate:
                    fs = int(eff_rate * 1000 / 8 * duration)

            is_direct = ('googlevideo.com' in f_url and 'manifest' not in f_url)
            format_note = (f.get('format_note') or '').strip()

            item = {
                'format_id': fid,
                'ext': ext,
                'height': height,
                'filesize': fs,
                'url': f_url,
                'has_video': has_v,
                'has_audio': has_a,
                'vcodec': vcodec,
                'acodec': acodec,
                'tbr': tbr,
                'abr': abr,
                'format_note': format_note,
                'is_direct': is_direct,
                'is_live': is_live
            }

            if has_v:
                video_candidates.append(item)
            elif has_a:
                audio_candidates.append(item)

        # Best companion audio for DASH video
        best_audio = None
        if audio_candidates:
            audio_candidates.sort(key=lambda a: (a['abr'] or a['tbr'] or 0, a['filesize']), reverse=True)
            m4a_audios = [a for a in audio_candidates if a['ext'] in ['m4a', 'aac', 'mp3']]
            best_audio = m4a_audios[0] if m4a_audios else audio_candidates[0]

        # Deduplicate video candidates by (height, ext)
        deduped_videos = {}
        for v in video_candidates:
            h = v['height']
            ext = v['ext']
            key = (h, ext)
            if key not in deduped_videos:
                deduped_videos[key] = v
            else:
                existing = deduped_videos[key]
                if existing['has_audio'] and not v['has_audio']:
                    continue
                elif v['has_audio'] and not existing['has_audio']:
                    deduped_videos[key] = v
                else:
                    if (v['is_direct'] and not existing['is_direct']) or (v['filesize'] > existing['filesize']):
                        deduped_videos[key] = v

        # Deduplicate audio candidates
        deduped_audios = {}
        for a in audio_candidates:
            abr_val = a['abr'] or a['tbr'] or 0
            abr_key = round(abr_val, -1) if abr_val else a['format_id']
            ext = a['ext']
            key = (abr_key, ext)
            if key not in deduped_audios:
                deduped_audios[key] = a
            else:
                if a['filesize'] > deduped_audios[key]['filesize']:
                    deduped_audios[key] = a

        final_formats = []

        # Process video formats: sort by resolution descending (4K -> 1080p -> 720p), then prefer audio
        sorted_videos = sorted(deduped_videos.values(), key=lambda x: (x['height'], x['has_audio'], x['filesize']), reverse=True)
        for v in sorted_videos:
            h = v['height']
            ext = v['ext']
            has_a = v['has_audio']
            fn = v['format_note']

            if is_live:
                label = f"{h}p (Live)" if h else "Live Stream"
                codec_desc = "Live Stream (HLS)"
                sort_prio = 4
            elif has_a:
                label = f"{h}p" if h else "Video"
                codec_desc = "Video + Audio"
                sort_prio = 3
            else:
                label = f"{h}p" if h else "Video"
                codec_desc = "Video (DASH)"
                sort_prio = 2

            if fn and fn.lower() not in label.lower() and not fn.lower().startswith(f"{h}p"):
                label += f" ({fn})"

            final_formats.append({
                'format_id': v['format_id'],
                'label': label,
                'ext': ext,
                'height': h,
                'bitrate': int(v.get('tbr') or 0),
                'duration': duration,
                'filesize': v['filesize'],
                'url': v['url'],
                'has_video': True,
                'has_audio': has_a,
                'codec_desc': codec_desc,
                'sort_prio': sort_prio,
                'companion_audio': best_audio if (not has_a and best_audio) else None,
                'is_live': is_live
            })

        # Process audio formats
        sorted_audios = sorted(deduped_audios.values(), key=lambda x: (x['abr'] or x['tbr'] or 0, x['filesize']), reverse=True)
        for a in sorted_audios:
            abr = int(a['abr'] or a['tbr'] or 0)
            ext = a['ext']
            label = f"Audio {abr} kbps" if abr else f"Audio ({ext.upper()})"
            final_formats.append({
                'format_id': a['format_id'],
                'label': label,
                'ext': ext,
                'height': 0,
                'bitrate': abr,
                'duration': duration,
                'filesize': a['filesize'],
                'url': a['url'],
                'has_video': False,
                'has_audio': True,
                'codec_desc': "Audio Only",
                'sort_prio': 1,
                'companion_audio': None,
                'is_live': False
            })

        raw_title = info.get('title', 'Video Download')
        clean_title = sanitize_filename(raw_title)

        return {
            'title': clean_title,
            'thumbnail': info.get('thumbnail'),
            'duration': duration,
            'is_live': is_live,
            'formats': final_formats,
            'webpage_url': url,
            'best_audio': best_audio
        }, None