"""Generate concise dining advice from MeshiLens' structured restaurant facts.

No review text, reviewer identity, photos, or Google Maps review content is included
in the request.  The optional Groq call happens only after the normal matching result
is available, so it can never block restaurant matching.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"
MAX_FACT_VALUE = 240


def _text(value: Any, limit: int = MAX_FACT_VALUE) -> str:
    return " ".join(str(value or "").split())[:limit]


def advice_facts(
    place: Mapping[str, Any],
    candidate: Mapping[str, Any],
    michelin: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return the bounded, review-free facts permitted in an advice prompt."""
    payment = candidate.get("payment")
    reservation_status = _text(candidate.get("reservation_status"))
    genres = candidate.get("genres", [])
    if isinstance(genres, str):
        genres = [genres]
    if not isinstance(genres, list):
        genres = []
    hyakumeiten = candidate.get("hyakumeiten", [])
    if not isinstance(hyakumeiten, list):
        hyakumeiten = []
    facts: dict[str, Any] = {
        "restaurant_name": _text(candidate.get("name") or place.get("name"), 120),
        "area": _text(candidate.get("address") or place.get("address")),
        "cuisine": [_text(item, 80) for item in genres if _text(item, 80)][:4],
        "tabelog_rating": candidate.get("rating"),
        "tabelog_review_count": candidate.get("review_count"),
        "lunch_price": _text(candidate.get("lunch_price")),
        "dinner_price": _text(candidate.get("dinner_price")),
        "reservation_status": reservation_status,
        "has_online_reservation": bool(candidate.get("reservation_url")),
        "payment_available": bool(payment),
        "hyakumeiten_years": sorted(
            {
                int(item.get("year"))
                for item in hyakumeiten
                if isinstance(item, Mapping) and str(item.get("year") or "").isdigit()
            },
            reverse=True,
        )[:8],
        "michelin_distinction": _text((michelin or {}).get("distinction_label")),
        "michelin_green_star": bool((michelin or {}).get("green_star")),
    }
    return {key: value for key, value in facts.items() if value not in ("", [], None)}


def _validate_advice(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("AI 回傳格式不正確")

    def clean_list(key: str, max_items: int, max_length: int) -> list[str]:
        items = value.get(key, [])
        if not isinstance(items, list):
            return []
        return [_text(item, max_length) for item in items if _text(item, max_length)][:max_items]

    summary = _text(value.get("summary"), 220)
    if not summary:
        raise ValueError("AI 未產生用餐建議")
    return {
        "headline": _text(value.get("headline"), 60) or "用餐建議",
        "summary": summary,
        "best_for": clean_list("best_for", 3, 48),
        "cautions": clean_list("cautions", 2, 60),
        "evidence": clean_list("evidence", 4, 72),
    }


class GroqDiningAdvisor:
    """Small dependency-free client for an optional Groq-backed dining summary."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 12,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def summarize(
        self,
        place: Mapping[str, Any],
        candidate: Mapping[str, Any],
        michelin: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("AI 用餐建議尚未設定")
        facts = advice_facts(place, candidate, michelin)
        request_body = {
            "model": self.model,
            "reasoning_effort": "low",
            "temperature": 0.2,
            "max_completion_tokens": 300,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 MeshiLens 的用餐建議助手。只可根據提供的 JSON 結構化資料，以繁體中文"
                        "輸出 JSON 物件：headline、summary、best_for、cautions、evidence。"
                        "不得假設菜色、口味、排隊、人潮、服務品質、營業狀態或評論意見；資料不足時要"
                        "明確說明。summary 最多 100 字，evidence 只能重述輸入中可驗證的事實。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(facts, ensure_ascii=False, separators=(",", ":")),
                },
            ],
        }
        request = Request(
            GROQ_API_URL,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429:
                raise RuntimeError("AI 暫時忙碌，請稍後再試") from exc
            raise RuntimeError("AI 用餐建議暫時無法取得") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("AI 用餐建議暫時無法取得") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
            return _validate_advice(json.loads(content))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("AI 用餐建議暫時無法取得") from exc


def advice_response(
    advisor: GroqDiningAdvisor,
    place: Mapping[str, Any],
    candidate: Mapping[str, Any],
    michelin: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Shape returned by the API, including provenance for the UI."""
    return {
        "advice": advisor.summarize(place, candidate, michelin),
        "model": advisor.model,
        "source": "MeshiLens 結構化店家資料（非評論摘要）",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
