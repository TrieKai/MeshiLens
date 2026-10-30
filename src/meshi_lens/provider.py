from __future__ import annotations

import logging
import time
from typing import Any, Mapping

from .fetch import Deadline, HTTPStatusError, ThrottledFetcher
from .tabelog_discovery import TabelogDiscovery
# Parsing and discovery moved out of this module; these names stay importable here.
from .tabelog_discovery import web_search_queries  # noqa: F401
from .tabelog_parse import (  # noqa: F401
    canonical_restaurant_url,
    coordinates_from_tabelog_html,
    extract_tabelog_urls,
    hyakumeiten_from_tabelog_html,
    merge_candidate_details,
    parse_peripheral_genre_links,
    parse_peripheral_restaurants,
    parse_tabelog_map_target_html,
    parse_tabelog_page,
    parse_tabelog_popularity_page,
    payment_from_tabelog_html,
    peripheral_genre_slug,
    peripheral_genre_slug_from_links,
    peripheral_genre_slugs,
    relocation_from_tabelog_html,
    reservation_from_tabelog_html,
    restaurant_to_dict,
    stable_reservation_url,
    tabelog_area_path,
    tabelog_peripheral_map_url,
    tabelog_popularity_list_url,
)


LOGGER = logging.getLogger("meshilens.provider")


POPULARITY_SORTS = (
    ("most_reserved", "最多預訂", "inbound_most_reserved"),
    ("local_reserved", "在地人預訂最多", "inbound_vacancy_net_yoyaku"),
    ("most_viewed", "瀏覽最多", "inbound_access"),
)


