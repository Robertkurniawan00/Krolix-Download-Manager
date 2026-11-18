import os
import sys
import math
import struct
import wave
import threading
from typing import Optional

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False


class SoundManager:
    """
    Zero Download Assistant Audio Feedback System.
    Provides harmonious, modern audio notifications for:
    - Download Completion (crisp dual-tone bell chime)
    - Download Error (gentle dual-tone alert)
    - Download Start (subtle soft pop)
    
    Uses Windows native winsound.PlaySound asynchronously with zero external dependencies.
    """
    _instance: Optional['SoundManager'] = None
    _lock = threading.Lock()
    def __new__(cls, db=None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, db=None):
        if self._initialized:
            if db and not getattr(self, "db", None):
                self.db = db
            return
        self.db = db
        self.sounds_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "sounds"))
        os.makedirs(self.sounds_dir, exist_ok=True)

    def _generate_wav(self, file_path: str, tones: list, duration_sec: float = 0.5):
        """Synthesizes high-fidelity 44.1 kHz 16-bit mono PCM WAV audio with exponential decay envelope."""
        sample_rate = 44100
        total_samples = int(sample_rate * duration_sec)
        
        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)        # Mono
            wf.setsampwidth(2)        # 16-bit (2 bytes)
            wf.setframerate(sample_rate)
            
            raw_data = bytearray()
            for i in range(total_samples):
                t = i / sample_rate
                val = 0.0
                
                # Render each harmonic tone segment
                for start_t, end_t, freq, amp in tones:
                    if start_t <= t <= end_t:
                        rel_t = t - start_t
                        dur = end_t - start_t
                        # Exponential bell decay envelope
                        decay = math.exp(-3.5 * (rel_t / max(0.01, dur)))
                        # Attack ramp for 5ms to avoid clicks
                        attack = min(1.0, rel_t / 0.005)
                        wave_val = math.sin(2.0 * math.pi * freq * rel_t)
                        # Add soft 2nd harmonic
                        wave_val += 0.25 * math.sin(2.0 * math.pi * (freq * 2.0) * rel_t)
                        val += wave_val * amp * decay * attack
                
                # Soft clip and convert to 16-bit signed integer
                clamped = max(-1.0, min(1.0, val))
                sample_int = int(clamped * 32767.0)
                raw_data.extend(struct.pack("<h", sample_int))
                
            wf.writeframes(raw_data)

    def _ensure_default_sounds(self):
        """Ensures that crisp, elegant default chime WAV files are generated and available."""
        complete_wav = os.path.join(self.sounds_dir, "complete.wav")
        error_wav = os.path.join(self.sounds_dir, "error.wav")
        start_wav = os.path.join(self.sounds_dir, "start.wav")

        # 1. Complete Chime: Melodic C6 (1046.5 Hz) -> G6 (1567.98 Hz) bell chime
        if not os.path.exists(complete_wav):
            try:
                tones = [
                    (0.00, 0.35, 1046.50, 0.45),  # C6
                    (0.08, 0.55, 1567.98, 0.55),  # G6
                    (0.12, 0.60, 2093.00, 0.20),  # C7 subtle overtone
                ]
                self._generate_wav(complete_wav, tones, duration_sec=0.65)
            except Exception:
                pass

        # 2. Error Sound: Soft double low alert (440 Hz -> 329.6 Hz)
        if not os.path.exists(error_wav):
            try:
                tones = [
                    (0.00, 0.20, 440.0, 0.40),
                    (0.12, 0.40, 329.63, 0.45),
                ]
                self._generate_wav(error_wav, tones, duration_sec=0.45)
            except Exception:
                pass

        # 3. Start Sound: Subtle pop cue (880 Hz -> 1320 Hz micro-chime)
        if not os.path.exists(start_wav):
            try:
                tones = [
                    (0.00, 0.12, 880.0, 0.30),
                    (0.04, 0.18, 1318.51, 0.35),
                ]
                self._generate_wav(start_wav, tones, duration_sec=0.22)
            except Exception:
                pass

    def _play_file(self, filename: str):
        if not HAS_WINSOUND or sys.platform != "win32":
            return
        sound_path = os.path.join(self.sounds_dir, filename)
        if not os.path.exists(sound_path):
            self._ensure_default_sounds()
        if os.path.exists(sound_path):
            try:
                # Play asynchronously without blocking download threads or UI loop
                winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            except Exception:
                pass

    def play_complete(self, force: bool = False):
        if not force and self.db:
            if self.db.get_setting("sound_enabled", "true") != "true":
                return
            if self.db.get_setting("sound_on_complete", "true") != "true":
                return
        self._play_file("complete.wav")

    def play_error(self, force: bool = False):
        if not force and self.db:
            if self.db.get_setting("sound_enabled", "true") != "true":
                return
            if self.db.get_setting("sound_on_error", "true") != "true":
                return
        self._play_file("error.wav")

    def play_start(self, force: bool = False):
        if not force and self.db:
            if self.db.get_setting("sound_enabled", "true") != "true":
                return
            if self.db.get_setting("sound_on_start", "false") != "true":
                return
        self._play_file("start.wav")

    def test_sound(self, sound_type: str = "complete"):
        """Auditions a specific sound in settings."""
        if sound_type == "complete":
            self.play_complete(force=True)
        elif sound_type == "error":
            self.play_error(force=True)
        elif sound_type == "start":
            self.play_start(force=True)


AudioFeedbackManager = SoundManager