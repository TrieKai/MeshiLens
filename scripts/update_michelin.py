from __future__ import annotations

import argparse
from concurrent.futures import as_completed, ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import time

from curl_cffi import requests

from meshi_lens.michelin import (
    DEFAULT_DATA_PATH,
    MICHELIN_JAPAN_URL,
    michelin_listing_meta,
    parse_michelin_detail,
    parse_michelin_listing,
)


HEADERS = {
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36"
    ),
}
DETAIL_SESSION = threading.local()


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


def fetch_detail(restaurant: dict[str, object]) -> dict[str, str]:
    session = getattr(DETAIL_SESSION, "value", None)
    if session is None:
        session = requests.Session()
        DETAIL_SESSION.value = session
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = session.get(
                str(restaurant["url"]),
                headers=HEADERS,
                timeout=30,
                allow_redirects=True,
                impersonate="chrome",
            )
            response.raise_for_status()
            detail = parse_michelin_detail(response.text)
            if not detail:
                raise RuntimeError("頁面沒有 Restaurant JSON-LD，可能遇到網站驗證")
            return detail
        except Exception as exc:
            last_error = exc
            session = requests.Session()
            DETAIL_SESSION.value = session
            if attempt < 4:
                time.sleep(min(3 * (attempt + 1), 12))
    raise RuntimeError(
        f"無法取得 Michelin 詳情頁 {restaurant.get('name')}：{last_error}"
    ) from last_error


def update_snapshot(
    output: Path,
    interval: float,
    *,
    enrich_details: bool = False,
    detail_interval: float = 1.2,
    detail_workers: int = 4,
    refresh_details: bool = False,
    refresh_listing: bool = True,
) -> dict[str, object]:
    previous: dict[str, dict[str, object]] = {}
    old_payload: dict[str, object] = {}
    if output.exists():
        try:
            old_payload = json.loads(output.read_text(encoding="utf-8"))
            previous = {
                str(item.get("id")): item
                for item in old_payload.get("restaurants", [])
                if isinstance(item, dict) and item.get("id")
            }
        except (json.JSONDecodeError, OSError, AttributeError):
            previous = {}
            old_payload = {}
    if refresh_listing:
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
    else:
        deduplicated = {key: dict(value) for key, value in previous.items()}
        expected_count = int(old_payload.get("count") or 0)
        if expected_count < 1 or len(deduplicated) != expected_count:
            raise RuntimeError("本地 Michelin 快照筆數不完整，不能只更新詳情")
        print(f"使用本地 Michelin 清單：{expected_count} 家")
    detail_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if enrich_details:
        pending: list[dict[str, object]] = []
        for restaurant in deduplicated.values():
            old = previous.get(str(restaurant["id"]), {})
            if old.get("details_fetched_at") and not refresh_details:
                restaurant.update(
                    phone=str(old.get("phone") or ""),
                    website=str(old.get("website") or ""),
                    details_fetched_at=str(old["details_fetched_at"]),
                )
            else:
                pending.append(restaurant)

        total = len(pending)
        if total:
            future_to_restaurant = {}
            completed = 0
            failures: list[dict[str, object]] = []
            with ThreadPoolExecutor(max_workers=max(1, detail_workers)) as executor:
                for index, restaurant in enumerate(pending, start=1):
                    future = executor.submit(fetch_detail, restaurant)
                    future_to_restaurant[future] = restaurant
                    finished = [item for item in future_to_restaurant if item.done()]
                    for item in finished:
                        completed_restaurant = future_to_restaurant.pop(item)
                        try:
                            completed_restaurant.update(item.result())
                            completed_restaurant["details_fetched_at"] = detail_timestamp
                            completed_restaurant.pop("details_error", None)
                        except RuntimeError:
                            failures.append(completed_restaurant)
                        completed += 1
                    if index < total:
                        time.sleep(max(detail_interval, 0.5))
                    if index % 25 == 0 or index == total:
                        print(
                            f"Michelin 詳情排程：{index}/{total}，完成 {completed}/{total}"
                        )

                for future in as_completed(future_to_restaurant):
                    restaurant = future_to_restaurant[future]
                    try:
                        restaurant.update(future.result())
                        restaurant["details_fetched_at"] = detail_timestamp
                        restaurant.pop("details_error", None)
                    except RuntimeError:
                        failures.append(restaurant)
                    completed += 1
                    if completed % 25 == 0 or completed == total:
                        print(f"Michelin 詳情完成：{completed}/{total}")

            if failures:
                print(f"Michelin 詳情重試：{len(failures)} 家")
                retry_errors = []
                for restaurant in failures:
                    try:
                        restaurant.update(fetch_detail(restaurant))
                        restaurant["details_fetched_at"] = detail_timestamp
                        restaurant.pop("details_error", None)
                    except RuntimeError as exc:
                        message = str(exc)
                        restaurant["details_error"] = message
                        retry_errors.append(message)
                if retry_errors:
                    print(
                        f"Michelin 詳情待下次重試：{len(retry_errors)} 家；"
                        + "；".join(retry_errors[:5])
                    )

    payload: dict[str, object] = {
        "source_url": MICHELIN_JAPAN_URL,
        "language": "zh_TW",
        "scope": "Japan",
        "fetched_at": (
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if refresh_listing
            else old_payload.get("fetched_at")
        ),
        "details_updated_at": detail_timestamp if enrich_details else None,
        "count": len(deduplicated),
        "details_error_count": sum(
            1 for item in deduplicated.values() if item.get("details_error")
        ),
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
    parser.add_argument("--detail-interval", type=float, default=1.2)
    parser.add_argument("--detail-workers", type=int, default=4)
    parser.add_argument("--include-details", action="store_true")
    parser.add_argument("--refresh-details", action="store_true")
    parser.add_argument("--details-only", action="store_true")
    args = parser.parse_args()
    payload = update_snapshot(
        args.output,
        max(args.interval, 0.5),
        enrich_details=args.include_details,
        detail_interval=max(args.detail_interval, 0.5),
        detail_workers=max(args.detail_workers, 1),
        refresh_details=args.refresh_details,
        refresh_listing=not args.details_only,
    )
    print(f"完成：{payload['count']} 家，儲存至 {args.output}")


if __name__ == "__main__":
    main()
