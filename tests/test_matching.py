from importlib.resources import files
import json
import math
import unittest

from meshi_lens.matching import (
    address_similarity,
    haversine_meters,
    normalize_address,
    normalize_name,
    normalize_phone,
    rank_candidates,
    score_candidate,
)


class MatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.place = {
            "name": "割烹 清水屋",
            "address": "日本、〒311-2437 茨城県潮来市永山2651-1",
            "phone": "0299-64-2011",
            "latitude": 35.9584063,
            "longitude": 140.5057859,
        }
        self.candidate = {
            "name": "清水屋",
            "address": "茨城県潮来市永山2651",
            "phone": "0299-64-2011",
            "latitude": 35.9584,
            "longitude": 140.5058,
            "rating": 3.54,
            "review_count": 119,
            "url": "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
        }

    def test_normalization(self) -> None:
        self.assertEqual(normalize_name("割烹 清水屋 本店"), "清水屋")
        self.assertEqual(normalize_name("うなぎ松のぶ"), "松のぶ")
        self.assertEqual(normalize_phone("0299-64-2011"), "0299642011")
        self.assertEqual(normalize_phone("+81 299-64-2011"), "0299642011")
        self.assertIn("永山2651", normalize_address("〒311-2437 茨城県潮来市永山2651-1"))

    def test_known_restaurant_is_high_confidence(self) -> None:
        result = score_candidate(self.place, self.candidate)
        self.assertEqual(result.confidence, "high")
        self.assertGreaterEqual(result.score, 90)
        self.assertIn("電話完全相同", result.reasons)

    def test_viewport_coordinates_do_not_overrule_real_candidate(self) -> None:
        wrong = {**self.candidate, "name": "別の店", "phone": "03-0000-0000"}
        ranked = rank_candidates(self.place, [wrong, self.candidate])
        self.assertEqual(ranked[0]["name"], "清水屋")

    def test_haversine(self) -> None:
        distance = haversine_meters(35.0, 140.0, 35.001, 140.0)
        self.assertTrue(math.isclose(distance or 0, 111.2, rel_tol=0.02))

    def test_coordinates_resolve_missing_phone_and_different_address(self) -> None:
        place = {
            "name": "麺香房 きくち",
            "latitude": 36.1752734,
            "longitude": 139.8372519,
        }
        candidate = {
            "name": "きくち",
            "latitude": 36.17527176918912,
            "longitude": 139.83725177760917,
        }
        result = score_candidate(place, candidate)
        self.assertEqual(result.confidence, "high")
        self.assertGreaterEqual(result.score, 75)

    def test_direct_maps_tabelog_link_is_high_confidence(self) -> None:
        result = score_candidate(self.place, {**self.candidate, "direct_source": True})
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.score, 98.0)

    def test_duplicate_listing_prefers_page_with_reviews(self) -> None:
        place = {
            "name": "CURRY HOUSE KURAGE",
            "phone": "+81 29-352-2232",
            "latitude": 36.3141659,
            "longitude": 140.5705587,
        }
        duplicate = {
            "name": "CURRY HOUSE KURAGE",
            "phone": "029-352-2232",
            "latitude": 36.314173868,
            "longitude": 140.570567680,
            "rating": None,
            "review_count": None,
            "url": "https://tabelog.com/ibaraki/A0801/A080102/8030804/",
        }
        established = {
            **duplicate,
            "latitude": 36.314173568,
            "longitude": 140.570567020,
            "rating": 3.1,
            "review_count": 17,
            "url": "https://tabelog.com/ibaraki/A0801/A080102/8028260/",
        }
        ranked = rank_candidates(place, [duplicate, established])
        self.assertEqual(ranked[0]["url"], established["url"])
        self.assertIn("評論資料較完整", ranked[0]["match_reasons"][-1])
        self.assertEqual(len(ranked), 1)

    def test_deduplicates_equivalent_tabelog_language_urls(self) -> None:
        first = {**self.candidate, "url": "https://tabelog.com/tw/ibaraki/A0804/A080401/8000477/"}
        ranked = rank_candidates(self.place, [self.candidate, first])
        self.assertEqual(len(ranked), 1)

    def test_prior_location_is_ranked_after_the_current_tabelog_listing(self) -> None:
        old = {
            **self.candidate,
            "url": "https://tabelog.com/ibaraki/A0804/A080401/8000478/",
            "address": "茨城県潮来市別所1-1-1",
            "phone": "0299-00-0000",
            "latitude": 35.9609,
            "longitude": 140.5058,
            "is_relocated": True,
            "relocated_to_url": self.candidate["url"],
            "rating": 4.0,
            "review_count": 10_000,
        }
        ranked = rank_candidates(self.place, [old, self.candidate])
        self.assertEqual(ranked[0]["url"], self.candidate["url"])
        self.assertIn("Tabelog 標示為移轉前資料", ranked[1]["match_reasons"])

    def test_traditional_chinese_and_old_kanji_fold_to_japanese_forms(self) -> None:
        self.assertEqual(normalize_name("一蘭 澀谷店"), normalize_name("一蘭 渋谷店"))
        self.assertEqual(normalize_name("神戶牛 髙橋"), normalize_name("神戸牛 高橋"))
        self.assertEqual(
            normalize_address("東京都澀谷區神南1丁目22-7"),
            normalize_address("東京都渋谷区神南1-22-7"),
        )

    def test_kanji_variant_table_folds_single_characters_once(self) -> None:
        table = json.loads(
            files("meshi_lens").joinpath("data/kanji-variants.json").read_text(encoding="utf-8")
        )
        self.assertTrue(all(len(source) == 1 and len(target) == 1 for source, target in table.items()))
        self.assertFalse(set(table) & set(table.values()))

    def test_romanised_maps_address_matches_the_japanese_tabelog_address(self) -> None:
        # Google Maps (zh-TW and English UI) and its share links romanise Japanese addresses.
        tabelog = {
            "name": "一蘭 渋谷店",
            "address": "東京都 渋谷区 神南1-22-7 岩本ビル Ｂ１Ｆ",
            "phone": "050-1808-2546",
        }
        for address in (
            "日本〒150-0041 Tokyo, Shibuya, Jinnan, 1 Chome−22−7 岩本ビル B1F",
            "岩本ビル B1F 1 Chome-22-7 Jinnan, Shibuya, Tokyo 150-0041日本",
            "1 Chome-22-7 Jinnan, Shibuya City, Tokyo 150-0041, Japan",
        ):
            with self.subTest(address=address):
                result = score_candidate({"name": "一蘭 澀谷店", "address": address}, tabelog)
                self.assertEqual(result.confidence, "medium")
                self.assertIn("店名高度相似", result.reasons)
                self.assertIn("地址高度相似", result.reasons)

    def test_romanised_address_needs_the_same_block_numbers(self) -> None:
        tabelog = "東京都 渋谷区 神南1-22-7 岩本ビル Ｂ１Ｆ"
        self.assertLess(address_similarity("1 Chome-20-5 Jinnan, Shibuya City, Tokyo", tabelog), 0.45)
        # The same numbers in another city count for little without the ward or building.
        self.assertEqual(address_similarity("1 Chome-22-7 Umeda, Kita Ward, Osaka", tabelog), 0.6)


if __name__ == "__main__":
    unittest.main()
