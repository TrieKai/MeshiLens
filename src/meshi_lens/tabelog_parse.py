"""Pure Tabelog parsing: HTML and URLs in, plain dicts out. No network, no state.

gurume 0.0.12 keeps its restaurant-page and search-page parsers private; the two
adapters at the bottom of this module are the only code that calls them.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import re
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from .localization import station_name, tabelog_label_zh_hant
from .matching import normalize_text


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
        "station": station_name(_first(data, "station", "nearest_station")),
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


def tabelog_popularity_list_url(value: str, sort_value: str) -> str:
    """Build a regional, public Tabelog ranking-list URL from a restaurant URL."""
    area_path = tabelog_area_path(value)
    if not area_path:
        return ""
    return f"https://tabelog.com/tw/{area_path}/rstLst/?SrtT={sort_value}"


def parse_tabelog_popularity_page(html: str, limit: int = 20) -> dict[str, Any]:
    """Read only the first twenty visible restaurant URLs from a public ranking list."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    scope_match = re.search(r"推薦適合在(.+?)美食餐廳", title)
    scope = scope_match.group(1).strip() if scope_match else ""
    urls: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select("a.list-rst__rst-name-target[href]"):
        url = canonical_restaurant_url(
            urljoin("https://tabelog.com/", str(anchor.get("href") or ""))
        )
        if not url or url in seen:
            continue
        urls.append(url)
        seen.add(url)
        if len(urls) >= max(1, min(limit, 20)):
            break
    return {"scope": scope, "urls": urls}


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
    slugs = peripheral_genre_slugs(genres, limit=1)
    return slugs[0] if slugs else ""


def peripheral_genre_slugs(genres: Any, limit: int = 3) -> list[str]:
    """Return up to three distinct official nearby-category slugs in source order."""
    values = [genres] if isinstance(genres, str) else genres if isinstance(genres, list) else []
    slugs: list[str] = []
    for value in values:
        text = str(value or "")
        best: tuple[int, str] | None = None
        for genre, slug in PERIPHERAL_GENRE_SLUGS.items():
            if genre in text:
                score = len(genre)
                if best is None or score > best[0]:
                    best = (score, slug)
        if best and best[1] not in slugs:
            slugs.append(best[1])
            if len(slugs) >= max(1, min(limit, 3)):
                break
    return slugs


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


def canonical_url_from_html(html: str) -> str | None:
    """Read the restaurant URL a Tabelog page declares as canonical."""
    canonical = _parse_tabelog_soup(html).find("link", rel="canonical")
    return canonical_restaurant_url(str(canonical.get("href") or "") if canonical else "")


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


def relocation_from_tabelog_soup(soup: Any) -> dict[str, Any]:
    """Read Tabelog's explicit "moved" notice without inferring from distance."""
    notice = soup.select_one(".rst-status-alert")
    text = notice.get_text(" ", strip=True) if notice else ""
    if "移転前の店舗情報" not in text:
        return {"is_relocated": False, "relocated_to_name": "", "relocated_to_url": ""}
    target = notice.find("a", href=True) if notice else None
    return {
        "is_relocated": True,
        "relocated_to_name": target.get_text(" ", strip=True) if target else "",
        "relocated_to_url": canonical_restaurant_url(
            str(target.get("href") or "") if target else ""
        ) or "",
    }


def relocation_from_tabelog_html(html: str) -> dict[str, Any]:
    return relocation_from_tabelog_soup(_parse_tabelog_soup(html))


def parse_tabelog_page(html: str, reservation_url: str = "") -> dict[str, Any]:
    """Parse a Tabelog restaurant HTML document once for coordinates and extras."""
    soup = _parse_tabelog_soup(html)
    info = _tabelog_info_map_from_soup(soup)
    latitude, longitude = coordinates_from_tabelog_soup(soup)
    selections = hyakumeiten_from_tabelog_soup(soup)
    reservation = reservation_from_tabelog_info(info, reservation_url)
    payment = payment_from_tabelog_info(info)
    relocation = relocation_from_tabelog_soup(soup)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "hyakumeiten": selections,
        "reservation": reservation,
        "payment": payment,
        "relocation": relocation,
    }


def apply_tabelog_page(candidate: dict[str, Any], page: Mapping[str, Any]) -> None:
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
    relocation = page.get("relocation") or {}
    candidate["is_relocated"] = bool(relocation.get("is_relocated"))
    candidate["relocated_to_name"] = str(relocation.get("relocated_to_name") or "")
    candidate["relocated_to_url"] = str(relocation.get("relocated_to_url") or "")


def candidate_from_restaurant_html(html: str, url: str) -> dict[str, Any] | None:
    """Parse a restaurant page (or its map tab) into a candidate.

    Returns None for pages without a name plus a phone or address, which is
    what an error or interstitial page parses into.
    """
    from gurume import RestaurantDetailRequest

    parser = RestaurantDetailRequest(
        restaurant_url=url,
        fetch_reviews=False,
        fetch_menu=False,
        fetch_courses=False,
    )
    candidate = restaurant_to_dict(parser._parse_restaurant(html, url))
    if not candidate.get("name") or not (
        candidate.get("phone") or candidate.get("address")
    ):
        return None
    apply_tabelog_page(
        candidate,
        parse_tabelog_page(html, str(candidate.get("reservation_url") or "")),
    )
    return candidate


def restaurants_from_search_html(html: str) -> list[dict[str, Any]]:
    """Parse the result cards of a Tabelog keyword search page."""
    from gurume import RestaurantSearchRequest

    return [
        restaurant_to_dict(item)
        for item in RestaurantSearchRequest()._parse_restaurants(html)
    ]
