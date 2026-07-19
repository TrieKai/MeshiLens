import json
from pathlib import Path
import tempfile
import unittest

from meshi_lens.michelin import (
    MichelinProvider,
    michelin_listing_meta,
    normalize_website,
    parse_michelin_detail,
    parse_michelin_listing,
)


LISTING_HTML = """
<div class="search-results__stats">日本 : 1-2 共 2 個餐廳</div>
<ul class="pagination">
  <li><a href="/tw/zh_TW/selection/japan/restaurants/page/2">2</a></li>
</ul>
<div class="js-restaurant__list_items">
<div class="js-restaurant__list_item" data-id="101" data-lat="35.65845" data-lng="139.70217">
  <div class="js-bookmark-restaurant" data-distinction="ONE_STAR" data-green-star="true"></div>
  <h3 class="card__menu-content--title"><a href="/tw/zh_TW/tokyo/restaurant/example">Example</a></h3>
  <div class="card__menu-footer--score">Tokyo, 日本</div>
  <div class="card__menu-footer--score">¥¥¥ · 日本菜</div>
</div>
<div class="js-restaurant__list_item" data-id="102" data-lat="35.70000" data-lng="139.70000">
  <div class="js-bookmark-restaurant" data-distinction="BIB_GOURMAND" data-green-star=""></div>
  <h3 class="card__menu-content--title"><a href="/tw/zh_TW/tokyo/restaurant/ramen-test">Ramen Test</a></h3>
  <div class="card__menu-footer--score">Tokyo, 日本</div>
  <div class="card__menu-footer--score">¥ · 拉麵</div>
</div>
</div>
<div class="js-restaurant__list_item" data-id="999" data-lat="0" data-lng="0">
  <h3 class="card__menu-content--title"><a href="/restaurant/unrelated">Unrelated recommendation</a></h3>
</div>
"""

DETAIL_HTML = """
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Restaurant",
  "name": "Tour D'argent Tokyo",
  "telephone": "+81 3-3239-3111"
}
</script>
<a data-event="CTA_website" href="https://tourdargent.jp/">訪問網</a>
"""


