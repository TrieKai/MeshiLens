from __future__ import annotations

import json
from pathlib import Path
import re
import threading
import time
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit

from .matching import haversine_meters, normalize_name, normalize_phone, similarity


MICHELIN_BASE_URL = "https://guide.michelin.com"
MICHELIN_JAPAN_URL = (
    "https://guide.michelin.com/tw/zh_TW/selection/japan/restaurants"
)
DEFAULT_DATA_PATH = Path(__file__).with_name("data") / "michelin-japan.json"
DETAIL_CACHE_SECONDS = 86_400
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


def normalize_website(value: str | None) -> str:
    """Canonicalize an official website URL for identity comparison."""
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    hostname = parsed.hostname.casefold().removeprefix("www.")
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port and not (
        parsed.scheme.lower() == "http" and port == 80
        or parsed.scheme.lower() == "https" and port == 443
    ):
        hostname = f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(("https", hostname, path, "", ""))


def parse_michelin_detail(html: str) -> dict[str, str]:
    """Extract identity fields from a server-rendered Michelin detail page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    phone = ""
    valid_restaurant = False
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(script.string or "null")
        except (json.JSONDecodeError, TypeError):
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, Mapping) and item.get("@type") == "Restaurant":
                valid_restaurant = True
                phone = str(item.get("telephone") or "").strip()
                break
        if phone:
            break

    website = ""
    link = soup.select_one('a[data-event="CTA_website"][href]')
    if link is not None:
        candidate = str(link.get("href") or "").strip()
        if normalize_website(candidate):
            website = candidate
    return {"phone": phone, "website": website} if valid_restaurant else {}


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
        self._detail_cache: dict[str, tuple[float, dict[str, str]]] = {}
        self._detail_lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.data_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _identity(
        place: Mapping[str, Any], tabelog: Mapping[str, Any] | None
    ) -> tuple[list[str], str, str, float | None, float | None]:
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
        phone = normalize_phone(str(place.get("phone") or ""))
        website = normalize_website(str(place.get("website") or ""))
        return names, phone, website, latitude, longitude

    def _fetch_detail(self, restaurant: Mapping[str, Any]) -> dict[str, str]:
        """Fetch one nearby detail page only when an identity signal needs resolving."""
        restaurant_id = str(restaurant.get("id") or restaurant.get("url") or "")
        now = time.monotonic()
        with self._detail_lock:
            cached = self._detail_cache.get(restaurant_id)
            if cached and now - cached[0] < DETAIL_CACHE_SECONDS:
                return dict(cached[1])
        try:
            from curl_cffi import requests

            response = requests.get(
                str(restaurant.get("url") or ""),
                headers={"Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7"},
                timeout=15,
                allow_redirects=True,
                impersonate="chrome",
            )
            response.raise_for_status()
            detail = parse_michelin_detail(response.text)
        except Exception:
            return {}
        if detail:
            with self._detail_lock:
                self._detail_cache[restaurant_id] = (now, dict(detail))
        return detail

    def _nearby_detail_enriched_restaurants(
        self,
        names: list[str],
        phone: str,
        website: str,
        latitude: float | None,
        longitude: float | None,
    ) -> list[Mapping[str, Any]]:
        """Resolve translated names with at most four close Michelin detail lookups."""
        if not (phone or website) or latitude is None or longitude is None:
            return self.restaurants
        replacements: dict[str, dict[str, Any]] = {}
        for restaurant in self.restaurants:
            distance = haversine_meters(
                latitude,
                longitude,
                _float(restaurant.get("latitude")),
                _float(restaurant.get("longitude")),
            )
            if distance is None or distance > 100:
                continue
            candidate_name = normalize_name(str(restaurant.get("name") or ""))
            name_score = max(
                (similarity(name, candidate_name) for name in names), default=0.0
            )
            if name_score >= 0.45:
                continue
            detail = self._fetch_detail(restaurant)
            if detail:
                replacements[str(restaurant.get("id") or restaurant.get("url"))] = {
                    **restaurant,
                    **detail,
                }
            if len(replacements) >= 4:
                break
        if not replacements:
            return self.restaurants
        return [
            replacements.get(str(restaurant.get("id") or restaurant.get("url")), restaurant)
            for restaurant in self.restaurants
        ]

    def match(
        self, place: Mapping[str, Any], tabelog: Mapping[str, Any] | None = None
    ) -> dict[str, Any] | None:
        names, phone, website, latitude, longitude = self._identity(place, tabelog)
        restaurants = self._nearby_detail_enriched_restaurants(
            names, phone, website, latitude, longitude
        )
        ranked: list[
            tuple[float, float, float | None, bool, bool, Mapping[str, Any]]
        ] = []
        for restaurant in restaurants:
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
            phone_match = bool(
                phone
                and phone == normalize_phone(str(restaurant.get("phone") or ""))
            )
            website_match = bool(
                website
                and website
                == normalize_website(str(restaurant.get("website") or ""))
            )
            identity_match = phone_match or website_match
            if distance is None:
                score = name_score * 100 + (85 if identity_match else 0)
                if not identity_match and name_score < 0.94:
                    continue
            else:
                if distance > 500:
                    continue
                distance_score = max(0.0, 1.0 - distance / 500)
                if identity_match:
                    identity_score = 70 if phone_match and website_match else 65
                    score = identity_score + distance_score * 30 + name_score * 5
                else:
                    score = name_score * 65 + distance_score * 35
                if not identity_match and name_score < 0.45 and distance > 25:
                    continue
            ranked.append(
                (score, name_score, distance, phone_match, website_match, restaurant)
            )

        if not ranked:
            return None
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        score, name_score, distance, phone_match, website_match, winner = ranked[0]
        identity_matches = [
            item
            for item in ranked
            if (item[4] if website_match else item[3])
        ]
        if phone_match or website_match:
            if distance is None and len(identity_matches) != 1:
                return None
            if len(identity_matches) > 1:
                second_distance = identity_matches[1][2]
                if (
                    distance is None
                    or second_distance is None
                    or second_distance - distance < 25
                ):
                    return None
            score = min(score, 100.0)
        close_matches = [
            item for item in ranked if item[2] is not None and item[2] <= 35
        ]
        unique_close_match = len(close_matches) == 1 and close_matches[0][5] is winner
        if not (phone_match or website_match) and score < 70 and not (
            unique_close_match and name_score >= 0.25
        ):
            return None

        result = dict(winner)
        reasons = []
        if phone_match:
            reasons.append("電話完全相同")
        if website_match:
            reasons.append("官方網站完全相同")
        if distance is not None:
            reasons.append(f"座標相距 {round(distance)} 公尺")
        result.update(
            match_score=round(score, 1),
            distance_meters=round(distance) if distance is not None else None,
            match_reasons=reasons,
            snapshot_fetched_at=self.dataset.get("fetched_at"),
            source_url=self.dataset.get("source_url") or MICHELIN_JAPAN_URL,
        )
        return result
