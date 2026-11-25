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
        if count <= 0:
            return
        remaining = float(count)
        while remaining > 0:
            with self.lock:
                limit = self.max_bytes_per_sec
                if limit <= 0:
                    return
                now = time.time()
                elapsed = max(0.0, now - self.last_time)
                self.last_time = now
                self.tokens = min(float(limit), self.tokens + elapsed * limit)

                # Consume up to `limit` per iteration so requests larger than 1s cap (e.g. 256KB chunk when limit < 256KB/s) never deadlock
                step = min(remaining, float(limit))
                if self.tokens >= step:
                    self.tokens -= step
                    remaining -= step
                    if remaining <= 0:
                        return
                    sleep_time = 0.0
                else:
                    missing = step - self.tokens
                    sleep_time = missing / limit

            if sleep_time > 0:
                time.sleep(min(sleep_time, 0.1))

    def acquire(self, count: int):
        """Alias for wait_for_token for worker compatibility."""
        self.wait_for_token(count)

    def throttle(self, count: int):
        """Alias for wait_for_token for HLS/DASH worker compatibility."""
        self.wait_for_token(count)