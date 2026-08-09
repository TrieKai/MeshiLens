from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import update_michelin


class MichelinUpdateTests(unittest.TestCase):
    def test_listing_refresh_retains_existing_detail_fields(self) -> None:
        previous = {
            "count": 1,
            "fetched_at": "2026-07-01T00:00:00Z",
            "details_updated_at": "2026-07-01T01:00:00Z",
            "restaurants": [
                {
                    "id": "1",
                    "name": "舊店名",
                    "url": "https://guide.michelin.com/old",
                    "phone": "+81 3-0000-0000",
                    "website": "https://example.jp/",
                    "details_fetched_at": "2026-07-01T01:00:00Z",
                }
            ],
        }
        refreshed_listing = [
            {
                "id": "1",
                "name": "新店名",
                "url": "https://guide.michelin.com/new",
            }
        ]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "michelin.json"
            output.write_text(json.dumps(previous), encoding="utf-8")
            with (
                mock.patch.object(update_michelin, "fetch_page", return_value="<html>"),
                mock.patch.object(
                    update_michelin,
                    "michelin_listing_meta",
                    return_value=(1, 1),
                ),
                mock.patch.object(
                    update_michelin,
                    "parse_michelin_listing",
                    return_value=refreshed_listing,
                ),
            ):
                payload = update_michelin.update_snapshot(output, 0.5)

        restaurant = payload["restaurants"][0]
        self.assertEqual(restaurant["name"], "新店名")
        self.assertEqual(restaurant["phone"], "+81 3-0000-0000")
        self.assertEqual(restaurant["website"], "https://example.jp/")
        self.assertEqual(
            restaurant["details_fetched_at"], "2026-07-01T01:00:00Z"
        )
        self.assertEqual(
            payload["details_updated_at"], "2026-07-01T01:00:00Z"
        )

    def test_new_listing_without_old_details_stays_unenriched(self) -> None:
        listing = [
            {
                "id": "2",
                "name": "新店",
                "url": "https://guide.michelin.com/new",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "michelin.json"
            with (
                mock.patch.object(update_michelin, "fetch_page", return_value="<html>"),
                mock.patch.object(
                    update_michelin,
                    "michelin_listing_meta",
                    return_value=(1, 1),
                ),
                mock.patch.object(
                    update_michelin,
                    "parse_michelin_listing",
                    return_value=listing,
                ),
            ):
                payload = update_michelin.update_snapshot(output, 0.5)

        restaurant = payload["restaurants"][0]
        self.assertNotIn("phone", restaurant)
        self.assertNotIn("website", restaurant)


if __name__ == "__main__":
    unittest.main()
