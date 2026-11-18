import os
import sys
import shutil
import subprocess
import threading
from typing import Optional, Callable

class AudioMuxer:
    """
    Combines separate video and audio DASH streams (such as YouTube 1080p/4K video + m4a audio)
    into a single unified video file with audio using ffmpeg.
    Operates strictly in the background without any command prompt windows.
    """

    @staticmethod
    def get_ffmpeg_path() -> Optional[str]:
        # 1. System PATH
        path = shutil.which("ffmpeg")
        if path and os.path.exists(path):
            return path

        # 2. Executable directory / assets / PyInstaller bundle
        meipass = getattr(sys, '_MEIPASS', None)
        candidates = [
            os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe"),
            os.path.join(os.path.dirname(sys.executable), "app", "assets", "bin", "ffmpeg.exe"),
            os.path.join(os.path.dirname(__file__), "..", "assets", "bin", "ffmpeg.exe"),
            os.path.join(os.path.dirname(__file__), "..", "..", "bin", "ffmpeg.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Zero Download Assistant\ffmpeg.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Zero Download Assistant\app\assets\bin\ffmpeg.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
            os.path.expandvars(r"%APPDATA%\ffmpeg\bin\ffmpeg.exe"),
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        ]
        if meipass:
            candidates.extend([
                os.path.join(meipass, "ffmpeg.exe"),
                os.path.join(meipass, "app", "assets", "bin", "ffmpeg.exe"),
                os.path.join(meipass, "bin", "ffmpeg.exe"),
            ])
        for c in candidates:
            if c and os.path.exists(c):
                return os.path.abspath(c)

        return None

    @classmethod
    def is_available(cls) -> bool:
        return cls.get_ffmpeg_path() is not None

    @classmethod
    def mux_dash_pair_async(
        cls,
        video_path: str,
        audio_path: str,
        on_success: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ):
        """Asynchronously muxes video and audio in a background thread."""
        thread = threading.Thread(
            target=cls.mux_dash_pair,
            args=(video_path, audio_path, on_success, on_error),
            daemon=True
        )
        thread.start()
        return thread

    @classmethod
    def mux_dash_pair(
        cls,
        video_path: str,
        audio_path: str,
        on_success: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ) -> bool:
        ffmpeg_bin = cls.get_ffmpeg_path()
        if not ffmpeg_bin:
            err = "FFmpeg is not installed or not found in system PATH. Video and audio files kept separate."
            if on_error:
                on_error(err)
            return False

        if not os.path.exists(video_path) or not os.path.exists(audio_path):
            err = f"File missing for muxing: video_exists={os.path.exists(video_path)}, audio_exists={os.path.exists(audio_path)}"
            if on_error:
                on_error(err)
            return False

        dir_name = os.path.dirname(video_path)
        base_name = os.path.basename(video_path)
        temp_output = os.path.join(dir_name, f"__muxing_{base_name}")

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-movflags", "+faststart",
            temp_output
        ]

        kwargs = {
            "capture_output": True,
            "text": True,
            "timeout": 300
        }

        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            sinfo = subprocess.STARTUPINFO()
            sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            sinfo.wShowWindow = 0
            kwargs["startupinfo"] = sinfo

        try:
            res = subprocess.run(cmd, **kwargs)
            if res.returncode == 0 and os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
                # Safely replace original video file with the muxed version
                try:
                    if os.path.exists(video_path):
                        os.remove(video_path)
                    os.replace(temp_output, video_path)
                except Exception:
                    # Fallback rename
                    shutil.move(temp_output, video_path)

                # Clean up companion audio file
                try:
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                except Exception:
                    pass

                if on_success:
                    on_success(video_path)
                return True
            else:
                err_msg = res.stderr or "FFmpeg muxing failed with non-zero exit code"
                if on_error:
                    on_error(err_msg)
                return False
        except Exception as e:
            if os.path.exists(temp_output):
                try:
                    os.remove(temp_output)
                except Exception:
                    pass
            if on_error:
                on_error(str(e))
            return False