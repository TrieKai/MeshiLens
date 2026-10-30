import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gurume.suggest import TabelogSuggestUnavailableError

from meshi_lens.fetch import Deadline, HTTPStatusError, ThrottledFetcher
from meshi_lens.matching import rank_candidates
from meshi_lens.provider import GurumeProvider
from meshi_lens.tabelog_discovery import (
    TABELOG_SEARCH_URL,
    Lookup,
    TabelogDiscovery,
    settles_identity,
    tabelog_search_params,
)
from meshi_lens.tabelog_parse import (
    candidate_from_restaurant_html,
    restaurants_from_search_html,
)


YAHOO_URL = "https://search.yahoo.co.jp/search"
NAKAMURA_URL = "https://tabelog.com/tokyo/A1301/A130101/13000001/"
SAITO_URL = "https://tabelog.com/tokyo/A1301/A130101/13000002/"
# The reported case: the only search hit is a different sushi bar 300 m away.
SAITO_PLACE = {
    "name": "鮨 さいとう",
    "latitude": 35.6717,
    "longitude": 139.7650,
    "coordinates_source": "place",
}


def restaurant_page(
    name: str,
    *,
    phone: str = "",
    address: str = "東京都中央区銀座1-2-3",
    latitude: float | None = None,
    longitude: float | None = None,
    rating: float | None = None,
    review_count: int | None = None,
    canonical: str = "",
) -> str:
    """A Tabelog restaurant page reduced to what gurume and MeshiLens read."""
    data: dict[str, object] = {"@type": "Restaurant", "name": name}
    if address:
        data["address"] = {"streetAddress": address}
    if rating is not None:
        data["aggregateRating"] = {"ratingValue": str(rating), "reviewCount": str(review_count or 0)}
    if latitude is not None:
        data["geo"] = {"latitude": latitude, "longitude": longitude}
    head = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    phone_row = f"<tr><th>予約・お問い合わせ</th><td>{phone}</td></tr>" if phone else ""
    return (
        f'<html><head>{head}<script type="application/ld+json">'
        f"{json.dumps(data, ensure_ascii=False)}</script></head>"
        f"<body><table>{phone_row}</table></body></html>"
    )


def search_page(*cards: tuple[str, str]) -> str:
    return "".join(
        f'<div class="list-rst"><a class="list-rst__rst-name-target" href="{url}">{name}</a>'
        '<span class="c-rating__val">3.60</span><em class="list-rst__rvw-count-num">120</em></div>'
        for name, url in cards
    )


def web_results(*urls: str) -> str:
    return "".join(f'<a href="{url}">result</a>' for url in urls)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def open_deadline() -> Deadline:
    """A deadline that never runs out, whatever time.monotonic is patched to."""
    return Deadline(25, clock=lambda: 0.0)


class FakeFetcher:
    """Serves pages by URL and honors the deadline the way ThrottledFetcher does."""

    def __init__(
        self,
        pages: dict[str, object],
        *,
        clock: FakeClock | None = None,
        seconds_per_request: float = 0.0,
    ) -> None:
        self.pages = pages
        self.clock = clock
        self.seconds_per_request = seconds_per_request
        self.requested: list[str] = []

    def throttle(self, _host: str, deadline: Deadline | None = None) -> None:
        if deadline is not None:
            deadline.check()

    def fetch(self, url: str, *, params=None, headers=None, deadline=None) -> str:
        if deadline is not None:
            deadline.check()
        self.requested.append(url)
        if self.clock is not None:
            self.clock.now += self.seconds_per_request
        page = self.pages.get(url)
        if isinstance(page, Exception):
            raise page
        if page is None:
            raise HTTPStatusError(404, url)
        return str(page)


def no_suggestions():
    return patch("gurume.suggest.get_keyword_suggestions", return_value=[])


