"""
Zero Download Assistant v2.8 - Site Grabber & Recursive Web Crawler Engine
Features:
- Multi-threaded recursive web crawling with depth control
- Domain and sub-domain boundary filtering
- Automatic media & file sniffing (Images, Audio, Video, Documents, Archives, Custom)
- Asynchronous HEAD/Range size probing
- Pause, cancel, and live telemetry callbacks
"""

import os
import queue
import threading
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from typing import Dict, List, Set, Optional, Callable
from dataclasses import dataclass
from ..utils.helpers import format_bytes, get_category_from_filename, sanitize_filename


@dataclass
class GrabbedItem:
    url: str
    filename: str
    filesize: int = -1
    category: str = "General"
    mime_type: str = ""
    source_page: str = ""
    checked: bool = True
    status: str = "Found"

    @property
    def filesize_formatted(self) -> str:
        if self.filesize > 0:
            return format_bytes(self.filesize)
        return "Unknown size"


class LinkExtractor(HTMLParser):
    """Fast HTML link and media parser for crawler."""
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.page_links: Set[str] = set()
        self.media_links: Set[str] = set()

    def handle_starttag(self, tag, attrs):
        attr_dict = {k.lower(): v for k, v in attrs if v}
        
        # 1. Hyperlinks
        if tag in ["a", "area"] and "href" in attr_dict:
            href = attr_dict["href"].strip()
            if href and not href.startswith(("javascript:", "mailto:", "tel:", "#")):
                full = urllib.parse.urljoin(self.base_url, href)
                self.page_links.add(full)
                self.media_links.add(full)

        # 2. Images
        elif tag in ["img", "image"] and "src" in attr_dict:
            src = attr_dict["src"].strip()
            if src and not src.startswith("data:"):
                self.media_links.add(urllib.parse.urljoin(self.base_url, src))
        elif tag == "img" and "data-src" in attr_dict:
            self.media_links.add(urllib.parse.urljoin(self.base_url, attr_dict["data-src"]))

        # 3. Video / Audio / Media sources
        elif tag in ["video", "audio", "source", "track"] and "src" in attr_dict:
            self.media_links.add(urllib.parse.urljoin(self.base_url, attr_dict["src"]))

        # 4. Embedded / Object links
        elif tag in ["embed", "object"] and "data" in attr_dict:
            self.media_links.add(urllib.parse.urljoin(self.base_url, attr_dict["data"]))


