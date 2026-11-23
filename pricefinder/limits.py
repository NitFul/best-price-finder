"""Daily search cap shared by all visitors, to protect free API credits."""

import threading
from datetime import date


class DailyLimiter:
    def __init__(self, limit: int):
        self.limit = limit
        self._day = date.today()
        self._count = 0
        self._lock = threading.Lock()

    def try_use(self) -> bool:
        """Count one search. Returns False if today's limit is reached."""
        with self._lock:
            if date.today() != self._day:
                self._day, self._count = date.today(), 0
            if self._count >= self.limit:
                return False
            self._count += 1
            return True

    @property
    def remaining(self) -> int:
        with self._lock:
            if date.today() != self._day:
                return self.limit
            return max(self.limit - self._count, 0)
