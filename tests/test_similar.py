import unittest

from meshi_lens.similar import rank_similar_candidates
from meshi_lens.localization import tabelog_genre_zh_hant_map


class SimilarRankingTests(unittest.TestCase):
    def test_cuisine_translation_map_is_loaded_from_editable_data_file(self) -> None:
        self.assertEqual(tabelog_genre_zh_hant_map()["アメリカ料理"], "美式料理")

    def test_prefers_same_cuisine_station_and_budget_without_fetching_details(self) -> None:
        seed = {
            "url": "https://tabelog.com/tokyo/A1301/A130101/1300001/",
            "genres": ["寿司"],
            "station": "銀座駅",
            "address": "東京都中央区銀座",
            "dinner_price": "￥20,000～￥29,999",
        }
        ranked = rank_similar_candidates(
            seed,
            [
                {"name": "元の店", "url": seed["url"], "genres": ["寿司"]},
                {
                    "name": "銀座の寿司店",
                    "url": "https://tabelog.com/tokyo/A1301/A130101/1300002/",
                    "genres": ["寿司"],
                    "station": "銀座駅",
                    "address": "東京都中央区銀座1-1-1",
                    "rating": 3.81,
                    "review_count": 210,
                    "dinner_price": "￥20,000～￥29,999",
                },
                {
                    "name": "別の寿司店",
                    "url": "https://tabelog.com/tokyo/A1301/A130101/1300003/",
                    "genres": ["寿司"],
                    "station": "新橋駅",
                    "rating": 3.95,
                    "review_count": 800,
                    "dinner_price": "￥50,000～￥59,999",
                },
            ],
        )
        self.assertEqual([item["name"] for item in ranked], ["銀座の寿司店"])
        self.assertEqual(ranked[0]["reasons"], ["同為壽司", "同為銀座站", "晚餐價位接近"])
        self.assertEqual(ranked[0]["address"], "東京都中央区銀座1-1-1")
        self.assertNotIn("元の店", [item["name"] for item in ranked])

    def test_rejects_a_same_cuisine_restaurant_in_a_different_prefecture(self) -> None:
        ranked = rank_similar_candidates(
            {
                "url": "https://tabelog.com/tokyo/A1301/A130101/1300001/",
                "genres": ["寿司"],
                "station": "銀座駅",
                "address": "東京都中央区銀座1-1-1",
            },
            [
                {
                    "name": "札幌の寿司店",
                    "url": "https://tabelog.com/hokkaido/A0101/A010101/1000001/",
                    "genres": ["寿司"],
                    "station": "札幌駅",
                    "address": "北海道札幌市中央区1-1",
                    "rating": 4.2,
                    "review_count": 5000,
                }
            ],
        )
        self.assertEqual(ranked, [])

    def test_accepts_a_nearby_different_station_in_the_same_ward(self) -> None:
        ranked = rank_similar_candidates(
            {
                "url": "https://tabelog.com/tokyo/A1301/A130101/1300001/",
                "genres": ["寿司"],
                "station": "銀座駅",
                "address": "東京都中央区銀座1-1-1",
            },
            [
                {
                    "name": "築地の寿司店",
                    "url": "https://tabelog.com/tokyo/A1301/A130101/1300002/",
                    "genres": ["寿司"],
                    "station": "築地駅",
                    "address": "東京都中央区築地2-2-2",
                    "rating": 3.8,
                    "review_count": 100,
                }
            ],
        )
        self.assertEqual(ranked[0]["reasons"][:2], ["同為壽司", "同一行政區"])

    def test_filters_candidates_without_a_similarity_signal(self) -> None:
        ranked = rank_similar_candidates(
            {"url": "https://tabelog.com/tokyo/A1301/A130101/1300001/", "genres": ["寿司"]},
            [
                {
                    "name": "遠方のカフェ",
                    "url": "https://tabelog.com/tokyo/A1301/A130101/1300002/",
                    "genres": ["カフェ"],
                    "rating": 3.9,
                    "review_count": 500,
                }
            ],
        )
        self.assertEqual(ranked, [])

    def test_localizes_tabelog_cuisine_in_display_reasons(self) -> None:
        ranked = rank_similar_candidates(
            {
                "url": "https://tabelog.com/tokyo/A1301/A130101/1300001/",
                "genres": ["アメリカ料理"],
                "station": "銀座駅",
            },
            [
                {
                    "name": "美式餐廳",
                    "url": "https://tabelog.com/tokyo/A1301/A130101/1300002/",
                    "genres": ["アメリカ料理"],
                    "station": "銀座駅",
                    "rating": 3.5,
                    "review_count": 20,
                }
            ],
        )
        self.assertEqual(ranked[0]["reasons"][:2], ["同為美式料理", "同為銀座站"])