class SiteCrawler(threading.Thread):
    """
    Asynchronous recursive site crawler and media grabber.
    """
    CATEGORY_EXTENSIONS = {
        "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico", ".tiff", ".avif"},
        "Videos": {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts", ".m3u8", ".mpd"},
        "Audio": {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"},
        "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub", ".mobi", ".csv"},
        "Compressed": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".dmg"},
        "Programs": {".exe", ".msi", ".apk", ".bat", ".cmd", ".ps1", ".jar"}
    }

    def __init__(
        self,
        start_url: str,
        max_depth: int = 1,
        stay_on_domain: bool = True,
        categories: Optional[List[str]] = None,
        custom_extensions: Optional[List[str]] = None,
        max_pages: int = 100,
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        on_item_found: Optional[Callable[[GrabbedItem], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_finished: Optional[Callable[[List[GrabbedItem]], None]] = None
    ):
        super().__init__(daemon=True)
        self.start_url = start_url.strip()
        self.max_depth = max_depth
        self.stay_on_domain = stay_on_domain
        self.categories = set(categories) if categories else set(self.CATEGORY_EXTENSIONS.keys())
        self.custom_extensions = set(e.lower() if e.startswith(".") else f".{e.lower()}" for e in (custom_extensions or []))
        self.max_pages = max_pages
        self.headers = headers or {}
        self.proxy = proxy

        self.on_item_found = on_item_found
        self.on_progress = on_progress
        self.on_finished = on_finished

        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()

        parsed = urllib.parse.urlparse(self.start_url)
        self.base_domain = parsed.netloc.lower()

        self.visited_urls: Set[str] = set()
        self.found_items: Dict[str, GrabbedItem] = {}
        self.scanned_pages = 0

    def stop(self):
        self.cancel_event.set()
        self.pause_event.set()

    def _get_opener(self):
        handlers = []
        if self.proxy:
            handlers.append(urllib.request.ProxyHandler({'http': self.proxy, 'https': self.proxy}))
        return urllib.request.build_opener(*handlers)

    def _matches_filters(self, url: str) -> tuple[bool, str]:
        path = urllib.parse.urlparse(url).path.lower()
        _, ext = os.path.splitext(path)
        
        if self.custom_extensions and ext in self.custom_extensions:
            return True, get_category_from_filename(path)

        for cat_name, ext_set in self.CATEGORY_EXTENSIONS.items():
            if cat_name in self.categories and ext in ext_set:
                return True, cat_name

        return False, "General"

    def _extract_filename(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        fn = os.path.basename(path)
        if not fn or fn == "/":
            fn = "index.html"
        try:
            fn = urllib.parse.unquote(fn)
        except Exception:
            pass
        return sanitize_filename(fn)

    def _probe_size_async(self, item: GrabbedItem, opener):
        try:
            req = urllib.request.Request(
                item.url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0", "Range": "bytes=0-0"}
            )
            with opener.open(req, timeout=10) as resp:
                cr = resp.headers.get("Content-Range")
                if cr and "/" in cr:
                    total_str = cr.split("/")[-1].strip()
                    if total_str.isdigit():
                        item.filesize = int(total_str)
                elif resp.headers.get("Content-Length"):
                    cl = resp.headers.get("Content-Length").strip()
                    if cl.isdigit():
                        item.filesize = int(cl)
                
                ct = resp.headers.get("Content-Type", "")
                if ct:
                    item.mime_type = ct.split(";")[0].strip()
        except Exception:
            pass

    def run(self):
        opener = self._get_opener()
        crawl_queue = queue.Queue()
        crawl_queue.put((self.start_url, 1))
        self.visited_urls.add(self.start_url)

        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        req_headers.update(self.headers)

        while not crawl_queue.empty() and not self.cancel_event.is_set():
            if not self.pause_event.is_set():
                self.pause_event.wait()
                if self.cancel_event.is_set():
                    break

            if self.scanned_pages >= self.max_pages:
                break

            current_url, depth = crawl_queue.get()
            self.scanned_pages += 1

            if self.on_progress:
                self.on_progress(self.scanned_pages, len(self.found_items))

            try:
                req = urllib.request.Request(current_url, headers=req_headers)
                with opener.open(req, timeout=15) as resp:
                    c_type = resp.headers.get("Content-Type", "").lower()
                    
                    matches, cat = self._matches_filters(current_url)
                    if matches and current_url not in self.found_items:
                        item = GrabbedItem(
                            url=current_url,
                            filename=self._extract_filename(current_url),
                            category=cat,
                            source_page=current_url
                        )
                        cl = resp.headers.get("Content-Length")
                        if cl and cl.isdigit():
                            item.filesize = int(cl)
                        self.found_items[current_url] = item
                        if self.on_item_found:
                            self.on_item_found(item)

                    if "text/html" not in c_type and "xhtml" not in c_type:
                        continue

                    html_bytes = resp.read(2 * 1024 * 1024)
                    try:
                        html_text = html_bytes.decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
                    except Exception:
                        html_text = html_bytes.decode("utf-8", errors="replace")

                    parser = LinkExtractor(current_url)
                    try:
                        parser.feed(html_text)
                    except Exception:
                        pass

                    for media_url in parser.media_links:
                        if self.cancel_event.is_set():
                            break
                        
                        m_ok, m_cat = self._matches_filters(media_url)
                        if m_ok and media_url not in self.found_items:
                            item = GrabbedItem(
                                url=media_url,
                                filename=self._extract_filename(media_url),
                                category=m_cat,
                                source_page=current_url
                            )
                            self.found_items[media_url] = item
                            
                            threading.Thread(target=self._probe_size_async, args=(item, opener), daemon=True).start()

                            if self.on_item_found:
                                self.on_item_found(item)

                    if depth < self.max_depth:
                        for page_url in parser.page_links:
                            if page_url in self.visited_urls:
                                continue

                            p_domain = urllib.parse.urlparse(page_url).netloc.lower()
                            if self.stay_on_domain and p_domain != self.base_domain and not p_domain.endswith("." + self.base_domain):
                                continue

                            is_media, _ = self._matches_filters(page_url)
                            if not is_media:
                                self.visited_urls.add(page_url)
                                crawl_queue.put((page_url, depth + 1))

            except Exception:
                pass

        if self.on_finished:
            self.on_finished(list(self.found_items.values()))