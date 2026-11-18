"""
Zero Download Assistant - PikPak Public Share Link Resolver
Extracts direct CDN download streams and file hierarchies from public PikPak
shares (mypikpak.com / mypikpak.net) without requiring account authentication.
Uses reverse-engineered client signature verification (captcha_sign) and
public share traversal endpoints.
"""

import re
import time
import json
import uuid
import hashlib
import urllib.request
import urllib.parse
from typing import Optional, List, Dict, Tuple

DEFAULT_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

WEB_CLIENT_ID = "YUMx5nI8ZU8Ap8pm"
WEB_CLIENT_VERSION = "2.0.0"
WEB_PACKAGE_NAME = "mypikpak.com"

WEB_ALGORITHMS = [
    "C9qPpZLN8ucRTaTiUMWYS9cQvWOE",
    "+r6CQVxjzJV6LCV",
    "F",
    "pFJRC",
    "9WXYIDGrwTCz2OiVlgZa90qpECPD6olt",
    "/750aCr4lm/Sly/c",
    "RB+DT/gZCrbV",
    "",
    "CyLsf7hdkIRxRm215hl",
    "7xHvLi2tOYP0Y92b",
    "ZGTXXxu8E/MIWaEDB+Sm/",
    "1UI3",
    "E7fP5Pfijd+7K+t6Tg/NhuLq0eEUVChpJSkrKxpO",
    "ihtqpG6FMt65+Xk+tWUH2",
    "NhXXU9rg4XXdzo7u5o",
]

USER_HOSTS = ["user.mypikpak.net", "user.mypikpak.com"]
API_DRIVE_HOSTS = ["api-drive.mypikpak.net", "api-drive.mypikpak.com"]


