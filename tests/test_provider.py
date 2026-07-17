import unittest
from urllib.parse import quote

from meshi_lens.provider import (
    canonical_restaurant_url,
    coordinates_from_tabelog_html,
    extract_tabelog_urls,
)


class ProviderTests(unittest.TestCase):
    def test_canonicalizes_review_and_language_urls(self) -> None:
        self.assertEqual(
            canonical_restaurant_url(
                "https://tabelog.com/tw/ibaraki/A0804/A080401/8000477/dtlrvwlst/"
            ),
            "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
        )

    def test_extracts_duckduckgo_redirect_once(self) -> None:
        target = "https://tabelog.com/ibaraki/A0804/A080401/8000477/"
        redirect = f"//duckduckgo.com/l/?uddg={quote(target, safe='')}"
        html = (
            f'<a class="result__a" href="{redirect}">清水屋</a>'
            f'<a class="result__a" href="{target}dtlrvwlst/">review</a>'
        )
        self.assertEqual(extract_tabelog_urls(html), [target])

    def test_extracts_tabelog_map_coordinates(self) -> None:
        html = '<div id="js-basics" data-lat="36.175271769" data-lng="139.837251778"></div>'
        self.assertEqual(
            coordinates_from_tabelog_html(html),
            (36.175271769, 139.837251778),
        )


if __name__ == "__main__":
    unittest.main()
