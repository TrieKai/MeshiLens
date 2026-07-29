"""Bounded AI reranking for structured Tabelog nearby candidates."""

from __future__ import annotations

import json
from math import isfinite
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .advice import DEFAULT_MODEL, GROQ_API_URL


MAX_SIMILAR_AI_CANDIDATES = 30
MAX_SIMILAR_AI_RECOMMENDATIONS = 6


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _genres(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item, 80) for item in value if _text(item, 80)][:4]


def _optional_number(value: Any) -> int | float | None:
    if value in ("", None):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def similar_ai_input(
    seed: Mapping[str, Any], candidates: list[Mapping[str, Any]]
) -> dict[str, Any]:
    """Return a compact, review-free prompt payload with opaque candidate IDs."""
    bounded = candidates[:MAX_SIMILAR_AI_CANDIDATES]
    return {
        "seed": {
            "name": _text(seed.get("name"), 160),
            "genres": _genres(seed.get("genres")),
            "station": _text(seed.get("station"), 100),
            "area": _text(seed.get("address"), 180),
            "lunch_price": _text(seed.get("lunch_price"), 80),
            "dinner_price": _text(seed.get("dinner_price"), 80),
        },
        "candidates": [
            {
                "id": f"c{index}",
                "name": _text(candidate.get("name"), 160),
                "genres": _genres(candidate.get("genres")),
                "genre_labels": _genres(candidate.get("genre_labels")),
                "rating": _optional_number(candidate.get("rating")),
                "review_count": _optional_number(candidate.get("review_count")),
                "station": _text(candidate.get("station"), 100),
                "area": _text(candidate.get("area"), 180),
                "lunch_price": _text(candidate.get("lunch_price"), 80),
                "dinner_price": _text(candidate.get("dinner_price"), 80),
            }
            for index, candidate in enumerate(bounded)
        ],
    }


def validate_similar_ai_ranking(
    value: Any, *, candidate_count: int
) -> list[dict[str, Any]]:
    """Validate that the model selected only supplied opaque candidate IDs."""
    if not isinstance(value, Mapping):
        raise ValueError("AI 相似店家排序格式不正確")
    ranking = value.get("ranking")
    if not isinstance(ranking, list) or len(ranking) > MAX_SIMILAR_AI_RECOMMENDATIONS:
        raise ValueError("AI 相似店家排序格式不正確")

    allowed_ids = {
        f"c{index}" for index in range(min(candidate_count, MAX_SIMILAR_AI_CANDIDATES))
    }
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in ranking:
        if not isinstance(item, Mapping):
            raise ValueError("AI 相似店家排序格式不正確")
        candidate_id = _text(item.get("id"), 8)
        if candidate_id not in allowed_ids or candidate_id in seen:
            raise ValueError("AI 回傳未知的相似店家")
        try:
            score = float(item.get("score"))
        except (TypeError, ValueError) as exc:
            raise ValueError("AI 相似店家分數格式不正確") from exc
        if not isfinite(score) or not 0 <= score <= 100:
            raise ValueError("AI 相似店家分數格式不正確")
        reason = _text(item.get("reason"), 80)
        if not reason:
            raise ValueError("AI 相似店家缺少排序理由")
        validated.append(
            {"id": candidate_id, "score": round(score), "reason": reason}
        )
        seen.add(candidate_id)
    return validated


def apply_similar_ai_ranking(
    candidates: list[Mapping[str, Any]], ranking: Any
) -> list[dict[str, Any]]:
    """Map a validated opaque-ID ranking back onto server-owned candidates."""
    validated = validate_similar_ai_ranking(
        {"ranking": ranking}, candidate_count=len(candidates)
    )
    recommendations: list[dict[str, Any]] = []
    for item in validated:
        index = int(item["id"][1:])
        candidate = dict(candidates[index])
        candidate["similarity_score"] = item["score"]
        candidate["reasons"] = [item["reason"]]
        recommendations.append(candidate)
    return recommendations


class GroqSimilarRanker:
    """One-call Groq client for semantic filtering and ranking of nearby candidates."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 12,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
        self.model = (
            model
            or os.environ.get("GROQ_SIMILAR_MODEL")
            or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        )
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _request_body(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        is_qwen = self.model.startswith("qwen/")
        instructions = (
            "你是 MeshiLens 的相似店家排序器。只根據輸入的結構化店家資料判斷用餐目的、"
            "完整料理類別、價位與品質是否相近。不可只因共有「咖啡廳、酒吧、居酒屋、"
            "食堂」等泛用類別就判定高度相似；店名與其他類別顯示為網咖、餐酒館或不同"
            "料理業態時應降權。評分與評論數只能作為同類店家的排序依據。不得假設菜色、"
            "口味、評論內容、營業狀態或輸入未提供的事實。"
            "只能從 candidates 的 id 選擇最多 6 家，也可以全部不選；不得新增、改寫或"
            "猜測候選 id。以繁體中文輸出 JSON 物件，格式固定為 "
            '{"ranking":[{"id":"c0","score":85,"reason":"分類與價位相近"}]}。'
            "score 必須是 0 至 100 的數字，reason 最多 30 字。只輸出 JSON。"
        )
        return {
            "model": self.model,
            "reasoning_effort": "none" if is_qwen else "low",
            "reasoning_format": "hidden",
            "temperature": 0.2,
            "max_completion_tokens": 900,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{instructions}\n\n結構化候選資料："
                        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
                    ),
                }
            ],
        }

    def rank(
        self, seed: Mapping[str, Any], candidates: list[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        if not self.configured:
            raise RuntimeError("AI 相似店家排序尚未設定")
        payload = similar_ai_input(seed, candidates)
        request = Request(
            GROQ_API_URL,
            data=json.dumps(self._request_body(payload)).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "MeshiLens/0.5 (+https://meshilens.vercel.app)",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                response_payload = json.loads(response.read().decode("utf-8"))
            content = response_payload["choices"][0]["message"]["content"]
            decoded = json.loads(content)
            return validate_similar_ai_ranking(
                decoded, candidate_count=len(payload["candidates"])
            )
        except HTTPError as exc:
            if exc.code == 429:
                raise RuntimeError("AI 相似店家排序暫時忙碌") from exc
            raise RuntimeError("AI 相似店家排序暫時無法取得") from exc
        except (
            URLError,
            TimeoutError,
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            raise RuntimeError("AI 相似店家排序暫時無法取得") from exc