class SettlesIdentityTests(unittest.TestCase):
    def test_a_nearby_shop_with_another_name_does_not_settle_identity(self) -> None:
        nakamura = {
            "name": "鮨 なかむら",
            "latitude": 35.6744,
            "longitude": 139.7650,
            "rating": 3.6,
            "review_count": 120,
            "url": NAKAMURA_URL,
        }
        self.assertFalse(settles_identity(SAITO_PLACE, nakamura))
        self.assertEqual(rank_candidates(SAITO_PLACE, [nakamura])[0]["confidence"], "low")

    def test_same_name_and_phone_settle_identity(self) -> None:
        self.assertTrue(
            settles_identity(
                {"name": "清水屋", "phone": "0299-64-2011"},
                {"name": "清水屋", "phone": "0299-64-2011", "rating": 3.54},
            )
        )

    def test_relocated_or_differently_named_phone_match_does_not_settle_identity(self) -> None:
        place = {"name": "清水屋", "phone": "0299-64-2011"}
        candidate = {"name": "清水屋", "phone": "0299-64-2011", "rating": 3.54}
        self.assertFalse(settles_identity(place, {**candidate, "is_relocated": True}))
        self.assertFalse(settles_identity(place, {**candidate, "name": "完全不同的店"}))


class DiscoveryTests(unittest.TestCase):
    def test_low_confidence_search_hit_still_runs_the_web_fallback(self) -> None:
        fetcher = FakeFetcher(
            {
                TABELOG_SEARCH_URL: search_page(("鮨 なかむら", NAKAMURA_URL)),
                f"{NAKAMURA_URL}dtlmap/": restaurant_page(
                    "鮨 なかむら", latitude=35.6744, longitude=139.7650, rating=3.6, review_count=120
                ),
                YAHOO_URL: web_results(NAKAMURA_URL, SAITO_URL),
                f"{SAITO_URL}dtlmap/": restaurant_page(
                    "鮨 さいとう",
                    address="東京都港区六本木1-4-5",
                    latitude=35.6718,
                    longitude=139.7651,
                    rating=4.5,
                    review_count=900,
                ),
            }
        )
        with no_suggestions():
            lookup = TabelogDiscovery(fetcher).discover(SAITO_PLACE, 6, open_deadline())

        self.assertEqual(lookup.path, "web_fallback")
        self.assertIn(YAHOO_URL, fetcher.requested)
        # The search hit is already known, so its page is not read a second time.
        self.assertEqual(fetcher.requested.count(f"{NAKAMURA_URL}dtlmap/"), 1)
        selected = rank_candidates(SAITO_PLACE, lookup.candidates)[0]
        self.assertEqual(selected["name"], "鮨 さいとう")
        self.assertEqual(selected["confidence"], "high")

    def test_high_confidence_search_hit_skips_the_web_fallback(self) -> None:
        fetcher = FakeFetcher(
            {
                TABELOG_SEARCH_URL: search_page(("鮨 さいとう", SAITO_URL)),
                f"{SAITO_URL}dtlmap/": restaurant_page(
                    "鮨 さいとう", latitude=35.6718, longitude=139.7651
                ),
            }
        )
        with no_suggestions():
            lookup = TabelogDiscovery(fetcher).discover(SAITO_PLACE, 6, open_deadline())

        self.assertEqual(lookup.path, "search")
        self.assertEqual(fetcher.requested, [TABELOG_SEARCH_URL, f"{SAITO_URL}dtlmap/"])

    def test_returns_the_cards_found_so_far_when_the_deadline_passes(self) -> None:
        cards = [
            (name, f"https://tabelog.com/tokyo/A1301/A130101/1300001{index}/")
            for index, name in enumerate(("鮨 なかむら", "鮨 たなか", "鮨 すずき"))
        ]
        clock = FakeClock()
        fetcher = FakeFetcher(
            {
                TABELOG_SEARCH_URL: search_page(*cards),
                **{
                    f"{url}dtlmap/": restaurant_page(name, phone="03-1111-2222")
                    for name, url in cards
                },
            },
            clock=clock,
            seconds_per_request=9,
        )
        with no_suggestions():
            lookup = TabelogDiscovery(fetcher).discover(
                SAITO_PLACE, 6, Deadline(25, clock=clock)
            )

        self.assertTrue(lookup.timed_out)
        # Search page at 0 s and two detail pages at 9 s and 18 s; 27 s is past the budget.
        self.assertEqual(len(fetcher.requested), 3)
        self.assertNotIn(YAHOO_URL, fetcher.requested)
        self.assertEqual(len(lookup.candidates), 3)
        self.assertEqual(
            sum(1 for candidate in lookup.candidates if candidate.get("phone")), 2
        )

    def test_a_deadline_hit_does_not_raise_even_when_tabelog_search_failed(self) -> None:
        clock = FakeClock()
        fetcher = FakeFetcher(
            {TABELOG_SEARCH_URL: HTTPStatusError(403, TABELOG_SEARCH_URL)},
            clock=clock,
            seconds_per_request=24.5,
        )
        with no_suggestions():
            lookup = TabelogDiscovery(fetcher).discover(
                SAITO_PLACE, 6, Deadline(25, clock=clock)
            )

        self.assertTrue(lookup.timed_out)
        self.assertEqual(lookup.candidates, [])
        self.assertEqual(fetcher.requested, [TABELOG_SEARCH_URL])

    def test_reports_a_blocked_search_once_the_web_fallback_failed_too(self) -> None:
        fetcher = FakeFetcher({TABELOG_SEARCH_URL: HTTPStatusError(403, TABELOG_SEARCH_URL)})
        with no_suggestions():
            with self.assertRaisesRegex(RuntimeError, "Tabelog 搜尋頁拒絕查詢（403）"):
                TabelogDiscovery(fetcher).discover(SAITO_PLACE, 6, open_deadline())

    def test_reads_only_the_page_google_maps_links(self) -> None:
        fetcher = FakeFetcher(
            {f"{SAITO_URL}dtlmap/": restaurant_page("鮨 さいとう")}
        )
        with patch("gurume.suggest.get_keyword_suggestions") as suggest:
            lookup = TabelogDiscovery(fetcher).discover(
                {**SAITO_PLACE, "tabelog_url": SAITO_URL}, 6, open_deadline()
            )

        suggest.assert_not_called()
        self.assertEqual(lookup.path, "direct")
        self.assertEqual(fetcher.requested, [f"{SAITO_URL}dtlmap/"])
        self.assertTrue(lookup.candidates[0]["direct_source"])

    def test_reuses_a_recent_search_page(self) -> None:
        fetcher = FakeFetcher({TABELOG_SEARCH_URL: search_page(("鮨 なかむら", NAKAMURA_URL))})
        discovery = TabelogDiscovery(fetcher)
        with no_suggestions():
            discovery.discover({"name": "鮨 さいとう"}, 6, open_deadline())
            discovery.discover({"name": "鮨 さいとう", "phone": "03-1111-2222"}, 6, open_deadline())

        self.assertEqual(fetcher.requested.count(TABELOG_SEARCH_URL), 1)

    def test_searches_by_name_and_prefecture_like_gurume(self) -> None:
        from gurume import RestaurantSearchRequest, SortType
        from gurume.area_mapping import get_area_slug
        from gurume.restaurant import build_search_url_and_params

        request = RestaurantSearchRequest(
            area="東京都", keyword="鮨 さいとう", sort_type=SortType.STANDARD
        )
        self.assertEqual(
            build_search_url_and_params(request._build_params(), get_area_slug("東京都"), None),
            (TABELOG_SEARCH_URL, tabelog_search_params("鮨 さいとう", "東京都")),
        )

    def test_provider_search_returns_without_requests_when_out_of_time(self) -> None:
        provider = GurumeProvider(minimum_interval=0)
        with (
            patch("gurume.suggest.get_keyword_suggestions") as suggest,
            patch("curl_cffi.requests.get") as get,
        ):
            results = provider.search(SAITO_PLACE, deadline=Deadline(0))

        self.assertEqual(results, [])
        suggest.assert_not_called()
        get.assert_not_called()


