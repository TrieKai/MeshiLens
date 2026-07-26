import unittest

from meshi_lens.cache import MemoryTTLCache
from meshi_lens.service import MatchService, SIMILAR_CACHE_VERSION


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.similar_calls = 0
        self.map_target_calls = 0

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

    def search_similar(self, _seed, limit=20):
        self.similar_calls += 1
        return [
            {
                "name": "近江町割烹",
                "rating": 3.72,
                "review_count": 91,
                "url": "https://tabelog.com/ishikawa/A1701/A170101/1700002/",
                "genres": ["日本料理"],
                "station": "金沢駅",
                "address": "石川県金沢市下近江町",
                "lunch_price": "￥10,000～￥14,999",
                "dinner_price": "￥10,000～￥14,999",
            }
        ][:limit]

    def fetch_similar_map_target(self, _url):
        self.map_target_calls += 1
        return {"address": "東京都文京区音羽1-17-16 中銀音羽マンシオン１F", "latitude": 35.7163, "longitude": 139.7287}


class FakeMichelinProvider:
    def match(self, _place, _tabelog=None):
        return {
            "name": "清水屋",
            "distinction": "BIB_GOURMAND",
            "distinction_label": "必比登推介",
            "url": "https://guide.michelin.com/example",
        }


class BatchMichelinProvider:
    def __init__(self) -> None:
        self.strict_calls: list[dict] = []

    def match_snapshot_strict(self, place):
        self.strict_calls.append(place)
        if place["name"] != "清水屋":
            return None
        return {
            "distinction": "BIB_GOURMAND",
            "distinction_label": "必比登推介",
            "green_star": False,
            "url": "https://guide.michelin.com/example",
            "snapshot_fetched_at": "2026-07-18T00:00:00Z",
        }

    def match(self, *_args, **_kwargs):
        raise AssertionError("batch must not use detail matcher")


class FailingProvider:
    def search(self, _place):
        raise RuntimeError("Tabelog 403")


class FakeAdvisor:
    model = "test-model"
    configured = True

    def __init__(self) -> None:
        self.calls = 0

    def summarize_facts(self, _facts):
        self.calls += 1
        return {
            "headline": "適合聚餐",
            "summary": "根據價位與獎項整理。",
            "best_for": ["聚餐"],
            "cautions": [],
            "evidence": ["Tabelog 評分"],
        }

    def summarize(self, place, candidate, michelin):
        from meshi_lens.advice import advice_facts

        return self.summarize_facts(advice_facts(place, candidate, michelin))


