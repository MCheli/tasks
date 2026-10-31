"""In-memory limit on failed password logins, keyed by email.

Keyed by email rather than IP: behind Cloudflare and NGINX every request reaches uvicorn from the
proxy's address. State is per worker process and resets on restart, which is enough to turn an
online password guess from thousands per minute into a handful per window.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class FailedLoginLimiter:
    def __init__(self, max_failures: int = 10, window_seconds: float = 15 * 60) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window_seconds:
            q.popleft()
        return q

    def is_blocked(self, email: str) -> bool:
        key = email.lower()
        if key not in self._failures:
            return False
        q = self._recent(key, time.monotonic())
        if not q:
            del self._failures[key]
            return False
        return len(q) >= self.max_failures

    def record_failure(self, email: str) -> None:
        now = time.monotonic()
        if len(self._failures) > 10_000:  # spraying many emails must not grow memory forever
            for key in [k for k in self._failures if not self._recent(k, now)]:
                del self._failures[key]
        self._recent(email.lower(), now).append(now)

    def reset(self, email: str | None = None) -> None:
        if email is None:
            self._failures.clear()
        else:
            self._failures.pop(email.lower(), None)


login_limiter = FailedLoginLimiter()
