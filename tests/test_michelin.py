import json
from pathlib import Path
import tempfile
import unittest

from meshi_lens.michelin import (
    MichelinProvider,
    michelin_listing_meta,
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


class MichelinTests(unittest.TestCase):
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
            matched = provider.match(
                {
                    "name": "Example Restaurant",
                    "latitude": 35.6584466,
                    "longitude": 139.7021636,
                }
            )
        self.assertIsNotNone(matched)
        self.assertEqual(matched["id"], "101")
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


if __name__ == "__main__":
    unittest.main()
