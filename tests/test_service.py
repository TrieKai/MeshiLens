import unittest

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


class ServiceTests(unittest.TestCase):
    def test_match_and_cache(self) -> None:
        provider = FakeProvider()
        service = MatchService(provider=provider)
        place = {
            "name": "割烹 清水屋",
            "alternate_name": "清水屋",
            "address": "茨城県潮来市永山2651-1",
            "phone": "0299-64-2011",
            "tabelog_url": "https://tabelog.com/ibaraki/A0804/A080401/8000477/dtlmenu/",
        }
        first = service.match(place)
        second = service.match(place)
        self.assertTrue(first["matched"])
        self.assertEqual(first["selected"]["rating"], 3.54)
        self.assertTrue(second["cached"])
        self.assertEqual(provider.calls, 1)
        self.assertEqual(
            first["place"]["tabelog_url"],
            "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
        )

    def test_requires_name(self) -> None:
        service = MatchService(provider=FakeProvider())
        with self.assertRaisesRegex(ValueError, "名稱"):
            service.match({"address": "somewhere"})


if __name__ == "__main__":
    unittest.main()
