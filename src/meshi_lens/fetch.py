"""How the Tabelog provider reads every page: per-host throttle, bounded timeout, status check."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlparse


REQUEST_TIMEOUT_SECONDS = 20.0
# A request started with less time than this left would only waste a Tabelog hit.
MINIMUM_REQUEST_SECONDS = 1.0
DEFAULT_HEADERS = {"Accept-Language": "ja,en;q=0.8"}


class DeadlineExceeded(TimeoutError):
    """The lookup's time budget ran out before the next request could start."""


class HTTPStatusError(RuntimeError):
    """A page answered with an error status; the message keeps the code for log labels."""

    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"{urlparse(url).hostname or url} 回應 HTTP {status}")
        self.status = status


class Deadline:
    """One lookup's wall-clock budget, shared by every request it makes."""

    def __init__(
        self, seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.seconds = seconds
        self._clock = clock
        self._expires_at = clock() + seconds

    def remaining(self) -> float:
        return self._expires_at - self._clock()

    def check(self, wait: float = 0.0) -> float:
        """Return how long a request starting after `wait` seconds may take."""
        available = self.remaining() - wait
        if available < MINIMUM_REQUEST_SECONDS:
            raise DeadlineExceeded(f"已超過 {self.seconds:g} 秒查詢時限")
        return available


class ThrottledFetcher:
    """Rate-limited GETs; each host keeps its own interval so Yahoo/DDG never wait on Tabelog."""

    def __init__(self, minimum_interval: float = 0.8) -> None:
        self.minimum_interval = minimum_interval
        self._last_request_by_host: dict[str, float] = {}
        self._host_locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def _host_lock(self, host: str) -> threading.Lock:
        with self._meta_lock:
            lock = self._host_locks.get(host)
            if lock is None:
                lock = threading.Lock()
                self._host_locks[host] = lock
            return lock

    def throttle(self, host: str, deadline: Deadline | None = None) -> None:
        """Take this host's next request slot, or give up once the deadline cannot fit it."""
        lock = self._host_lock(host)
        if deadline is None:
            lock.acquire()
        elif not lock.acquire(
            timeout=max(0.0, deadline.remaining() - MINIMUM_REQUEST_SECONDS)
        ):
            raise DeadlineExceeded(f"等待 {host} 請求間隔時超過查詢時限")
        try:
            last = self._last_request_by_host.get(host, 0.0)
            delay = self.minimum_interval - (time.monotonic() - last)
            if deadline is not None:
                deadline.check(wait=max(0.0, delay))
            if delay > 0:
                time.sleep(delay)
            self._last_request_by_host[host] = time.monotonic()
        finally:
            lock.release()

    def fetch(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        deadline: Deadline | None = None,
    ) -> str:
        """GET a page as text; error statuses raise HTTPStatusError, never return a body."""
        from curl_cffi import requests

        self.throttle(urlparse(url).hostname or url, deadline)
        timeout = REQUEST_TIMEOUT_SECONDS
        if deadline is not None:
            timeout = min(timeout, deadline.check())
        response = requests.get(
            url,
            params=dict(params) if params else None,
            headers=dict(headers or DEFAULT_HEADERS),
            timeout=timeout,
            allow_redirects=True,
            impersonate="chrome",
        )
        if response.status_code >= 400:
            raise HTTPStatusError(response.status_code, url)
        return response.text