class AutocompleteTests(unittest.TestCase):
    @staticmethod
    def lookup(place: dict[str, object]) -> Lookup:
        return Lookup(place, 6, open_deadline())

    def test_reuses_autocomplete_detail_page_before_requesting_a_map_page(self) -> None:
        url = "https://tabelog.com/tokyo/A1301/A130101/13000001/"
        fetcher = FakeFetcher({})

        candidate = TabelogDiscovery(fetcher)._fetch_candidate(
            url, open_deadline(), restaurant_page("早い店", phone="03-1234-5678", rating=3.5)
        )

        self.assertEqual(fetcher.requested, [])
        self.assertEqual(candidate["name"], "早い店")
        self.assertEqual(candidate["address"], "東京都中央区銀座1-2-3")

    def test_stops_autocomplete_details_after_exact_phone_match(self) -> None:
        class FakeResponse:
            status_code = 200

            def __init__(self, restaurant_id: str) -> None:
                self.text = restaurant_page(
                    "清水屋",
                    phone="0299-64-2011",
                    address="茨城県潮来市永山2651",
                    rating=3.54,
                    canonical=f"https://tabelog.com/ibaraki/A0804/A080401/{restaurant_id}/",
                )

        requested_ids: list[str] = []

        def fake_get(_url: str, **kwargs: object) -> FakeResponse:
            restaurant_id = str(dict(kwargs["params"])["rcd"])
            requested_ids.append(restaurant_id)
            return FakeResponse(restaurant_id)

        suggestions = [
            SimpleNamespace(datatype="Restaurant", name="清水屋", id_in_datatype=restaurant_id)
            for restaurant_id in ("8000477", "8000478", "8000479")
        ]
        discovery = TabelogDiscovery(ThrottledFetcher(minimum_interval=0))
        with (
            patch("gurume.suggest.get_keyword_suggestions", return_value=suggestions),
            patch("curl_cffi.requests.get", side_effect=fake_get),
        ):
            lookup = discovery.discover(
                {"name": "清水屋", "phone": "0299-64-2011"}, 3, open_deadline()
            )

        self.assertEqual(requested_ids, ["8000477"])
        self.assertEqual(lookup.path, "suggestions")
        self.assertEqual(
            [candidate["url"] for candidate in lookup.candidates],
            ["https://tabelog.com/ibaraki/A0804/A080401/8000477/"],
        )

    def test_skips_autocomplete_for_an_hour_once_tabelog_switches_it_off(self) -> None:
        discovery = TabelogDiscovery(FakeFetcher({}))
        place = {"name": "一蘭 澀谷店"}
        with patch(
            "gurume.suggest.get_keyword_suggestions",
            side_effect=TabelogSuggestUnavailableError(TabelogSuggestUnavailableError.HELP),
        ) as suggest:
            with patch("meshi_lens.tabelog_discovery.time.monotonic", return_value=1_000.0):
                discovery._suggestions(self.lookup(place))
            # The folded name 「一蘭渋谷店」 would be a second query; it is not sent.
            self.assertEqual(suggest.call_count, 1)

            with patch("meshi_lens.tabelog_discovery.time.monotonic", return_value=1_000.0 + 3_599):
                discovery._suggestions(self.lookup(place))
            self.assertEqual(suggest.call_count, 1)

            with patch("meshi_lens.tabelog_discovery.time.monotonic", return_value=1_000.0 + 3_601):
                discovery._suggestions(self.lookup(place))
            self.assertEqual(suggest.call_count, 2)

    def test_other_autocomplete_errors_still_try_the_next_query(self) -> None:
        discovery = TabelogDiscovery(FakeFetcher({}))
        place = {"name": "一蘭 澀谷店"}
        with patch(
            "gurume.suggest.get_keyword_suggestions", side_effect=RuntimeError("timeout")
        ) as suggest:
            discovery._suggestions(self.lookup(place))
            discovery._suggestions(self.lookup(place))

        # The original and the folded name, on both lookups.
        self.assertEqual(suggest.call_count, 4)


