"""Find a Google Maps place's Tabelog listing in ordered stages under one deadline.

Every stage stops on the same rule the final ranking uses: a candidate that
`matching.score_candidate` rates high settles the lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
import time
from typing import Any, Mapping

from .cache import MemoryTTLCache
from .fetch import Deadline, DeadlineExceeded, ThrottledFetcher
from .matching import normalize_name, score_candidate, similarity
from .tabelog_parse import (
    canonical_restaurant_url,
    canonical_url_from_html,
    candidate_from_restaurant_html,
    extract_tabelog_urls,
    merge_candidate_details,
    restaurants_from_search_html,
)


LOGGER = logging.getLogger("meshilens.provider")

TABELOG_HOST = "tabelog.com"
TABELOG_SEARCH_URL = "https://tabelog.com/rst/rstsearch"
SUGGEST_TIMEOUT_SECONDS = 10.0
# Search cards often omit phone and address; only the likeliest few pages are read.
DETAIL_PAGE_LIMIT = 4
# Same lifetime gurume gave search pages when it fetched them itself.
SEARCH_CACHE_SECONDS = 1800
WEB_SEARCH_ENGINES = (
    ("https://search.yahoo.co.jp/search", "p"),
    ("https://html.duckduckgo.com/html/", "q"),
)
WEB_SEARCH_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ja,en;q=0.8"}


def area_from_address(address: str) -> str | None:
    normalized = address.replace("日本、", "").replace("日本,", "")
    match = re.search(r"(?:〒\s*\d{3}-?\d{4}\s*)?([^\s,，]{2,12}?[都道府県])", normalized)
    return match.group(1) if match else None


def web_search_queries(place: Mapping[str, Any]) -> list[str]:
    """Build identity-focused fallbacks for translated Google Maps names."""
    queries: list[str] = []
    # Drop any label left in front of the number, e.g. 「號碼:」 from zh-TW 「電話號碼:」.
    raw_phone = re.sub(r"^[^\d+]+", "", str(place.get("phone") or "").strip())
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


def tabelog_search_params(keyword: str, area: str | None) -> dict[str, str]:
    """The keyword search gurume's query_restaurants sends: standard order, first page."""
    params = {"SrtT": "trend", "PG": "1"}
    if area:
        params["sa"] = area
    params["sk"] = keyword
    params["sw"] = keyword
    return params


