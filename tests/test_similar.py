import unittest

from meshi_lens.similar import rank_similar_candidates


class SimilarRankingTests(unittest.TestCase):
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
        self.assertEqual([item["name"] for item in ranked], ["銀座の寿司店", "別の寿司店"])
        self.assertEqual(ranked[0]["reasons"], ["同為寿司", "同為銀座駅", "晚餐價位接近"])
        self.assertNotIn("元の店", [item["name"] for item in ranked])

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
