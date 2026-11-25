import os
import sys
import re
import time
import shutil
import threading
import subprocess
import urllib.parse
import binascii
import hashlib
from typing import Optional, Callable, Any
from .torrent_search_client import TorrentSearchClient


def _bdecode_with_span(data: bytes, idx: int = 0):
    if idx >= len(data):
        raise ValueError("Unexpected end of bencoded data")
    char = data[idx:idx + 1]
    if char == b"i":
        end = data.index(b"e", idx)
        val = int(data[idx + 1:end])
        return val, end + 1
    elif char.isdigit():
        colon = data.index(b":", idx)
        length = int(data[idx:colon])
        start = colon + 1
        end = start + length
        val = data[start:end]
        return val, end
    elif char == b"l":
        idx += 1
        res = []
        while idx < len(data) and data[idx:idx + 1] != b"e":
            item, idx = _bdecode_with_span(data, idx)
            res.append(item)
        return res, idx + 1
    elif char == b"d":
        idx += 1
        res = {}
        while idx < len(data) and data[idx:idx + 1] != b"e":
            k, idx = _bdecode_with_span(data, idx)
            v, idx = _bdecode_with_span(data, idx)
            if isinstance(k, bytes):
                k = k.decode("utf-8", errors="replace")
            res[k] = v
        return res, idx + 1
    else:
        raise ValueError(f"Invalid bencode character {char} at {idx}")


def bdecode(data: bytes) -> Any:
    """Pure Python lightweight bencode decoder."""
    val, _ = _bdecode_with_span(data, 0)
    return val


def parse_torrent_or_magnet(source: str) -> dict:
    """
    Extracts info_hash (20 bytes hex), name, announce URLs, and total size
    from a magnet link, a local .torrent file, or a raw info-hash.
    """
    info = {
        "info_hash": "",
        "name": "BitTorrent Swarm",
        "announces": [],
        "total_size": 1024 * 1024 * 1024
    }
    if not source:
        return info

    clean_source = source.strip()

    if clean_source.startswith("magnet:"):
        parsed = urllib.parse.urlparse(clean_source)
        params = urllib.parse.parse_qs(parsed.query)

        xt_list = params.get("xt", [])
        for xt in xt_list:
            if xt.startswith("urn:btih:"):
                raw_hash = xt[len("urn:btih:"):].strip()
                if len(raw_hash) == 40:
                    info["info_hash"] = raw_hash.lower()
                elif len(raw_hash) == 32:
                    try:
                        import base64
                        decoded = base64.b32decode(raw_hash.upper())
                        info["info_hash"] = binascii.hexlify(decoded).decode("ascii").lower()
                    except Exception:
                        info["info_hash"] = raw_hash.lower()

        dn_list = params.get("dn", [])
        if dn_list:
            info["name"] = urllib.parse.unquote(dn_list[0])

        xl_list = params.get("xl", [])
        if xl_list:
            try:
                xl_val = int(xl_list[0])
                if xl_val > 0:
                    info["total_size"] = xl_val
            except Exception:
                pass

        tr_list = params.get("tr", [])
        for tr in tr_list:
            clean_tr = urllib.parse.unquote(tr).strip()
            if clean_tr and clean_tr not in info["announces"]:
                info["announces"].append(clean_tr)

    elif os.path.exists(clean_source) and os.path.isfile(clean_source):
        try:
            with open(clean_source, "rb") as f:
                content = f.read()
            decoded = bdecode(content)
            if isinstance(decoded, dict):
                info_dict = decoded.get("info")
                if info_dict:
                    info_marker = content.find(b"4:info")
                    if info_marker != -1:
                        info_start = info_marker + 6
                        try:
                            _, info_end = _bdecode_with_span(content, info_start)
                            info["info_hash"] = hashlib.sha1(content[info_start:info_end]).hexdigest().lower()
                        except Exception:
                            pass
                    if not info["info_hash"]:
                        info["info_hash"] = hashlib.sha1(content).hexdigest().lower()

                    if "name" in info_dict:
                        n = info_dict["name"]
                        info["name"] = n.decode("utf-8", errors="ignore") if isinstance(n, bytes) else str(n)

                    if "length" in info_dict:
                        info["total_size"] = int(info_dict["length"])
                    elif "files" in info_dict:
                        info["total_size"] = sum(int(file_info.get("length", 0)) for file_info in info_dict["files"])

                if "announce" in decoded:
                    ann = decoded["announce"]
                    ann_str = ann.decode("utf-8", errors="ignore") if isinstance(ann, bytes) else str(ann)
                    if ann_str and ann_str not in info["announces"]:
                        info["announces"].append(ann_str)

                if "announce-list" in decoded:
                    for tier in decoded["announce-list"]:
                        for t in tier:
                            t_str = t.decode("utf-8", errors="ignore") if isinstance(t, bytes) else str(t)
                            if t_str and t_str not in info["announces"]:
                                info["announces"].append(t_str)
        except Exception as e:
            print(f"[parse_torrent_or_magnet] Error parsing torrent: {e}")

    else:
        if re.fullmatch(r"[0-9a-fA-F]{40}", clean_source):
            info["info_hash"] = clean_source.lower()
            info["name"] = f"Torrent [{clean_source[:8].upper()}]"
        elif re.fullmatch(r"[A-Za-z2-7]{32}", clean_source):
            try:
                import base64
                decoded = base64.b32decode(clean_source.upper())
                info["info_hash"] = binascii.hexlify(decoded).decode("ascii").lower()
                info["name"] = f"Torrent [{info['info_hash'][:8].upper()}]"
            except Exception:
                pass

    if not info["info_hash"]:
        info["info_hash"] = hashlib.sha1(clean_source.encode("utf-8", errors="ignore")).hexdigest().lower()

    return info