class ServiceTests(unittest.TestCase):
    def test_similar_cache_version_is_current(self) -> None:
        self.assertEqual(SIMILAR_CACHE_VERSION, "nearby-v16")

    def test_michelin_batch_returns_badges_per_card_without_detail_matching(self) -> None:
        michelin = BatchMichelinProvider()
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=michelin,
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        result = service.match_michelin_batch(
            {
                "cards": [
                    {"key": "one", "name": "清水屋", "latitude": 35.6, "longitude": 139.7},
                    {"key": "two", "name": "別的店"},
                    {"key": "three"},
                    "not-a-card",
                ]
            }
        )
        self.assertEqual(result["results"][0]["status"], "matched")
        self.assertEqual(result["results"][0]["badge"]["label"], "必比登推介")
        self.assertEqual(result["results"][1], {"key": "two", "status": "no_match"})
        self.assertEqual(result["results"][2], {"key": "three", "status": "invalid"})
        self.assertEqual(result["results"][3], {"key": "", "status": "invalid"})
        self.assertEqual(len(michelin.strict_calls), 2)

    def test_michelin_batch_enforces_card_limit(self) -> None:
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=BatchMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        with self.assertRaisesRegex(ValueError, "最多"):
            service.match_michelin_batch(
                {"cards": [{"key": str(index), "name": "清水屋"} for index in range(11)]}
            )

    def test_rejects_an_explicit_overseas_place_before_provider_lookup(self) -> None:
        provider = FakeProvider()
        service = MatchService(
            provider=provider,
            michelin_provider=FakeMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        with self.assertRaisesRegex(ValueError, "日本合理範圍外"):
            service.match(
                {
                    "name": "Overseas Restaurant",
                    "latitude": 40.7128,
                    "longitude": -74.006,
                    "coordinates_source": "place",
                }
            )
        self.assertEqual(provider.calls, 0)

    def test_viewport_coordinates_do_not_reject_a_place(self) -> None:
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=FakeMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        result = service.match(
            {
                "name": "清水屋",
                "latitude": 40.7128,
                "longitude": -74.006,
                "coordinates_source": "viewport",
            }
        )
        self.assertIn("matched", result)

    def test_batch_skips_explicit_overseas_cards(self) -> None:
        michelin = BatchMichelinProvider()
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=michelin,
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        result = service.match_michelin_batch(
            {
                "cards": [
                    {
                        "key": "overseas",
                        "name": "Overseas Restaurant",
                        "latitude": 40.7128,
                        "longitude": -74.006,
                        "coordinates_source": "place",
                    }
                ]
            }
        )
        self.assertEqual(result["results"], [{"key": "overseas", "status": "no_match"}])
        self.assertEqual(michelin.strict_calls, [])

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

    def test_michelin_rematch_uses_tabelog_hint_and_separate_cache(self) -> None:
        class TrackingMichelin:
            def __init__(self) -> None:
                self.calls: list[object] = []

            def match(self, place, tabelog=None):
                self.calls.append(tabelog)
                if tabelog and tabelog.get("phone") == "03-1111-2222":
                    return {
                        "name": "清水屋",
                        "distinction_label": "米其林一星",
                        "url": "https://guide.michelin.com/refined",
                    }
                return None

        michelin = TrackingMichelin()
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=michelin,
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        place = {"name": "Shimizuya", "latitude": 35.65, "longitude": 139.70}
        first = service.match_michelin(place)
        second = service.match_michelin(
            {
                **place,
                "tabelog": {
                    "name": "清水屋",
                    "phone": "03-1111-2222",
                    "website": "https://example.com",
                },
            }
        )
        self.assertIsNone(first["michelin"])
        self.assertEqual(second["michelin"]["distinction_label"], "米其林一星")
        self.assertEqual(len(michelin.calls), 2)
        self.assertIsNone(michelin.calls[0])
        self.assertEqual(michelin.calls[1]["phone"], "03-1111-2222")

    def test_advice_accepts_facts_payload(self) -> None:
        advisor = FakeAdvisor()
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=FakeMichelinProvider(),
            advisor=advisor,
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
        )
        result = service.advice(
            {
                "facts": {
                    "restaurant_name": "清水屋",
                    "tabelog_rating": 3.5,
                    "michelin_distinction": "必比登推介",
                }
            }
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["advice"]["headline"], "適合聚餐")
        self.assertEqual(advisor.calls, 1)

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

    def test_similar_returns_ranked_tabelog_cards_and_caches_one_search(self) -> None:
        provider = FakeProvider()
        service = MatchService(
            provider=provider,
            michelin_provider=FakeMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
            similar_cache=MemoryTTLCache(),
        )
        payload = {
            "selected": {
                "name": "割烹 清水屋",
                "url": "https://tabelog.com/ishikawa/A1701/A170101/1700001/",
                "genres": ["日本料理"],
                "station": "金沢駅",
                "address": "石川県金沢市",
                "dinner_price": "￥10,000～￥14,999",
            }
        }
        first = service.similar(payload)
        second = service.similar(payload)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(provider.similar_calls, 1)
        self.assertEqual(first["recommendations"][0]["name"], "近江町割烹")
        self.assertEqual(first["recommendations"][0]["address"], "石川県金沢市下近江町")
        self.assertIn("同為日本料理", first["recommendations"][0]["reasons"])
        self.assertEqual(first["diagnostics"]["search_scope"], "金沢駅")
        self.assertEqual(first["diagnostics"]["returned_count"], 1)
        self.assertEqual(
            first["recommendations"][0]["reasons"][:2],
            ["同為日本料理", "同為金沢站"],
        )

    def test_similar_map_target_uses_full_tabelog_address_after_explicit_click(self) -> None:
        provider = FakeProvider()
        service = MatchService(
            provider=provider,
            michelin_provider=FakeMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
            similar_cache=MemoryTTLCache(),
        )
        payload = {"name": "MENSHO", "url": "https://tabelog.com/tokyo/A1323/A132302/13203848/"}
        first = service.similar_map_target(payload)
        second = service.similar_map_target(payload)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(provider.map_target_calls, 1)
        self.assertEqual(first["address"], "東京都文京区音羽1-17-16 中銀音羽マンシオン１F")
        self.assertIn("MENSHO+%E6%9D%B1%E4%BA%AC%E9%83%BD", first["maps_url"])

    def test_similar_requires_a_cuisine_and_canonical_tabelog_url(self) -> None:
        service = MatchService(
            provider=FakeProvider(),
            michelin_provider=FakeMichelinProvider(),
            cache=MemoryTTLCache(),
            michelin_cache=MemoryTTLCache(),
            advice_cache=MemoryTTLCache(),
            similar_cache=MemoryTTLCache(),
        )
        with self.assertRaisesRegex(ValueError, "料理類型"):
            service.similar(
                {
                    "selected": {
                        "name": "清水屋",
                        "url": "https://tabelog.com/ishikawa/A1701/A170101/1700001/",
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()