def settles_identity(place: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    """Whether a candidate is one rank_candidates would select without asking.

    A listing Tabelog marks as moved never settles a lookup: its new page may
    be what the next stage finds.
    """
    if candidate.get("is_relocated"):
        return False
    return score_candidate(place, candidate).confidence == "high"


def _url_key(url: str) -> str:
    return canonical_restaurant_url(url) or url


@dataclass
class Lookup:
    """What one place's discovery has found so far."""

    place: Mapping[str, Any]
    limit: int
    deadline: Deadline
    candidates: list[dict[str, Any]] = field(default_factory=list)
    path: str = ""
    timed_out: bool = False
    search_error: Exception | None = None
    web_error: Exception | None = None

    @property
    def name(self) -> str:
        return str(self.place.get("alternate_name") or self.place.get("name") or "").strip()

    @property
    def settled(self) -> bool:
        return any(settles_identity(self.place, candidate) for candidate in self.candidates)

    def has_url(self, url: str) -> bool:
        key = _url_key(url)
        return bool(key) and any(
            _url_key(str(candidate.get("url") or "")) == key for candidate in self.candidates
        )

    def add(self, candidate: dict[str, Any]) -> None:
        if not self.has_url(str(candidate.get("url") or "")):
            self.candidates.append(candidate)


def _parsed_candidate(html: str, url: str) -> dict[str, Any] | None:
    try:
        return candidate_from_restaurant_html(html, url)
    except Exception:
        return None


def _raise_if_nothing_found(lookup: Lookup) -> None:
    """Fail only when nothing was found and the web fallback failed as well."""
    if lookup.candidates or lookup.web_error is None:
        return
    if lookup.search_error is not None:
        message = str(lookup.search_error)
        if "403" in message:
            raise RuntimeError(
                "Tabelog 搜尋頁拒絕查詢（403），備援搜尋也暫時失敗，請稍後再試。"
            ) from lookup.web_error
        raise RuntimeError(f"Tabelog 搜尋暫時失敗：{message}") from lookup.web_error
    raise RuntimeError(f"找不到 Tabelog 候選店家：{lookup.web_error}") from lookup.web_error


class TabelogDiscovery:
    """Ordered lookup stages sharing one fetcher, one stop rule and one deadline."""

    # Tabelog's autocomplete answers `suggest_empty` for every keyword while it is
    # switched off upstream; retry it this rarely instead of on every lookup.
    SUGGEST_RETRY_SECONDS = 3600.0

    def __init__(self, fetcher: ThrottledFetcher) -> None:
        self.fetcher = fetcher
        self._suggest_unavailable_until = 0.0
        self._search_cards = MemoryTTLCache(ttl_seconds=SEARCH_CACHE_SECONDS, max_items=256)

    def discover(
        self, place: Mapping[str, Any], limit: int, deadline: Deadline
    ) -> Lookup:
        """Run the stages until one settles identity or the deadline passes.

        Running out of time returns what was found so far instead of raising.
        """
        try:
            import gurume  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "尚未安裝 gurume；請先執行 `uv sync`，再啟動服務。"
            ) from exc

        lookup = Lookup(place, limit, deadline)
        if not lookup.name:
            raise ValueError("店家名稱不可為空")
        if canonical_restaurant_url(str(place.get("tabelog_url") or "")):
            stages = (self._direct,)
        else:
            stages = (self._suggestions, self._tabelog_search, self._web_search)
        try:
            for stage in stages:
                if lookup.settled:
                    break
                deadline.check()
                stage(lookup)
        except DeadlineExceeded:
            lookup.timed_out = True
        else:
            _raise_if_nothing_found(lookup)
        return lookup

    def _direct(self, lookup: Lookup) -> None:
        """Google Maps already links the Tabelog page; read only that one."""
        lookup.path = "direct"
        url = canonical_restaurant_url(str(lookup.place.get("tabelog_url") or "")) or ""
        candidate = self._fetch_candidate(url, lookup.deadline)
        if candidate:
            candidate["direct_source"] = True
            lookup.add(candidate)

    def _suggestions(self, lookup: Lookup) -> None:
        """Read the autocomplete hits' pages until one settles identity."""
        if time.monotonic() < self._suggest_unavailable_until:
            return
        restaurant_ids = self._suggested_restaurant_ids(lookup)
        if restaurant_ids:
            lookup.path = "suggestions"
        for restaurant_id in restaurant_ids[: min(lookup.limit, 3)]:
            try:
                html = self.fetcher.fetch(
                    "https://tabelog.com/rst/rstdtl_top",
                    params={"rcd": restaurant_id},
                    deadline=lookup.deadline,
                )
                url = canonical_url_from_html(html)
            except DeadlineExceeded:
                raise
            except Exception:
                continue
            if not url or lookup.has_url(url):
                continue
            candidate = self._fetch_candidate(url, lookup.deadline, html)
            if candidate:
                lookup.add(candidate)
                if settles_identity(lookup.place, candidate):
                    break

    def _suggested_restaurant_ids(self, lookup: Lookup) -> list[str]:
        """Restaurant IDs whose autocomplete names closely match the place."""
        from gurume.suggest import TabelogSuggestUnavailableError, get_keyword_suggestions

        names = [
            str(lookup.place.get("alternate_name") or "").strip(),
            str(lookup.place.get("name") or "").strip(),
        ]
        queries: list[str] = []
        for name in names:
            for query in (name, normalize_name(name)):
                if query and query not in queries:
                    queries.append(query)

        restaurant_ids: list[str] = []
        target_names = [normalize_name(name) for name in names if normalize_name(name)]
        for query in queries:
            self.fetcher.throttle(TABELOG_HOST, lookup.deadline)
            timeout = min(SUGGEST_TIMEOUT_SECONDS, lookup.deadline.check())
            try:
                suggestions = get_keyword_suggestions(query, timeout=timeout)
            except TabelogSuggestUnavailableError:
                # Switched off for every keyword, so the remaining queries would fail too.
                self._suggest_unavailable_until = (
                    time.monotonic() + self.SUGGEST_RETRY_SECONDS
                )
                LOGGER.info(
                    "suggest unavailable; skipping for %ss",
                    int(self.SUGGEST_RETRY_SECONDS),
                )
                return []
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
        return restaurant_ids

    def _tabelog_search(self, lookup: Lookup) -> None:
        """Search Tabelog by name, then read the pages of the most name-like cards."""
        if lookup.candidates:
            # Autocomplete already found this name's listings; the search would repeat them.
            return
        lookup.path = "search"
        try:
            cards = self._search(lookup)[: lookup.limit]
        except DeadlineExceeded:
            raise
        except Exception as exc:
            lookup.search_error = exc
            return
        target = normalize_name(lookup.name)
        cards.sort(
            key=lambda card: similarity(target, normalize_name(card["name"])),
            reverse=True,
        )
        for card in cards:
            lookup.add(card)
        for index, card in enumerate(lookup.candidates[:DETAIL_PAGE_LIMIT]):
            if not card.get("url"):
                continue
            detail = self._fetch_candidate(str(card["url"]), lookup.deadline)
            if detail:
                lookup.candidates[index] = merge_candidate_details(card, detail)

    def _search(self, lookup: Lookup) -> list[dict[str, Any]]:
        from gurume.restaurant import USER_AGENT

        params = tabelog_search_params(
            lookup.name, area_from_address(str(lookup.place.get("address") or ""))
        )
        key = "|".join(f"{name}={value}" for name, value in params.items())
        cached = self._search_cards.get(key)
        if cached is None:
            html = self.fetcher.fetch(
                TABELOG_SEARCH_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
                deadline=lookup.deadline,
            )
            cached = {"cards": restaurants_from_search_html(html)}
            self._search_cards.set(key, cached)
        return [dict(card) for card in cached["cards"]]

    def _web_search(self, lookup: Lookup) -> None:
        """Read Tabelog pages a public search engine indexes for the phone or name."""
        try:
            urls = self._web_search_urls(lookup)
        except DeadlineExceeded:
            raise
        except Exception as exc:
            lookup.web_error = exc
            return
        lookup.path = "web_fallback"
        for url in urls:
            if lookup.has_url(url):
                continue
            candidate = self._fetch_candidate(url, lookup.deadline)
            if candidate:
                lookup.add(candidate)

    def _web_search_urls(self, lookup: Lookup) -> list[str]:
        last_error: Exception | None = None
        for query in web_search_queries(lookup.place):
            for url, parameter in WEB_SEARCH_ENGINES:
                try:
                    urls = extract_tabelog_urls(
                        self.fetcher.fetch(
                            url,
                            params={parameter: query[:500]},
                            headers=WEB_SEARCH_HEADERS,
                            deadline=lookup.deadline,
                        ),
                        limit=min(lookup.limit, 4),
                    )
                except DeadlineExceeded:
                    raise
                except Exception as exc:
                    last_error = exc
                    continue
                if urls:
                    return urls
        if last_error:
            raise last_error
        return []

    def _fetch_candidate(
        self, url: str, deadline: Deadline, html: str = ""
    ) -> dict[str, Any] | None:
        """Read one restaurant: an already fetched page first, then its map tab
        (which also carries coordinates), then its main page."""
        if html and (candidate := _parsed_candidate(html, url)):
            return candidate
        base = url.rstrip("/")
        for page_url in (f"{base}/dtlmap/", f"{base}/"):
            try:
                page = self.fetcher.fetch(page_url, deadline=deadline)
            except DeadlineExceeded:
                raise
            except Exception:
                continue
            if candidate := _parsed_candidate(page, url):
                return candidate
        return None
