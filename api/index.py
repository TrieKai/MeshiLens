"""Vercel entrypoint for the MeshiLens matching API."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import parse_qs, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIRECTORY = PROJECT_ROOT / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from meshi_lens.service import MatchService  # noqa: E402


LOGGER = logging.getLogger("meshilens")
SERVICE = MatchService()


def request_path(value: str) -> str:
    """Recover the public API path before Vercel's catch-all rewrite."""
    parsed = urlsplit(value)
    rewritten_path = (parse_qs(parsed.query).get("path") or [""])[0].strip("/")
    if rewritten_path:
        return f"/{rewritten_path}"
    return parsed.path.removeprefix("/api") or "/"


class handler(BaseHTTPRequestHandler):
    """Handle Vercel requests without starting a long-lived HTTP server."""

    server_version = "MeshiLens/0.1"

    def _cors_origin(self) -> str | None:
        allowed_origin = os.environ.get("MESHI_ALLOWED_ORIGIN", "").rstrip("/")
        origin = self.headers.get("Origin", "").rstrip("/")
        return origin if allowed_origin and origin == allowed_origin else None

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _path(self) -> str:
        return request_path(self.path)

    def do_OPTIONS(self) -> None:  # noqa: N802
        origin = self._cors_origin()
        if not origin:
            self._send(403, {"error": "不允許的來源"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self._path() == "/health":
            self._send(200, {"status": "ok", "service": "MeshiLens"})
            return
        self._send(404, {"error": "找不到路徑"})

    def do_POST(self) -> None:  # noqa: N802
        if self._path() not in {
            "/match",
            "/michelin",
            "/michelin/batch",
            "/advice",
            "/similar",
            "/similar-map-target",
            "/popularity",
            "/review-insights",
        }:
            self._send(404, {"error": "找不到路徑"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16_384:
                raise ValueError("請求大小不正確")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("請求內容必須是物件")
            if self._path() == "/michelin/batch":
                result = SERVICE.match_michelin_batch(payload)
            elif self._path() == "/michelin":
                result = SERVICE.match_michelin(payload)
            elif self._path() == "/advice":
                result = SERVICE.advice(payload)
            elif self._path() == "/similar":
                result = SERVICE.similar(payload)
            elif self._path() == "/similar-map-target":
                result = SERVICE.similar_map_target(payload)
            elif self._path() == "/popularity":
                result = SERVICE.popularity(payload)
            elif self._path() == "/review-insights":
                result = SERVICE.review_insights(payload)
            else:
                result = SERVICE.match(payload, include_michelin=False)
            self._send(200, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            LOGGER.exception("MeshiLens request failed")
            self._send(502, {"error": str(exc) or "MeshiLens 服務暫時無法取得"})

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)
