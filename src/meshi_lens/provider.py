from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import re
import threading
import time
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from .localization import tabelog_label_zh_hant
from .matching import haversine_meters, normalize_name, normalize_phone, normalize_text, similarity


TABELOG_RESULT_RE = re.compile(
    r"https?://tabelog\.com/(?:en/|tw/|cn/|kr/)?"
    r"(?P<path>[a-z0-9-]+/A\d+/A\d+/\d+)/?",
    re.IGNORECASE,
)
PERIPHERAL_GENRE_SLUGS = {
    # Tabelog's current official peripheral-map cuisine links.  Keeping these
    # direct avoids an otherwise necessary discovery request for common cases.
    "和食": "washoku", "日本料理": "japanese", "寿司": "sushi", "鮨": "sushi",
    "海鮮・魚介": "seafood", "海鮮": "seafood", "そば（蕎麦）": "soba", "そば": "soba",
    "うなぎ": "unagi", "焼き鳥": "yakitori", "お好み焼き": "okonomiyaki",
    "もんじゃ焼き": "monjya", "洋食": "yoshoku", "フレンチ": "french",
    "イタリアン": "italian", "スペイン料理": "spain", "ステーキ": "steak",
    "中華料理": "chinese", "韓国料理": "korea", "タイ料理": "thai",
    "ラーメン": "ramen", "カレー": "curry", "もつ鍋": "motsu", "鍋": "nabe",
    "居酒屋": "izakaya", "パン": "pan", "スイーツ": "sweets", "バー・お酒": "bar",
    "天ぷら": "tempura", "焼肉": "yakiniku", "料理旅館": "ryokan", "ビストロ": "bistro",
    "ハンバーグ": "hamburgersteak", "ハンバーガー": "hamburger", "とんかつ": "tonkatsu",
    "串揚げ": "kushiage", "うどん": "udon", "しゃぶしゃぶ": "syabusyabu",
    "沖縄料理": "okinawafood", "パスタ": "pasta", "ピザ": "pizza", "餃子": "gyouza",
    "ホルモン": "horumon", "カフェ": "cafe", "喫茶店": "kissaten", "ケーキ": "cake",
    "タピオカ": "tapioca", "食堂": "teishoku", "ビュッフェ・バイキング": "viking",
}
HYAKUMEITEN_URL_RE = re.compile(
    r"https?://award\.tabelog\.com/hyakumeiten/(?P<slug>[^/]+)/(?P<year>20\d{2})/?",
    re.IGNORECASE,
)
HYAKUMEITEN_LABEL_RE = re.compile(
    r"^(?:食べログ\s*)?(?P<descriptor>.+?)\s*百名店\s*(?P<year>20\d{2})\s*選出店$"
)
PAYMENT_MARKER_RE = re.compile(
    r"(?P<kind>カード|クレジットカード|電子マネー|QRコード決済)\s*(?P<status>不可|可)"
)
PERIPHERAL_CATEGORY_RE = re.compile(
    r"/(?:en/|tw/|cn/|kr/)?[a-z0-9-]+/A\d+/A\d+/\d+/peripheral_map/"
    r"(?P<slug>[a-z][a-z0-9_-]*)/?(?:[?#].*)?$",
    re.IGNORECASE,
)


def _model_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    return {
        key: getattr(value, key)
        for key in dir(value)
        if not key.startswith("_")
        and not callable(getattr(value, key, None))
        and key
        in {
            "name",
            "rating",
            "review_count",
            "address",
            "phone",
            "url",
            "latitude",
            "longitude",
            "genres",
            "station",
            "lunch_price",
            "dinner_price",
            "business_hours",
            "closed_days",
            "reservation_url",
            "has_reservation",
        }
    }


