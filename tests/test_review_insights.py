import unittest
from pathlib import Path

from meshi_lens.cache import MemoryTTLCache
from meshi_lens.review_insights import (
    DEFAULT_REVIEW_INSIGHTS_TTL_SECONDS,
    MAX_REVIEWS,
    MAX_TOTAL_CHARS,
    SOURCE_NOTE,
    GroqReviewInsightsAdvisor,
    bound_review_texts,
    parse_public_review_texts,
    review_insights_cache_key,
    review_list_url,
    sanitize_review_insights_request,
    validate_tabelog_restaurant_url,
)
from meshi_lens.service import MatchService


FIXTURES = Path(__file__).parent / "fixtures"


class FakeReviewProvider:
    def __init__(self, html: str = "", error: Exception | None = None) -> None:
        self.html = html
        self.error = error
        self.calls = 0

    def fetch_review_list_html(self, _url: str) -> str:
        self.calls += 1
        if self.error:
            raise self.error
        return self.html


class FakeReviewAdvisor:
    model = "test-review-model"
    configured = True

    def __init__(self) -> None:
        self.calls = 0
        self.last_texts: list[str] | None = None

    def summarize(self, restaurant_name: str, review_texts: list[str]):
        self.calls += 1
        self.last_texts = list(review_texts)
        return {
            "summary": f"{restaurant_name} の公開評論多提到接客與季節食材。",
            "positive_themes": ["接客丁寧", "季節食材"],
            "cautions": ["價格偏高"],
            "sample_size": len(review_texts),
            "source_note": SOURCE_NOTE,
        }


