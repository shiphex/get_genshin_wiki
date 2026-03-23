"""Rate limiter for controlling request frequency."""

import time
import threading
from typing import Optional


class RateLimiter:
    """Thread-safe rate limiter for API requests."""

    def __init__(self, interval: float = 5.0):
        """
        Initialize rate limiter.

        Args:
            interval: Minimum time between requests in seconds
        """
        self.interval = interval
        self.last_request_time: Optional[float] = None
        self.lock = threading.Lock()

    def wait(self) -> None:
        """Wait until enough time has passed since the last request."""
        with self.lock:
            now = time.time()
            if self.last_request_time is not None:
                elapsed = now - self.last_request_time
                if elapsed < self.interval:
                    sleep_time = self.interval - elapsed
                    time.sleep(sleep_time)
            self.last_request_time = time.time()

    def reset(self) -> None:
        """Reset the rate limiter."""
        with self.lock:
            self.last_request_time = None

    @property
    def interval(self) -> float:
        """Get current interval."""
        return self._interval

    @interval.setter
    def interval(self, value: float) -> None:
        """Set interval."""
        if value <= 0:
            raise ValueError("Interval must be positive")
        self._interval = value
