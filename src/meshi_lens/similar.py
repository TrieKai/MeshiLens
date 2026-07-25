"""Rank nearby-ish Tabelog search results without reading restaurant detail pages."""

from __future__ import annotations

from math import log10
import re
from typing import Any, Mapping

from .localization import tabelog_label_zh_hant, tabelog_station_zh_hant
from .matching import normalize_text


def _text(value: Any) -> str:
    return str(value or "").strip()


def _genres(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _normalized_station(value: Any) -> str:
    return normalize_text(_text(value).removesuffix("駅"))


def _price_midpoint(value: Any) -> float | None:
    amounts = [
        int(item.replace(",", ""))
        for item in re.findall(r"\d[\d,]*", _text(value))
    ]
    if not amounts:
        return None
    return sum(amounts[:2]) / min(len(amounts), 2)


def _price_similarity(seed: Mapping[str, Any], candidate: Mapping[str, Any]) -> tuple[float, str]:
    for field, label in (("dinner_price", "晚餐價位"), ("lunch_price", "午餐價位")):
        left = _price_midpoint(seed.get(field))
        right = _price_midpoint(candidate.get(field))
        if left is None or right is None:
            continue
        difference = abs(left - right)
        if difference <= 2_500:
            return 15.0, f"{label}接近"
        if difference <= 6_000:
            return 8.0, f"{label}相近"
    return 0.0, ""


def _same_genre(seed: Mapping[str, Any], candidate: Mapping[str, Any]) -> str:
    for left in _genres(seed.get("genres")):
        normalized_left = normalize_text(left)
        if not normalized_left:
            continue
        for right in _genres(candidate.get("genres")):
            normalized_right = normalize_text(right)
            if normalized_left == normalized_right:
                return left
            if len(normalized_left) >= 2 and (
                normalized_left in normalized_right or normalized_right in normalized_left
            ):
                return left
    return ""


def _rating_score(candidate: Mapping[str, Any]) -> float:
    try:
        rating = float(candidate.get("rating"))
    except (TypeError, ValueError):
        rating = 0.0
    try:
        review_count = max(0, int(candidate.get("review_count") or 0))
    except (TypeError, ValueError):
        review_count = 0
    return min(8.0, rating / 5 * 8) + min(7.0, log10(review_count + 1) / 3 * 7)


def _same_restaurant(seed: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    seed_url = _text(seed.get("url")).rstrip("/")
    candidate_url = _text(candidate.get("url")).rstrip("/")
    return bool(seed_url and seed_url == candidate_url)


def rank_similar_candidates(
    seed: Mapping[str, Any],
    candidates: list[Mapping[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return a small, explainable set of similar Tabelog search cards.

    Search results are intentionally used as-is.  This function never asks for a
    candidate's detail page, preserving the one-search-request budget per seed.
    """
    ranked: list[dict[str, Any]] = []
    seed_station = _normalized_station(seed.get("station"))
    seed_address = normalize_text(_text(seed.get("address")))
    for raw in candidates:
        if not isinstance(raw, Mapping) or _same_restaurant(seed, raw):
            continue
        name = _text(raw.get("name"))
        url = _text(raw.get("url"))
        if not name or not url:
            continue

        score = 0.0
        reasons: list[str] = []
        genre = _same_genre(seed, raw)
        if genre:
            score += 45
            reasons.append(f"同為{tabelog_label_zh_hant(genre)}")

        candidate_station = _normalized_station(raw.get("station"))
        if seed_station and candidate_station and seed_station == candidate_station:
            score += 25
            reasons.append(f"同為{tabelog_station_zh_hant(seed.get('station'))}")
        else:
            candidate_area = normalize_text(_text(raw.get("area")))
            if candidate_area and candidate_area in seed_address:
                score += 14
                reasons.append(f"同在{_text(raw.get('area'))}")

        price_score, price_reason = _price_similarity(seed, raw)
        if price_score:
            score += price_score
            reasons.append(price_reason)
        score += _rating_score(raw)

        # A keyword search can include loosely related restaurants.  Do not
        # promote a card unless it shares a strong cuisine or location signal.
        if score < 35:
            continue
        item = {
            "name": name,
            "rating": raw.get("rating"),
            "review_count": raw.get("review_count"),
            "url": url,
            "genres": _genres(raw.get("genres"))[:4],
            "station": _text(raw.get("station")),
            "area": _text(raw.get("area")),
            "lunch_price": _text(raw.get("lunch_price")),
            "dinner_price": _text(raw.get("dinner_price")),
            "similarity_score": round(min(score, 100)),
            "reasons": reasons[:3],
        }
        ranked.append(item)

    ranked.sort(
        key=lambda item: (
            -int(item["similarity_score"]),
            -(float(item["rating"]) if item["rating"] is not None else 0.0),
            -(int(item["review_count"]) if item["review_count"] is not None else 0),
            item["name"],
        )
    )
    return ranked[: max(1, min(limit, 5))]
