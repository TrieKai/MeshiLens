import unittest
from urllib.parse import quote

from meshi_lens.provider import (
    canonical_restaurant_url,
    coordinates_from_tabelog_html,
    extract_tabelog_urls,
    hyakumeiten_from_tabelog_html,
    merge_candidate_details,
    restaurant_to_dict,
    web_search_queries,
)


class ProviderTests(unittest.TestCase):
    def test_searches_by_local_phone_before_translated_name(self) -> None:
        self.assertEqual(
            web_search_queries(
                {
                    "name": "Sandwich Shop MURATA",
                    "alternate_name": "",
                    "phone": "+81 29-897-1508",
                }
            ),
            [
                'site:tabelog.com "029-897-1508"',
                'site:tabelog.com "Sandwich Shop MURATA"',
            ],
        )

    def test_canonicalizes_review_and_language_urls(self) -> None:
        self.assertEqual(
            canonical_restaurant_url(
                "https://tabelog.com/tw/ibaraki/A0804/A080401/8000477/dtlrvwlst/"
            ),
            "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
        )

    def test_extracts_duckduckgo_redirect_once(self) -> None:
        target = "https://tabelog.com/ibaraki/A0804/A080401/8000477/"
        redirect = f"//duckduckgo.com/l/?uddg={quote(target, safe='')}"
        html = (
            f'<a class="result__a" href="{redirect}">清水屋</a>'
            f'<a class="result__a" href="{target}dtlrvwlst/">review</a>'
        )
        self.assertEqual(extract_tabelog_urls(html), [target])

    def test_extracts_tabelog_map_coordinates(self) -> None:
        html = '<div id="js-basics" data-lat="36.175271769" data-lng="139.837251778"></div>'
        self.assertEqual(
            coordinates_from_tabelog_html(html),
            (36.175271769, 139.837251778),
        )

    def test_extracts_hyakumeiten_history(self) -> None:
        html = """
        <div class="rdheader-badge-award">
          <a title="百名店ページへ"
             href="https://award.tabelog.com/hyakumeiten/japanese_west/2025/">
            <span><i>日本料理WEST百名店2025選出店</i></span>
          </a>
          <div class="rdheader-badge-award__tooltip">
            <p>食べログ 日本料理 WEST 百名店 2025 選出店</p>
          </div>
        </div>
        <div class="rstinfo-table-badge-hyakumeiten">
          <a href="https://award.tabelog.com/hyakumeiten/japanese_west/2025/">
            <i>日本料理 百名店 2025 選出店</i>
          </a>
        </div>
        <div class="rstinfo-table-badge-hyakumeiten">
          <a href="https://award.tabelog.com/hyakumeiten/japanese_west/2023/">
            <i>日本料理 百名店 2023 選出店</i>
          </a>
          <div class="rstinfo-table-badge-hyakumeiten__tooltip"><p>食べログ 日本料理 WEST 百名店 2023 選出店</p></div>
        </div>
        <div class="rstinfo-table-badge-hyakumeiten">
          <a href="https://award.tabelog.com/hyakumeiten/japanese_west/2021/">
            <i>日本料理 百名店 2021 選出店</i>
          </a>
          <div class="rstinfo-table-badge-hyakumeiten__tooltip"><p>食べログ 日本料理 WEST 百名店 2021 選出店</p></div>
        </div>
        """
        self.assertEqual(
            hyakumeiten_from_tabelog_html(html),
            [
                {
                    "label": "食べログ 日本料理 WEST 百名店 2025 選出店",
                    "category": "日本料理",
                    "area": "WEST",
                    "year": 2025,
                    "url": "https://award.tabelog.com/hyakumeiten/japanese_west/2025/",
                },
                {
                    "label": "食べログ 日本料理 WEST 百名店 2023 選出店",
                    "category": "日本料理",
                    "area": "WEST",
                    "year": 2023,
                    "url": "https://award.tabelog.com/hyakumeiten/japanese_west/2023/",
                },
                {
                    "label": "食べログ 日本料理 WEST 百名店 2021 選出店",
                    "category": "日本料理",
                    "area": "WEST",
                    "year": 2021,
                    "url": "https://award.tabelog.com/hyakumeiten/japanese_west/2021/",
                },
            ],
        )

    def test_keeps_additional_restaurant_details(self) -> None:
        candidate = restaurant_to_dict(
            {
                "name": "片折",
                "genres": ["日本料理"],
                "station": "金沢駅",
                "lunch_price": "￥40,000～￥49,999",
                "dinner_price": "￥40,000～￥49,999",
                "business_hours": "月・火 11:30 - 14:00",
                "closed_days": "日曜日",
            }
        )
        self.assertEqual(candidate["station"], "金沢駅")
        self.assertEqual(candidate["lunch_price"], "￥40,000～￥49,999")
        self.assertEqual(candidate["dinner_price"], "￥40,000～￥49,999")
        self.assertEqual(candidate["business_hours"], "月・火 11:30 - 14:00")
        self.assertEqual(candidate["closed_days"], "日曜日")

    def test_merges_coordinates_from_enriched_detail(self) -> None:
        summary = {
            "name": "カフェ ポエティカ",
            "url": "https://tabelog.com/ibaraki/A0802/A080201/8028118",
            "rating": 3.32,
            "latitude": None,
            "longitude": None,
        }
        detail = {
            "name": "カフェ ポエティカ",
            "url": "https://tabelog.com/ibaraki/A0802/A080201/8028118/",
            "rating": None,
            "latitude": 36.126572,
            "longitude": 140.118419,
            "genres": ["カフェ"],
            "is_hyakumeiten": False,
        }
        merged = merge_candidate_details(summary, detail)
        self.assertEqual(merged["rating"], 3.32)
        self.assertEqual(merged["latitude"], 36.126572)
        self.assertEqual(merged["longitude"], 140.118419)
        self.assertEqual(merged["genres"], ["カフェ"])

    def test_ignores_non_hyakumeiten_award(self) -> None:
        html = """
        <div class="rdheader-badge-award">
          <a href="https://award.tabelog.com/2026/restaurants/gold">
            The Tabelog Award 2026 Gold
          </a>
        </div>
        """
        self.assertEqual(hyakumeiten_from_tabelog_html(html), [])


if __name__ == "__main__":
    unittest.main()
