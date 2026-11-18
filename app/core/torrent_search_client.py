"""
Zero Download Assistant - Multi-Tracker Torrent API Client & Multi-Provider Engine
Connects Zero with Tier-1 Torrent Indexers:
1. AniRena (https://www.anirena.com/) - High-speed Anime releases & direct torrents
2. The Pirate Bay via Direct API (apibay.org) - Verified real sizes, seeders, and hash magnets
3. Nyaa.si - Global anime tracker with exact metadata
4. Multi-mirror Torznab Search (1337x, YTS, TorrentGalaxy, LimeTorrents)
5. Automatic sanitization of dummy/corrupt size values
"""

import urllib.request
import urllib.parse
import json
import ssl
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional


DEFAULT_TORZNAB_GATEWAY = ""

# Curated list of high-availability tier-1 public trackers to boost peers and seeders
TIER1_PUBLIC_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "udp://explodie.org:6969/announce",
    "udp://tracker.tiny-vps.com:6969/announce",
    "udp://p4p.arenabg.com:1337/announce",
    "udp://retracker.lanta-net.ru:2710/announce",
    "http://tracker.dler.org:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://tracker.dump.cl:6969/announce",
    "udp://tracker.bittor.pw:1337/announce"
]


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Intercepts HTTP 301/302 redirects to extract magnet URI from Location header."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TorrentSearchClient:
    def __init__(self, base_url: str = DEFAULT_TORZNAB_GATEWAY):
        self.base_url = (base_url or "").rstrip("/")
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    def _get_headers(self, auth_token: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ZeroDownloadAssistant/2.8 (Windows NT 10.0; Win64; x64) qBittorrent/4.6.5",
            "Accept": "application/json"
        }
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        return headers

    @staticmethod
    def parse_size_to_bytes(size_str: str) -> int:
        """Parses human-readable strings like '143.10 GB', '204.6 MB', '351 MiB' into bytes."""
        if not size_str or size_str == "--":
            return 0
        m = re.match(r"^([0-9\.]+)\s*([a-zA-Z]+)?$", size_str.strip())
        if not m:
            return 0
        val = float(m.group(1))
        unit = (m.group(2) or "B").upper()
        multipliers = {
            "B": 1,
            "K": 1024, "KB": 1024, "KIB": 1024,
            "M": 1024**2, "MB": 1024**2, "MIB": 1024**2,
            "G": 1024**3, "GB": 1024**3, "GIB": 1024**3,
            "T": 1024**4, "TB": 1024**4, "TIB": 1024**4,
        }
        return int(val * multipliers.get(unit, 1))

    @staticmethod
    def format_bytes(b: int) -> str:
        if not b or b <= 0:
            return "--"
        units = ["B", "KB", "MB", "GB", "TB"]
        idx = 0
        val = float(b)
        while val >= 1024.0 and idx < len(units) - 1:
            val /= 1024.0
            idx += 1
        return f"{val:.2f} {units[idx]}"

    @staticmethod
    def extract_size_from_title(title: str) -> tuple:
        """Attempts to recover real torrent size from release name (e.g. '[1.45 GB]', '700MB', '2.1GiB')."""
        if not title:
            return 0, "--"
        m = re.search(r'(?:\[|\(|\b)(\d+(?:\.\d+)?)\s*(GB|MB|KB|TB|GiB|MiB|KiB|TiB)(?:\]|\)|\b)', title, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1))
                unit = m.group(2).upper()
                multipliers = {
                    "KB": 1024, "KIB": 1024,
                    "MB": 1024**2, "MIB": 1024**2,
                    "GB": 1024**3, "GIB": 1024**3,
                    "TB": 1024**4, "TIB": 1024**4
                }
                bytes_val = int(val * multipliers.get(unit, 1))
                return bytes_val, f"{val:.2f} {unit}"
            except Exception:
                pass
        return 0, "--"

    @staticmethod
    def resolve_magnet(url: str) -> str:
        """
        Resolves AniRena or HTTP magnet redirect URLs into full magnet:?xt=... links.
        If the input is already a magnet link, returns it immediately.
        """
        if not url:
            return ""
        if url.startswith("magnet:"):
            return url

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), _NoRedirectHandler)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        try:
            opener.open(req, timeout=8)
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location")
            if loc and loc.startswith("magnet:"):
                return loc
        except Exception:
            pass
        return url

    # =========================================================================
    # Provider 1: AniRena (https://www.anirena.com/)
    # =========================================================================
    def search_anirena(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Direct parser for AniRena Anime Tracker.
        Retrieves actual sizes, seeders, leechers, and direct torrent/magnet endpoints.
        """
        clean_q = (query or "").strip()
        if not clean_q:
            return []

        url = f"https://www.anirena.com/?s={urllib.parse.quote_plus(clean_q)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        results = []
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=self._ctx, timeout=10) as r:
                html = r.read().decode("utf-8", errors="ignore")

            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
            for row in rows:
                m_title = re.search(r'class="[^"]*tl-torrent-name[^"]*"[^>]*data-torrent-id=([a-f0-9\-]+)[^>]*>(.*?)</a>', row)
                if not m_title:
                    m_title = re.search(r'data-torrent-id=([a-f0-9\-]+)[^>]*class="[^"]*tl-torrent-name[^"]*"[^>]*>(.*?)</a>', row)
                if not m_title:
                    continue

                tid = m_title.group(1).strip()
                title = re.sub(r"<[^>]+>", "", m_title.group(2)).strip()

                m_grp = re.search(r"class=tl-group[^>]*>(.*?)</a>", row)
                if m_grp:
                    grp = re.sub(r"<[^>]+>", "", m_grp.group(1)).strip()
                    if grp and not title.startswith(grp):
                        title = f"{grp} {title}"

                m_cat = re.search(r'<td\s+title="([^"]+)"\s+class=col-cat>', row)
                cat = "Anime"
                if m_cat:
                    raw_cat = m_cat.group(1).strip()
                    if "Audio" in raw_cat:
                        cat = "Music / Audio"
                    elif "Manga" in raw_cat:
                        cat = "Manga"
                    else:
                        cat = "Anime"

                m_sz = re.search(r'<td class="col-size[^"]*">\s*([0-9\.]+\s*[A-Za-z]+)\s*</td>', row)
                if not m_sz:
                    m_sz = re.search(r'<span class="tl-meta-size[^"]*">.*?([0-9\.]+\s*[A-Za-z]+)\s*</span>', row, re.DOTALL)
                size_str = m_sz.group(1).strip() if m_sz else "--"
                size_bytes = self.parse_size_to_bytes(size_str)

                m_se = re.search(r"class=col-se>\s*<span class=tl-se>\s*(\d+)\s*</span>", row)
                if not m_se:
                    m_se = re.search(r"class=tl-se>\s*(\d+)\s*</span>", row)
                seeds = int(m_se.group(1)) if m_se else 0

                m_le = re.search(r"class=col-le>\s*<span class=tl-le>\s*(\d+)\s*</span>", row)
                if not m_le:
                    m_le = re.search(r"class=tl-le>\s*(\d+)\s*</span>", row)
                peers = int(m_le.group(1)) if m_le else 0

                magnet_endpoint = f"https://www.anirena.com/torrents/{tid}/magnet"
                torrent_url = f"https://www.anirena.com/torrents/{tid}.torrent"

                results.append({
                    "title": title,
                    "size_bytes": size_bytes,
                    "size_formatted": size_str,
                    "seeds": seeds,
                    "peers": peers,
                    "indexer": "AniRena",
                    "category": cat,
                    "magnet": magnet_endpoint,
                    "torrent_url": torrent_url,
                    "guid": tid,
                    "publish_date": ""
                })
                if len(results) >= limit:
                    break
        except Exception as e:
            print(f"[TorrentSearchClient] AniRena search error: {e}")

        return results

    # =========================================================================
    # Provider 2: The Pirate Bay Direct API (apibay.org)
    # =========================================================================
    def search_apibay(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Direct official API for The Pirate Bay.
        Bypasses proxy scrapers to deliver 100% exact file sizes in bytes and real seeders.
        """
        clean_q = (query or "").strip()
        if not clean_q:
            return []

        url = f"https://apibay.org/q.php?q={urllib.parse.quote_plus(clean_q)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

        results = []
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=self._ctx, timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))

            if not isinstance(data, list) or (data and data[0].get("name") == "No results returned"):
                return []

            category_map = {
                "1": "Audio",
                "2": "Video / Movies",
                "3": "Applications",
                "4": "Games",
                "5": "Porn",
                "6": "Other"
            }

            for item in data[:limit]:
                name = item.get("name") or "Unnamed Release"
                info_hash = item.get("info_hash") or ""
                if not info_hash:
                    continue

                size_bytes = int(item.get("size") or 0)
                seeds = int(item.get("seeders") or 0)
                peers = int(item.get("leechers") or 0)
                cat_id_prefix = str(item.get("category", "2"))[0]
                category = category_map.get(cat_id_prefix, "General / Media")

                tr_params = "&".join(f"tr={urllib.parse.quote(t)}" for t in TIER1_PUBLIC_TRACKERS[:6])
                magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={urllib.parse.quote(name)}&{tr_params}"

                results.append({
                    "title": name,
                    "size_bytes": size_bytes,
                    "size_formatted": self.format_bytes(size_bytes),
                    "seeds": seeds,
                    "peers": peers,
                    "indexer": "The Pirate Bay",
                    "category": category,
                    "magnet": magnet,
                    "guid": info_hash.lower(),
                    "publish_date": ""
                })
        except Exception as e:
            print(f"[TorrentSearchClient] apibay error: {e}")

        return results

    # =========================================================================
    # Provider 3: Nyaa.si (Direct RSS feed)
    # =========================================================================
    def search_nyaa(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Direct search against Nyaa.si anime tracker."""
        clean_q = (query or "").strip()
        if not clean_q:
            return []

        url = f"https://nyaa.si/?f=0&c=0_0&q={urllib.parse.quote_plus(clean_q)}&page=rss"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml"
        }

        results = []
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=self._ctx, timeout=8) as r:
                xml_data = r.read()

            root = ET.fromstring(xml_data)
            items = root.findall(".//item")

            for it in items[:limit]:
                title = it.findtext("title") or "Unnamed Anime"
                size_str = it.findtext("{https://nyaa.si/xmlns/nyaa}size") or "--"
                size_bytes = self.parse_size_to_bytes(size_str)
                seeds = int(it.findtext("{https://nyaa.si/xmlns/nyaa}seeders") or 0)
                peers = int(it.findtext("{https://nyaa.si/xmlns/nyaa}leechers") or 0)
                cat = it.findtext("{https://nyaa.si/xmlns/nyaa}category") or "Anime"
                info_hash = it.findtext("{https://nyaa.si/xmlns/nyaa}infoHash") or ""
                torrent_link = it.findtext("link") or ""

                if info_hash:
                    tr_params = "&".join(f"tr={urllib.parse.quote(t)}" for t in [
                        "http://nyaa.tracker.wf:7777/announce",
                        "udp://open.stealth.si:80/announce",
                        "udp://tracker.opentrackr.org:1337/announce"
                    ])
                    magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={urllib.parse.quote(title)}&{tr_params}"
                else:
                    magnet = torrent_link

                results.append({
                    "title": title,
                    "size_bytes": size_bytes,
                    "size_formatted": size_str,
                    "seeds": seeds,
                    "peers": peers,
                    "indexer": "Nyaa.si",
                    "category": cat,
                    "magnet": magnet,
                    "torrent_url": torrent_link,
                    "guid": info_hash or torrent_link,
                    "publish_date": it.findtext("pubDate") or ""
                })
        except Exception as e:
            print(f"[TorrentSearchClient] Nyaa error: {e}")

        return results

    # =========================================================================
    # Provider 4: Torznab Multi-Mirror (1337x, YTS, TorrentGalaxy)
    # =========================================================================
    def search_torznab_mirror(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Queries Torznab multi-tracker gateway, automatically filtering dummy size artifacts."""
        clean_q = (query or "").strip()
        if not clean_q or not self.base_url:
            return []

        search_url = f"{self.base_url}/api/torznab/search"
        payload = json.dumps({"query": clean_q, "limit": limit}).encode("utf-8")
        req = urllib.request.Request(search_url, data=payload, headers=self._get_headers())

        results = []
        try:
            with urllib.request.urlopen(req, context=self._ctx, timeout=10) as res:
                if res.status != 200:
                    return []
                data = json.loads(res.read().decode("utf-8"))
                raw_results = data.get("results", [])

                for item in raw_results:
                    indexer = item.get("indexer") or "Public Indexer"
                    raw_size = int(item.get("size") or 0)
                    title = item.get("title") or "Unnamed Torrent"

                    if "Pirate" in indexer:
                        continue
                    if raw_size in (1500000000, 1400000000, 1503238553) or (raw_size > 0 and abs(raw_size - 1500000000) < 10000000):
                        ext_bytes, ext_fmt = self.extract_size_from_title(title)
                        if ext_bytes > 0:
                            raw_size = ext_bytes
                            formatted_sz = ext_fmt
                        else:
                            continue
                    else:
                        formatted_sz = self.format_bytes(raw_size) if raw_size > 0 else "--"

                    magnet = item.get("download_url") or item.get("magnet") or item.get("link") or ""
                    if not magnet or not (magnet.startswith("magnet:") or magnet.startswith("http")):
                        continue

                    seeds = item.get("seeders")
                    seeds = int(seeds) if (seeds is not None and str(seeds).isdigit()) else 0
                    peers = item.get("leechers")
                    peers = int(peers) if (peers is not None and str(peers).isdigit()) else 0

                    results.append({
                        "title": title,
                        "size_bytes": raw_size,
                        "size_formatted": formatted_sz,
                        "seeds": seeds,
                        "peers": peers,
                        "indexer": indexer,
                        "category": item.get("category_name") or "General",
                        "magnet": magnet,
                        "guid": item.get("guid") or "",
                        "publish_date": item.get("publish_date") or ""
                    })
        except Exception as e:
            print(f"[TorrentSearchClient] Torznab search error: {e}")

        return results

    # =========================================================================
    # Aggregated Parallel Search Engine
    # =========================================================================
    def search_torrents(self, query: str, limit: int = 100, source: str = "all") -> List[Dict[str, Any]]:
        """
        Executes parallel searches across all available providers (AniRena, The Pirate Bay, Nyaa.si, Multi-Mirror),
        deduplicates releases, sorts by seeders, and delivers verified real file sizes.
        """
        clean_q = (query or "").strip()
        if not clean_q:
            return []

        all_results = []
        source_key = (source or "all").lower()

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_src = {}

            if source_key in ("all", "anirena"):
                future_to_src[executor.submit(self.search_anirena, clean_q, limit)] = "AniRena"

            if source_key in ("all", "the pirate bay", "pirate bay", "tpb"):
                future_to_src[executor.submit(self.search_apibay, clean_q, limit)] = "The Pirate Bay"

            if source_key in ("all", "nyaa", "nyaa.si", "anime"):
                future_to_src[executor.submit(self.search_nyaa, clean_q, limit)] = "Nyaa.si"

            if source_key in ("all", "multi-tracker", "torznab"):
                future_to_src[executor.submit(self.search_torznab_mirror, clean_q, limit)] = "Multi-Tracker"

            for future in as_completed(future_to_src):
                src_name = future_to_src[future]
                try:
                    res = future.result()
                    if res:
                        all_results.extend(res)
                except Exception as e:
                    print(f"[TorrentSearchClient] Provider {src_name} failed: {e}")

        # Deduplicate results by title or guid
        seen = set()
        clean_unique = []
        for r in all_results:
            key = (r.get("guid") or r.get("title", "")).lower().strip()
            if key in seen:
                continue
            seen.add(key)
            clean_unique.append(r)

        # Sort by seeders descending
        clean_unique.sort(key=lambda x: x.get("seeds", 0), reverse=True)
        return clean_unique[:limit]

    def fetch_to_cloud(self, magnet_or_url: str, auth_token: str) -> Dict[str, Any]:
        """
        Offloads torrent / magnet link to cloud seedbox.
        The VPS downloads and seeds with high datacenter speeds.
        """
        if not self.base_url:
            return {"success": False, "error": "Gateway URL not configured"}
        fetch_url = f"{self.base_url}/api/debrid/fetch"
        payload = json.dumps({
            "link": magnet_or_url,
            "server": "auto",
            "simulationMode": "seeding_only"
        }).encode("utf-8")

        req = urllib.request.Request(fetch_url, data=payload, headers=self._get_headers(auth_token))
        try:
            with urllib.request.urlopen(req, context=self._ctx, timeout=15) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_public_trackers_string() -> str:
        """Returns comma-separated high tier tracker URLs for aria2c injection."""
        try:
            from .tracker_manager import TrackerManager
            return TrackerManager.get_instance().get_trackers_string()
        except Exception:
            return ",".join(TIER1_PUBLIC_TRACKERS)
