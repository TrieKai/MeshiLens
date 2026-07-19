import unittest

from meshi_lens.cache import MemoryTTLCache
from meshi_lens.service import MatchService


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, _place):
        self.calls += 1
        return [
            {
                "name": "清水屋",
                "address": "茨城県潮来市永山2651",
                "phone": "0299-64-2011",
                "rating": 3.54,
                "review_count": 119,
                "url": "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
            }
        ]


class FakeMichelinProvider:
    def match(self, _place, _tabelog=None):
        return {
            "name": "清水屋",
            "distinction": "BIB_GOURMAND",
            "distinction_label": "必比登推介",
            "url": "https://guide.michelin.com/example",
        }


class FailingProvider:
    def search(self, _place):
        raise RuntimeError("Tabelog 403")


class FakeAdvisor:
    model = "test-model"
    configured = True

    def __init__(self) -> None:
        self.calls = 0

    def summarize(self, _place, _candidate, _michelin):
        self.calls += 1
        return {
            "headline": "適合聚餐",
            "summary": "根據價位與獎項整理。",
            "best_for": ["聚餐"],
            "cautions": [],
            "evidence": ["Tabelog 評分"],
        }


class ServiceTests(unittest.TestCase):
    def test_match_and_cache(self) -> None:
        provider = FakeProvider()
        service = MatchService(
            provider=provider,
            michelin_provider=FakeMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        place = {
            "name": "割烹 清水屋",
            "alternate_name": "清水屋",
            "address": "茨城県潮来市永山2651-1",
            "phone": "0299-64-2011",
            "website": "https://www.kappo-shimizuya.com/",
            "tabelog_url": "https://tabelog.com/ibaraki/A0804/A080401/8000477/dtlmenu/",
        }
        first = service.match(place)
        second = service.match(place)
        self.assertTrue(first["matched"])
        self.assertEqual(first["selected"]["rating"], 3.54)
        self.assertEqual(first["michelin"]["distinction"], "BIB_GOURMAND")
        self.assertEqual(first["place"]["website"], "https://www.kappo-shimizuya.com/")
        self.assertTrue(second["cached"])
        self.assertEqual(provider.calls, 1)
        self.assertEqual(
            first["place"]["tabelog_url"],
            "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
        )

    def test_requires_name(self) -> None:
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=FakeMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        with self.assertRaisesRegex(ValueError, "名稱"):
            service.match({"address": "somewhere"})

    def test_returns_michelin_when_tabelog_is_unavailable(self) -> None:
        service = MatchService(
            provider=FailingProvider(),
            michelin_provider=FakeMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        result = service.match({"name": "清水屋"})
        self.assertIsNone(result["selected"])
        self.assertEqual(result["michelin"]["distinction_label"], "必比登推介")
        self.assertEqual(result["tabelog_error"], "Tabelog 403")

    def test_michelin_can_return_without_waiting_for_tabelog(self) -> None:
        provider = FakeProvider()
        service = MatchService(
            provider=provider,
            michelin_provider=FakeMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        result = service.match_michelin({"name": "清水屋"})
        self.assertEqual(result["michelin"]["distinction_label"], "必比登推介")
        self.assertEqual(provider.calls, 0)

    def test_tabelog_match_can_skip_michelin(self) -> None:
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=FakeMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        result = service.match({"name": "清水屋"}, include_michelin=False)
        self.assertIsNone(result["michelin"])

    def test_advice_is_separate_and_cached(self) -> None:
        advisor = FakeAdvisor()
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=FakeMichelinProvider(),
            advisor=advisor,
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        payload = {
            "place": {"name": "清水屋"},
            "candidate": {"name": "清水屋", "url": "https://tabelog.com/example/", "rating": 3.5},
            "michelin": {"distinction_label": "必比登推介"},
        }
        first = service.advice(payload)
        second = service.advice(payload)
        self.assertEqual(first["advice"]["headline"], "適合聚餐")
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(advisor.calls, 1)

    def test_advice_cache_misses_when_facts_change(self) -> None:
        advisor = FakeAdvisor()
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=FakeMichelinProvider(),
            advisor=advisor,
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        base = {
            "place": {"name": "清水屋", "address": "茨城県潮来市"},
            "candidate": {
                "name": "清水屋",
                "rating": 3.5,
                "dinner_price": "￥10,000～￥14,999",
                "genres": ["割烹・小料理"],
            },
            "michelin": None,
        }
        first = service.advice(base)
        same_facts = service.advice(
            {
                **base,
                "candidate": {**base["candidate"], "url": "https://tabelog.com/other/", "score": 88},
            }
        )
        changed = service.advice(
            {**base, "candidate": {**base["candidate"], "rating": 3.9}}
        )
        self.assertFalse(first["cached"])
        self.assertTrue(same_facts["cached"])
        self.assertFalse(changed["cached"])
        self.assertEqual(advisor.calls, 2)

    def test_advice_is_hidden_until_groq_is_configured(self) -> None:
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=FakeMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        result = service.advice(
            {"place": {"name": "清水屋"}, "candidate": {"name": "清水屋"}}
        )
        self.assertFalse(result["available"])
        self.assertIsNone(result["advice"])


if __name__ == "__main__":
    unittest.main()