class PikPakResolver:
    _device_id: Optional[str] = None
    _cached_captcha_token: Optional[str] = None
    _captcha_expiry: float = 0.0

    @classmethod
    def get_device_id(cls) -> str:
        if not cls._device_id:
            cls._device_id = uuid.uuid4().hex
        return cls._device_id

    @staticmethod
    def is_pikpak_url(url: str) -> bool:
        if not url:
            return False
        clean = url.strip().lower()
        return bool(
            re.search(r'https?://(?:www\.)?mypikpak\.(?:com|net|org)/(?:s/|drive/url/)', clean) or
            ("mypikpak." in clean and ("share_id=" in clean or "/s/" in clean)) or
            re.search(r'https?://(?:api-drive\.)?mypikpak\.(?:com|net)/drive/v1/share', clean)
        )

    @staticmethod
    def parse_share_url(raw_url: str) -> Tuple[str, str, str]:
        """
        Extracts (share_id, parent_id, pass_code) from a PikPak share URL.
        Example: https://mypikpak.com/s/VOX123_456/parentFolder?pwd=1234
        """
        clean = raw_url.strip()
        parsed = urllib.parse.urlparse(clean)
        qs = urllib.parse.parse_qs(parsed.query)

        pass_code = ""
        for key in ["pwd", "pass_code", "password", "code"]:
            if key in qs and qs[key]:
                pass_code = qs[key][0].strip()
                break

        # Check path patterns: /s/{share_id}/{parent_id}
        path_parts = [p for p in parsed.path.split("/") if p]
        share_id = ""
        parent_id = ""

        if "s" in path_parts:
            s_idx = path_parts.index("s")
            if len(path_parts) > s_idx + 1:
                share_id = path_parts[s_idx + 1]
            if len(path_parts) > s_idx + 2:
                parent_id = path_parts[s_idx + 2]
        elif "drive" in path_parts and "url" in path_parts:
            u_idx = path_parts.index("url")
            if len(path_parts) > u_idx + 1:
                share_id = path_parts[u_idx + 1]
        elif "share_id" in qs and qs["share_id"]:
            share_id = qs["share_id"][0]

        return share_id, parent_id, pass_code

    @classmethod
    def _compute_captcha_sign(cls, device_id: str, ts: str) -> str:
        s = WEB_CLIENT_ID + WEB_CLIENT_VERSION + WEB_PACKAGE_NAME + device_id + ts
        for alg in WEB_ALGORITHMS:
            s = hashlib.md5((s + alg).encode("utf-8")).hexdigest()
        return "1." + s

    @classmethod
    def get_captcha_token(cls, action: str = "GET:/drive/v1/share/detail", force_refresh: bool = False) -> str:
        """
        Fetches an anonymous captcha_token using the reverse-engineered
        handshake with user.mypikpak.net/com.
        """
        now = time.time()
        if not force_refresh and cls._cached_captcha_token and now < cls._captcha_expiry:
            return cls._cached_captcha_token

        device_id = cls.get_device_id()
        ts = str(int(now * 1000))
        sign = cls._compute_captcha_sign(device_id, ts)

        body = {
            "action": action,
            "captcha_token": "",
            "client_id": WEB_CLIENT_ID,
            "device_id": device_id,
            "meta": {
                "captcha_sign": sign,
                "client_version": WEB_CLIENT_VERSION,
                "package_name": WEB_PACKAGE_NAME,
                "timestamp": ts,
                "user_id": ""
            },
            "redirect_uri": "xlaccsdk01://xbase.cloud/callback?state=harbor"
        }
        req_data = json.dumps(body).encode("utf-8")
        headers = {
            "User-Agent": DEFAULT_DESKTOP_UA,
            "Content-Type": "application/json",
            "X-Client-ID": WEB_CLIENT_ID,
            "X-Device-ID": device_id,
        }

        last_err = None
        for host in USER_HOSTS:
            url = f"https://{host}/v1/shield/captcha/init?client_id={WEB_CLIENT_ID}"
            try:
                req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    token = data.get("captcha_token")
                    if token:
                        cls._cached_captcha_token = token
                        expires_in = int(data.get("expires_in") or 300)
                        cls._captcha_expiry = now + max(60, expires_in - 30)
                        return token
            except Exception as e:
                last_err = e

        if cls._cached_captcha_token:
            return cls._cached_captcha_token
        raise RuntimeError(f"Gagal menginisialisasi PikPak anonymous captcha token: {last_err}")

    @classmethod
    def _api_request(cls, endpoint: str, query: Optional[dict] = None, method: str = "GET") -> dict:
        device_id = cls.get_device_id()
        action = f"{method.upper()}:{endpoint}"
        captcha_token = cls.get_captcha_token(action=action)

        q_str = ""
        if query:
            filtered_q = {k: v for k, v in query.items() if v is not None and v != ""}
            if filtered_q:
                q_str = "?" + urllib.parse.urlencode(filtered_q)

        headers = {
            "User-Agent": DEFAULT_DESKTOP_UA,
            "Content-Type": "application/json",
            "X-Client-ID": WEB_CLIENT_ID,
            "X-Device-ID": device_id,
            "X-Captcha-Token": captcha_token,
        }

        last_err = None
        for host in API_DRIVE_HOSTS:
            full_url = f"https://{host}{endpoint}{q_str}"
            try:
                req = urllib.request.Request(full_url, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    err_code = resp_data.get("error_code")
                    if err_code == 9:
                        # Captcha expired -> refresh and retry once
                        captcha_token = cls.get_captcha_token(action=action, force_refresh=True)
                        headers["X-Captcha-Token"] = captcha_token
                        req2 = urllib.request.Request(full_url, headers=headers, method=method)
                        with urllib.request.urlopen(req2, timeout=15) as resp2:
                            return json.loads(resp2.read().decode("utf-8"))
                    return resp_data
            except Exception as e:
                last_err = e

        raise RuntimeError(f"PikPak API request failed ({endpoint}): {last_err}")

    @classmethod
    def get_share_info(cls, share_id: str, pass_code: str = "") -> dict:
        """Query share status and pass_code_token."""
        return cls._api_request("/drive/v1/share", {
            "share_id": share_id,
            "pass_code": pass_code,
            "thumbnail_size": "SIZE_LARGE",
            "limit": "100"
        })

    @classmethod
    def get_share_detail(cls, share_id: str, parent_id: str = "", pass_code_token: str = "", page_token: str = "") -> dict:
        """Fetch list of files in share or folder."""
        return cls._api_request("/drive/v1/share/detail", {
            "share_id": share_id,
            "parent_id": parent_id or "",
            "pass_code_token": pass_code_token or "",
            "thumbnail_size": "SIZE_LARGE",
            "with_audit": "true",
            "limit": "100",
            "page_token": page_token or "",
            "filters": '{"phase":{"eq":"PHASE_TYPE_COMPLETE"},"trashed":{"eq":false}}'
        })

    @classmethod
    def get_file_info(cls, share_id: str, file_id: str, pass_code_token: str = "") -> dict:
        """Fetch direct download link and stream media urls for a specific file in share."""
        return cls._api_request("/drive/v1/share/file_info", {
            "share_id": share_id,
            "file_id": file_id,
            "pass_code_token": pass_code_token or ""
        })

    @classmethod
    def resolve_public_share(cls, url: str, pass_code: str = "") -> List[Dict]:
        """
        Recursively resolves all downloadable files from a public PikPak share.
        Returns a list of dicts with:
          - name: filename
          - url: direct stream download url
          - size: bytes
          - path: relative folder path
          - headers: required headers (Referer, User-Agent)
        """
        share_id, initial_parent, url_pwd = cls.parse_share_url(url)
        if not share_id:
            raise ValueError(f"URL PikPak tidak valid atau share ID tidak ditemukan: {url}")

        pwd = pass_code or url_pwd or ""

        # 1. Check share status & get pass_code_token
        pass_code_token = ""
        share_meta = cls.get_share_info(share_id, pwd)
        status = share_meta.get("share_status", "")
        if status == "NOT_FOUND":
            raise ValueError("Tautan PikPak tidak ditemukan atau sudah dihapus (404 Not Found).")
        if status in ("PASS_CODE_EMPTY", "PASS_CODE_ERROR"):
            raise ValueError("Tautan PikPak dilindungi kata sandi. Silakan masukkan pass_code yang sesuai.")

        pass_code_token = share_meta.get("pass_code_token") or ""

        # 2. Recursively list all files
        raw_files = []
        def _list_recursive(p_id: str, path_prefix: str):
            page_token = ""
            while True:
                resp = cls.get_share_detail(share_id, parent_id=p_id, pass_code_token=pass_code_token, page_token=page_token)
                files = resp.get("files") or []
                sub_folders = []
                for f in files:
                    kind = f.get("kind", "")
                    if kind == "drive#folder":
                        sub_folders.append(f)
                    else:
                        raw_files.append({
                            "id": f.get("id"),
                            "name": f.get("name"),
                            "size": int(f.get("size") or 0),
                            "path": path_prefix,
                            "raw_file": f
                        })
                for folder in sub_folders:
                    folder_name = folder.get("name", "folder")
                    sub_path = f"{path_prefix}/{folder_name}" if path_prefix else folder_name
                    _list_recursive(folder.get("id"), sub_path)

                page_token = resp.get("next_page_token") or ""
                if not page_token:
                    break

        _list_recursive(initial_parent, "")

        if not raw_files:
            raise ValueError("Tidak ada file yang dapat diunduh di dalam tautan berbagi PikPak ini.")

        # 3. Resolve direct download URLs for each file
        resolved_items = []
        for item in raw_files:
            f_id = item["id"]
            direct_url = ""
            try:
                info_resp = cls.get_file_info(share_id, f_id, pass_code_token)
                fi = info_resp.get("file_info") or info_resp
                # Priority 1: web_content_link
                direct = fi.get("web_content_link") or ""
                if direct:
                    direct_url = direct
                else:
                    # Priority 2: medias (original quality video stream)
                    medias = fi.get("medias") or []
                    if medias and isinstance(medias, list):
                        for m in medias:
                            l = m.get("link") or {}
                            u = l.get("url")
                            if u:
                                direct_url = u
                                break
            except Exception as e:
                print(f"[PikPakResolver] Gagal mengambil file_info untuk {item['name']}: {e}")

            if direct_url:
                resolved_items.append({
                    "name": item["name"],
                    "url": direct_url,
                    "size": item["size"],
                    "path": item["path"],
                    "headers": {
                        "User-Agent": DEFAULT_DESKTOP_UA,
                        "Referer": "https://mypikpak.com/"
                    }
                })

        return resolved_items

    @classmethod
    def resolve_single_or_first(cls, url: str, pass_code: str = "") -> Optional[Dict]:
        """Convenience method returning the first or primary file for single-download mode."""
        items = cls.resolve_public_share(url, pass_code=pass_code)
        if items:
            return items[0]
        return None