ARIA2_ERROR_MESSAGES = {
    1: "Terjadi kesalahan internal pada proses BitTorrent (Unknown error).",
    2: "Waktu koneksi habis (Connection timed out).",
    3: "Resource atau tracker torrent tidak ditemukan (Not found).",
    4: "Tracker tidak merespon setelah beberapa kali percobaan.",
    5: "Download dibatalkan karena kecepatan unduh terlalu lambat.",
    6: "Masalah koneksi jaringan saat mengunduh torrent.",
    7: "Unduhan torrent belum selesai atau terputus.",
    8: "Tracker/Server tidak mendukung resume unduhan.",
    9: "Ruang penyimpanan disk tidak mencukupi untuk menyimpan file torrent.",
    10: "Inkonsistensi piece torrent pada control file.",
    11: "Torrent dengan hash yang sama sedang berjalan.",
    12: "Magnet torrent dengan hash yang sama sudah ada di antrean.",
    13: "File tujuan sudah ada dan tidak dapat ditimpa.",
    14: "Gagal mengganti nama file tujuan torrent.",
    15: "Tidak dapat membuka file torrent yang ada di disk.",
    16: "Gagal membuat atau menulis file torrent di disk tujuan.",
    17: "Terjadi kesalahan I/O disk saat mengunduh file.",
    18: "Gagal membuat direktori folder tujuan unduhan.",
    19: "Gagal menyelesaikan nama domain tracker (DNS resolution failed).",
    22: "Respon tracker tidak valid atau server tracker bermasalah.",
    24: "Autentikasi HTTP tracker gagal.",
    25: "File .torrent tidak dapat dibaca atau rusak (Invalid bencode).",
    26: "File .torrent korup atau informasi metadata tidak lengkap.",
    27: "Format tautan Magnet URI tidak valid.",
    28: "Konfigurasi argumen engine unduhan tidak dikenali (Invalid engine option).",
    29: "Server tracker menolak permintaan unduhan (Server unavailable).",
    32: "Verifikasi checksum hash piece torrent gagal (Checksum mismatch).",
}


