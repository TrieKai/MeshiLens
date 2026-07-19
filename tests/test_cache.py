import tempfile
import unittest
from pathlib import Path
from unittest import mock

from meshi_lens.cache import (
    DEFAULT_ADVICE_TTL_SECONDS,
    DEFAULT_MATCH_TTL_SECONDS,
    DEFAULT_MICHELIN_TTL_SECONDS,
    FileTTLCache,
    LayeredTTLCache,
    MemoryTTLCache,
    UpstashRestCache,
    build_cache,
)
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
        return {"name": "清水屋", "distinction_label": "必比登推介"}


class CacheTests(unittest.TestCase):
    def test_default_ttls(self) -> None:
        self.assertEqual(DEFAULT_MATCH_TTL_SECONDS, 21_600)
        self.assertEqual(DEFAULT_MICHELIN_TTL_SECONDS, 86_400)
        self.assertEqual(DEFAULT_ADVICE_TTL_SECONDS, 86_400)

    def test_memory_ttl_expires(self) -> None:
        cache = MemoryTTLCache(ttl_seconds=10, max_items=8)
        cache.set("a", {"ok": True})
        self.assertEqual(cache.get("a"), {"ok": True})
        with mock.patch("meshi_lens.cache.time.time", return_value=1_000_000):
            cache.set("a", {"ok": True})
        with mock.patch("meshi_lens.cache.time.time", return_value=1_000_011):
            self.assertIsNone(cache.get("a"))

    def test_file_cache_persists_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = FileTTLCache(directory, ttl_seconds=3_600, namespace="match")
            first.set("place|key", {"matched": True, "selected": {"name": "清水屋"}})
            second = FileTTLCache(directory, ttl_seconds=3_600, namespace="match")
            self.assertEqual(second.get("place|key")["selected"]["name"], "清水屋")

    def test_layered_cache_warms_l1_from_l2(self) -> None:
        l1 = MemoryTTLCache(ttl_seconds=3_600, max_items=8)
        l2 = MemoryTTLCache(ttl_seconds=3_600, max_items=8)
        layered = LayeredTTLCache(l1, l2)
        l2.set("k", {"value": 1})
        self.assertEqual(layered.get("k"), {"value": 1})
        self.assertEqual(l1.get("k"), {"value": 1})

    def test_build_cache_uses_file_backend_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(
                "os.environ",
                {
                    "MESHI_CACHE_DIR": directory,
                    "UPSTASH_REDIS_REST_URL": "",
                    "UPSTASH_REDIS_REST_TOKEN": "",
                    "MESHI_REDIS_URL": "",
                    "REDIS_URL": "",
                    "MESHI_CACHE_FILE": "",
                },
                clear=False,
            ):
                cache = build_cache(ttl_seconds=100, namespace="unit")
                cache.set("abc", {"n": 1})
                files = list(Path(directory).joinpath("unit").glob("*.json"))
                self.assertEqual(len(files), 1)
                self.assertEqual(cache.get("abc"), {"n": 1})

    def test_build_cache_uses_vercel_upstash_rest_variables(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "KV_REST_API_URL": "https://example.upstash.io",
                "KV_REST_API_TOKEN": "test-token",
                "UPSTASH_REDIS_REST_URL": "",
                "UPSTASH_REDIS_REST_TOKEN": "",
                "MESHI_REDIS_URL": "",
                "REDIS_URL": "",
            },
            clear=False,
        ):
            cache = build_cache(ttl_seconds=100, namespace="unit")
        self.assertIsInstance(cache, LayeredTTLCache)
        self.assertIsInstance(cache.layers[0], MemoryTTLCache)
        self.assertIsInstance(cache.layers[1], UpstashRestCache)

    def test_match_service_reuses_injected_persistent_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shared = FileTTLCache(directory, ttl_seconds=3_600, namespace="match")
            first = MatchService(
                provider=FakeProvider(),
                michelin_provider=FakeMichelinProvider(),
                cache=shared,
                michelin_cache=MemoryTTLCache(),
                advice_cache=MemoryTTLCache(),
            )
            place = {"name": "清水屋", "phone": "0299-64-2011"}
            first.match(place, include_michelin=False)
            provider = FakeProvider()
            second = MatchService(
                provider=provider,
                michelin_provider=FakeMichelinProvider(),
                cache=FileTTLCache(directory, ttl_seconds=3_600, namespace="match"),
                michelin_cache=MemoryTTLCache(),
                advice_cache=MemoryTTLCache(),
            )
            result = second.match(place, include_michelin=False)
            self.assertTrue(result["cached"])
            self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
