from __future__ import annotations

from collections import OrderedDict
import threading
import time
from typing import Any, Mapping

from .matching import rank_candidates
from .michelin import MichelinProvider
from .provider import GurumeProvider, canonical_restaurant_url


class TTLCache:
    def __init__(self, ttl_seconds: int = 21_600, max_items: int = 256) -> None:
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


class MatchService:
    def __init__(
        self,
        provider: GurumeProvider | None = None,
        michelin_provider: MichelinProvider | None = None,
    ) -> None:
        self.provider = provider or GurumeProvider()
        self.michelin_provider = michelin_provider or MichelinProvider()
        self.cache = TTLCache()

    @staticmethod
    def validate_place(payload: Mapping[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()[:200]
        if not name:
            raise ValueError("找不到 Google Maps 店家名稱")
        result: dict[str, Any] = {
            "name": name,
            "alternate_name": str(payload.get("alternate_name") or "").strip()[:200],
            "address": str(payload.get("address") or "").strip()[:500],
            "phone": str(payload.get("phone") or "").strip()[:50],
            "tabelog_url": canonical_restaurant_url(
                str(payload.get("tabelog_url") or "").strip()[:300]
            )
            or "",
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
        }
        for key in ("latitude", "longitude"):
            if result[key] not in (None, ""):
                try:
                    result[key] = float(result[key])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{key} 格式不正確") from exc
        return result

    @staticmethod
    def _cache_key(place: Mapping[str, Any]) -> str:
        return "|".join(
            str(place.get(key) or "")
            for key in (
                "name",
                "alternate_name",
                "address",
                "phone",
                "tabelog_url",
                "latitude",
                "longitude",
            )
        )

    def match(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        place = self.validate_place(payload)
        key = self._cache_key(place)
        cached = self.cache.get(key)
        if cached:
            return {**cached, "cached": True}

        michelin = self.michelin_provider.match(place)
        try:
            candidates = rank_candidates(place, self.provider.search(place))
            tabelog_error = ""
        except Exception as exc:
            if not michelin:
                raise
            candidates = []
            tabelog_error = str(exc) or "Tabelog 查詢失敗"
        selected = candidates[0] if candidates and candidates[0]["confidence"] != "low" else None
        if selected:
            michelin = self.michelin_provider.match(place, selected) or michelin
        result = {
            "place": place,
            "selected": selected,
            "candidates": candidates,
            "michelin": michelin,
            "matched": selected is not None,
            "needs_confirmation": bool(selected and selected["confidence"] != "high"),
            "source": "Tabelog 日本語版",
            "tabelog_error": tabelog_error,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cached": False,
        }
        self.cache.set(key, result)
        return result
