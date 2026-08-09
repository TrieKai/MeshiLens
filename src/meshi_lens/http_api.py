"""Shared HTTP API validation and routing for local and Vercel handlers."""

from __future__ import annotations

import json
from typing import Any, Mapping


MAX_REQUEST_BYTES = 16_384
POST_PATHS = frozenset(
    {
        "/match",
        "/michelin",
        "/michelin/batch",
        "/advice",
        "/similar",
        "/similar-map-target",
        "/popularity",
        "/review-insights",
    }
)


class UnsupportedMediaType(ValueError):
    """Raised when an API request does not contain JSON."""


def is_extension_origin(origin: str) -> bool:
    return origin.startswith(("chrome-extension://", "moz-extension://"))


def request_origin_allowed(
    origin: str,
    configured_origin: str = "",
    *,
    require_origin: bool,
) -> bool:
    """Reject browser web origins while permitting CLI/server requests in cloud mode."""
    normalized = origin.rstrip("/")
    configured = configured_origin.rstrip("/")
    if configured:
        return normalized == configured
    if not normalized:
        return not require_origin
    return is_extension_origin(normalized)


def parse_json_object(body: bytes, content_type: str) -> dict[str, Any]:
    media_type = content_type.partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise UnsupportedMediaType("Content-Type 必須是 application/json")

    def reject_constant(value: str) -> None:
        raise ValueError(f"JSON 不接受 {value}")

    payload = json.loads(body, parse_constant=reject_constant)
    if not isinstance(payload, dict):
        raise ValueError("請求內容必須是物件")
    return payload


def dispatch_request(
    service: Any,
    path: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if path == "/michelin/batch":
        return service.match_michelin_batch(payload)
    if path == "/michelin":
        return service.match_michelin(payload)
    if path == "/advice":
        return service.advice(payload)
    if path == "/similar":
        return service.similar(payload)
    if path == "/similar-map-target":
        return service.similar_map_target(payload)
    if path == "/popularity":
        return service.popularity(payload)
    if path == "/review-insights":
        return service.review_insights(payload)
    if path == "/match":
        return service.match(payload, include_michelin=False)
    raise ValueError("找不到路徑")