class ReviewInsightsTests(unittest.TestCase):
    def test_url_validation_accepts_canonical_and_rejects_cross_host(self) -> None:
        url = validate_tabelog_restaurant_url(
            "https://tabelog.com/tw/ibaraki/A0804/A080401/8000477/dtlrvwlst/"
        )
        self.assertEqual(url, "https://tabelog.com/ibaraki/A0804/A080401/8000477/")
        self.assertEqual(
            review_list_url(url),
            "https://tabelog.com/ibaraki/A0804/A080401/8000477/dtlrvwlst/",
        )
        with self.assertRaisesRegex(ValueError, "tabelog.com"):
            validate_tabelog_restaurant_url("https://evil.example/ibaraki/A0804/A080401/8000477/")
        with self.assertRaisesRegex(ValueError, "合法"):
            validate_tabelog_restaurant_url("https://tabelog.com/rstLst/")

    def test_parser_fixture_strips_authors_and_bounds_count(self) -> None:
        html = (FIXTURES / "tabelog_review_list.html").read_text(encoding="utf-8")
        texts = parse_public_review_texts(html)
        self.assertGreaterEqual(len(texts), 8)
        joined = "\n".join(texts)
        self.assertNotIn("太郎レビュアー", joined)
        self.assertNotIn("花子", joined)
        self.assertNotIn("avatar1.jpg", joined)
        self.assertIn("接客が丁寧", joined)

        bounded = bound_review_texts(texts)
        self.assertLessEqual(len(bounded), MAX_REVIEWS)
        self.assertLessEqual(sum(len(item) for item in bounded), MAX_TOTAL_CHARS)
        self.assertEqual(len(bounded), 8)

    def test_empty_or_changed_markup_degrades(self) -> None:
        empty = (FIXTURES / "tabelog_review_list_empty.html").read_text(encoding="utf-8")
        self.assertEqual(parse_public_review_texts(empty), [])
        self.assertEqual(parse_public_review_texts(""), [])
        self.assertEqual(bound_review_texts([]), [])

    def test_bound_review_texts_enforces_total_chars(self) -> None:
        long_text = "味" * 900
        bounded = bound_review_texts([long_text] * 10, max_chars_per_review=480, max_total_chars=1000)
        self.assertLessEqual(len(bounded), MAX_REVIEWS)
        self.assertLessEqual(sum(len(item) for item in bounded), 1000)

    def test_sanitize_request_requires_name_and_url(self) -> None:
        cleaned = sanitize_review_insights_request(
            {
                "tabelog_url": "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
                "restaurant_name": "清水屋",
                "review_text": "should be ignored",
            }
        )
        self.assertEqual(
            cleaned["tabelog_url"],
            "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
        )
        self.assertNotIn("review_text", cleaned)
        with self.assertRaisesRegex(ValueError, "店家名稱"):
            sanitize_review_insights_request(
                {"tabelog_url": "https://tabelog.com/ibaraki/A0804/A080401/8000477/"}
            )

    def test_cache_and_service_never_store_review_bodies(self) -> None:
        html = (FIXTURES / "tabelog_review_list.html").read_text(encoding="utf-8")
        provider = FakeReviewProvider(html=html)
        advisor = FakeReviewAdvisor()
        cache = MemoryTTLCache(ttl_seconds=DEFAULT_REVIEW_INSIGHTS_TTL_SECONDS)
        service = MatchService(
            provider=provider,  # type: ignore[arg-type]
            review_advisor=advisor,  # type: ignore[arg-type]
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
            review_insights_cache=cache,
        )
        payload = {
            "tabelog_url": "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
            "restaurant_name": "清水屋",
        }
        first = service.review_insights(payload)
        self.assertTrue(first["available"])
        self.assertFalse(first["cached"])
        self.assertEqual(first["insights"]["source_note"], SOURCE_NOTE)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(advisor.calls, 1)
        self.assertTrue(advisor.last_texts)

        key = review_insights_cache_key(
            payload["tabelog_url"], model=advisor.model
        )
        cached = cache.get(key)
        self.assertIsNotNone(cached)
        serialized = str(cached)
        self.assertNotIn("太郎レビュアー", serialized)
        self.assertNotIn("接客が丁寧で、季節の食材", serialized)
        self.assertIn("insights", cached)

        second = service.review_insights(payload)
        self.assertTrue(second["cached"])
        self.assertEqual(provider.calls, 1)
        self.assertEqual(advisor.calls, 1)

    def test_forbidden_and_empty_pages_fail_closed(self) -> None:
        service = MatchService(
            provider=FakeReviewProvider(error=RuntimeError("403 Forbidden")),  # type: ignore[arg-type]
            review_advisor=FakeReviewAdvisor(),  # type: ignore[arg-type]
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
            review_insights_cache=MemoryTTLCache(),
        )
        with self.assertRaisesRegex(RuntimeError, "暫時無法取得"):
            service.review_insights(
                {
                    "tabelog_url": "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
                    "restaurant_name": "清水屋",
                }
            )

        empty_service = MatchService(
            provider=FakeReviewProvider(html="<html></html>"),  # type: ignore[arg-type]
            review_advisor=FakeReviewAdvisor(),  # type: ignore[arg-type]
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
            review_insights_cache=MemoryTTLCache(),
        )
        with self.assertRaisesRegex(RuntimeError, "暫時無法取得"):
            empty_service.review_insights(
                {
                    "tabelog_url": "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
                    "restaurant_name": "清水屋",
                }
            )

    def test_unconfigured_advisor_skips_network(self) -> None:
        advisor = GroqReviewInsightsAdvisor(api_key="")
        provider = FakeReviewProvider(html="should not fetch")
        service = MatchService(
            provider=provider,  # type: ignore[arg-type]
            review_advisor=advisor,
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
            review_insights_cache=MemoryTTLCache(),
        )
        result = service.review_insights(
            {
                "tabelog_url": "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
                "restaurant_name": "清水屋",
            }
        )
        self.assertFalse(result["available"])
        self.assertIsNone(result["insights"])
        self.assertEqual(provider.calls, 0)

    def test_prompt_forbids_verbatim_quotes(self) -> None:
        advisor = GroqReviewInsightsAdvisor(api_key="test-key")
        body = advisor._request_body("清水屋", ["接客が丁寧でした"] * 3)
        content = body["messages"][0]["content"]
        self.assertIn("禁止逐字引用", content)
        self.assertIn("禁止提及作者名稱", content)
        self.assertIn("清水屋", content)

    def test_ttl_constant_is_seven_days(self) -> None:
        self.assertEqual(DEFAULT_REVIEW_INSIGHTS_TTL_SECONDS, 7 * 86_400)


if __name__ == "__main__":
    unittest.main()