class TorrentWorker(threading.Thread):
    """
    High-Performance, Zero-Crash BitTorrent & Magnet Engine for Zero Download Assistant.
    Powered by bundled aria2c standalone binary (v1.37.0).
    
    Features:
    - 100% stable: no native Python C-extension crashes or memory access violations.
    - Native Magnet link resolution & .torrent file parsing.
    - Full DHT, Peer Exchange (PeX), Local Peer Discovery (LSD), UDP/HTTP Trackers.
    - Live real-time telemetry: Downloaded bytes, Total size, DL/UL speed, Seeds, Peers, ETA.
    - Full Pause, Resume, and Cancellation lifecycle control.
    - Multi-file directory hierarchy creation.
    """
    @staticmethod
    def get_aria2_path() -> Optional[str]:
        search_dirs = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "bin")),
            os.path.abspath(os.path.join(os.path.dirname(sys.executable), "app", "assets", "bin")),
            os.path.abspath(os.path.join(os.path.dirname(sys.executable), "_internal", "app", "assets", "bin")),
            os.path.abspath(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Krolix Download Manager", "app", "assets", "bin")),
            os.path.abspath(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Krolix Download Manager", "_internal", "app", "assets", "bin")),
            os.path.dirname(os.path.abspath(sys.executable)),
        ]
        if hasattr(sys, "_MEIPASS"):
            search_dirs.insert(0, os.path.join(sys._MEIPASS, "app", "assets", "bin"))
            search_dirs.insert(0, sys._MEIPASS)

        exe_name = "aria2c.exe" if sys.platform == "win32" else "aria2c"
        for d in search_dirs:
            p = os.path.join(d, exe_name)
            if os.path.exists(p) and os.path.isfile(p):
                return p

        # Fallback to system PATH
        sh_path = shutil.which("aria2c")
        if sh_path:
            return sh_path
        return None

    @staticmethod
    def _parse_torrent_bencode(filepath: str) -> dict:
        """
        Directly parse a local .torrent file using bencode to extract exact
        name, total size, and file list instantaneously without spawning subprocesses.
        """
        with open(filepath, "rb") as f:
            src = f.read()

        pos = 0

        def decode():
            nonlocal pos
            char = src[pos:pos + 1]
            if char == b"i":
                pos += 1
                end = src.index(b"e", pos)
                val = int(src[pos:end])
                pos = end + 1
                return val
            elif char == b"l":
                pos += 1
                res = []
                while src[pos:pos + 1] != b"e":
                    res.append(decode())
                pos += 1
                return res
            elif char == b"d":
                pos += 1
                res = {}
                while src[pos:pos + 1] != b"e":
                    k = decode()
                    v = decode()
                    if isinstance(k, bytes):
                        k = k.decode("utf-8", errors="replace")
                    res[k] = v
                pos += 1
                return res
            elif char.isdigit():
                colon = src.index(b":", pos)
                length = int(src[pos:colon])
                pos = colon + 1
                val = src[pos:pos + length]
                pos += length
                return val
            else:
                raise ValueError(f"Unexpected byte {char} at {pos}")

        meta = decode()
        info = meta.get("info", {})

        def to_str(b_val):
            if isinstance(b_val, bytes):
                return b_val.decode("utf-8", errors="replace")
            return str(b_val)

        name = to_str(info.get("name.utf-8") or info.get("name") or "torrent_download")
        files = []
        total_bytes = 0

        if "files" in info and isinstance(info["files"], list):
            for idx, item in enumerate(info["files"], start=1):
                fsize = int(item.get("length", 0))
                total_bytes += fsize
                raw_path = item.get("path.utf-8") or item.get("path") or []
                parts = [to_str(p) for p in raw_path if p]
                rel_path = "/".join([name] + parts) if parts else name
                fname = parts[-1] if parts else name
                ext = os.path.splitext(fname)[1].lower().lstrip(".")
                files.append({
                    "index": idx,
                    "name": fname,
                    "size": fsize,
                    "path": rel_path,
                    "ext": ext
                })
        else:
            total_bytes = int(info.get("length", 0))
            ext = os.path.splitext(name)[1].lower().lstrip(".")
            files.append({
                "index": 1,
                "name": name,
                "size": total_bytes,
                "path": name,
                "ext": ext
            })

        is_private = bool(info.get("private") == 1 or meta.get("private") == 1)
        ann = to_str(meta.get("announce") or "")
        ann_list = meta.get("announce-list") or []
        all_announces = [ann]
        if isinstance(ann_list, list):
            for tier in ann_list:
                if isinstance(tier, list):
                    all_announces.extend(to_str(x) for x in tier)
                else:
                    all_announces.append(to_str(tier))

        private_indicators = [
            "passkey", "authkey", "torrentpass", "/announce.php",
            "avistaz", "passthepopcorn", "beyond-hd", "redacted", "gazelle",
            "privatetracker", "iptorrents", "torrentleech", "filelist", "hdbits",
            "karagarga", "cinematik", "broadcasthenet", "animebytes", "ggn",
            "empornium", "femdomcult", "myspleen", "secret-cinema"
        ]
        for a_url in all_announces:
            a_lower = a_url.lower()
            if any(ind in a_lower for ind in private_indicators):
                is_private = True
                break

        return {
            "name": name,
            "total_bytes": total_bytes,
            "files": files,
            "is_private": is_private
        }

    @staticmethod
    def get_file_list(source: str) -> list:
        """
        Return list of files in a torrent/magnet without downloading.
        Each item: {index (1-based), name, size, path, ext}
        """
        # Instant native bencode parsing if source is a local .torrent file
        if os.path.isfile(source) and source.lower().endswith(".torrent"):
            try:
                parsed = TorrentWorker._parse_torrent_bencode(source)
                if parsed and parsed.get("files"):
                    return parsed["files"]
            except Exception:
                pass

        # Remote .torrent URL: download to temp file and parse with bencode
        if (source.startswith("http://") or source.startswith("https://")) and (".torrent" in source.lower()):
            try:
                import urllib.request, ssl, tempfile
                req = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"})
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
                    raw_b = resp.read()
                with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as tf:
                    tf.write(raw_b)
                    tmp_t_path = tf.name
                try:
                    parsed = TorrentWorker._parse_torrent_bencode(tmp_t_path)
                finally:
                    try:
                        os.remove(tmp_t_path)
                    except Exception:
                        pass
                if parsed and parsed.get("files"):
                    return parsed["files"]
            except Exception as e:
                print(f"[TorrentWorker] Error parsing remote torrent file list: {e}")

        aria2_bin = TorrentWorker.get_aria2_path()
        if not aria2_bin:
            return []

        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="zero_filelist_")
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0

            result = subprocess.run(
                [aria2_bin, "--show-files", "--follow-torrent=mem", f"--dir={tmp_dir}", source],
                capture_output=True, text=True, timeout=20,
                creationflags=creationflags, startupinfo=startupinfo,
                encoding="utf-8", errors="ignore"
            )
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            files = []

            # Parse aria2c --show-files standard 2-line format:
            #   1|./path/to/file.mkv
            #    |1.2GiB (1,234,567,890)
            pattern = re.compile(
                r"^\s*(\d+)\|([^\n\r]+)[\r\n]+\s*\|(?:[^(]*\(([\d,]+)\)|([^\n\r]+))",
                re.MULTILINE
            )
            for m in pattern.finditer(output):
                try:
                    idx = int(m.group(1))
                    fpath = m.group(2).strip()
                    if m.group(3):
                        fsize = int(m.group(3).replace(",", ""))
                    else:
                        fsize = TorrentWorker._parse_size_bytes((m.group(4) or "0").strip())
                    fname = os.path.basename(fpath.replace("\\", "/")) or fpath
                    ext = os.path.splitext(fname)[1].lower().lstrip(".")
                    files.append({
                        "index": idx,
                        "name": fname,
                        "size": fsize,
                        "path": fpath,
                        "ext": ext
                    })
                except Exception:
                    continue

            # Fallback single-line format: "idx|path|size"
            if not files:
                for line in output.splitlines():
                    line = line.strip()
                    if "|" in line:
                        parts = line.split("|")
                        if len(parts) >= 3:
                            try:
                                idx = int(parts[0].strip())
                                fpath = parts[1].strip()
                                try:
                                    fsize = int(parts[2].strip().replace(",", ""))
                                except Exception:
                                    fsize = TorrentWorker._parse_size_bytes(parts[2].strip())
                                fname = os.path.basename(fpath.replace("\\", "/")) or fpath
                                ext = os.path.splitext(fname)[1].lower().lstrip(".")
                                files.append({
                                    "index": idx,
                                    "name": fname,
                                    "size": fsize,
                                    "path": fpath,
                                    "ext": ext
                                })
                            except (ValueError, IndexError):
                                continue
            return files
        except Exception:
            return []
        finally:
            try:
                import shutil as _shutil
                _shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    @classmethod
    def _resolve_remote_torrent(cls, source: str, save_dir: str = "", headers: Optional[dict] = None) -> tuple:
        """
        Intelligently resolves a remote .torrent URL into a valid local file:
        1. Checks if already present in save_dir, ~/Downloads, or subdirectories.
        2. Tries downloading with curl_cffi (impersonating Chrome) and full headers.
        3. Tries downloading with urllib.request with origin referer.
        4. If 403 occurs (Cloudflare challenge), performs fuzzy filename search in ~/Downloads.
        Returns: (local_file_path, error_message)
        """
        import urllib.parse, ssl, re, shutil
        if os.path.isfile(source):
            return source, None

        raw_unquoted = urllib.parse.unquote(source.split("?")[0].split("#")[0])
        raw_fn = os.path.basename(raw_unquoted) or "download.torrent"
        if not raw_fn.lower().endswith(".torrent"):
            raw_fn += ".torrent"

        # Candidate target cache directory
        effective_cache_dir = os.path.join(save_dir, ".torrents") if save_dir else os.path.join(os.path.expanduser("~"), ".zero_download", "torrents")
        os.makedirs(effective_cache_dir, exist_ok=True)
        target_torrent = os.path.join(effective_cache_dir, raw_fn)

        if os.path.isfile(target_torrent) and os.path.getsize(target_torrent) > 100:
            return target_torrent, None

        # 1. Check existing Downloads folder candidates
        dl_dirs = [
            save_dir,
            os.path.join(save_dir, ".torrents") if save_dir else "",
            os.path.expanduser("~/Downloads"),
            os.path.join(os.path.expanduser("~"), "Downloads", "Torrents"),
        ]
        for d in dl_dirs:
            if d and os.path.isdir(d):
                cand = os.path.join(d, raw_fn)
                if os.path.isfile(cand) and os.path.getsize(cand) > 100:
                    try:
                        shutil.copy2(cand, target_torrent)
                        return target_torrent, None
                    except Exception:
                        return cand, None

        # Fuzzy check in ~/Downloads
        dl_dir = os.path.expanduser("~/Downloads")
        if os.path.isdir(dl_dir):
            raw_clean = re.sub(r'[^a-zA-Z0-9]', '', raw_fn.lower())
            for f in os.listdir(dl_dir):
                if f.lower().endswith(".torrent"):
                    f_clean = re.sub(r'[^a-zA-Z0-9]', '', f.lower())
                    if (f_clean in raw_clean or raw_clean in f_clean) and len(f_clean) > 8:
                        cand = os.path.join(dl_dir, f)
                        if os.path.isfile(cand) and os.path.getsize(cand) > 100:
                            try:
                                shutil.copy2(cand, target_torrent)
                                return target_torrent, None
                            except Exception:
                                return cand, None

        # 2. Build full browser headers
        parsed_url = urllib.parse.urlsplit(source)
        origin_ref = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        hdrs = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": origin_ref,
            "Origin": f"{parsed_url.scheme}://{parsed_url.netloc}",
            "Accept": "application/x-bittorrent, application/octet-stream, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            for k, v in headers.items():
                if k.lower() in ("referer", "user-agent", "cookie", "authorization"):
                    hdrs[k] = str(v)

        # 3. Attempt downloading via curl_cffi (impersonating Chrome to bypass basic Cloudflare/bot shields)
        try:
            from curl_cffi import requests as c_req
            r = c_req.get(source, impersonate="chrome120", headers=hdrs, timeout=15)
            if r.status_code == 200 and len(r.content) > 100 and r.content[:1] == b'd':
                with open(target_torrent, "wb") as f:
                    f.write(r.content)
                return target_torrent, None
        except Exception:
            pass

        # 4. Attempt downloading via urllib.request
        try:
            import urllib.request
            req = urllib.request.Request(source, headers=hdrs)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                data = resp.read()
            if len(data) > 100 and data[:1] == b'd':
                with open(target_torrent, "wb") as f:
                    f.write(data)
                return target_torrent, None
        except Exception as e:
            # Check Downloads one more time before failing
            if os.path.isdir(dl_dir):
                for f in os.listdir(dl_dir):
                    if f.lower().endswith(".torrent"):
                        cand = os.path.join(dl_dir, f)
                        if os.path.isfile(cand) and os.path.getsize(cand) > 100:
                            try:
                                p_info = cls._parse_torrent_bencode(cand)
                                if p_info and p_info.get("name") and p_info["name"].lower() in source.lower():
                                    shutil.copy2(cand, target_torrent)
                                    return target_torrent, None
                            except Exception:
                                continue

            err_str = str(e)
            if "403" in err_str:
                return None, "Situs web memblokir unduhan langsung (HTTP 403 / Cloudflare). Silakan download file .torrent lewat browser terlebih dahulu, lalu buka file .torrent di Zero atau gunakan Magnet link."
            return None, f"Gagal mengunduh file .torrent dari URL: {e}"

        return None, "Gagal mengunduh file .torrent yang valid dari URL"

    @classmethod
    def get_torrent_info(cls, source: str, headers: Optional[dict] = None) -> dict:
        """
        Extract comprehensive metadata (name, total_bytes, files) from a .torrent or magnet link.
        """
        import urllib.parse
        name = "torrent_download"
        total_bytes = -1
        files = []

        # 1. Local .torrent file: try instant bencode parser first
        if os.path.isfile(source) and source.lower().endswith(".torrent"):
            try:
                parsed = cls._parse_torrent_bencode(source)
                if parsed:
                    return {
                        "name": parsed.get("name") or "torrent_download",
                        "total_bytes": parsed.get("total_bytes", -1) if parsed.get("total_bytes", 0) > 0 else -1,
                        "files": parsed.get("files", []),
                        "is_multi_file": len(parsed.get("files", [])) > 1,
                        "is_private": parsed.get("is_private", False)
                    }
            except Exception:
                pass

        # 1b. Remote .torrent URL: resolve and parse with bencode
        if (source.startswith("http://") or source.startswith("https://")) and (".torrent" in source.lower()):
            resolved_path, _ = cls._resolve_remote_torrent(source, "", headers)
            if resolved_path and os.path.exists(resolved_path):
                parsed = cls._parse_torrent_bencode(resolved_path)
                if parsed:
                    return {
                        "name": parsed.get("name") or "torrent_download",
                        "total_bytes": parsed.get("total_bytes", -1) if parsed.get("total_bytes", 0) > 0 else -1,
                        "files": parsed.get("files", []),
                        "is_multi_file": len(parsed.get("files", [])) > 1,
                        "is_private": parsed.get("is_private", False)
                    }

        # 2. Extract magnet query parameters (dn for name, xl for exact length)
        is_private_source = False
        if source.startswith("magnet:"):
            try:
                parsed_q = urllib.parse.parse_qs(urllib.parse.urlsplit(source).query)
                if "dn" in parsed_q and parsed_q["dn"]:
                    name = parsed_q["dn"][0]
                if "xl" in parsed_q and parsed_q["xl"]:
                    try:
                        xl_val = int(parsed_q["xl"][0])
                        if xl_val > 0:
                            total_bytes = xl_val
                    except Exception:
                        pass
                tr_list = parsed_q.get("tr", [])
                private_indicators = [
                    "passkey", "authkey", "torrentpass", "/announce.php",
                    "avistaz", "passthepopcorn", "beyond-hd", "redacted", "gazelle",
                    "privatetracker", "iptorrents", "torrentleech", "filelist", "hdbits",
                    "karagarga", "cinematik", "broadcasthenet", "animebytes", "ggn",
                    "empornium", "femdomcult", "myspleen", "secret-cinema"
                ]
                for tr_u in tr_list:
                    tr_lower = tr_u.lower()
                    if any(ind in tr_lower for ind in private_indicators):
                        is_private_source = True
                        break
            except Exception:
                pass
        else:
            base_f = os.path.basename(source)
            if base_f.lower().endswith(".torrent"):
                name = base_f[:-8]
            elif base_f:
                name = base_f

        # 3. Query file list via aria2c if not a pure magnet (or if file list available)
        if not source.startswith("magnet:"):
            files = cls.get_file_list(source)
            if files:
                calc_total = sum(f.get("size", 0) for f in files)
                if calc_total > 0:
                    total_bytes = calc_total
                if len(files) == 1:
                    name = files[0]["name"]
                elif len(files) > 1:
                    first_path = files[0].get("path", "").replace("\\", "/").lstrip("./")
                    if "/" in first_path:
                        top_dir = first_path.split("/")[0]
                        if top_dir:
                            name = top_dir

        return {
            "name": name,
            "total_bytes": total_bytes,
            "files": files,
            "is_multi_file": len(files) > 1,
            "is_private": is_private_source
        }

    get_torrent_metadata = get_torrent_info


    def __init__(
        self,
        source: str,
        save_dir: str,
        task_id: Optional[str] = None,
        pause_event: Optional[threading.Event] = None,
        cancel_event: Optional[threading.Event] = None,
        on_progress: Optional[Callable[[int, int, float, float, int, int, float], None]] = None,
        on_finished: Optional[Callable[[bool, Optional[str], Optional[str]], None]] = None,
        download_rate_limit: int = 0,
        upload_rate_limit: int = 0,
        selected_files: Optional[list] = None,
        seed_duration_days: int = 3,
        seed_ratio: float = 2.0,
        headers: Optional[dict] = None,
        **kwargs
    ):
        super().__init__(daemon=True)
        self.source = source
        self.save_dir = os.path.abspath(save_dir)
        self.task_id = task_id
        self.headers = dict(headers or {})
        self.pause_event = pause_event
        self.cancel_event = cancel_event
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.download_rate_limit = download_rate_limit
        self.upload_rate_limit = upload_rate_limit
        self.selected_files = selected_files  # list of 1-based int indices or None (all)
        self.seed_duration_days = max(0, min(31, int(seed_duration_days or 3)))
        self.seed_ratio = float(self.headers.get("seed_ratio", seed_ratio or 2.0))
        self._proc: Optional[subprocess.Popen] = None
        self._is_cancelled = False
        self._is_paused = False


    @staticmethod
    def _parse_size_bytes(size_str: str) -> int:
        if not size_str:
            return 0
        match = re.match(r"^([0-9\.]+)\s*([a-zA-Z]+)?$", size_str.strip())
        if not match:
            return 0
        val = float(match.group(1))
        unit = (match.group(2) or "B").upper()
        multipliers = {
            "B": 1,
            "K": 1024, "KB": 1024, "KIB": 1024,
            "M": 1024**2, "MB": 1024**2, "MIB": 1024**2,
            "G": 1024**3, "GB": 1024**3, "GIB": 1024**3,
            "T": 1024**4, "TB": 1024**4, "TIB": 1024**4,
        }
        return int(val * multipliers.get(unit, 1))

    @staticmethod
    def _parse_eta_seconds(eta_str: str) -> float:
        if not eta_str:
            return 0.0
        sec = 0.0
        h_m = re.search(r"(\d+)h", eta_str)
        m_m = re.search(r"(\d+)m", eta_str)
        s_m = re.search(r"(\d+)s", eta_str)
        if h_m:
            sec += int(h_m.group(1)) * 3600
        if m_m:
            sec += int(m_m.group(1)) * 60
        if s_m:
            sec += int(s_m.group(1))
        return sec

    def _send_tracker_stop(self, actual_source: str, peer_id: str, downloaded: int = 0):
        """Explicitly notify HTTP/HTTPS BitTorrent trackers that the download is stopped to prevent ghost peer locks."""
        try:
            meta = parse_torrent_or_magnet(actual_source)
            if not meta or not meta.get("announces") or not meta.get("info_hash"):
                return
            import binascii
            import urllib.request
            import urllib.parse
            import ssl
            info_hash_bytes = binascii.unhexlify(meta["info_hash"])
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            headers = {"User-Agent": "qBittorrent/4.6.5", "Connection": "close"}
            
            for ann_url in meta["announces"]:
                if not (ann_url.startswith("http://") or ann_url.startswith("https://")):
                    continue
                for port in [6881, 6882, 6883, 6884, 6885]:
                    params = {
                        "info_hash": info_hash_bytes,
                        "peer_id": peer_id.encode("utf-8"),
                        "port": port,
                        "uploaded": 0,
                        "downloaded": downloaded,
                        "left": max(0, meta.get("total_size", 0) - downloaded),
                        "compact": 1,
                        "event": "stopped",
                        "numwant": 0
                    }
                    parts = [f"{k}={urllib.parse.quote_from_bytes(v)}" if isinstance(v, bytes) else f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()]
                    full_url = ann_url + ("&" if "?" in ann_url else "?") + "&".join(parts)
                    try:
                        req = urllib.request.Request(full_url, headers=headers)
                        with urllib.request.urlopen(req, context=ctx, timeout=3):
                            pass
                    except Exception:
                        pass
        except Exception:
            pass

    def stop(self):
        self._is_cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2.0)
                except Exception:
                    self._proc.kill()
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass

    def run(self):
        aria2_bin = self.get_aria2_path()
        if not aria2_bin:
            if self.on_finished:
                self.on_finished(False, "aria2c engine binary not found in app/assets/bin", None)
            return

        os.makedirs(self.save_dir, exist_ok=True)

        # Baseline snapshot of files in save_dir before download
        initial_files = set(os.listdir(self.save_dir))

        # Pre-cache or resolve remote .torrent file if source is an HTTP/HTTPS URL
        actual_source = self.source
        if (self.source.startswith("http://") or self.source.startswith("https://")) and (".torrent" in self.source.lower()):
            resolved_torrent, err = self._resolve_remote_torrent(self.source, self.save_dir, self.headers)
            if not resolved_torrent:
                print(f"[TorrentWorker] Could not resolve remote torrent: {err}")
                if self.on_finished:
                    self.on_finished(False, err or "Gagal mengunduh file .torrent dari URL", None)
                return
            actual_source = resolved_torrent

        # Determine if torrent is private to protect private tracker accounts
        is_private = False
        try:
            info_meta = self.get_torrent_info(actual_source)
            is_private = bool(info_meta.get("is_private", False))
        except Exception:
            pass

        # Generate a deterministic 20-character BitTorrent Peer ID per task
        # This guarantees aria2c re-uses the exact same location/peer lease on restarts
        import hashlib
        unique_seed = f"ZeroTorrent-{self.task_id or os.path.basename(actual_source)}"
        suffix_12 = hashlib.sha1(unique_seed.encode("utf-8")).hexdigest()[:12]
        deterministic_peer_id = f"-qB4650-{suffix_12}"

        # Real Seeding Configuration: seed duration in minutes and target ratio
        seed_minutes = int(self.seed_duration_days * 24 * 60) if self.seed_duration_days > 0 else 0

        cmd = [
            aria2_bin,
            "--allow-overwrite=true",
            "--follow-torrent=mem",
            f"--seed-time={seed_minutes}",
            f"--seed-ratio={self.seed_ratio}",
            "--bt-seed-unverified=true",
            f"--peer-id-prefix={deterministic_peer_id}",
            "--user-agent=qBittorrent/4.6.5",
            "--no-want-digest-header=true",
            "--listen-port=6881-6889",
            "--bt-force-encryption=true",
            "--summary-interval=1",
            "--console-log-level=warn",
            "--show-console-readout=true",
            "--file-allocation=none",
            f"--dir={self.save_dir}",
        ]

        if is_private:
            # Strictly protect private trackers (Avistaz, PTP, etc.): disable DHT, LPD, PEX, and no public trackers
            cmd.extend([
                "--enable-dht=false",
                "--bt-enable-lpd=false",
                "--enable-peer-exchange=false",
            ])
        else:
            # Public swarm: maximize discovery via DHT, LPD, and public tracker announce list
            cmd.extend([
                "--enable-dht=true",
                "--bt-enable-lpd=true",
                "--dht-entry-point=router.bittorrent.com:6881",
                "--dht-entry-point=dht.transmissionbt.com:6881",
                "--dht-entry-point=router.utorrent.com:6881",
            ])
            public_trackers = TorrentSearchClient.get_public_trackers_string()
            if public_trackers:
                cmd.append(f"--bt-tracker={public_trackers}")

        if self.download_rate_limit > 0:
            cmd.append(f"--max-download-limit={self.download_rate_limit}")
        if self.upload_rate_limit > 0:
            cmd.append(f"--max-upload-limit={self.upload_rate_limit}")

        # Selective file download (--select-file=1,3,5)
        if self.selected_files:
            indices_str = ",".join(str(i) for i in sorted(set(self.selected_files)))
            cmd.append(f"--select-file={indices_str}")

        cmd.append(actual_source)

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                bufsize=1,
                creationflags=creationflags,
                startupinfo=startupinfo
            )

            # Telemetry regex for aria2 stdout
            # Active download: [#16d246 1.4MiB/14MiB(10%) CN:5 SD:2 DL:128KiB ETA:1m38s]
            # Active download with upload: [#16d246 1.4MiB/14MiB(10%) CN:5 SD:2 DL:128KiB UL:10KiB ETA:1m38s]
            # Real seeding mode: [#16d246 14MiB/14MiB(100%) CN:5 SD:2 DL:0B UL:128KiB SEED]
            progress_regex = re.compile(
                r"\[#\w+\s+(?P<dl>[0-9\.]+[a-zA-Z]+)/(?P<tot>[0-9\.]+[a-zA-Z]+)(?:\((?P<pct>[0-9\.]+)%\))?"
                r"(?:\s+CN:(?P<cn>\d+))?"
                r"(?:\s+SD:(?P<sd>\d+))?"
                r"(?:\s+DL:(?P<dl_spd>[0-9\.]+[a-zA-Z]+))?"
                r"(?:\s+UL:(?P<ul_spd>[0-9\.]+[a-zA-Z]+))?"
                r"(?:\s+ETA:(?P<eta>[0-9a-zA-Z]+))?"
                r"(?:\s*(?P<seed>SEED(?:ING)?))?\]"
            )

            last_dl_bytes = 0
            last_tot_bytes = -1
            self.tracker_status = ""

            while self._proc.poll() is None:
                if self.cancel_event and self.cancel_event.is_set():
                    self._is_cancelled = True
                    try:
                        self._proc.terminate()
                        try:
                            self._proc.wait(timeout=2.0)
                        except Exception:
                            self._proc.kill()
                    except Exception:
                        pass
                    break

                # Handle pause: terminate process gracefully so tracker receives event=stopped
                if self.pause_event and not self.pause_event.is_set():
                    self._is_paused = True
                    try:
                        self._proc.terminate()
                        try:
                            self._proc.wait(timeout=2.0)
                        except Exception:
                            self._proc.kill()
                    except Exception:
                        pass
                    break

                line = self._proc.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                # Parse Tracker messages and failure reasons
                if "Tracker returned failure reason:" in line:
                    m_tr = re.search(r"Tracker returned failure reason:\s*([^\r\n]+)", line)
                    if m_tr:
                        raw_reason = m_tr.group(1).strip()
                        if "more than 3 locations" in raw_reason.lower() or "already have 3 peers" in raw_reason.lower() or "3 peers" in raw_reason.lower():
                            self.tracker_status = "Batas 3 peer tracker terlampaui (Membersihkan sesi ghost...)"
                            threading.Thread(target=self._send_tracker_stop, args=(actual_source, deterministic_peer_id), daemon=True).start()
                        else:
                            self.tracker_status = f"Tracker: {raw_reason}"
                        if self.on_progress:
                            try:
                                self.on_progress(last_dl_bytes, last_tot_bytes, 0.0, 0.0, 0, 0, 0.0, self.tracker_status)
                            except TypeError:
                                self.on_progress(last_dl_bytes, last_tot_bytes, 0.0, 0.0, 0, 0, 0.0)

                m = progress_regex.search(line)
                if m:
                    dl_str = m.group("dl")
                    tot_str = m.group("tot")
                    cn_str = m.group("cn") or "0"
                    sd_str = m.group("sd") or "0"
                    spd_str = m.group("dl_spd") or "0B"
                    ul_str = m.group("ul_spd") or "0B"
                    eta_str = m.group("eta") or ""
                    is_seed_mode = bool(m.group("seed"))

                    dl_b = self._parse_size_bytes(dl_str)
                    tot_b = self._parse_size_bytes(tot_str)
                    dl_spd = float(self._parse_size_bytes(spd_str))
                    ul_spd = float(self._parse_size_bytes(ul_str))
                    peers = int(cn_str)
                    seeds = int(sd_str)
                    eta_s = self._parse_eta_seconds(eta_str)

                    if is_seed_mode or (tot_b > 0 and dl_b >= tot_b):
                        self.tracker_status = f"Seeding (Swarm: {peers}P)" if peers > 0 else "Seeding"
                    elif seeds > 0 or peers > 0:
                        self.tracker_status = ""

                    last_dl_bytes = dl_b
                    last_tot_bytes = tot_b

                    if self.on_progress:
                        try:
                            self.on_progress(dl_b, tot_b, dl_spd, ul_spd, seeds, peers, eta_s, self.tracker_status)
                        except TypeError:
                            self.on_progress(dl_b, tot_b, dl_spd, ul_spd, seeds, peers, eta_s)

            ret = self._proc.wait()
            if self._is_cancelled or (self.cancel_event and self.cancel_event.is_set()):
                self._send_tracker_stop(actual_source, deterministic_peer_id, last_dl_bytes)
                if self.on_finished:
                    self.on_finished(False, "Cancelled by user", None)
                return

            if self._is_paused or (self.pause_event and not self.pause_event.is_set()):
                self._send_tracker_stop(actual_source, deterministic_peer_id, last_dl_bytes)
                if self.on_finished:
                    self.on_finished(False, "Paused by user", None)
                return

            if ret == 0:
                # Find new or modified file/directory in save_dir
                current_files = set(os.listdir(self.save_dir))
                new_files = list(current_files - initial_files)
                final_path = None
                if new_files:
                    # Prefer non-aria2 metadata files
                    clean_files = [f for f in new_files if not f.endswith(".aria2")]
                    if clean_files:
                        final_path = os.path.join(self.save_dir, clean_files[0])
                    else:
                        final_path = os.path.join(self.save_dir, new_files[0])

                # If new_files was empty (resumed download or folder existed before start),
                # determine the exact torrent directory or target file from metadata
                if not final_path or final_path == self.save_dir:
                    try:
                        meta = self.get_torrent_info(actual_source)
                        t_name = meta.get("name")
                        if t_name and os.path.exists(os.path.join(self.save_dir, t_name)):
                            final_path = os.path.join(self.save_dir, t_name)
                    except Exception:
                        pass

                if not final_path:
                    final_path = self.save_dir

                fin_size = last_dl_bytes
                if final_path and os.path.isfile(final_path):
                    fin_size = os.path.getsize(final_path)
                elif final_path and os.path.isdir(final_path):
                    fin_size = sum(
                        os.path.getsize(os.path.join(r, f))
                        for r, _, fs in os.walk(final_path)
                        for f in fs
                        if not f.endswith(".aria2")
                    )

                if self.on_progress:
                    try:
                        self.on_progress(fin_size, fin_size, 0.0, 0.0, 0, 0, 0.0, "Complete")
                    except TypeError:
                        self.on_progress(fin_size, fin_size, 0.0, 0.0, 0, 0, 0.0)

                if self.on_finished:
                    self.on_finished(True, None, final_path)
            else:
                desc = ARIA2_ERROR_MESSAGES.get(ret, f"BitTorrent engine exited with code {ret}")
                err_msg = f"{desc} (Code {ret})"
                if self.on_finished:
                    self.on_finished(False, err_msg, None)
        except Exception as e:
            if self._proc:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            if self.on_finished:
                self.on_finished(False, str(e), None)
