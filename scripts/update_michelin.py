from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import time

from curl_cffi import requests

from meshi_lens.michelin import (
    DEFAULT_DATA_PATH,
    MICHELIN_JAPAN_URL,
    michelin_listing_meta,
    parse_michelin_listing,
)


HEADERS = {
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36"
    ),
}


def fetch_page(session: requests.Session, page: int) -> str:
    url = MICHELIN_JAPAN_URL if page == 1 else f"{MICHELIN_JAPAN_URL}/page/{page}"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.get(
                url,
                headers=HEADERS,
                timeout=30,
                allow_redirects=True,
                impersonate="chrome",
            )
            response.raise_for_status()
            if not parse_michelin_listing(response.text):
                raise RuntimeError("頁面沒有 SSR 餐廳卡片，可能遇到網站驗證")
            return response.text
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"無法取得 Michelin 第 {page} 頁：{last_error}") from last_error


def update_snapshot(output: Path, interval: float) -> dict[str, object]:
    session = requests.Session()
    first_html = fetch_page(session, 1)
    expected_count, page_count = michelin_listing_meta(first_html)
    if expected_count < 1 or page_count < 1:
        raise RuntimeError("無法讀取 Michelin 日本清單筆數或分頁")

    restaurants = parse_michelin_listing(first_html)
    for page in range(2, page_count + 1):
        time.sleep(interval)
        restaurants.extend(parse_michelin_listing(fetch_page(session, page)))
        print(f"Michelin 日本快照：{page}/{page_count} 頁，{len(restaurants)} 家")

    deduplicated = {restaurant["id"]: restaurant for restaurant in restaurants}
    if len(deduplicated) != expected_count:
        raise RuntimeError(
            f"Michelin 筆數不一致：頁面宣告 {expected_count}，解析到 {len(deduplicated)}"
        )
    payload: dict[str, object] = {
        "source_url": MICHELIN_JAPAN_URL,
        "language": "zh_TW",
        "scope": "Japan",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(deduplicated),
        "restaurants": list(deduplicated.values()),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(output)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="低頻更新 Michelin Guide 日本繁中 SSR 快照"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--interval", type=float, default=1.5)
    args = parser.parse_args()
    payload = update_snapshot(args.output, max(args.interval, 0.5))
    print(f"完成：{payload['count']} 家，儲存至 {args.output}")


if __name__ == "__main__":
    main()