def _first(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _coordinates(data: Mapping[str, Any]) -> tuple[Any, Any]:
    latitude = _first(data, "latitude", "lat")
    longitude = _first(data, "longitude", "lng", "lon")
    coordinates = data.get("coordinates") or data.get("location")
    if isinstance(coordinates, Mapping):
        latitude = latitude or _first(coordinates, "latitude", "lat")
        longitude = longitude or _first(coordinates, "longitude", "lng", "lon")
    return latitude, longitude


def stable_reservation_url(value: Any) -> str:
    """Keep actionable booking URLs and reject Tabelog's generic help/account pages."""
    url = str(value or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    path = parsed.path.rstrip("/").lower()
    generic_paths = {
        "/ai_request_booking/guide/index",
        "/yoyaku/tabelog_booking/send_remind",
    }
    return "" if path in generic_paths else url


def restaurant_to_dict(value: Any) -> dict[str, Any]:
    data = _model_dict(value)
    latitude, longitude = _coordinates(data)
    genres = _first(data, "genres", "genre", "categories") or []
    if isinstance(genres, str):
        genres = [genres]
    return {
        "name": _first(data, "name", "restaurant_name", "display_name") or "",
        "rating": _first(data, "rating", "score"),
        "review_count": _first(data, "review_count", "reviews_count", "reviewCount"),
        "address": _first(data, "address", "full_address") or "",
        "phone": _first(data, "phone", "telephone", "tel") or "",
        "url": _first(data, "url", "restaurant_url") or "",
        "latitude": latitude,
        "longitude": longitude,
        "genres": genres,
        "area": _first(data, "area", "location_area") or "",
        "station": _first(data, "station", "nearest_station") or "",
        "lunch_price": _first(data, "lunch_price", "lunch_budget") or "",
        "dinner_price": _first(data, "dinner_price", "dinner_budget") or "",
        "business_hours": _first(data, "business_hours", "hours") or "",
        "closed_days": _first(data, "closed_days", "regular_holiday") or "",
        "reservation_url": stable_reservation_url(
            _first(data, "reservation_url", "booking_url")
        ),
        "has_reservation": bool(data.get("has_reservation")),
    }


def merge_candidate_details(
    summary: Mapping[str, Any], detail: Mapping[str, Any]
) -> dict[str, Any]:
    """Prefer non-empty detail fields while retaining search-card fallbacks."""
    merged = dict(summary)
    merged.update(
        {
            key: value
            for key, value in detail.items()
            if value not in (None, "", [], {})
        }
    )
    return merged


def area_from_address(address: str) -> str | None:
    normalized = address.replace("日本、", "").replace("日本,", "")
    match = re.search(r"(?:〒\s*\d{3}-?\d{4}\s*)?([^\s,，]{2,12}?[都道府県])", normalized)
    return match.group(1) if match else None


def web_search_queries(place: Mapping[str, Any]) -> list[str]:
    """Build identity-focused fallbacks for translated Google Maps names."""
    queries: list[str] = []
    raw_phone = str(place.get("phone") or "").strip()
    if raw_phone:
        local_phone = re.sub(r"^\+?81[\s().-]*", "0", raw_phone)
        local_phone = re.sub(r"[^\d-]", "", local_phone)
        if local_phone:
            queries.append(f'site:tabelog.com "{local_phone}"')

    for value in (place.get("alternate_name"), place.get("name")):
        name = str(value or "").replace('"', "").strip()
        query = f'site:tabelog.com "{name}"' if name else ""
        if query and query not in queries:
            queries.append(query)
    return queries


def canonical_restaurant_url(value: str) -> str | None:
    """Reduce a Tabelog result/review URL to its Japanese restaurant page."""
    decoded = unquote(value)
    if "duckduckgo.com/l/" in decoded:
        redirected = parse_qs(urlparse(decoded).query).get("uddg", [])
        if redirected:
            decoded = unquote(redirected[0])
    match = TABELOG_RESULT_RE.search(decoded)
    return f"https://tabelog.com/{match.group('path')}/" if match else None


def tabelog_area_path(value: str) -> str:
    match = TABELOG_RESULT_RE.search(str(value or ""))
    if not match:
        return ""
    return "/".join(match.group("path").split("/")[:3])


def tabelog_peripheral_map_url(value: str, genre_slug: str = "") -> str:
    """Build Tabelog's restaurant-specific nearby-restaurants URL."""
    canonical = canonical_restaurant_url(value)
    if not canonical:
        return ""
    suffix = f"{genre_slug.strip('/')}/" if genre_slug else ""
    return f"{canonical}peripheral_map/{suffix}"


def parse_peripheral_restaurants(html: str, limit: int = 20) -> list[dict[str, Any]]:
    """Parse the compact restaurant cards on a Tabelog peripheral-map page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in soup.select("h5 a[href], h4 a[href], .list-rst__rst-name-target[href]"):
        url = canonical_restaurant_url(str(anchor.get("href") or ""))
        name = anchor.get_text(" ", strip=True)
        if not url or not name or url in seen:
            continue
        card = anchor.find_parent(["li", "div"])
        text = card.get_text(" ", strip=True) if card else ""
        rating_match = re.search(r"\b([2-4]\.\d{2})\b", text)
        reviews_match = re.search(r"([\d,]+)人", text)
        parts = [part.strip() for part in text.split("/") if part.strip()]
        genres = []
        if len(parts) >= 2:
            genre_text = re.sub(r"\s+[2-4]\.\d{2}\s+[\d,]+人.*$", "", parts[1])
            genres = [item.strip() for item in genre_text.split("、") if item.strip()]
        found.append({
            "name": name, "url": url, "rating": float(rating_match.group(1)) if rating_match else None,
            "review_count": int(reviews_match.group(1).replace(",", "")) if reviews_match else None,
            "genres": genres, "area": parts[0] if parts else "", "station": "", "address": "",
        })
        seen.add(url)
        if len(found) >= max(1, min(limit, 20)):
            break
    return found


def peripheral_genre_slug(genres: Any) -> str:
    values = [genres] if isinstance(genres, str) else genres if isinstance(genres, list) else []
    for value in values:
        text = str(value or "")
        best: tuple[int, str] | None = None
        for genre, slug in PERIPHERAL_GENRE_SLUGS.items():
            if genre in text:
                score = len(genre)
                if best is None or score > best[0]:
                    best = (score, slug)
        if best:
            return best[1]
    return ""


def parse_peripheral_genre_links(html: str) -> list[dict[str, str]]:
    """Return the official cuisine filters offered by a nearby-restaurants page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        label = anchor.get_text(" ", strip=True)
        href = urljoin("https://tabelog.com", str(anchor.get("href") or ""))
        match = PERIPHERAL_CATEGORY_RE.search(href)
        if not label or not match:
            continue
        slug = match.group("slug").lower()
        if slug in seen:
            continue
        links.append({"label": label, "slug": slug})
        seen.add(slug)
    return links


def peripheral_genre_slug_from_links(genres: Any, links: list[Mapping[str, Any]]) -> str:
    """Match Tabelog's own category labels to the selected restaurant genres."""
    values = [genres] if isinstance(genres, str) else genres if isinstance(genres, list) else []
    best: tuple[int, str] | None = None
    for value in values:
        genre = normalize_text(str(value or ""))
        if not genre:
            continue
        for link in links:
            label = normalize_text(str(link.get("label") or ""))
            slug = str(link.get("slug") or "").strip().lower()
            if not label or not slug:
                continue
            if genre == label:
                score = 10_000 + len(genre)
            elif genre in label or label in genre:
                score = min(len(genre), len(label))
            else:
                continue
            if best is None or score > best[0]:
                best = (score, slug)
    return best[1] if best else ""


def extract_tabelog_urls(html: str, limit: int = 6) -> list[str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    urls: list[str] = []
    for anchor in soup.select("a.result__a, a[href]"):
        url = canonical_restaurant_url(str(anchor.get("href") or ""))
        if url and url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _parse_tabelog_soup(html: str) -> Any:
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "lxml")


def coordinates_from_tabelog_soup(soup: Any) -> tuple[float | None, float | None]:
    basics = soup.select_one("#js-basics[data-lat][data-lng]")
    if basics:
        try:
            return float(str(basics.get("data-lat"))), float(str(basics.get("data-lng")))
        except (TypeError, ValueError):
            pass

    def restaurant_node(value: Any) -> Mapping[str, Any] | None:
        if isinstance(value, Mapping):
            node_type = value.get("@type")
            if node_type == "Restaurant" or (
                isinstance(node_type, list) and "Restaurant" in node_type
            ):
                return value
            for child in value.values():
                if node := restaurant_node(child):
                    return node
        elif isinstance(value, list):
            for child in value:
                if node := restaurant_node(child):
                    return node
        return None

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            node = restaurant_node(json.loads(script.string or script.get_text()))
            geo = node.get("geo") if node else None
            if isinstance(geo, Mapping):
                return float(geo["latitude"]), float(geo["longitude"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return None, None


def coordinates_from_tabelog_html(html: str) -> tuple[float | None, float | None]:
    return coordinates_from_tabelog_soup(_parse_tabelog_soup(html))


def parse_tabelog_map_target_html(html: str) -> dict[str, Any]:
    """Read the exact address and coordinates from Tabelog's map-only frame.

    This parser is only used after the user explicitly asks to open one
    recommendation in Google Maps. It deliberately does not read reviews.
    """
    soup = _parse_tabelog_soup(html)
    latitude, longitude = coordinates_from_tabelog_soup(soup)
    if latitude is None or longitude is None:
        match = re.search(
            r"new\s+google\.maps\.LatLng\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)",
            html,
        )
        if match:
            latitude, longitude = float(match.group(1)), float(match.group(2))
    address = ""
    for label in soup.find_all("strong"):
        if "住所" not in label.get_text(" ", strip=True):
            continue
        parts: list[str] = []
        for sibling in label.next_siblings:
            if getattr(sibling, "name", None) == "br":
                break
            text = sibling.get_text(" ", strip=True) if hasattr(sibling, "get_text") else str(sibling)
            if text.strip():
                parts.append(text.strip())
        address = re.sub(r"\s+", " ", " ".join(parts)).strip()
        break
    return {"address": address, "latitude": latitude, "longitude": longitude}


def hyakumeiten_from_tabelog_soup(soup: Any) -> list[dict[str, Any]]:
    """Extract every Hyakumeiten selection listed on a restaurant page."""
    anchors = soup.select('a[href*="award.tabelog.com/hyakumeiten/"]')

    selections: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for anchor in anchors:
        url = str(anchor.get("href") or "")
        url_match = HYAKUMEITEN_URL_RE.search(url)
        if not url_match or url in seen_urls:
            continue

        wrapper = anchor.find_parent(
            "div",
            class_=lambda value: value
            and (
                "rdheader-badge-award" in value
                or "rstinfo-table-badge-hyakumeiten" in value
            ),
        )
        tooltip = wrapper.select_one('[class*="tooltip"] p') if wrapper else None
        label = (
            tooltip.get_text(" ", strip=True)
            if tooltip
            else anchor.get_text(" ", strip=True)
        )
        label = re.sub(r"\s+", " ", label).strip()
        label_match = HYAKUMEITEN_LABEL_RE.match(label)
        descriptor = label_match.group("descriptor").strip() if label_match else ""
        area_match = re.search(r"(?:\s*)(TOKYO|EAST|WEST)$", descriptor)
        area = area_match.group(1) if area_match else ""
        category = descriptor[: area_match.start()].strip() if area_match else descriptor
        year = int(
            label_match.group("year") if label_match else url_match.group("year")
        )
        selections.append(
            {
                "label": label or f"百名店 {year} 選出店",
                "category": tabelog_label_zh_hant(category),
                "area": area,
                "year": year,
                "url": url,
            }
        )
        seen_urls.add(url)
    return sorted(
        selections,
        key=lambda item: (
            int(item.get("year") or 0),
            str(item.get("category") or ""),
            str(item.get("area") or ""),
        ),
        reverse=True,
    )


def hyakumeiten_from_tabelog_html(html: str) -> list[dict[str, Any]]:
    return hyakumeiten_from_tabelog_soup(_parse_tabelog_soup(html))


def _tabelog_info_map_from_soup(soup: Any) -> dict[str, str]:
    """Read the label/value rows used by Tabelog's restaurant information table."""
    info: dict[str, str] = {}
    for row in soup.find_all("tr"):
        header = row.find("th")
        value = row.find("td")
        if header is None or value is None:
            continue
        key = re.sub(r"\s+", "", header.get_text(" ", strip=True))
        text = re.sub(r"\s+", " ", value.get_text(" ", strip=True)).strip()
        if key and text and key not in info:
            info[key] = text
    return info


def _tabelog_info_map(html: str) -> dict[str, str]:
    return _tabelog_info_map_from_soup(_parse_tabelog_soup(html))


def reservation_from_tabelog_info(
    info: Mapping[str, str], reservation_url: str = ""
) -> dict[str, Any]:
    """Return a stable reservation state plus gurume's online-booking URL."""
    value = info.get("予約可否", "")
    if reservation_url:
        status = "online"
    elif re.search(r"予約\s*不可", value):
        status = "unavailable"
    elif re.search(r"予約\s*可", value):
        status = "available"
    else:
        status = "unknown"
    return {
        "status": status,
        "url": reservation_url,
        "details": value,
    }


def reservation_from_tabelog_html(
    html: str, reservation_url: str = ""
) -> dict[str, Any]:
    return reservation_from_tabelog_info(_tabelog_info_map(html), reservation_url)


def payment_from_tabelog_info(info: Mapping[str, str]) -> dict[str, Any]:
    """Extract card, electronic-money and QR-payment support from Tabelog."""
    value = info.get("支払い方法", "")
    if not value:
        return {}

    markers = list(PAYMENT_MARKER_RE.finditer(value))
    payment: dict[str, Any] = {"details": value}
    key_by_kind = {
        "カード": "cards",
        "クレジットカード": "cards",
        "電子マネー": "electronic_money",
        "QRコード決済": "qr_code",
    }
    for index, marker in enumerate(markers):
        section_end = markers[index + 1].start() if index + 1 < len(markers) else len(value)
        details = value[marker.end() : section_end].strip(" \t\r\n、。・()（）")
        payment[key_by_kind[marker.group("kind")]] = {
            "accepted": marker.group("status") == "可",
            "details": details,
        }
    return payment


def payment_from_tabelog_html(html: str) -> dict[str, Any]:
    return payment_from_tabelog_info(_tabelog_info_map(html))


def parse_tabelog_page(html: str, reservation_url: str = "") -> dict[str, Any]:
    """Parse a Tabelog restaurant HTML document once for coordinates and extras."""
    soup = _parse_tabelog_soup(html)
    info = _tabelog_info_map_from_soup(soup)
    latitude, longitude = coordinates_from_tabelog_soup(soup)
    selections = hyakumeiten_from_tabelog_soup(soup)
    reservation = reservation_from_tabelog_info(info, reservation_url)
    payment = payment_from_tabelog_info(info)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "hyakumeiten": selections,
        "reservation": reservation,
        "payment": payment,
    }


def _apply_tabelog_page(candidate: dict[str, Any], page: Mapping[str, Any]) -> None:
    if page.get("latitude") is not None:
        candidate["latitude"] = page["latitude"]
    if page.get("longitude") is not None:
        candidate["longitude"] = page["longitude"]
    selections = list(page.get("hyakumeiten") or [])
    candidate["is_hyakumeiten"] = bool(selections)
    candidate["hyakumeiten"] = selections
    reservation = page.get("reservation") or {}
    candidate["reservation_status"] = reservation.get("status") or "unknown"
    candidate["reservation_details"] = reservation.get("details") or ""
    if reservation.get("url"):
        candidate["reservation_url"] = reservation["url"]
    candidate["payment"] = dict(page.get("payment") or {})


def _add_tabelog_extras(candidate: dict[str, Any], html: str) -> None:
    page = parse_tabelog_page(html, str(candidate.get("reservation_url") or ""))
    _apply_tabelog_page(candidate, page)


class GurumeProvider:
    """Small, rate-limited adapter around gurume's public Python API."""

    TABELOG_HOST = "tabelog.com"

    def __init__(self, minimum_interval: float = 0.8) -> None:
        self.minimum_interval = minimum_interval
        self._last_request_by_host: dict[str, float] = {}
        self._host_locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def _host_lock(self, host: str) -> threading.Lock:
        with self._meta_lock:
            lock = self._host_locks.get(host)
            if lock is None:
                lock = threading.Lock()
                self._host_locks[host] = lock
            return lock

    def _throttle(self, host: str = TABELOG_HOST) -> None:
        """Rate-limit per host so Yahoo/DDG are not blocked by Tabelog's interval."""
        lock = self._host_lock(host)
        with lock:
            last = self._last_request_by_host.get(host, 0.0)
            delay = self.minimum_interval - (time.monotonic() - last)
            if delay > 0:
                time.sleep(delay)
            self._last_request_by_host[host] = time.monotonic()

    def _discover_with_web_search(
        self, place: Mapping[str, Any], limit: int
    ) -> list[str]:
        """Find indexed Tabelog detail URLs when Tabelog's search page returns 403."""
        from curl_cffi import requests

        search_engines = (
            ("https://search.yahoo.co.jp/search", "p", "search.yahoo.co.jp"),
            ("https://html.duckduckgo.com/html/", "q", "html.duckduckgo.com"),
        )
        last_error: Exception | None = None
        for query in web_search_queries(place):
            for url, parameter, host in search_engines:
                try:
                    self._throttle(host)
                    response = requests.get(
                        url,
                        params={parameter: query[:500]},
                        headers={
                            "User-Agent": "Mozilla/5.0",
                            "Accept-Language": "ja,en;q=0.8",
                        },
                        timeout=20.0,
                        allow_redirects=True,
                        impersonate="chrome",
                    )
                    response.raise_for_status()
                    urls = extract_tabelog_urls(response.text, limit=limit)
                    if urls:
                        return urls
                except Exception as exc:
                    last_error = exc
        if last_error:
            raise last_error
        return []

    def _discover_with_suggestions(
        self, place: Mapping[str, Any], limit: int
    ) -> dict[str, str]:
        """Resolve strong autocomplete matches, retaining already-fetched detail HTML."""
        from bs4 import BeautifulSoup
        from curl_cffi import requests
        from gurume.suggest import get_keyword_suggestions

        names = [
            str(place.get("alternate_name") or "").strip(),
            str(place.get("name") or "").strip(),
        ]
        queries: list[str] = []
        for name in names:
            for query in (name, normalize_name(name)):
                if query and query not in queries:
                    queries.append(query)

        restaurant_ids: list[str] = []
        target_names = [normalize_name(name) for name in names if normalize_name(name)]
        for query in queries:
            try:
                self._throttle(self.TABELOG_HOST)
                suggestions = get_keyword_suggestions(query)
            except Exception:
                continue
            for suggestion in suggestions:
                if getattr(suggestion, "datatype", "") != "Restaurant":
                    continue
                suggestion_name = normalize_name(str(getattr(suggestion, "name", "")))
                best_score = max(
                    (similarity(target, suggestion_name) for target in target_names),
                    default=0.0,
                )
                restaurant_id = str(getattr(suggestion, "id_in_datatype", ""))
                if best_score >= 0.88 and restaurant_id.isdigit():
                    if restaurant_id not in restaurant_ids:
                        restaurant_ids.append(restaurant_id)
            if restaurant_ids:
                break

        pages: dict[str, str] = {}
        for restaurant_id in restaurant_ids[:limit]:
            try:
                self._throttle(self.TABELOG_HOST)
                response = requests.get(
                    "https://tabelog.com/rst/rstdtl_top",
                    params={"rcd": restaurant_id},
                    headers={"Accept-Language": "ja,en;q=0.8"},
                    timeout=20.0,
                    allow_redirects=True,
                    impersonate="chrome",
                )
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "lxml")
                canonical = soup.find("link", rel="canonical")
                url = canonical_restaurant_url(
                    str(canonical.get("href") or "") if canonical else ""
                )
                if url and url not in pages:
                    pages[url] = response.text
            except Exception:
                continue
        return pages

    @staticmethod
    def _candidate_from_html(
        html: str, url: str, request_type: Any
    ) -> dict[str, Any] | None:
        """Parse a full Tabelog restaurant page without a second network request."""
        parser = request_type(
            restaurant_url=url,
            fetch_reviews=False,
            fetch_menu=False,
            fetch_courses=False,
        )
        parse_restaurant = getattr(parser, "_parse_restaurant", None)
        if not callable(parse_restaurant):
            return None
        candidate = restaurant_to_dict(parse_restaurant(html, url))
        if not candidate.get("name") or not (
            candidate.get("phone") or candidate.get("address")
        ):
            return None
        _apply_tabelog_page(
            candidate,
            parse_tabelog_page(html, str(candidate.get("reservation_url") or "")),
        )
        candidate.setdefault("is_hyakumeiten", False)
        candidate.setdefault("hyakumeiten", [])
        candidate.setdefault(
            "reservation_status", "online" if candidate.get("reservation_url") else "unknown"
        )
        candidate.setdefault("reservation_details", "")
        candidate.setdefault("payment", {})
        return candidate

    def _fetch_details(
        self,
        urls: list[str],
        request_type: Any,
        *,
        include_coordinates: bool = True,
        preloaded_html: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        from curl_cffi import requests

        candidates: list[dict[str, Any]] = []
        for url in urls:
            cached_html = str((preloaded_html or {}).get(url) or "")
            if cached_html:
                try:
                    candidate = self._candidate_from_html(cached_html, url, request_type)
                    if candidate:
                        candidates.append(candidate)
                        continue
                except Exception:
                    pass
            if include_coordinates:
                try:
                    self._throttle(self.TABELOG_HOST)
                    map_response = requests.get(
                        f"{url.rstrip('/')}/dtlmap/",
                        headers={"Accept-Language": "ja,en;q=0.8"},
                        timeout=20.0,
                        allow_redirects=True,
                        impersonate="chrome",
                    )
                    map_response.raise_for_status()
                    candidate = self._candidate_from_html(
                        map_response.text, url, request_type
                    )
                    if candidate:
                        candidates.append(candidate)
                        continue
                except Exception:
                    pass
            try:
                self._throttle(self.TABELOG_HOST)
                response = request_type(
                    restaurant_url=url,
                    fetch_reviews=False,
                    fetch_menu=False,
                    fetch_courses=False,
                ).fetch_sync()
                candidate = restaurant_to_dict(getattr(response, "restaurant", response))
                if include_coordinates and not candidate.get("latitude"):
                    try:
                        self._throttle(self.TABELOG_HOST)
                        map_response = requests.get(
                            f"{url.rstrip('/')}/dtlmap/",
                            headers={"Accept-Language": "ja,en;q=0.8"},
                            timeout=20.0,
                            allow_redirects=True,
                            impersonate="chrome",
                        )
                        map_response.raise_for_status()
                        page = parse_tabelog_page(
                            map_response.text,
                            str(candidate.get("reservation_url") or ""),
                        )
                        _apply_tabelog_page(candidate, page)
                    except Exception:
                        pass
                candidate.setdefault("is_hyakumeiten", False)
                candidate.setdefault("hyakumeiten", [])
                candidate.setdefault(
                    "reservation_status",
                    "online" if candidate.get("reservation_url") else "unknown",
                )
                candidate.setdefault("reservation_details", "")
                candidate.setdefault("payment", {})
                candidates.append(candidate)
            except Exception:
                continue
        return candidates

    def fetch_review_list_html(self, restaurant_url: str) -> str:
        """Fetch one public review-list page with host throttling. No retries on failure."""
        from curl_cffi import requests

        canonical = canonical_restaurant_url(restaurant_url)
        if not canonical:
            raise ValueError("不是合法的 Tabelog 店家 URL")
        url = f"{canonical.rstrip('/')}/dtlrvwlst/"
        self._throttle(self.TABELOG_HOST)
        response = requests.get(
            url,
            headers={"Accept-Language": "ja,en;q=0.8"},
            timeout=20.0,
            allow_redirects=True,
            impersonate="chrome",
        )
        if response.status_code == 403:
            raise RuntimeError("Tabelog 暫時拒絕公開評論頁請求（403）")
        response.raise_for_status()
        return response.text

    def search_similar(
        self, seed: Mapping[str, Any], limit: int = 20
    ) -> list[dict[str, Any]]:
        """Read a bounded Tabelog nearby-restaurants category for recommendations.

        Unlike identity matching, this deliberately has no web-search fallback
        and never fetches candidate detail pages.  Known cuisines use one
        official category page; an unknown cuisine first reads the generic
        nearby page solely to discover its official category link, then may
        read that one category page.  Results remain bounded to the first set.
        """
        try:
            from gurume import RestaurantSearchRequest, SortType
        except ImportError as exc:
            raise RuntimeError(
                "尚未安裝 gurume；請先執行 `uv sync`，再啟動服務。"
            ) from exc

        raw_genres = seed.get("genres")
        if isinstance(raw_genres, str):
            raw_genres = [raw_genres]
        genre = next(
            (
                str(item).strip()
                for item in raw_genres or []
                if str(item).strip()
            ),
            "",
        )
        if not genre:
            return []
        generic_peripheral_url = tabelog_peripheral_map_url(str(seed.get("url") or ""))
        known_slug = peripheral_genre_slug(raw_genres)
        if generic_peripheral_url:
            from curl_cffi import requests

            def fetch_peripheral(url: str) -> str:
                self._throttle(self.TABELOG_HOST)
                response = requests.get(
                    url,
                    params={"type": "0"},
                    headers={"Accept-Language": "ja,en;q=0.8"}, timeout=20.0,
                    allow_redirects=True, impersonate="chrome",
                )
                response.raise_for_status()
                return response.text

            if known_slug:
                category_url = tabelog_peripheral_map_url(
                    str(seed.get("url") or ""), known_slug
                )
                return parse_peripheral_restaurants(fetch_peripheral(category_url), limit)

            generic_html = fetch_peripheral(generic_peripheral_url)
            discovered_slug = peripheral_genre_slug_from_links(
                raw_genres, parse_peripheral_genre_links(generic_html)
            )
            if discovered_slug:
                category_url = tabelog_peripheral_map_url(
                    str(seed.get("url") or ""), discovered_slug
                )
                return parse_peripheral_restaurants(fetch_peripheral(category_url), limit)
            return parse_peripheral_restaurants(generic_html, limit)
        station = str(seed.get("station") or "").strip().removesuffix("駅")
        area = station or area_from_address(str(seed.get("address") or ""))
        if not area:
            return []

        self._throttle(self.TABELOG_HOST)
        results = RestaurantSearchRequest(
            area=area,
            keyword=genre,
            sort_type=SortType.RANKING,
        ).search_sync()
        return [restaurant_to_dict(item) for item in list(results)[: max(1, min(limit, 20))]]

    def fetch_similar_map_target(self, restaurant_url: str) -> dict[str, Any]:
        """Read one map-only frame after an explicit recommendation click."""
        from curl_cffi import requests

        canonical = canonical_restaurant_url(restaurant_url)
        restaurant_id = canonical.rstrip("/").split("/")[-1] if canonical else ""
        if not restaurant_id.isdigit():
            raise ValueError("不是合法的 Tabelog 店家 URL")
        self._throttle(self.TABELOG_HOST)
        response = requests.get(
            "https://tabelog.com/badge/google_badge_frame",
            params={"rcd": restaurant_id},
            headers={"Accept-Language": "ja,en;q=0.8"},
            timeout=20.0,
            allow_redirects=True,
            impersonate="chrome",
        )
        response.raise_for_status()
        target = parse_tabelog_map_target_html(response.text)
        if not target.get("address"):
            raise RuntimeError("Tabelog 地圖頁未提供地址")
        return target

    @staticmethod
    def _has_phone_match(
        place: Mapping[str, Any], candidates: list[Mapping[str, Any]]
    ) -> bool:
        place_phone = normalize_phone(str(place.get("phone") or ""))
        if not place_phone:
            return False
        return any(
            place_phone == normalize_phone(str(candidate.get("phone") or ""))
            for candidate in candidates
        )

    @staticmethod
    def _has_strong_identity_match(
        place: Mapping[str, Any], candidates: list[Mapping[str, Any]]
    ) -> bool:
        place_phone = normalize_phone(str(place.get("phone") or ""))
        for candidate in candidates:
            candidate_phone = normalize_phone(str(candidate.get("phone") or ""))
            if place_phone and candidate_phone and place_phone == candidate_phone:
                return True
            distance = haversine_meters(
                place.get("latitude"),
                place.get("longitude"),
                candidate.get("latitude"),
                candidate.get("longitude"),
            )
            if distance is not None and distance <= 500:
                return True
        return False

    def search(self, place: Mapping[str, Any], limit: int = 6) -> list[dict[str, Any]]:
        try:
            from gurume import RestaurantDetailRequest, SortType, query_restaurants
        except ImportError as exc:
            raise RuntimeError(
                "尚未安裝 gurume；請先執行 `uv sync`，再啟動服務。"
            ) from exc

        name = str(place.get("alternate_name") or place.get("name") or "").strip()
        if not name:
            raise ValueError("店家名稱不可為空")
        direct_url = canonical_restaurant_url(str(place.get("tabelog_url") or ""))
        if direct_url:
            direct_candidates = self._fetch_details(
                [direct_url], RestaurantDetailRequest
            )
            for candidate in direct_candidates:
                candidate["direct_source"] = True
            return direct_candidates

        suggestion_candidates: list[dict[str, Any]] = []
        suggestion_pages = self._discover_with_suggestions(place, min(limit, 3))
        if suggestion_pages:
            suggestion_candidates = self._fetch_details(
                list(suggestion_pages), RestaurantDetailRequest,
                preloaded_html=suggestion_pages,
            )
            suggestion_has_reviews = any(
                candidate.get("rating") is not None
                or int(candidate.get("review_count") or 0) > 0
                for candidate in suggestion_candidates
            )
            # Phone match or strong geo + reviews: skip Tabelog search and web fallback.
            if self._has_phone_match(place, suggestion_candidates) or (
                self._has_strong_identity_match(place, suggestion_candidates)
                and suggestion_has_reviews
            ):
                return suggestion_candidates
        area = area_from_address(str(place.get("address") or ""))
        search_error: Exception | None = None
        used_fallback = False
        if suggestion_candidates:
            results = []
        else:
            self._throttle(self.TABELOG_HOST)
            try:
                results = query_restaurants(
                    area=area,
                    keyword=name,
                    sort_type=SortType.STANDARD,
                )
            except Exception as exc:
                search_error = exc
                results = []
        candidates = [restaurant_to_dict(item) for item in list(results)[:limit]]

        if not candidates:
            # Prefer returning weak suggestion hits over an extra web crawl when we
            # already have Tabelog detail pages for the same place name.
            if suggestion_candidates and self._has_strong_identity_match(
                place, suggestion_candidates
            ):
                return suggestion_candidates
            try:
                fallback_urls = self._discover_with_web_search(place, min(limit, 4))
                fallback_candidates = self._fetch_details(
                    fallback_urls, RestaurantDetailRequest
                )
                candidates = list(suggestion_candidates)
                known_urls = {str(item.get("url") or "") for item in candidates}
                candidates.extend(
                    item
                    for item in fallback_candidates
                    if str(item.get("url") or "") not in known_urls
                )
                used_fallback = True
            except Exception as fallback_error:
                if suggestion_candidates:
                    return suggestion_candidates
                if search_error:
                    message = str(search_error)
                    if "403" in message:
                        raise RuntimeError(
                            "Tabelog 搜尋頁拒絕查詢（403），備援搜尋也暫時失敗，請稍後再試。"
                        ) from fallback_error
                    raise RuntimeError(f"Tabelog 搜尋暫時失敗：{message}") from fallback_error
                raise RuntimeError(f"找不到 Tabelog 候選店家：{fallback_error}") from fallback_error

        if not candidates:
            return []

        # Fetch details only for plausible names. Search cards often omit phone/address.
        candidates.sort(
            key=lambda item: similarity(normalize_name(name), normalize_name(item["name"])),
            reverse=True,
        )
        if used_fallback:
            return candidates
        enriched: list[dict[str, Any]] = []
        for candidate in candidates[:4]:
            if not candidate["url"]:
                enriched.append(candidate)
                continue
            try:
                details = self._fetch_details(
                    [candidate["url"]], RestaurantDetailRequest
                )
                enriched.append(
                    merge_candidate_details(candidate, details[0])
                    if details
                    else candidate
                )
            except Exception:
                enriched.append(candidate)
        enriched.extend(candidates[4:])
        # High-confidence identity: do not kick off Yahoo/DDG fallback crawls.
        if self._has_strong_identity_match(place, enriched):
            return enriched
        try:
            fallback_urls = self._discover_with_web_search(place, min(limit, 4))
            fallback_candidates = self._fetch_details(
                fallback_urls, RestaurantDetailRequest
            )
            known_urls = {str(item.get("url") or "") for item in enriched}
            enriched.extend(
                item
                for item in fallback_candidates
                if str(item.get("url") or "") not in known_urls
            )
        except Exception:
            pass
        return enriched
