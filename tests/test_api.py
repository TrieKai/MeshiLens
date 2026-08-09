import json
from pathlib import Path
import unittest

from api.index import request_path
from meshi_lens.http_api import (
    UnsupportedMediaType,
    parse_json_object,
    request_origin_allowed,
)


class ApiRoutingTests(unittest.TestCase):
    def test_cloud_origin_policy_rejects_websites(self) -> None:
        self.assertTrue(
            request_origin_allowed(
                "chrome-extension://abcdefghijklmnop",
                require_origin=False,
            )
        )
        self.assertFalse(
            request_origin_allowed(
                "https://attacker.example",
                require_origin=False,
            )
        )
        self.assertTrue(request_origin_allowed("", require_origin=False))

    def test_configured_origin_must_match_exactly(self) -> None:
        configured = "chrome-extension://trusted"
        self.assertTrue(
            request_origin_allowed(
                configured,
                configured,
                require_origin=False,
            )
        )
        self.assertFalse(
            request_origin_allowed(
                "chrome-extension://other",
                configured,
                require_origin=False,
            )
        )
        self.assertFalse(
            request_origin_allowed("", configured, require_origin=False)
        )

    def test_json_parser_requires_json_object_and_rejects_nan(self) -> None:
        self.assertEqual(
            parse_json_object(b'{"name":"test"}', "application/json; charset=utf-8"),
            {"name": "test"},
        )
        with self.assertRaises(UnsupportedMediaType):
            parse_json_object(b'{"name":"test"}', "text/plain")
        with self.assertRaisesRegex(ValueError, "物件"):
            parse_json_object(b"[]", "application/json")
        with self.assertRaisesRegex(ValueError, "NaN"):
            parse_json_object(b'{"latitude":NaN}', "application/json")

    def test_recovers_path_forwarded_by_vercel_rewrite(self) -> None:
        self.assertEqual(request_path("/api?path=match"), "/match")
        self.assertEqual(
            request_path("/api?path=michelin%2Fbatch"),
            "/michelin/batch",
        )

    def test_keeps_direct_api_paths_for_local_invocation(self) -> None:
        self.assertEqual(request_path("/api/review-insights?debug=1"), "/review-insights")
        self.assertEqual(request_path("/api"), "/")

    def test_vercel_rewrite_forwards_the_captured_subpath(self) -> None:
        config = json.loads(
            Path("vercel.json").read_text(encoding="utf-8")
        )
        rewrite = next(
            item
            for item in config["rewrites"]
            if item["source"] == "/api/:path*"
        )
        self.assertEqual(rewrite["destination"], "/api?path=:path*")


if __name__ == "__main__":
    unittest.main()
