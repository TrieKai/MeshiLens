from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from typing import Any

from .service import MatchService


LOGGER = logging.getLogger("meshilens")
SERVICE = MatchService()


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "MeshiLens/0.1"

    def _allowed_origin(self) -> str | None:
        origin = self.headers.get("Origin", "")
        if origin.startswith("chrome-extension://") or origin.startswith("moz-extension://"):
            return origin
        return None

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
        if self.path not in {"/match", "/michelin"}:
            self._send(404, {"error": "找不到路徑"})
            return
        if not self._allowed_origin():
            self._send(403, {"error": "只接受瀏覽器擴充功能的請求"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16_384:
                raise ValueError("請求大小不正確")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("請求內容必須是物件")
            result = (
                SERVICE.match_michelin(payload)
                if self.path == "/michelin"
                else SERVICE.match(payload, include_michelin=False)
            )
            self._send(200, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            LOGGER.exception("Tabelog lookup failed")
            self._send(502, {"error": str(exc) or "Tabelog 查詢失敗"})

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
