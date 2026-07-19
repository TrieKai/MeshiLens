"""Pluggable TTL caches for match / Michelin / advice results.

Backends (auto-selected):
1. Redis / Upstash when a URL is configured
2. Disk file cache (local /tmp) otherwise
Always wraps an in-memory L1 layer.
"""

from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Protocol
from urllib import error as urlerror
from urllib import request as urlrequest


LOGGER = logging.getLogger("meshilens.cache")

DEFAULT_MATCH_TTL_SECONDS = 21_600
DEFAULT_MICHELIN_TTL_SECONDS = 86_400
DEFAULT_ADVICE_TTL_SECONDS = 2_592_000


class CacheBackend(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...

    def set(self, key: str, value: dict[str, Any]) -> None: ...


class MemoryTTLCache:
    """Process-local LRU TTL cache (L1)."""

    def __init__(self, ttl_seconds: int = DEFAULT_MATCH_TTL_SECONDS, max_items: int = 256) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._items: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._items.get(key)
            if not entry:
                return None
            created_at, value = entry
            if time.time() - created_at > self.ttl_seconds:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._items[key] = (time.time(), value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)


class FileTTLCache:
    """JSON files under a directory; survives local process restarts."""

    def __init__(
        self,
        directory: str | Path,
        ttl_seconds: int = DEFAULT_MATCH_TTL_SECONDS,
        max_items: int = 512,
        *,
        namespace: str = "default",
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self.directory = Path(directory) / namespace
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path_for(self, key: str) -> Path:
        digest = sha256(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path_for(key)
        try:
            with self._lock:
                if not path.is_file():
                    return None
                payload = json.loads(path.read_text(encoding="utf-8"))
            created_at = float(payload.get("created_at") or 0)
            value = payload.get("value")
            if not isinstance(value, dict):
                return None
            if time.time() - created_at > self.ttl_seconds:
                path.unlink(missing_ok=True)
                return None
            return value
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        path = self._path_for(key)
        payload = json.dumps(
            {"created_at": time.time(), "value": value},
            ensure_ascii=False,
        )
        try:
            with self._lock:
                path.write_text(payload, encoding="utf-8")
                self._evict_if_needed()
        except OSError as exc:
            LOGGER.debug("file cache write failed: %s", exc)

    def _evict_if_needed(self) -> None:
        files = sorted(self.directory.glob("*.json"), key=lambda item: item.stat().st_mtime)
        overflow = len(files) - self.max_items
        for path in files[: max(0, overflow)]:
            path.unlink(missing_ok=True)


class UpstashRestCache:
    """Upstash Redis REST API — works on Vercel without a persistent TCP pool."""

    def __init__(
        self,
        rest_url: str,
        rest_token: str,
        ttl_seconds: int = DEFAULT_MATCH_TTL_SECONDS,
        *,
        namespace: str = "default",
        timeout: float = 2.5,
    ) -> None:
        self.rest_url = rest_url.rstrip("/")
        self.rest_token = rest_token
        self.ttl_seconds = ttl_seconds
        self.namespace = namespace
        self.timeout = timeout

    def _redis_key(self, key: str) -> str:
        digest = sha256(key.encode("utf-8")).hexdigest()
        return f"meshilens:{self.namespace}:{digest}"

    def _command(self, *parts: str | int) -> Any:
        body = json.dumps(list(parts)).encode("utf-8")
        request = urlrequest.Request(
            self.rest_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.rest_token}",
                "Content-Type": "application/json",
            },
        )
        with urlrequest.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(str(payload["error"]))
        return payload.get("result") if isinstance(payload, dict) else payload

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            raw = self._command("GET", self._redis_key(key))
            if not raw:
                return None
            value = json.loads(raw) if isinstance(raw, str) else raw
            return value if isinstance(value, dict) else None
        except (OSError, TypeError, ValueError, json.JSONDecodeError, urlerror.URLError) as exc:
            LOGGER.debug("upstash get failed: %s", exc)
            return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        try:
            self._command(
                "SET",
                self._redis_key(key),
                json.dumps(value, ensure_ascii=False),
                "EX",
                int(self.ttl_seconds),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError, urlerror.URLError) as exc:
            LOGGER.debug("upstash set failed: %s", exc)


class RedisURLCache:
    """Optional redis:// / rediss:// backend when the redis package is installed."""

    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int = DEFAULT_MATCH_TTL_SECONDS,
        *,
        namespace: str = "default",
    ) -> None:
        import redis

        self.ttl_seconds = ttl_seconds
        self.namespace = namespace
        self._client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2.5,
            socket_timeout=2.5,
        )

    def _redis_key(self, key: str) -> str:
        digest = sha256(key.encode("utf-8")).hexdigest()
        return f"meshilens:{self.namespace}:{digest}"

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            raw = self._client.get(self._redis_key(key))
            if not raw:
                return None
            value = json.loads(raw)
            return value if isinstance(value, dict) else None
        except Exception as exc:
            LOGGER.debug("redis get failed: %s", exc)
            return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        try:
            self._client.set(
                self._redis_key(key),
                json.dumps(value, ensure_ascii=False),
                ex=int(self.ttl_seconds),
            )
        except Exception as exc:
            LOGGER.debug("redis set failed: %s", exc)


