from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urljoin

from .matching import haversine_meters, normalize_name, similarity


MICHELIN_BASE_URL = "https://guide.michelin.com"
MICHELIN_JAPAN_URL = (
    "https://guide.michelin.com/tw/zh_TW/selection/japan/restaurants"
)
DEFAULT_DATA_PATH = Path(__file__).with_name("data") / "michelin-japan.json"
DISTINCTION_LABELS = {
    "THREE_STARS": "米其林三星",
    "TWO_STARS": "米其林二星",
    "ONE_STAR": "米其林一星",
    "BIB_GOURMAND": "必比登推介",
    "SELECTED": "米其林指南入選",
}


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_michelin_listing(html: str) -> list[dict[str, Any]]:
    """Parse the server-rendered restaurant cards on a Michelin listing page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    restaurants: list[dict[str, Any]] = []
    results = soup.select_one(".js-restaurant__list_items")
    if results is None:
        return restaurants
    for card in results.select(".js-restaurant__list_item"):
        title_link = card.select_one(".card__menu-content--title a[href]")
        if title_link is None:
            continue
        bookmark = card.select_one(".js-bookmark-restaurant")
        distinction = str(
            bookmark.get("data-distinction") if bookmark is not None else ""
        ).strip()
        if distinction not in DISTINCTION_LABELS:
            distinction = "SELECTED"

        scores = [
            re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
            for node in card.select(".card__menu-footer--score")
        ]
        price = ""
        cuisine = ""
        if len(scores) > 1:
            details = [part.strip() for part in scores[1].split("·", 1)]
            price = details[0] if details else ""
            cuisine = details[1] if len(details) > 1 else ""

        green_star = (
            str(bookmark.get("data-green-star") if bookmark is not None else "")
            .strip()
            .lower()
            == "true"
        )
        restaurant = {
            "id": str(card.get("data-id") or ""),
            "name": title_link.get_text(" ", strip=True),
            "url": urljoin(MICHELIN_BASE_URL, str(title_link.get("href") or "")),
            "latitude": _float(card.get("data-lat")),
            "longitude": _float(card.get("data-lng")),
            "location": scores[0] if scores else "",
            "price": price,
            "cuisine": cuisine,
            "distinction": distinction,
            "distinction_label": DISTINCTION_LABELS[distinction],
            "green_star": green_star,
        }
        if restaurant["id"] and restaurant["name"] and restaurant["url"]:
            restaurants.append(restaurant)
    return restaurants


def michelin_listing_meta(html: str) -> tuple[int, int]:
    """Return the reported result count and final SSR page number."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    heading = soup.select_one(".search-results__stats")
    count_match = re.search(
        r"共\s*([0-9,]+)\s*個餐廳", heading.get_text(" ", strip=True) if heading else ""
    )
    count = int(count_match.group(1).replace(",", "")) if count_match else 0
    pages = [1]
    for anchor in soup.select('a[href*="/restaurants/page/"]'):
        match = re.search(r"/restaurants/page/(\d+)", str(anchor.get("href") or ""))
        if match:
            pages.append(int(match.group(1)))
    return count, max(pages)


class MichelinProvider:
    """Match Google Maps places against a locally stored Michelin Japan snapshot."""

    def __init__(self, data_path: Path | str = DEFAULT_DATA_PATH) -> None:
        self.data_path = Path(data_path)
        self.dataset = self._load()
        self.restaurants = list(self.dataset.get("restaurants") or [])

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.data_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _identity(
        place: Mapping[str, Any], tabelog: Mapping[str, Any] | None
    ) -> tuple[list[str], float | None, float | None]:
        names = [
            normalize_name(str(place.get("name") or "")),
            normalize_name(str(place.get("alternate_name") or "")),
            normalize_name(str((tabelog or {}).get("name") or "")),
        ]
        names = list(dict.fromkeys(name for name in names if name))
        latitude = _float(place.get("latitude"))
        longitude = _float(place.get("longitude"))
        if latitude is None or longitude is None:
            latitude = _float((tabelog or {}).get("latitude"))
            longitude = _float((tabelog or {}).get("longitude"))
        return names, latitude, longitude

    def match(
        self, place: Mapping[str, Any], tabelog: Mapping[str, Any] | None = None
    ) -> dict[str, Any] | None:
        names, latitude, longitude = self._identity(place, tabelog)
        ranked: list[tuple[float, float, float | None, Mapping[str, Any]]] = []
        for restaurant in self.restaurants:
            candidate_name = normalize_name(str(restaurant.get("name") or ""))
            name_score = max(
                (similarity(name, candidate_name) for name in names), default=0.0
            )
            distance = haversine_meters(
                latitude,
                longitude,
                _float(restaurant.get("latitude")),
                _float(restaurant.get("longitude")),
            )
            if distance is None:
                score = name_score * 100
                if name_score < 0.94:
                    continue
            else:
                if distance > 500:
                    continue
                distance_score = max(0.0, 1.0 - distance / 500)
                score = name_score * 65 + distance_score * 35
                if name_score < 0.45 and distance > 25:
                    continue
            ranked.append((score, name_score, distance, restaurant))

        if not ranked:
            return None
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        score, name_score, distance, winner = ranked[0]
        close_matches = [
            item for item in ranked if item[2] is not None and item[2] <= 35
        ]
        unique_close_match = len(close_matches) == 1 and close_matches[0][3] is winner
        if score < 70 and not (unique_close_match and name_score >= 0.25):
            return None

        result = dict(winner)
        result.update(
            match_score=round(score, 1),
            distance_meters=round(distance) if distance is not None else None,
            snapshot_fetched_at=self.dataset.get("fetched_at"),
            source_url=self.dataset.get("source_url") or MICHELIN_JAPAN_URL,
        )
        return result
