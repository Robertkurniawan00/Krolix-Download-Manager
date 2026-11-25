import re
import urllib.request
import urllib.parse
import ssl
from typing import Optional, Tuple


DEFAULT_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


class CloudLinkResolver:
    @staticmethod
    def fix_headers(url: str, headers: Optional[dict] = None) -> dict:
        """
        Ensures that CDN streams have the correct Referer and complete browser User-Agent
        so servers like nginx / Cloudflare / video delivery CDNs do not reject with 403 Forbidden.
        """
        fixed = dict(headers or {})
        clean_url = (url or "").strip().lower()

        # 1. Ensure User-Agent is complete with AppleWebKit/537.36
        cur_ua = fixed.get("User-Agent") or fixed.get("user-agent") or ""
        if not cur_ua or "AppleWebKit" not in cur_ua:
            fixed["User-Agent"] = DEFAULT_DESKTOP_UA

        # 2. Host-specific Referer overrides
        # MixDrop / mxcontent.net
        if "mxcontent.net" in clean_url or "mixdrop" in clean_url or "mxdrop" in clean_url:
            cur_ref = fixed.get("Referer") or fixed.get("referer") or ""
            # If referer is missing or from a third-party embedding site (like archivebate), override to the origin player host
            if not cur_ref or ("mixdrop" not in cur_ref.lower() and "mxdrop" not in cur_ref.lower()):
                fixed["Referer"] = "https://mxdrop.top/"
            fixed["Origin"] = "https://mxdrop.top"

        # StreamTape / tapecontent.net
        elif "tapecontent.net" in clean_url or "streamtape" in clean_url:
            fixed["Referer"] = "https://streamtape.com/"

        # DoodStream
        elif any(d in clean_url for d in ["dood.", "ds202.club", "doodstream"]):
            fixed["Referer"] = "https://doodstream.com/"

        # Voe.sx
        elif "voe.sx" in clean_url:
            fixed["Referer"] = "https://voe.sx/"

        # Filemoon
        elif "filemoon.sx" in clean_url or "filemoon" in clean_url:
            fixed["Referer"] = "https://filemoon.sx/"

        # StreamWish
        elif "streamwish" in clean_url or "strwsh" in clean_url:
            fixed["Referer"] = "https://streamwish.to/"

        # LuluStream / streamhihi / tnmr.org / cdn-tnmr.org CDN
        elif any(d in clean_url for d in ["luluvdo", "lulustream", "streamhihi", "tnmr.org", "cdn-tnmr.org", "luluvid"]):
            cur_ref = fixed.get("Referer") or fixed.get("referer") or ""
            if not cur_ref:
                fixed["Referer"] = "https://missav.ws/"
            elif not any(x in cur_ref.lower() for x in ["missav", "netflav", "luluvdo", "lulustream", "streamhihi", "luluvid"]):
                fixed["Referer"] = "https://missav.ws/"
            p_ref = urllib.parse.urlsplit(fixed["Referer"])
            fixed["Origin"] = f"{p_ref.scheme}://{p_ref.netloc}" if p_ref.netloc else "https://missav.ws"
            if "Accept-Language" not in fixed and "accept-language" not in fixed:
                fixed["Accept-Language"] = "en-US,en;q=0.9"

        # TurbosPlayer / TurboVid
        elif "turbosplayer.com" in clean_url or "turbovid" in clean_url:
            cur_ref = fixed.get("Referer") or fixed.get("referer") or ""
            if not cur_ref or ("turbosplayer" not in cur_ref.lower() and "turbovid" not in cur_ref.lower()):
                fixed["Referer"] = "https://turbosplayer.com/"
            fixed["Origin"] = "https://turbosplayer.com"

        # JavClan embed player (when embedded inside third-party portals like jav.guru)
        elif "javclan.com" in clean_url:
            cur_ref = fixed.get("Referer") or fixed.get("referer") or ""
            if not cur_ref or "javclan.com" not in cur_ref.lower():
                fixed["Referer"] = "https://javclan.com/"
                fixed.pop("Cookie", None)
                fixed.pop("cookie", None)
            fixed["Origin"] = "https://javclan.com"

        # Stripchat / Doppio CDN streams
        elif any(d in clean_url for d in ["doppiocdn", "stripcdn", "stripchat", "cam-cdn", "bcvcdn"]):
            cur_ref = fixed.get("Referer") or fixed.get("referer") or ""
            if not cur_ref or "stripchat" not in cur_ref.lower():
                fixed["Referer"] = "https://stripchat.com/"
            fixed["Origin"] = "https://stripchat.com"

        # PikPak Cloud Storage & CDN streams
        elif any(d in clean_url for d in ["mypikpak.com", "mypikpak.net", "mypikpak.org", "pikpak.me"]):
            fixed["Referer"] = "https://mypikpak.com/"
            fixed["Origin"] = "https://mypikpak.com"

        # AV01 / IW01 Video CDN streams
        elif any(d in clean_url for d in ["av01.media", "av01.tv", "av01.xyz", "iw01.xyz"]):
            cur_ref = fixed.get("Referer") or fixed.get("referer") or ""
            if not cur_ref or not any(x in cur_ref.lower() for x in ["av01.media", "av01.tv"]):
                fixed["Referer"] = "https://www.av01.media/"
            fixed["Origin"] = "https://www.av01.media"

        # Public Object Storage / Ad-Site CDNs (Google UserContent, TikTok CDN, ByteImg, FBCDN):
        # Never forward third-party adult/embed site Referer, Origin, or Cookies or CDN WAF blocks with 403/429/Timeout!
        elif any(d in clean_url for d in [
            "googleusercontent.com",
            "storage.googleapis.com",
            "tiktokcdn.com",
            "tiktokv.com",
            "tiktok.com/ad-site",
            "ibyteimg.com",
            "byteimg.com",
            "fbcdn.net",
        ]):
            fixed.pop("Referer", None)
            fixed.pop("referer", None)
            fixed.pop("Origin", None)
            fixed.pop("origin", None)
            fixed.pop("Cookie", None)
            fixed.pop("cookie", None)

        return fixed

    @staticmethod
    def _unpack_packer(p: str, a: int, c: int, k_str: str) -> str:
        def baseN(num: int, b: int) -> str:
            chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            res = ""
            while num > 0:
                res = chars[num % b] + res
                num //= b
            return res or "0"
        words = k_str.split('|')
        for i in range(c - 1, -1, -1):
            key = baseN(i, a) if a <= 62 else str(i)
            val = words[i] if i < len(words) and words[i] else key
            p = re.sub(r'\b' + re.escape(key) + r'\b', lambda _m, v=val: v, p)
        return p

    @staticmethod
    def _fetch_text_resilient(url: str, headers: Optional[dict] = None, timeout: int = 8) -> Tuple[str, str]:
        """
        Resiliently fetches page HTML / script text using:
        1) Standard urllib request (fast path & unit-test mockable)
        2) Fallback to Fragmented TLS ClientHello DPI bypass (bypasses ISP SNI / DNS blocks like TrustPositif)
        Returns (content_text, final_url).
        """
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers=headers or {"User-Agent": DEFAULT_DESKTOP_UA})
            with urllib.request.urlopen(req, context=ctx, timeout=min(timeout, 4)) as resp:
                data = resp.read()
                if data:
                    return data.decode('utf-8', errors='ignore'), resp.geturl() or url
        except Exception:
            pass

        try:
            from .hls_downloader import fetch_url_with_dpi_bypass
            raw_bytes, eff_url = fetch_url_with_dpi_bypass(url, headers=headers, timeout=timeout)
            if raw_bytes:
                return raw_bytes.decode('utf-8', errors='ignore'), eff_url
        except Exception:
            pass

        return "", url

    @staticmethod
    def resolve_stream_url(url: str, headers: Optional[dict] = None) -> Tuple[str, dict]:
        """
        Attempts to resolve a fresh, valid CDN link when a direct media link
        has expired or returned 403 Forbidden.
        """
        clean_url = (url or "").strip()
        fixed_headers = CloudLinkResolver.fix_headers(clean_url, headers)

        # Hetzner speedtest decommissioned speed.hetzner.de -> migrate to fsn1-speed.hetzner.com
        if "speed.hetzner.de" in clean_url.lower():
            clean_url = re.sub(r'https?://speed\.hetzner\.de', 'https://fsn1-speed.hetzner.com', clean_url, flags=re.IGNORECASE)
            return clean_url, fixed_headers

        # Unpack embedded HTML players passing stream URLs in query strings (e.g. s1.devcorp.me/player.html?file=[{file: https://...m3u8}])
        if any(token in clean_url.lower() for token in ["player.html", "viewplayer.html", "play.html", "embed.html", "/player/?", "?file=", "&file=", "?source=", "&source=", "?src=", "&src=", "?stream=", "&stream="]):
            decoded = urllib.parse.unquote(urllib.parse.unquote(clean_url))
            m3u8_m = re.search(r'https?://[^\s"\'<>\\]+?\.(?:m3u8|mpd|mp4)(?:\?[^\s"\'<>\\]*)?', decoded, flags=re.IGNORECASE)
            if m3u8_m:
                stream_link = m3u8_m.group(0).rstrip('"\'\\')
                if not fixed_headers.get("Referer") and not fixed_headers.get("referer"):
                    try:
                        outer_parsed = urllib.parse.urlparse(clean_url)
                        fixed_headers["Referer"] = f"{outer_parsed.scheme}://{outer_parsed.netloc}/"
                    except Exception:
                        pass
                return stream_link, fixed_headers

        # MixDrop / mxcontent.net resolution
        if "mxcontent.net" in clean_url.lower() or "mixdrop" in clean_url.lower() or "mxdrop" in clean_url.lower():
            video_id = None
            m = re.search(r'/v2/([a-zA-Z0-9]+)\.mp4', clean_url)
            if m:
                video_id = m.group(1)
            else:
                m2 = re.search(r'/[ef]/([a-zA-Z0-9]+)', clean_url)
                if m2:
                    video_id = m2.group(1)

            if video_id:
                embed_urls = [
                    f"https://mxdrop.top/e/{video_id}",
                    f"https://mixdrop.ag/e/{video_id}",
                    f"https://mixdrop.co/e/{video_id}"
                ]

                for embed_url in embed_urls:
                    try:
                        req_hdrs = {
                            "User-Agent": DEFAULT_DESKTOP_UA,
                            "Referer": "https://archivebate.com/"
                        }
                        html, final_url = CloudLinkResolver._fetch_text_resilient(embed_url, headers=req_hdrs, timeout=8)
                        if not html:
                            continue
                        origin = final_url.split('/e/')[0] if '/e/' in final_url else "https://mxdrop.top"

                        for match in re.finditer(r"eval\(function\(p,a,c,k,e,[rd]\)\{.*?return p\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)", html, re.DOTALL):
                            p_code, a_val, c_val, k_str = match.groups()
                            unpacked = CloudLinkResolver._unpack_packer(p_code, int(a_val), int(c_val), k_str)
                            wurl_match = re.search(r'MDCore\.wurl\s*=\s*["\']([^"\']+)["\']', unpacked)
                            if wurl_match:
                                raw_wurl = wurl_match.group(1).strip()
                                if raw_wurl.startswith("//"):
                                    raw_wurl = "https:" + raw_wurl
                                return raw_wurl, {
                                    "Referer": f"{origin}/",
                                    "Origin": origin,
                                    "User-Agent": DEFAULT_DESKTOP_UA
                                }
                    except Exception:
                        pass

        # LuluStream / streamhihi / tnmr.org / cdn-tnmr.org resolution
        if any(d in clean_url.lower() for d in ["tnmr.org", "cdn-tnmr", "luluvdo", "streamhihi", "lulustream", "luluvid"]):
            video_id = None
            m = re.search(r'/(?:hls2/\d+/\d+/|[efd]/)([a-zA-Z0-9]+)(?:_[a-z0-9]+)?(?:/|$|\.|\?)', clean_url)
            if m:
                video_id = m.group(1)
            else:
                m2 = re.search(r'/(?:[efd]/|embed-)([a-zA-Z0-9]+)\.html', clean_url)
                if m2:
                    video_id = m2.group(1)

            if not video_id:
                # Check referer / page_url for reverse-hex token
                ref_chk = fixed_headers.get("Referer") or fixed_headers.get("referer") or fixed_headers.get("page_url") or ""
                ed_m = re.search(r'searcho/\?ed=([0-9a-fA-F]+)', ref_chk)
                if ed_m:
                    try:
                        dec = bytes.fromhex(ed_m.group(1)[::-1]).decode('ascii', errors='ignore')
                        m_dec = re.search(r'e/([a-zA-Z0-9]+)', dec)
                        if m_dec:
                            video_id = m_dec.group(1)
                    except Exception:
                        pass

            if video_id:
                # Prioritize host from referer if present
                ref_u = fixed_headers.get("Referer") or fixed_headers.get("referer") or ""
                prioritized_host = None
                if ref_u:
                    p_ref = urllib.parse.urlsplit(ref_u)
                    if any(d in p_ref.netloc.lower() for d in ["streamhihi", "lulustream", "luluvid", "luluvdo"]):
                        prioritized_host = f"{p_ref.scheme}://{p_ref.netloc}"

                embed_urls = []
                if prioritized_host:
                    embed_urls.append(f"{prioritized_host}/e/{video_id}")
                for cand in [
                    f"https://luluvid.com/e/{video_id}",
                    f"https://lulustream.com/e/{video_id}",
                    f"https://streamhihi.com/e/{video_id}",
                    f"https://luluvdo.com/e/{video_id}"
                ]:
                    if cand not in embed_urls:
                        embed_urls.append(cand)

                active_ua = fixed_headers.get("User-Agent") or fixed_headers.get("user-agent") or DEFAULT_DESKTOP_UA

                for embed_url in embed_urls:
                    try:
                        req_hdrs = {
                            "User-Agent": active_ua,
                            "Referer": embed_url,
                            "Accept-Language": "en-US,en;q=0.9"
                        }
                        html, _ = CloudLinkResolver._fetch_text_resilient(embed_url, headers=req_hdrs, timeout=8)
                        if not html:
                            continue
                        for match in re.finditer(r"eval\(function\(p,a,c,k,e,[rd]\)\{.*?return p\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)", html, re.DOTALL):
                            p_code, a_val, c_val, k_str = match.groups()
                            unpacked = CloudLinkResolver._unpack_packer(p_code, int(a_val), int(c_val), k_str)
                            m3u8_m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', unpacked)
                            if m3u8_m:
                                fresh_m3u8 = m3u8_m.group(0)
                                target_ref = fixed_headers.get("Referer") or fixed_headers.get("referer") or ""
                                if not target_ref or not any(x in target_ref.lower() for x in ["missav", "netflav"]):
                                    target_ref = "https://missav.ws/"
                                p_tref = urllib.parse.urlsplit(target_ref)
                                origin = f"{p_tref.scheme}://{p_tref.netloc}"
                                hdrs = {
                                    "Referer": target_ref,
                                    "Origin": origin,
                                    "User-Agent": active_ua,
                                    "Accept-Language": "en-US,en;q=0.9"
                                }
                                # If master playlist, resolve the media playlist variant
                                if "master.m3u8" in fresh_m3u8:
                                    resolved_variant = False
                                    try:
                                        m_text, _ = CloudLinkResolver._fetch_text_resilient(fresh_m3u8, headers=hdrs, timeout=6)
                                        if "#EXTM3U" in m_text:
                                            for l in m_text.splitlines():
                                                cand_line = l.strip()
                                                if cand_line and not cand_line.startswith("#"):
                                                    fresh_m3u8 = urllib.parse.urljoin(fresh_m3u8, cand_line)
                                                    resolved_variant = True
                                                    break
                                    except Exception:
                                        pass
                                    if not resolved_variant:
                                        fresh_m3u8 = fresh_m3u8.replace("master.m3u8", "index-v1-a1.m3u8")
                                return fresh_m3u8, hdrs
                    except Exception:
                        pass

        # StreamWish / strwsh / awish / wishfast resolution
        if any(d in clean_url.lower() for d in ["streamwish", "strwsh", "awish", "wishfast", "flaswish", "sfastwish"]):
            video_id = None
            m = re.search(r'/(?:[ef]/|embed-)([a-zA-Z0-9]+)', clean_url)
            if m:
                video_id = m.group(1)
            if video_id:
                embed_urls = [
                    f"https://streamwish.to/e/{video_id}",
                    f"https://strwsh.com/e/{video_id}",
                    f"https://awish.pro/e/{video_id}"
                ]
                for embed_url in embed_urls:
                    try:
                        req_hdrs = {
                            "User-Agent": DEFAULT_DESKTOP_UA,
                            "Referer": fixed_headers.get("Referer") or "https://streamwish.to/"
                        }
                        html, _ = CloudLinkResolver._fetch_text_resilient(embed_url, headers=req_hdrs, timeout=8)
                        if not html:
                            continue
                        for match in re.finditer(r"eval\(function\(p,a,c,k,e,[rd]\)\{.*?return p\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)", html, re.DOTALL):
                            p_code, a_val, c_val, k_str = match.groups()
                            unpacked = CloudLinkResolver._unpack_packer(p_code, int(a_val), int(c_val), k_str)
                            m3u8_m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', unpacked)
                            if m3u8_m:
                                return m3u8_m.group(0), {
                                    "Referer": f"{embed_url}",
                                    "Origin": embed_url.split('/e/')[0] if '/e/' in embed_url else "https://streamwish.to",
                                    "User-Agent": DEFAULT_DESKTOP_UA
                                }
                    except Exception:
                        pass

        # Filemoon resolution
        if any(d in clean_url.lower() for d in ["filemoon.sx", "filemoon.to", "filemoon"]):
            video_id = None
            m = re.search(r'/[ef]/([a-zA-Z0-9]+)', clean_url)
            if m:
                video_id = m.group(1)
            if video_id:
                embed_urls = [
                    f"https://filemoon.sx/e/{video_id}",
                    f"https://filemoon.to/e/{video_id}"
                ]
                for embed_url in embed_urls:
                    try:
                        req_hdrs = {
                            "User-Agent": DEFAULT_DESKTOP_UA,
                            "Referer": fixed_headers.get("Referer") or "https://filemoon.sx/"
                        }
                        html, _ = CloudLinkResolver._fetch_text_resilient(embed_url, headers=req_hdrs, timeout=8)
                        if not html:
                            continue
                        for match in re.finditer(r"eval\(function\(p,a,c,k,e,[rd]\)\{.*?return p\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)", html, re.DOTALL):
                            p_code, a_val, c_val, k_str = match.groups()
                            unpacked = CloudLinkResolver._unpack_packer(p_code, int(a_val), int(c_val), k_str)
                            m3u8_m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', unpacked)
                            if m3u8_m:
                                return m3u8_m.group(0), {
                                    "Referer": f"{embed_url}",
                                    "Origin": embed_url.split('/e/')[0] if '/e/' in embed_url else "https://filemoon.sx",
                                    "User-Agent": DEFAULT_DESKTOP_UA
                                }
                    except Exception:
                        pass

        # AV01 / IW01 stream token renewal
        if any(d in clean_url.lower() for d in ["av01.media", "av01.tv", "av01.xyz", "iw01.xyz"]):
            try:
                from .av01_resolver import AV01Resolver
                vid = AV01Resolver.extract_video_id(clean_url, fixed_headers)
                if vid:
                    fresh_tok = AV01Resolver.get_cdn_token(vid, force_refresh=True)
                    if fresh_tok:
                        clean_url = AV01Resolver.sign_segment_url(clean_url, video_id=vid, force_refresh=True)
                        return clean_url, fixed_headers
            except Exception:
                pass

        return clean_url, fixed_headers

    @staticmethod
    def resolve(url: str) -> str:
        clean_url = (url or "").strip()

        # 0. Hetzner speedtest decommissioned speed.hetzner.de -> migrate to fsn1-speed.hetzner.com
        if "speed.hetzner.de" in clean_url.lower():
            clean_url = re.sub(r'https?://speed\.hetzner\.de', 'https://fsn1-speed.hetzner.com', clean_url, flags=re.IGNORECASE)

        # 0b. Embedded HTML players passing stream URLs in query strings
        if any(token in clean_url.lower() for token in ["player.html", "viewplayer.html", "play.html", "embed.html", "/player/?", "?file=", "&file=", "?source=", "&source=", "?src=", "&src=", "?stream=", "&stream="]):
            decoded = urllib.parse.unquote(urllib.parse.unquote(clean_url))
            m3u8_m = re.search(r'https?://[^\s"\'<>\\]+?\.(?:m3u8|mpd|mp4)(?:\?[^\s"\'<>\\]*)?', decoded, flags=re.IGNORECASE)
            if m3u8_m:
                return m3u8_m.group(0).rstrip('"\'\\')

        # 1. Google Drive Sharing Link
        # e.g. https://drive.google.com/file/d/1A2B3C4D5E.../view
        gdrive_match = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', clean_url)
        if gdrive_match:
            file_id = gdrive_match.group(1)
            return f"https://drive.google.com/uc?export=download&id={file_id}"

        # 2. Dropbox Link
        # e.g. https://www.dropbox.com/s/xyz/file.zip?dl=0 -> dl=1
        if "dropbox.com" in clean_url:
            if "?dl=0" in clean_url:
                return clean_url.replace("?dl=0", "?dl=1")
            elif "&dl=0" in clean_url:
                return clean_url.replace("&dl=0", "&dl=1")
            elif "dl=" not in clean_url:
                separator = "&" if "?" in clean_url else "?"
                return f"{clean_url}{separator}dl=1"

        # 3. GitHub Blob to Raw
        # e.g. https://github.com/user/repo/blob/main/file.zip -> https://raw.githubusercontent.com/user/repo/main/file.zip
        github_match = re.match(r'https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)', clean_url)
        if github_match:
            user, repo, branch, path = github_match.groups()
            return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"

        # 4. Mediafire direct link extraction
        if "mediafire.com/file/" in clean_url:
            try:
                html, _ = CloudLinkResolver._fetch_text_resilient(clean_url, headers={"User-Agent": DEFAULT_DESKTOP_UA}, timeout=10)
                if html:
                    # Find direct download button
                    direct_match = re.search(r'href="(https?://download\d+\.mediafire\.com/[^"]+)"', html)
                    if direct_match:
                        return direct_match.group(1)
            except Exception:
                pass

        # 5. MixDrop / mxcontent.net direct link resolution
        if any(d in clean_url.lower() for d in ["mxdrop.top/e/", "mixdrop.ag/e/", "mixdrop.co/e/", "mixdrop.to/e/"]):
            fresh_url, _ = CloudLinkResolver.resolve_stream_url(clean_url)
            if fresh_url != clean_url:
                return fresh_url

        # 5b. AV01 Video Page -> Master Manifest Resolution
        # e.g. https://www.av01.media/videos/224550 -> https://www.av01.media/api/v1/videos/224550/manifest/master.m3u8
        if any(d in clean_url.lower() for d in ["av01.media/videos/", "av01.tv/videos/", "av01.xyz/videos/"]):
            try:
                from .av01_resolver import AV01Resolver
                page_info = AV01Resolver.resolve_video_page(clean_url)
                if page_info and page_info.get("stream_url"):
                    return page_info["stream_url"]
            except Exception:
                pass

        # 6. PikPak Public Share Link (Auto-extract direct CDN stream)
        try:
            from .pikpak_resolver import PikPakResolver
            if PikPakResolver.is_pikpak_url(clean_url):
                pik_item = PikPakResolver.resolve_single_or_first(clean_url)
                if pik_item and pik_item.get("url"):
                    return pik_item["url"]
        except Exception:
            pass

        return clean_url
