import math
import unittest

from meshi_lens.matching import (
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


if __name__ == "__main__":
    unittest.main()
