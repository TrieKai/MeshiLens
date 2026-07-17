from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt
import re
import unicodedata
from typing import Any, Mapping


TYPE_WORDS = (
    "うなぎ",
    "鰻",
    "割烹",
    "食堂",
    "レストラン",
    "料理店",
    "居酒屋",
    "喫茶店",
    "カフェ",
)
BRANCH_WORDS = ("本店", "支店", "駅前店", "別館", "新館")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff]", "", value)


def normalize_name(value: str | None) -> str:
    normalized = normalize_text(value)
    for word in (*TYPE_WORDS, *BRANCH_WORDS):
        normalized = normalized.replace(normalize_text(word), "")
    return normalized


def normalize_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", value or ""))
    if digits.startswith("81") and len(digits) in (11, 12):
        digits = f"0{digits[2:]}"
    return digits


def normalize_address(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = re.sub(r"〒?\d{3}-?\d{4}", "", normalized)
    normalized = normalized.replace("番地", "-").replace("番", "-").replace("号", "")
    return re.sub(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff]", "", normalized)


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left in right or right in left:
        shorter, longer = sorted((len(left), len(right)))
        return 0.88 + 0.12 * (shorter / longer)
    return SequenceMatcher(None, left, right).ratio()


def haversine_meters(
    lat1: float | None,
    lng1: float | None,
    lat2: float | None,
    lng2: float | None,
) -> float | None:
    if None in (lat1, lng1, lat2, lng2):
        return None
    earth_radius = 6_371_000
    lat_delta = radians(float(lat2) - float(lat1))
    lng_delta = radians(float(lng2) - float(lng1))
    a = sin(lat_delta / 2) ** 2 + cos(radians(float(lat1))) * cos(
        radians(float(lat2))
    ) * sin(lng_delta / 2) ** 2
    return 2 * earth_radius * asin(sqrt(a))


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class MatchResult:
    score: float
    confidence: str
    reasons: tuple[str, ...]
    distance_meters: float | None


def score_candidate(place: Mapping[str, Any], candidate: Mapping[str, Any]) -> MatchResult:
    reasons: list[str] = []
    score = 0.0

    if candidate.get("direct_source"):
        return MatchResult(
            score=98.0,
            confidence="high",
            reasons=("Google Maps 直接提供 Tabelog 店家連結",),
            distance_meters=None,
        )

    place_phone = normalize_phone(str(place.get("phone") or ""))
    candidate_phone = normalize_phone(str(candidate.get("phone") or ""))
    if place_phone and candidate_phone and place_phone == candidate_phone:
        score += 52
        reasons.append("電話完全相同")

    candidate_name = normalize_name(str(candidate.get("name") or ""))
    place_names = (
        normalize_name(str(place.get("name") or "")),
        normalize_name(str(place.get("alternate_name") or "")),
    )
    name_score = max(
        (similarity(place_name, candidate_name) for place_name in place_names),
        default=0.0,
    )
    score += name_score * 25
    if name_score >= 0.88:
        reasons.append("店名高度相似")

    address_score = similarity(
        normalize_address(str(place.get("address") or "")),
        normalize_address(str(candidate.get("address") or "")),
    )
    if address_score >= 0.45:
        score += address_score * 35
        if address_score >= 0.82:
            reasons.append("地址高度相似")

    distance = haversine_meters(
        _float(place.get("latitude")),
        _float(place.get("longitude")),
        _float(candidate.get("latitude")),
        _float(candidate.get("longitude")),
    )
    if distance is not None:
        if distance <= 100:
            score += 52
            reasons.append(f"座標相距 {round(distance)} 公尺")
        elif distance <= 1_000:
            score += 52 * (1_000 - distance) / 900

    score = min(round(score, 1), 100.0)
    confidence = "high" if score >= 75 else "medium" if score >= 52 else "low"
    return MatchResult(score, confidence, tuple(reasons), distance)


def rank_candidates(
    place: Mapping[str, Any], candidates: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        match = score_candidate(place, candidate)
        enriched = dict(candidate)
        enriched.update(
            score=match.score,
            confidence=match.confidence,
            match_reasons=list(match.reasons),
            distance_meters=(
                round(match.distance_meters) if match.distance_meters is not None else None
            ),
        )
        ranked.append(enriched)
    ranked.sort(
        key=lambda item: (
            item["score"],
            int(item.get("rating") is not None),
            int(item.get("review_count") or 0),
        ),
        reverse=True,
    )

    if ranked:
        winner = ranked[0]
        winner_phone = normalize_phone(str(winner.get("phone") or ""))
        winner_name = normalize_name(str(winner.get("name") or ""))
        duplicates = []
        for other in ranked[1:]:
            other_phone = normalize_phone(str(other.get("phone") or ""))
            candidate_distance = haversine_meters(
                _float(winner.get("latitude")),
                _float(winner.get("longitude")),
                _float(other.get("latitude")),
                _float(other.get("longitude")),
            )
            same_phone = bool(
                winner_phone and other_phone and winner_phone == other_phone
            )
            same_name = similarity(
                winner_name, normalize_name(str(other.get("name") or ""))
            ) >= 0.95
            same_location = candidate_distance is not None and candidate_distance <= 50
            if same_name and same_location and (same_phone or not winner_phone):
                duplicates.append(other)
        if duplicates and winner.get("review_count"):
            winner["match_reasons"].append("同址重複頁面中評論資料較完整")
            winner["duplicate_urls"] = [item.get("url") for item in duplicates]
    return ranked
