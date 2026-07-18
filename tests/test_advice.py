import unittest

from meshi_lens.advice import GroqDiningAdvisor, _validate_advice, advice_facts


class AdviceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.place = {"name": "割烹 清水屋", "address": "茨城県潮来市永山2651-1"}
        self.candidate = {
            "name": "清水屋",
            "rating": 3.54,
            "review_count": 119,
            "genres": ["割烹・小料理"],
            "dinner_price": "￥10,000～￥14,999",
            "reservation_status": "available",
            "hyakumeiten": [{"year": 2024}, {"year": 2025}],
            "payment": {"cards": {"accepted": True}},
        }

    def test_facts_are_structured_and_exclude_review_text(self) -> None:
        facts = advice_facts(self.place, self.candidate, {"distinction_label": "必比登推介"})
        self.assertEqual(facts["restaurant_name"], "清水屋")
        self.assertEqual(facts["hyakumeiten_years"], [2025, 2024])
        self.assertEqual(facts["michelin_distinction"], "必比登推介")
        self.assertNotIn("reviews", facts)
        self.assertNotIn("review_text", facts)

    def test_response_is_bounded(self) -> None:
        advice = _validate_advice(
            {
                "headline": "適合特別聚餐",
                "summary": "晚餐預算偏高，且有可預約資訊。",
                "best_for": ["聚餐", "日式料理"],
                "cautions": ["午餐價位未提供"],
                "evidence": ["Tabelog 3.54 分", "2025 百名店"],
            }
        )
        self.assertEqual(advice["best_for"], ["聚餐", "日式料理"])
        self.assertEqual(advice["evidence"][0], "Tabelog 3.54 分")

    def test_unconfigured_advisor_does_not_make_a_network_request(self) -> None:
        advisor = GroqDiningAdvisor(api_key="")
        with self.assertRaisesRegex(RuntimeError, "尚未設定"):
            advisor.summarize(self.place, self.candidate, None)


if __name__ == "__main__":
    unittest.main()
