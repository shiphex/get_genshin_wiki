"""速率限制器，用于控制请求频率。"""

import time
import threading
from typing import Optional


class RateLimiter:
    """线程安全的API请求速率限制器。"""

    def __init__(self, interval: float = 5.0):
        """
        初始化速率限制器。

        参数:
            interval: 请求之间的最小时间间隔（秒）
        """
        self.interval = interval
        self.last_request_time: Optional[float] = None
        self.lock = threading.Lock()

    def wait(self) -> None:
        """等待直到距离上次请求已经过了足够的时间。"""
        with self.lock:
            now = time.time()
            if self.last_request_time is not None:
                elapsed = now - self.last_request_time
                if elapsed < self.interval:
                    sleep_time = self.interval - elapsed
                    time.sleep(sleep_time)
            self.last_request_time = time.time()

    def reset(self) -> None:
        """重置速率限制器。"""
        with self.lock:
            self.last_request_time = None

    @property
    def interval(self) -> float:
        """获取当前间隔时间。"""
        return self._interval

    @interval.setter
    def interval(self, value: float) -> None:
        """设置间隔时间。"""
        if value <= 0:
            raise ValueError("间隔时间必须为正数")
        self._interval = value