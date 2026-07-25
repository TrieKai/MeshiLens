"""Rank nearby-ish Tabelog search results without reading restaurant detail pages."""

from __future__ import annotations

from math import log10
import re
from typing import Any, Mapping

from .localization import tabelog_label_zh_hant, tabelog_station_zh_hant
from .matching import normalize_text

PREFECTURE_RE = re.compile(r"(?:東京都|北海道|(?:京都|大阪)府|.{2,3}県)")
QUOTED_STATION_RE = re.compile(r"[「『]([^」』]+)[」』]")
LINE_QUALIFIED_STATION_RE = re.compile(
    r"^(?:(?:JR|東京メトロ|都営(?:地下鉄)?|東急|京王|京急|小田急|西武|東武|相鉄|京成)[^「『]*線)(.+?駅?)$"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _genres(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _station_name(value: Any) -> str:
    """Extract the station name from Maps' line-qualified station labels."""
    station = _text(value)
    quoted = QUOTED_STATION_RE.search(station)
    if quoted:
        return quoted.group(1).strip()
    line_qualified = LINE_QUALIFIED_STATION_RE.match(station)
    return line_qualified.group(1).strip() if line_qualified else station


def _normalized_station(value: Any) -> str:
    return normalize_text(_station_name(value).removesuffix("駅"))


def _address_locality(value: Any) -> str:
    """Return the city/ward-like segment used for a conservative nearby check."""
    address = _text(value)
    prefecture = PREFECTURE_RE.search(address)
    if prefecture:
        address = address[prefecture.end() :]
    match = re.match(r"([^\d\s,，]{1,14}?(?:区|市|町|村))", address)
    return normalize_text(match.group(1)) if match else ""


def _nearby_location(
    seed: Mapping[str, Any], candidate: Mapping[str, Any]
) -> tuple[float, str]:
    """Return a verified local signal; never treat cuisine alone as nearby."""
    seed_station = _normalized_station(seed.get("station"))
    candidate_station = _normalized_station(candidate.get("station"))
    if seed_station and candidate_station and seed_station == candidate_station:
        station_label = tabelog_station_zh_hant(_station_name(seed.get("station")))
        if not station_label.endswith("站"):
            station_label = f"{station_label}站"
        return 25.0, f"同為{station_label}"

    seed_address = normalize_text(_text(seed.get("address")))
    candidate_area = _text(candidate.get("area"))
    normalized_area = normalize_text(candidate_area)
    if normalized_area and len(normalized_area) >= 2 and normalized_area in seed_address:
        return 14.0, f"同在{candidate_area}"

    seed_prefecture = normalize_text(PREFECTURE_RE.search(_text(seed.get("address"))).group(0)) if PREFECTURE_RE.search(_text(seed.get("address"))) else ""
    candidate_prefecture_match = PREFECTURE_RE.search(_text(candidate.get("address")))
    candidate_prefecture = normalize_text(candidate_prefecture_match.group(0)) if candidate_prefecture_match else ""
    seed_locality = _address_locality(seed.get("address"))
    candidate_locality = _address_locality(candidate.get("address"))
    if (
        seed_prefecture
        and seed_prefecture == candidate_prefecture
        and seed_locality
        and seed_locality == candidate_locality
    ):
        return 18.0, "同一行政區"
    return 0.0, ""


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


def rank_similar_candidates_with_diagnostics(
    seed: Mapping[str, Any],
    candidates: list[Mapping[str, Any]],
    *,
    limit: int = 3,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Rank search cards and return aggregate, non-identifying filter diagnostics.

    Search results are intentionally used as-is.  This function never asks for a
    candidate's detail page, preserving the one-search-request budget per seed.
    """
    ranked: list[dict[str, Any]] = []
    diagnostics = {
        "returned_count": 0,
        "same_restaurant_count": 0,
        "unverified_location_count": 0,
        "below_quality_count": 0,
    }
    for raw in candidates:
        if not isinstance(raw, Mapping):
            continue
        diagnostics["returned_count"] += 1
        if _same_restaurant(seed, raw):
            diagnostics["same_restaurant_count"] += 1
            continue
        name = _text(raw.get("name"))
        url = _text(raw.get("url"))
        if not name or not url:
            diagnostics["below_quality_count"] += 1
            continue

        score = 0.0
        reasons: list[str] = []
        genre = _same_genre(seed, raw)
        if genre:
            score += 45
            reasons.append(f"同為{tabelog_label_zh_hant(genre)}")

        location_score, location_reason = _nearby_location(seed, raw)
        # Search cards sometimes contain broad ranking results.  A matching
        # cuisine is not sufficient: recommend only a verifiably nearby card.
        if not location_score:
            diagnostics["unverified_location_count"] += 1
            continue
        score += location_score
        reasons.append(location_reason)

        price_score, price_reason = _price_similarity(seed, raw)
        if price_score:
            score += price_score
            reasons.append(price_reason)
        score += _rating_score(raw)

        # A keyword search can include loosely related restaurants.  Location
        # is already mandatory; retain a small quality threshold as well.
        if score < 35:
            diagnostics["below_quality_count"] += 1
            continue
        item = {
            "name": name,
            "rating": raw.get("rating"),
            "review_count": raw.get("review_count"),
            "url": url,
            "address": _text(raw.get("address")),
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
    recommendations = ranked[: max(1, min(limit, 5))]
    diagnostics["recommendation_count"] = len(recommendations)
    return recommendations, diagnostics


def rank_similar_candidates(
    seed: Mapping[str, Any],
    candidates: list[Mapping[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return a small, explainable set of similar Tabelog search cards."""
    recommendations, _ = rank_similar_candidates_with_diagnostics(
        seed, candidates, limit=limit
    )
    return recommendations
