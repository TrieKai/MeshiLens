from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from typing import Any

from .http_api import (
    MAX_REQUEST_BYTES,
    POST_PATHS,
    UnsupportedMediaType,
    dispatch_request,
    parse_json_object,
    request_origin_allowed,
)
from .service import MatchService


LOGGER = logging.getLogger("meshilens")
SERVICE = MatchService()


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "MeshiLens/0.1"

    def _allowed_origin(self) -> str | None:
        origin = self.headers.get("Origin", "").rstrip("/")
        configured = os.environ.get("MESHI_ALLOWED_ORIGIN", "").rstrip("/")
        return (
            origin
            if request_origin_allowed(origin, configured, require_origin=True)
            else None
        )

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        allowed_origin = self._allowed_origin()
        if allowed_origin:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self._allowed_origin():
            self._send(403, {"error": "不允許的來源"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self._allowed_origin() or "")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, {"status": "ok", "service": "MeshiLens"})
        else:
            self._send(404, {"error": "找不到路徑"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in POST_PATHS:
            self._send(404, {"error": "找不到路徑"})
            return
        if not self._allowed_origin():
            self._send(403, {"error": "只接受瀏覽器擴充功能的請求"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("請求大小不正確")
            payload = parse_json_object(
                self.rfile.read(length),
                self.headers.get("Content-Type", ""),
            )
            result = dispatch_request(SERVICE, self.path, payload)
            self._send(200, result)
        except UnsupportedMediaType as exc:
            self._send(415, {"error": str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
        except RuntimeError as exc:
            LOGGER.exception("MeshiLens request failed")
            self._send(502, {"error": str(exc) or "MeshiLens 服務暫時無法取得"})
        except Exception:
            LOGGER.exception("MeshiLens request failed")
            self._send(502, {"error": "MeshiLens 服務暫時無法取得"})

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    address = ("127.0.0.1", 18765)
    server = ThreadingHTTPServer(address, RequestHandler)
    LOGGER.info("MeshiLens 已啟動：http://%s:%s", *address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("正在關閉")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