class GurumeParserContractTests(unittest.TestCase):
    """gurume 0.0.12 keeps these parsers private; fail loudly if an upgrade moves them."""

    def test_parses_a_restaurant_page(self) -> None:
        candidate = candidate_from_restaurant_html(
            restaurant_page(
                "鮨 さいとう",
                phone="03-3333-4444",
                latitude=35.6718,
                longitude=139.7651,
                rating=4.5,
                review_count=900,
            ),
            SAITO_URL,
        )
        self.assertEqual(candidate["name"], "鮨 さいとう")
        self.assertEqual(candidate["phone"], "03-3333-4444")
        self.assertEqual(candidate["rating"], 4.5)
        self.assertEqual(candidate["review_count"], 900)
        self.assertEqual((candidate["latitude"], candidate["longitude"]), (35.6718, 139.7651))
        self.assertEqual(candidate["url"], SAITO_URL)
        self.assertFalse(candidate["is_relocated"])

    def test_rejects_a_page_without_phone_or_address(self) -> None:
        self.assertIsNone(
            candidate_from_restaurant_html(restaurant_page("鮨 さいとう", address=""), SAITO_URL)
        )

    def test_parses_search_result_cards(self) -> None:
        cards = restaurants_from_search_html(search_page(("鮨 なかむら", NAKAMURA_URL)))
        self.assertEqual(
            [(card["name"], card["url"], card["rating"], card["review_count"]) for card in cards],
            [("鮨 なかむら", NAKAMURA_URL, 3.6, 120)],
        )


if __name__ == "__main__":
    unittest.main()
