import json
from pathlib import Path
import unittest

from api.index import request_path


class ApiRoutingTests(unittest.TestCase):
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