class LayeredTTLCache:
    """Try L1 then L2; writes propagate to every layer."""

    def __init__(self, *layers: CacheBackend) -> None:
        if not layers:
            raise ValueError("at least one cache layer is required")
        self.layers = layers

    def get(self, key: str) -> dict[str, Any] | None:
        for index, layer in enumerate(self.layers):
            value = layer.get(key)
            if value is None:
                continue
            for warmer in self.layers[:index]:
                warmer.set(key, value)
            return value
        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        for layer in self.layers:
            layer.set(key, value)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def default_cache_dir() -> Path:
    configured = _env("MESHI_CACHE_DIR")
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "meshilens-cache"


def build_cache(
    *,
    ttl_seconds: int,
    max_items: int = 256,
    namespace: str = "match",
) -> CacheBackend:
    """Build L1 memory + optional Redis/Upstash or file L2."""
    memory = MemoryTTLCache(ttl_seconds=ttl_seconds, max_items=max_items)

    # Vercel's Upstash Marketplace integration provisions KV_REST_API_*.
    # Keep the UPSTASH_* aliases for direct Upstash projects and local setups.
    rest_url = (
        _env("KV_REST_API_URL")
        or _env("UPSTASH_REDIS_REST_URL")
        or _env("MESHI_UPSTASH_REDIS_REST_URL")
    )
    rest_token = (
        _env("KV_REST_API_TOKEN")
        or _env("UPSTASH_REDIS_REST_TOKEN")
        or _env("MESHI_UPSTASH_REDIS_REST_TOKEN")
    )
    if rest_url and rest_token:
        LOGGER.info("MeshiLens cache[%s]: memory + Upstash REST", namespace)
        return LayeredTTLCache(
            memory,
            UpstashRestCache(
                rest_url, rest_token, ttl_seconds=ttl_seconds, namespace=namespace
            ),
        )

    redis_url = _env("MESHI_REDIS_URL") or _env("REDIS_URL")
    if redis_url:
        try:
            LOGGER.info("MeshiLens cache[%s]: memory + Redis URL", namespace)
            return LayeredTTLCache(
                memory,
                RedisURLCache(redis_url, ttl_seconds=ttl_seconds, namespace=namespace),
            )
        except ImportError:
            LOGGER.warning(
                "MESHI_REDIS_URL/REDIS_URL is set but redis is not installed; "
                "falling back to file cache. Install with: uv add redis"
            )

    disable_file = _env("MESHI_CACHE_FILE").lower() in {"0", "false", "off", "no"}
    if disable_file:
        LOGGER.info("MeshiLens cache[%s]: memory only", namespace)
        return memory

    LOGGER.info("MeshiLens cache[%s]: memory + file (%s)", namespace, default_cache_dir())
    return LayeredTTLCache(
        memory,
        FileTTLCache(
            default_cache_dir(),
            ttl_seconds=ttl_seconds,
            max_items=max(max_items, 512),
            namespace=namespace,
        ),
    )


# Backward-compatible alias used by older imports / tests.
TTLCache = MemoryTTLCache
