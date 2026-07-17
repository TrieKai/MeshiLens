from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import re
import threading
import time
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse

from .matching import haversine_meters, normalize_name, normalize_phone, similarity


TABELOG_RESULT_RE = re.compile(
    r"https?://tabelog\.com/(?:en/|tw/|cn/|kr/)?"
    r"(?P<path>[a-z0-9-]+/A\d+/A\d+/\d+)/?",
    re.IGNORECASE,
)
HYAKUMEITEN_URL_RE = re.compile(
    r"https?://award\.tabelog\.com/hyakumeiten/(?P<slug>[^/]+)/(?P<year>20\d{2})/?",
    re.IGNORECASE,
)
HYAKUMEITEN_LABEL_RE = re.compile(
    r"^(?:食べログ\s*)?(?P<descriptor>.+?)\s*百名店\s*(?P<year>20\d{2})\s*選出店$"
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
        "station": _first(data, "station", "nearest_station") or "",
        "lunch_price": _first(data, "lunch_price", "lunch_budget") or "",
        "dinner_price": _first(data, "dinner_price", "dinner_budget") or "",
        "business_hours": _first(data, "business_hours", "hours") or "",
        "closed_days": _first(data, "closed_days", "regular_holiday") or "",
    }


def area_from_address(address: str) -> str | None:
    normalized = address.replace("日本、", "").replace("日本,", "")
    match = re.search(r"(?:〒\s*\d{3}-?\d{4}\s*)?([^\s,，]{2,12}?[都道府県])", normalized)
    return match.group(1) if match else None


def canonical_restaurant_url(value: str) -> str | None:
    """Reduce a Tabelog result/review URL to its Japanese restaurant page."""
    decoded = unquote(value)
    if "duckduckgo.com/l/" in decoded:
        redirected = parse_qs(urlparse(decoded).query).get("uddg", [])
        if redirected:
            decoded = unquote(redirected[0])
    match = TABELOG_RESULT_RE.search(decoded)
    return f"https://tabelog.com/{match.group('path')}/" if match else None


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


def coordinates_from_tabelog_html(html: str) -> tuple[float | None, float | None]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
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


def hyakumeiten_from_tabelog_html(html: str) -> list[dict[str, Any]]:
    """Extract every Hyakumeiten selection listed on a restaurant page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
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
                "category": category,
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


def _add_tabelog_badges(candidate: dict[str, Any], html: str) -> None:
    selections = hyakumeiten_from_tabelog_html(html)
    candidate["is_hyakumeiten"] = bool(selections)
    candidate["hyakumeiten"] = selections


class GurumeProvider:
    """Small, rate-limited adapter around gurume's public Python API."""

    def __init__(self, minimum_interval: float = 0.8) -> None:
        self.minimum_interval = minimum_interval
        self._last_request = 0.0
        self._lock = threading.Lock()

    def _throttle(self) -> None:
        with self._lock:
            delay = self.minimum_interval - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
            self._last_request = time.monotonic()

    def _discover_with_web_search(
        self, place: Mapping[str, Any], limit: int
    ) -> list[str]:
        """Find indexed Tabelog detail URLs when Tabelog's search page returns 403."""
        from curl_cffi import requests

        name = str(place.get("alternate_name") or place.get("name") or "").strip()
        query = f'site:tabelog.com "{name.replace(chr(34), "").strip()}"'[:500]
        search_engines = (
            ("https://search.yahoo.co.jp/search", {"p": query}),
            ("https://html.duckduckgo.com/html/", {"q": query}),
        )
        last_error: Exception | None = None
        for url, params in search_engines:
            try:
                self._throttle()
                response = requests.get(
                    url,
                    params=params,
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
    ) -> list[str]:
        """Resolve strong Tabelog autocomplete matches to canonical detail URLs."""
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
                self._throttle()
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

        urls: list[str] = []
        for restaurant_id in restaurant_ids[:limit]:
            try:
                self._throttle()
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
                if url and url not in urls:
                    urls.append(url)
            except Exception:
                continue
        return urls

    def _fetch_details(
        self,
        urls: list[str],
        request_type: Any,
        *,
        include_coordinates: bool = True,
    ) -> list[dict[str, Any]]:
        from curl_cffi import requests

        candidates: list[dict[str, Any]] = []
        for url in urls:
            if include_coordinates:
                try:
                    self._throttle()
                    map_response = requests.get(
                        f"{url.rstrip('/')}/dtlmap/",
                        headers={"Accept-Language": "ja,en;q=0.8"},
                        timeout=20.0,
                        allow_redirects=True,
                        impersonate="chrome",
                    )
                    map_response.raise_for_status()
                    parser = request_type(
                        restaurant_url=url,
                        fetch_reviews=False,
                        fetch_menu=False,
                        fetch_courses=False,
                    )
                    parse_restaurant = getattr(parser, "_parse_restaurant", None)
                    if callable(parse_restaurant):
                        candidate = restaurant_to_dict(
                            parse_restaurant(map_response.text, url)
                        )
                        latitude, longitude = coordinates_from_tabelog_html(
                            map_response.text
                        )
                        candidate["latitude"] = latitude
                        candidate["longitude"] = longitude
                        _add_tabelog_badges(candidate, map_response.text)
                        candidates.append(candidate)
                        continue
                except Exception:
                    pass
            try:
                self._throttle()
                response = request_type(
                    restaurant_url=url,
                    fetch_reviews=False,
                    fetch_menu=False,
                    fetch_courses=False,
                ).fetch_sync()
                candidate = restaurant_to_dict(getattr(response, "restaurant", response))
                if include_coordinates and not candidate.get("latitude"):
                    try:
                        self._throttle()
                        map_response = requests.get(
                            f"{url.rstrip('/')}/dtlmap/",
                            headers={"Accept-Language": "ja,en;q=0.8"},
                            timeout=20.0,
                            allow_redirects=True,
                            impersonate="chrome",
                        )
                        map_response.raise_for_status()
                        latitude, longitude = coordinates_from_tabelog_html(
                            map_response.text
                        )
                        candidate["latitude"] = latitude
                        candidate["longitude"] = longitude
                        _add_tabelog_badges(candidate, map_response.text)
                    except Exception:
                        pass
                candidate.setdefault("is_hyakumeiten", False)
                candidate.setdefault("hyakumeiten", [])
                candidates.append(candidate)
            except Exception:
                continue
        return candidates

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
        suggestion_urls = self._discover_with_suggestions(place, min(limit, 3))
        if suggestion_urls:
            suggestion_candidates = self._fetch_details(
                suggestion_urls, RestaurantDetailRequest
            )
            suggestion_has_reviews = any(
                candidate.get("rating") is not None
                or int(candidate.get("review_count") or 0) > 0
                for candidate in suggestion_candidates
            )
            if (
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
            self._throttle()
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
                self._throttle()
                response = RestaurantDetailRequest(
                    restaurant_url=candidate["url"],
                    fetch_reviews=False,
                    fetch_menu=False,
                    fetch_courses=False,
                ).fetch_sync()
                detail = restaurant_to_dict(getattr(response, "restaurant", response))
                enriched.append(
                    {
                        key: detail.get(key) or candidate.get(key)
                        for key in candidate.keys()
                    }
                )
            except Exception:
                enriched.append(candidate)
        enriched.extend(candidates[4:])
        return enriched