class MichelinTests(unittest.TestCase):
    def test_parses_phone_and_official_website_from_detail_page(self) -> None:
        detail = parse_michelin_detail(DETAIL_HTML)
        self.assertEqual(detail["phone"], "+81 3-3239-3111")
        self.assertEqual(detail["website"], "https://tourdargent.jp/")

    def test_normalizes_equivalent_official_websites(self) -> None:
        self.assertEqual(
            normalize_website("http://www.tourdargent.jp/"),
            normalize_website("https://tourdargent.jp"),
        )
        self.assertEqual(
            normalize_website("https://example.com/menu/?from=maps#top"),
            "https://example.com/menu",
        )

    def test_parses_ssr_cards_and_listing_meta(self) -> None:
        self.assertEqual(michelin_listing_meta(LISTING_HTML), (2, 2))
        restaurants = parse_michelin_listing(LISTING_HTML)
        self.assertEqual(restaurants[0]["distinction"], "ONE_STAR")
        self.assertEqual(restaurants[0]["distinction_label"], "米其林一星")
        self.assertTrue(restaurants[0]["green_star"])
        self.assertEqual(restaurants[0]["cuisine"], "日本菜")
        self.assertEqual(restaurants[1]["distinction"], "BIB_GOURMAND")

    def test_matches_by_name_and_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "michelin.json"
            path.write_text(
                json.dumps(
                    {
                        "source_url": "https://guide.michelin.com/example",
                        "fetched_at": "2026-07-18T00:00:00Z",
                        "restaurants": parse_michelin_listing(LISTING_HTML),
                    }
                ),
                encoding="utf-8",
            )
            provider = MichelinProvider(path)
            self.assertTrue(
                all("_normalized_name" in restaurant for restaurant in provider.restaurants)
            )
            matched = provider.match(
                {
                    "name": "Example Restaurant",
                    "latitude": 35.6584466,
                    "longitude": 139.7021636,
                }
            )
        self.assertIsNotNone(matched)
        self.assertEqual(matched["id"], "101")
        self.assertNotIn("_normalized_name", matched)
        self.assertLessEqual(matched["distance_meters"], 2)
        self.assertEqual(matched["snapshot_fetched_at"], "2026-07-18T00:00:00Z")

    def test_does_not_match_nearby_restaurant_with_different_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "michelin.json"
            path.write_text(
                json.dumps({"restaurants": parse_michelin_listing(LISTING_HTML)}),
                encoding="utf-8",
            )
            provider = MichelinProvider(path)
            matched = provider.match(
                {
                    "name": "Completely Different Cafe",
                    "latitude": 35.65880,
                    "longitude": 139.70250,
                }
            )
        self.assertIsNone(matched)

    def test_strict_snapshot_match_never_enriches_and_requires_high_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "michelin.json"
            path.write_text(
                json.dumps(
                    {
                        "fetched_at": "2026-07-18T00:00:00Z",
                        "restaurants": parse_michelin_listing(LISTING_HTML),
                    }
                ),
                encoding="utf-8",
            )
            provider = MichelinProvider(path)
            provider._fetch_detail = lambda _restaurant: self.fail("must not enrich")
            matched = provider.match_snapshot_strict(
                {
                    "name": "Example Restaurant",
                    "latitude": 35.6584466,
                    "longitude": 139.7021636,
                }
            )
            weak = provider.match_snapshot_strict(
                {
                    "name": "Example Restaurant",
                    "latitude": 35.6592,
                    "longitude": 139.7021636,
                }
            )
            no_coordinates = provider.match_snapshot_strict({"name": "Example Restaurant"})
        self.assertEqual(matched["id"], "101")
        self.assertGreaterEqual(matched["match_score"], 85)
        self.assertIsNone(weak)
        self.assertIsNone(no_coordinates)

    def test_matches_cross_language_name_by_phone_website_and_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "michelin.json"
            path.write_text(
                json.dumps(
                    {
                        "restaurants": [
                            {
                                "id": "1194082",
                                "name": "Tour D'argent Tokyo",
                                "url": "https://guide.michelin.com/restaurant/tour-d-argent",
                                "latitude": 35.680691,
                                "longitude": 139.734172,
                                "distinction": "ONE_STAR",
                                "distinction_label": "米其林一星",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            provider = MichelinProvider(path)
            provider._fetch_detail = lambda _restaurant: {
                "phone": "+81 3-3239-3111",
                "website": "https://tourdargent.jp/",
            }
            matched = provider.match(
                {
                    "name": "法國料理 銀塔 東京",
                    "phone": "03-3239-3111",
                    "website": "http://www.tourdargent.jp/",
                    "latitude": 35.6809101,
                    "longitude": 139.7340409,
                }
            )
        self.assertIsNotNone(matched)
        self.assertEqual(matched["id"], "1194082")
        self.assertEqual(matched["match_score"], 98.4)
        self.assertIn("電話完全相同", matched["match_reasons"])
        self.assertIn("官方網站完全相同", matched["match_reasons"])

    def test_rejects_ambiguous_shared_phone_without_website(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "michelin.json"
            restaurants = [
                {
                    "id": str(index),
                    "name": name,
                    "url": f"https://guide.michelin.com/restaurant/{index}",
                    "phone": "03-0000-0000",
                    "latitude": 35.0 + offset,
                    "longitude": 139.0,
                    "distinction_label": "米其林指南入選",
                }
                for index, name, offset in (
                    (1, "Hotel Restaurant A", 0.00005),
                    (2, "Hotel Restaurant B", 0.00010),
                )
            ]
            path.write_text(json.dumps({"restaurants": restaurants}), encoding="utf-8")
            provider = MichelinProvider(path)
            matched = provider.match(
                {
                    "name": "完全不同的中文名稱",
                    "phone": "03-0000-0000",
                    "latitude": 35.0,
                    "longitude": 139.0,
                }
            )
        self.assertIsNone(matched)


if __name__ == "__main__":
    unittest.main()
