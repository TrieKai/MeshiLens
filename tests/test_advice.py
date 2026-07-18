import unittest
from unittest.mock import patch

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

    def test_qwen_uses_non_reasoning_json_mode(self) -> None:
        advisor = GroqDiningAdvisor(api_key="test-key")
        body = advisor._request_body(advice_facts(self.place, self.candidate, None))
        self.assertEqual(body["model"], "qwen/qwen3.6-27b")
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(body["reasoning_format"], "hidden")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["max_completion_tokens"], 700)
        self.assertEqual(body["messages"][0]["role"], "user")
        self.assertIn("清水屋", body["messages"][0]["content"])

    def test_gpt_oss_keeps_its_own_reasoning_effort(self) -> None:
        advisor = GroqDiningAdvisor(api_key="test-key", model="openai/gpt-oss-20b")
        body = advisor._request_body({"restaurant_name": "測試"})
        self.assertEqual(body["reasoning_effort"], "low")

    def test_sends_an_identifying_user_agent_to_groq(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read() -> bytes:
                return b'{"choices":[{"message":{"content":"{\\"summary\\":\\"test\\"}"}}]}'

        advisor = GroqDiningAdvisor(api_key="test-key")
        with patch("meshi_lens.advice.urlopen", return_value=FakeResponse()) as urlopen:
            advisor.summarize(self.place, self.candidate, None)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), "MeshiLens/0.4 (+https://meshilens.vercel.app)")
        self.assertEqual(request.get_header("Accept"), "application/json")


if __name__ == "__main__":
    unittest.main()