class GurumeProvider:
    """Rate-limited Tabelog reads; gurume only parses the pages fetched here."""

    # Leaves /match well inside the 35-second extension and Android client timeouts.
    SEARCH_BUDGET_SECONDS = 25.0

    def __init__(self, minimum_interval: float = 0.8) -> None:
        self.fetcher = ThrottledFetcher(minimum_interval)
        self.discovery = TabelogDiscovery(self.fetcher)

    def search(
        self,
        place: Mapping[str, Any],
        limit: int = 6,
        *,
        deadline: Deadline | None = None,
    ) -> list[dict[str, Any]]:
        """Find Tabelog candidates for one place within one time budget."""
        started = time.monotonic()
        path = "error"
        timed_out = False
        try:
            lookup = self.discovery.discover(
                place, limit, deadline or Deadline(self.SEARCH_BUDGET_SECONDS)
            )
            path = lookup.path or "none"
            timed_out = lookup.timed_out
            return lookup.candidates
        finally:
            LOGGER.info(
                "search path=%s latency_ms=%s deadline_hit=%s",
                path,
                int((time.monotonic() - started) * 1000),
                str(timed_out).lower(),
            )

    def fetch_review_list_html(self, restaurant_url: str) -> str:
        """Fetch one public review-list page with host throttling. No retries on failure."""
        canonical = canonical_restaurant_url(restaurant_url)
        if not canonical:
            raise ValueError("不是合法的 Tabelog 店家 URL")
        try:
            return self.fetcher.fetch(f"{canonical.rstrip('/')}/dtlrvwlst/")
        except HTTPStatusError as exc:
            if exc.status == 403:
                raise RuntimeError("Tabelog 暫時拒絕公開評論頁請求（403）") from exc
            raise

    def fetch_popularity_rankings(
        self, restaurant_url: str, limit: int = 20
    ) -> dict[str, Any]:
        """Fetch three public regional list pages, bounded to their first twenty cards."""
        area_path = tabelog_area_path(restaurant_url)
        if not area_path:
            raise ValueError("不是合法的 Tabelog 店家 URL")
        rankings: list[dict[str, Any]] = []
        scope = ""
        for key, label, sort_value in POPULARITY_SORTS:
            url = tabelog_popularity_list_url(restaurant_url, sort_value)
            html = self.fetcher.fetch(
                url, headers={"Accept-Language": "zh-TW,ja;q=0.8"}
            )
            parsed = parse_tabelog_popularity_page(html, limit=limit)
            scope = scope or str(parsed.get("scope") or "")
            rankings.append(
                {
                    "key": key,
                    "label": label,
                    "source_url": url,
                    "urls": parsed["urls"],
                }
            )
        return {"area_path": area_path, "scope": scope, "rankings": rankings}

    def _peripheral_html(self, url: str) -> str:
        return self.fetcher.fetch(url, params={"type": "0"})

    def search_similar(
        self, seed: Mapping[str, Any], limit: int = 30
    ) -> list[dict[str, Any]]:
        """Read a bounded set of Tabelog nearby-category pages for recommendations.

        Unlike identity matching, this deliberately has no web-search fallback
        and never fetches candidate detail pages.  Up to three known cuisine
        categories are merged and deduplicated into at most thirty candidates.
        An unknown cuisine first reads the generic nearby page solely to
        discover one official category link.
        """
        raw_genres = seed.get("genres")
        if isinstance(raw_genres, str):
            raw_genres = [raw_genres]
        if not any(str(item).strip() for item in raw_genres or []):
            return []
        seed_url = str(seed.get("url") or "")
        generic_peripheral_url = tabelog_peripheral_map_url(seed_url)
        if not generic_peripheral_url:
            raise ValueError("不是合法的 Tabelog 店家 URL")
        known_slugs = peripheral_genre_slugs(raw_genres)
        bounded_limit = max(1, min(limit, 30))

        if known_slugs:
            found: list[dict[str, Any]] = []
            seen_urls: dict[str, int] = {}
            last_error: Exception | None = None
            for slug in known_slugs:
                category_url = tabelog_peripheral_map_url(seed_url, slug)
                try:
                    category_candidates = parse_peripheral_restaurants(
                        self._peripheral_html(category_url), min(bounded_limit, 20)
                    )
                except Exception as exc:
                    last_error = exc
                    continue
                for candidate in category_candidates:
                    url = str(candidate.get("url") or "").rstrip("/")
                    if not url:
                        continue
                    if url in seen_urls:
                        existing = found[seen_urls[url]]
                        existing_genres = existing.get("genres")
                        candidate_genres = candidate.get("genres")
                        merged_genres: list[str] = []
                        for value in (
                            existing_genres
                            if isinstance(existing_genres, list)
                            else []
                        ) + (
                            candidate_genres
                            if isinstance(candidate_genres, list)
                            else []
                        ):
                            text = str(value or "").strip()
                            if text and text not in merged_genres:
                                merged_genres.append(text)
                        existing["genres"] = merged_genres[:4]
                        for field in (
                            "rating",
                            "review_count",
                            "address",
                            "station",
                            "area",
                            "lunch_price",
                            "dinner_price",
                        ):
                            if existing.get(field) in (None, "") and candidate.get(
                                field
                            ) not in (None, ""):
                                existing[field] = candidate[field]
                        continue
                    found.append(candidate)
                    seen_urls[url] = len(found) - 1
                    if len(found) >= bounded_limit:
                        return found
            if found:
                return found
            if last_error:
                raise last_error
            return []

        generic_html = self._peripheral_html(generic_peripheral_url)
        discovered_slug = peripheral_genre_slug_from_links(
            raw_genres, parse_peripheral_genre_links(generic_html)
        )
        if discovered_slug:
            category_url = tabelog_peripheral_map_url(seed_url, discovered_slug)
            return parse_peripheral_restaurants(
                self._peripheral_html(category_url), bounded_limit
            )
        return parse_peripheral_restaurants(generic_html, bounded_limit)

    def fetch_similar_map_target(self, restaurant_url: str) -> dict[str, Any]:
        """Read one map-only frame after an explicit recommendation click."""
        canonical = canonical_restaurant_url(restaurant_url)
        restaurant_id = canonical.rstrip("/").split("/")[-1] if canonical else ""
        if not restaurant_id.isdigit():
            raise ValueError("不是合法的 Tabelog 店家 URL")
        html = self.fetcher.fetch(
            "https://tabelog.com/badge/google_badge_frame",
            params={"rcd": restaurant_id},
        )
        target = parse_tabelog_map_target_html(html)
        if not target.get("address"):
            raise RuntimeError("Tabelog 地圖頁未提供地址")
        return target
