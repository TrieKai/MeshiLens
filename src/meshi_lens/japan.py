"""Conservative country classification for MeshiLens place lookups."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

JAPAN_BOUNDS = (20.0, 46.5, 122.0, 154.5)
JAPAN_POSTCODE_PATTERN = re.compile(r"〒\s*\d{3}\s*[-‐‑–—]?\s*\d{4}")
JAPAN_PHONE_PATTERN = re.compile(r"(?:^|[^\d])\+81(?:[\s()\-]|\d)")
JAPAN_ADDRESS_PATTERN = re.compile(
    r"\bJapan\b|日本|北海道|(?:東京都|京都府|大阪府)|"
    r"(?:青森|岩手|宮城|秋田|山形|福島|茨城|栃木|群馬|埼玉|千葉|神奈川|新潟|"
    r"富山|石川|福井|山梨|長野|岐阜|静岡|愛知|三重|滋賀|兵庫|奈良|和歌山|鳥取|"
    r"島根|岡山|広島|山口|徳島|香川|愛媛|高知|福岡|佐賀|長崎|熊本|大分|宮崎|"
    r"鹿児島|沖縄)県"
)


def is_japan_tabelog_url(value: Any) -> bool:
    parsed = urlparse(str(value or ""))
    return (
        parsed.scheme == "https"
        and parsed.netloc == "tabelog.com"
        and bool(re.match(r"^/[a-z0-9-]+/A\d+/A\d+/\d+/", parsed.path, re.IGNORECASE))
    )


def has_japan_signal(place: Mapping[str, Any]) -> bool:
    address = str(place.get("address") or "")
    return (
        is_japan_tabelog_url(place.get("tabelog_url"))
        or bool(JAPAN_PHONE_PATTERN.search(str(place.get("phone") or "")))
        or bool(JAPAN_POSTCODE_PATTERN.search(address))
        or bool(JAPAN_ADDRESS_PATTERN.search(address))
    )


def exact_coordinates_outside_japan(place: Mapping[str, Any]) -> bool:
    if place.get("coordinates_source") != "place":
        return False
    try:
        latitude = float(place["latitude"])
        longitude = float(place["longitude"])
    except (KeyError, TypeError, ValueError):
        return False
    min_latitude, max_latitude, min_longitude, max_longitude = JAPAN_BOUNDS
    return not (min_latitude <= latitude <= max_latitude and min_longitude <= longitude <= max_longitude)


def classify_japan_place(place: Mapping[str, Any]) -> str:
    if has_japan_signal(place):
        return "japan"
    if exact_coordinates_outside_japan(place):
        return "not_japan"
    return "unknown"
