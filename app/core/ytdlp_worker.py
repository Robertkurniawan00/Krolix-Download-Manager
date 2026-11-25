"""
Zero Download Assistant - Advanced yt-dlp Worker Engine
High-performance video, audio, playlist, and subtitle extraction.
"""

import os
import threading
from typing import Callable, Optional, List, Dict, Any
import yt_dlp

from .audio_muxer import AudioMuxer
from .torrent_downloader import TorrentWorker
from ..utils.helpers import sanitize_filename, _ensure_valid_certifi


class YtdlpWorker(threading.Thread):
    def __init__(
        self,
        url: str,
        format_id: str = "best",
        save_dir: str = "",
        filename: str = "",
        task_id: str = "",
        pause_event: Optional[threading.Event] = None,
        cancel_event: Optional[threading.Event] = None,
        on_progress: Optional[Callable] = None,
        on_finished: Optional[Callable] = None,
        on_info: Optional[Callable] = None,
        on_status: Optional[Callable[[str], None]] = None,
        # Extended options:
        download_mode: str = "video",
        video_quality: str = "best",
        container_format: str = "mp4",
        audio_format: str = "mp3",
        audio_bitrate: str = "320",
        embed_subtitles: bool = False,
        subtitle_langs: Optional[List[str]] = None,
        embed_thumbnail: bool = False,
        embed_metadata: bool = True,
        concurrent_fragments: int = 16,
        use_aria2: bool = False,
        cookies_browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        rate_limit: int = 0,
        proxy: Optional[str] = None,
        is_playlist: bool = False,
        playlist_items: Optional[str] = None
    ):
        super().__init__()
        self.url = url
        self.format_id = format_id or "best"
        self.save_dir = save_dir or os.path.expanduser("~/Downloads")
        self.filename = filename or ""
        self.task_id = task_id or ""
        self.pause_event = pause_event
        self.cancel_event = cancel_event
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.on_info = on_info
        self.on_status = on_status

        self.download_mode = download_mode
        self.video_quality = video_quality
        self.container_format = container_format.lower() if container_format else "mp4"
        self.audio_format = audio_format.lower() if audio_format else "mp3"
        self.audio_bitrate = str(audio_bitrate or "320")
        self.embed_subtitles = embed_subtitles
        self.subtitle_langs = subtitle_langs or []
        self.embed_thumbnail = embed_thumbnail
        self.embed_metadata = embed_metadata
        self.concurrent_fragments = max(1, concurrent_fragments)
        self.use_aria2 = use_aria2
        self.cookies_browser = cookies_browser
        self.cookie_file = cookie_file
        self.rate_limit = rate_limit
        self.proxy = proxy
        self.is_playlist = is_playlist
        self.playlist_items = playlist_items

        self.daemon = True
        self._output_files: List[str] = []
        self._last_status_msg: str = ""

    @staticmethod
    def _format_duration(seconds: Optional[int]) -> str:
        if not seconds or seconds <= 0:
            return "--:--"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @staticmethod
    def _format_size(size_bytes: Optional[int]) -> str:
        if not size_bytes or size_bytes <= 0:
            return "--"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    @classmethod
    def fetch_info(
        cls,
        url: str,
        cookies_browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        proxy: Optional[str] = None
    ) -> dict:
        _ensure_valid_certifi()

        def _build_opts(use_cookies: bool = True) -> dict:
            opts = {
                'quiet': True,
                'no_warnings': True,
                'noprogress': True,
                'extract_flat': 'in_playlist',
                'nocheckcertificate': True,
                'skip_download': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
                }
            }
            ffmpeg_path = AudioMuxer.get_ffmpeg_path()
            if ffmpeg_path:
                opts['ffmpeg_location'] = ffmpeg_path
            if proxy:
                opts['proxy'] = proxy

            if use_cookies:
                cb = (cookies_browser or "").strip().lower()
                if cb and cb not in ("none", "tanpa cookie", ""):
                    opts['cookiesfrombrowser'] = (cb, None, None, None)
                elif cookie_file and os.path.exists(cookie_file):
                    opts['cookiefile'] = cookie_file

            return opts

        info = None
        try:
            with yt_dlp.YoutubeDL(_build_opts(use_cookies=True)) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            # If failed due to browser cookie lock or profile issue, retry without cookies
            if cookies_browser:
                try:
                    with yt_dlp.YoutubeDL(_build_opts(use_cookies=False)) as ydl:
                        info = ydl.extract_info(url, download=False)
                except Exception:
                    raise e
            else:
                raise e

        if not info:
            raise ValueError("Tidak dapat mengambil informasi media dari URL ini.")

        # Detect playlist (materializing lazy generators safely up to 50 preview items)
        raw_entries = info.get('entries')
        is_playlist = info.get('_type') == 'playlist' or (raw_entries is not None and not isinstance(raw_entries, (str, bytes, dict)))
        entries = []
        if is_playlist and raw_entries is not None:
            for idx, ent in enumerate(raw_entries):
                entries.append(ent)
                if idx >= 49:
                    break
        playlist_title = info.get('title', '') if is_playlist else ''
        playlist_count = info.get('playlist_count') or len(entries) or 1

        parsed_entries = []
        for i, ent in enumerate(entries[:50]):
            if not ent:
                continue
            e_dur = ent.get('duration') or 0
            parsed_entries.append({
                'index': i + 1,
                'id': ent.get('id', ''),
                'title': ent.get('title', f"Video {i+1}"),
                'duration': e_dur,
                'duration_str': cls._format_duration(e_dur),
                'url': ent.get('url') or ent.get('webpage_url') or f"https://www.youtube.com/watch?v={ent.get('id')}",
                'uploader': ent.get('uploader') or ent.get('channel') or ''
            })

        # Main video attributes
        title = info.get('title') or (entries[0].get('title') if entries else 'Unknown Title')
        uploader = info.get('uploader') or info.get('channel') or (entries[0].get('uploader') if entries else 'Unknown')
        duration = info.get('duration') or (entries[0].get('duration') if entries else 0)
        view_count = info.get('view_count')
        upload_date = info.get('upload_date') or ''

        # Best thumbnail
        thumbnail_url = info.get('thumbnail') or ''
        if not thumbnail_url and info.get('thumbnails'):
            thumbs = info.get('thumbnails')
            if isinstance(thumbs, list) and thumbs:
                thumbnail_url = thumbs[-1].get('url', '')

        # Subtitles parsing
        subtitles_map: Dict[str, dict] = {}
        for code, sub_list in (info.get('subtitles') or {}).items():
            name = sub_list[0].get('name', code) if sub_list else code
            subtitles_map[code] = {'code': code, 'name': name, 'is_auto': False}
        for code, sub_list in (info.get('automatic_captions') or {}).items():
            if code not in subtitles_map:
                name = sub_list[0].get('name', code) if sub_list else code
                subtitles_map[code] = {'code': code, 'name': f"{name} (Auto)", 'is_auto': True}

        subtitles_list = sorted(subtitles_map.values(), key=lambda s: s['name'])

        # Formats extraction
        formats = []
        heights_set = set()
        for f in info.get('formats', []):
            f_id = f.get('format_id')
            vcodec = f.get('vcodec') or 'none'
            acodec = f.get('acodec') or 'none'
            if vcodec == 'none' and acodec == 'none':
                continue

            height = f.get('height') or 0
            width = f.get('width') or 0
            fps = f.get('fps')
            ext = f.get('ext') or ''
            filesize = f.get('filesize') or f.get('filesize_approx') or 0
            if filesize <= 0 and duration and duration > 0:
                tbr = f.get('tbr') or f.get('vbr') or 0
                if tbr > 0:
                    filesize = int((tbr * 1024 / 8) * duration)

            if height > 0:
                heights_set.add(height)

            if vcodec != 'none' and acodec != 'none':
                fmt_type = "video+audio"
            elif vcodec != 'none':
                fmt_type = "video only"
            else:
                fmt_type = "audio only"

            res_str = f"{width}x{height}" if (width and height) else (f"{height}p" if height else ('Audio Saja' if fmt_type == 'audio only' else 'Unknown'))

            fmt = {
                'id': f_id,
                'resolution': res_str,
                'height': height,
                'fps': fps,
                'vcodec': vcodec,
                'acodec': acodec,
                'filesize': filesize,
                'filesize_str': cls._format_size(filesize),
                'format_note': f.get('format_note') or '',
                'ext': ext,
                'type': fmt_type,
                'vbr': f.get('vbr') or 0,
                'abr': f.get('abr') or 0,
                'tbr': f.get('tbr') or 0,
            }
            formats.append(fmt)

        formats.sort(key=lambda x: (x.get('height', 0), x.get('filesize', 0)), reverse=True)
        available_heights = sorted(list(heights_set), reverse=True)

        return {
            'title': title,
            'uploader': uploader,
            'channel': info.get('channel') or uploader,
            'duration': duration or 0,
            'duration_str': cls._format_duration(duration),
            'view_count': view_count,
            'upload_date': upload_date,
            'thumbnail_url': thumbnail_url,
            'webpage_url': info.get('webpage_url') or url,
            'is_playlist': is_playlist,
            'playlist_title': playlist_title,
            'playlist_count': playlist_count,
            'playlist_entries': parsed_entries,
            'formats': formats,
            'available_heights': available_heights,
            'subtitles': subtitles_list
        }

    def _emit_status(self, msg: str):
        self._last_status_msg = msg
        if self.on_status:
            try:
                self.on_status(msg)
            except Exception:
                pass

    def run(self):
        _ensure_valid_certifi()

        os.makedirs(self.save_dir, exist_ok=True)
        ffmpeg_path = AudioMuxer.get_ffmpeg_path()
        aria2_path = TorrentWorker.get_aria2_path()

        # Output template determination
        if self.is_playlist:
            pl_dir_name = sanitize_filename(self.filename or "Playlist")
            out_folder = os.path.join(self.save_dir, pl_dir_name)
            os.makedirs(out_folder, exist_ok=True)
            outtmpl = os.path.join(out_folder, "%(playlist_index)02d - %(title).100s.%(ext)s")
            base_name = pl_dir_name
        else:
            raw_fn = self.filename or "download"
            clean_name = sanitize_filename(raw_fn)
            base_name, _ = os.path.splitext(clean_name)
            if len(base_name) > 100:
                base_name = base_name[:100].rstrip(" ._")
            outtmpl = os.path.join(self.save_dir, f"{base_name}.%(ext)s")

        ydl_opts: Dict[str, Any] = {
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'nocheckcertificate': True,
            'outtmpl': outtmpl,
            'progress_hooks': [self._progress_hook],
            'postprocessor_hooks': [self._postprocessor_hook],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            },
            'retries': 10,
            'fragment_retries': 10,
            'buffersize': 1048576,
            'http_chunk_size': 10485760,
            'live_from_start': True,
        }

        if ffmpeg_path:
            ydl_opts['ffmpeg_location'] = ffmpeg_path

        # Network & Proxy
        if self.proxy:
            ydl_opts['proxy'] = self.proxy
        if self.rate_limit and self.rate_limit > 0:
            ydl_opts['ratelimit'] = self.rate_limit

        # Concurrency & Aria2c
        if self.concurrent_fragments > 1:
            ydl_opts['concurrent_fragment_downloads'] = self.concurrent_fragments

        if self.use_aria2 and aria2_path and os.path.exists(aria2_path):
            ydl_opts['external_downloader'] = {'default': aria2_path}
            ydl_opts['external_downloader_args'] = {'aria2c': ['-s', '16', '-x', '16', '-k', '1M', '-j', '16']}

        # Browser cookies
        cb = (self.cookies_browser or "").strip().lower()
        if cb and cb not in ("none", "tanpa cookie", ""):
            ydl_opts['cookiesfrombrowser'] = (cb, None, None, None)
        elif self.cookie_file and os.path.exists(self.cookie_file):
            ydl_opts['cookiefile'] = self.cookie_file

        # Playlist handling
        if not self.is_playlist:
            ydl_opts['noplaylist'] = True
        else:
            ydl_opts['noplaylist'] = False
            if self.playlist_items:
                ydl_opts['playlist_items'] = self.playlist_items

        postprocessors = []

        # Mode configuration: AUDIO vs VIDEO
        if self.download_mode == "audio" or self.format_id == "bestaudio":
            ydl_opts['format'] = 'bestaudio/best'
            acodec = self.audio_format if self.audio_format in ('mp3', 'm4a', 'flac', 'wav', 'opus', 'aac') else 'mp3'
            audio_pp: Dict[str, Any] = {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': acodec,
            }
            if acodec in ('mp3', 'm4a', 'aac', 'opus'):
                audio_pp['preferredquality'] = self.audio_bitrate
            postprocessors.append(audio_pp)

            if self.embed_metadata:
                postprocessors.append({'key': 'FFmpegMetadata', 'add_metadata': True})

            if self.embed_thumbnail:
                ydl_opts['writethumbnail'] = True
                postprocessors.append({'key': 'EmbedThumbnail', 'already_have_thumbnail': False})

        else:
            # Video mode
            container = self.container_format if self.container_format in ('mp4', 'mkv', 'webm') else 'mp4'

            if self.format_id and self.format_id not in ('best', 'bestvideo'):
                # Exact format ID selected; fallback safely if format already has audio or is audio-only
                ydl_opts['format'] = f"{self.format_id}+bestaudio/{self.format_id}/best"
            elif self.video_quality and self.video_quality != 'best':
                h = self.video_quality.replace('p', '')
                if container == 'mp4':
                    ydl_opts['format'] = (
                        f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
                        f"bestvideo[height<={h}]+bestaudio/"
                        f"best[height<={h}]/best"
                    )
                else:
                    ydl_opts['format'] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
            else:
                if container == 'mp4':
                    ydl_opts['format'] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
                else:
                    ydl_opts['format'] = "bestvideo+bestaudio/best"

            ydl_opts['merge_output_format'] = container

            # Subtitles
            if self.embed_subtitles:
                ydl_opts['writesubtitles'] = True
                ydl_opts['writeautomaticsub'] = True
                if self.subtitle_langs:
                    ydl_opts['subtitleslangs'] = self.subtitle_langs
                else:
                    ydl_opts['subtitleslangs'] = ['id', 'en']
                if ffmpeg_path:
                    postprocessors.append({'key': 'FFmpegEmbedSubtitle', 'already_have_subtitle': False})

            # Metadata & Thumbnail
            if self.embed_metadata:
                postprocessors.append({'key': 'FFmpegMetadata', 'add_metadata': True})

            if self.embed_thumbnail:
                ydl_opts['writethumbnail'] = True
                postprocessors.append({'key': 'EmbedThumbnail', 'already_have_thumbnail': False})

        if postprocessors:
            ydl_opts['postprocessors'] = postprocessors

        self._emit_status("Memulai koneksi...")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])

            if self.cancel_event and self.cancel_event.is_set():
                if self.on_finished:
                    self.on_finished(False, "Dibatalkan oleh pengguna", None)
                return

            if self.pause_event and not self.pause_event.is_set():
                if self.on_finished:
                    self.on_finished(False, "Dijeda oleh pengguna", None)
                return

            # Discover final output file
            final_path = None
            if self._output_files:
                for f in reversed(self._output_files):
                    if os.path.exists(f) and os.path.getsize(f) > 0:
                        final_path = f
                        break

            if not final_path:
                possible_exts = ['.mp4', '.mp3', '.mkv', '.m4a', '.flac', '.wav', '.opus', '.webm', '.ts', '']
                for ext in possible_exts:
                    candidate = os.path.join(self.save_dir, f"{base_name}{ext}")
                    if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                        final_path = candidate
                        break

            if not final_path and self.is_playlist:
                pl_folder = os.path.join(self.save_dir, base_name)
                if os.path.exists(pl_folder):
                    final_path = pl_folder

            if not final_path:
                final_path = os.path.join(self.save_dir, sanitize_filename(self.filename or 'download.mp4'))

            self._emit_status("Unduhan selesai.")
            if self.on_finished:
                self.on_finished(True, None, final_path)

        except yt_dlp.utils.DownloadCancelled as e:
            msg = str(e) or "Unduhan dibatalkan."
            self._emit_status(msg)
            if self.on_finished:
                self.on_finished(False, msg, None)
        except Exception as e:
            err_msg = str(e)
            self._emit_status(f"Error: {err_msg}")
            if self.on_finished:
                self.on_finished(False, err_msg, None)

    def _progress_hook(self, d: dict):
        if self.cancel_event and self.cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Dibatalkan oleh pengguna")

        if self.pause_event and not self.pause_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Dijeda oleh pengguna")

        status = d.get('status')
        if status == 'downloading':
            downloaded = d.get('downloaded_bytes') or 0
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            speed = d.get('speed') or 0.0
            eta = d.get('eta') or 0.0

            fn = d.get('filename')
            if fn and fn not in self._output_files:
                self._output_files.append(fn)

            if self.on_progress:
                try:
                    self.on_progress(downloaded, total, float(speed), float(eta))
                except Exception:
                    pass

        elif status == 'finished':
            fn = d.get('filename')
            if fn and fn not in self._output_files:
                self._output_files.append(fn)
            self._emit_status("Memproses file...")

    def _postprocessor_hook(self, d: dict):
        if self.cancel_event and self.cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Dibatalkan oleh pengguna")

        pp = d.get('postprocessor') or ''
        status = d.get('status') or ''

        if status == 'started':
            if 'ExtractAudio' in pp:
                self._emit_status(f"Mengekstrak audio {self.audio_format.upper()}...")
            elif 'EmbedSubtitle' in pp:
                self._emit_status("Menyematkan subtitle...")
            elif 'EmbedThumbnail' in pp:
                self._emit_status("Menyematkan cover thumbnail...")
            elif 'Metadata' in pp:
                self._emit_status("Menyematkan metadata ID3/tag...")
            elif 'Merger' in pp:
                self._emit_status("Menggabungkan stream video dan audio...")
            else:
                self._emit_status(f"Memproses: {pp}...")
        elif status == 'finished':
            info_dict = d.get('info_dict') or {}
            out_file = info_dict.get('_filename') or info_dict.get('filepath')
            if out_file and out_file not in self._output_files:
                self._output_files.append(out_file)
