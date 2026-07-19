from __future__ import annotations

import time
from typing import Any, Mapping

from .advice import GroqDiningAdvisor, advice_cache_key, advice_response
from .cache import (
    DEFAULT_ADVICE_TTL_SECONDS,
    DEFAULT_MATCH_TTL_SECONDS,
    DEFAULT_MICHELIN_TTL_SECONDS,
    CacheBackend,
    build_cache,
)
from .matching import rank_candidates
from .michelin import MichelinProvider
from .provider import GurumeProvider, canonical_restaurant_url


class MatchService:
    def __init__(
        self,
        provider: GurumeProvider | None = None,
        michelin_provider: MichelinProvider | None = None,
        advisor: GroqDiningAdvisor | None = None,
        *,
        cache: CacheBackend | None = None,
        michelin_cache: CacheBackend | None = None,
        advice_cache: CacheBackend | None = None,
    ) -> None:
        self.provider = provider or GurumeProvider()
        self.michelin_provider = michelin_provider or MichelinProvider()
        self.advisor = advisor or GroqDiningAdvisor()
        self.cache = cache or build_cache(
            ttl_seconds=DEFAULT_MATCH_TTL_SECONDS, max_items=256, namespace="match"
        )
        self.michelin_cache = michelin_cache or build_cache(
            ttl_seconds=DEFAULT_MICHELIN_TTL_SECONDS,
            max_items=512,
            namespace="michelin",
        )
        self.advice_cache = advice_cache or build_cache(
            ttl_seconds=DEFAULT_ADVICE_TTL_SECONDS,
            max_items=512,
            namespace="advice",
        )

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
            "website": str(payload.get("website") or "").strip()[:500],
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
                "website",
                "tabelog_url",
                "latitude",
                "longitude",
            )
        )

    def match_michelin(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        place = self.validate_place(payload)
        key = self._cache_key(place)
        cached = self.michelin_cache.get(key)
        if cached:
            return {**cached, "cached": True}
        result = {
            "place": place,
            "michelin": self.michelin_provider.match(place),
            "cached": False,
        }
        self.michelin_cache.set(key, result)
        return result

    def advice(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        place = self.validate_place(payload.get("place") or {})
        candidate = payload.get("candidate")
        if not isinstance(candidate, Mapping) or not str(candidate.get("name") or "").strip():
            raise ValueError("找不到已配對的 Tabelog 店家")
        michelin = payload.get("michelin")
        if michelin is not None and not isinstance(michelin, Mapping):
            raise ValueError("Michelin 資料格式不正確")
        if not self.advisor.configured:
            return {"available": False, "advice": None, "cached": False}
        key = advice_cache_key(place, candidate, michelin if isinstance(michelin, Mapping) else None)
        cached = self.advice_cache.get(key)
        if cached:
            return {**cached, "cached": True}
        result = advice_response(self.advisor, place, candidate, michelin)
        result["available"] = True
        result["cached"] = False
        self.advice_cache.set(key, result)
        return result

    def match(
        self, payload: Mapping[str, Any], *, include_michelin: bool = True
    ) -> dict[str, Any]:
        place = self.validate_place(payload)
        key = self._cache_key(place)
        cached = self.cache.get(key)
        if cached:
            return {**cached, "cached": True}

        michelin = self.michelin_provider.match(place) if include_michelin else None
        try:
            candidates = rank_candidates(place, self.provider.search(place))
            tabelog_error = ""
        except Exception as exc:
            if not michelin or not include_michelin:
                raise
            candidates = []
            tabelog_error = str(exc) or "Tabelog 查詢失敗"
        selected = candidates[0] if candidates and candidates[0]["confidence"] != "low" else None
        if selected and include_michelin:
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
