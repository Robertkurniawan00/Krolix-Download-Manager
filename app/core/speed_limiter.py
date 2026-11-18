import time
import threading

class SpeedLimiter:
    def __init__(self, max_bytes_per_sec: int = 0):
        self.max_bytes_per_sec = max_bytes_per_sec
        self.tokens = max_bytes_per_sec
        self.last_time = time.time()
        self.lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.max_bytes_per_sec > 0

    @property
    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool, default_limit: int = 1048576):
        if not enabled:
            self.set_limit(0)
        elif self.max_bytes_per_sec <= 0:
            self.set_limit(default_limit)

    def set_limit(self, max_bytes_per_sec: int):
        with self.lock:
            self.max_bytes_per_sec = max_bytes_per_sec
            self.tokens = max_bytes_per_sec
            self.last_time = time.time()

    def wait_for_token(self, count: int):
        if self.max_bytes_per_sec <= 0:
            return

        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last_time
                self.last_time = now
                self.tokens = min(self.max_bytes_per_sec, self.tokens + elapsed * self.max_bytes_per_sec)

                if self.tokens >= count:
                    self.tokens -= count
                    return
                
                # Calculate sleep time needed
                missing = count - self.tokens
                sleep_time = missing / self.max_bytes_per_sec
            
            time.sleep(min(sleep_time, 0.1))

    def acquire(self, count: int):
        """Alias for wait_for_token for worker compatibility."""
        self.wait_for_token(count)