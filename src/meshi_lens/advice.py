"""Generate concise dining advice from MeshiLens' structured restaurant facts.

No review text, reviewer identity, photos, or Google Maps review content is included
in the request.  The optional Groq call happens only after the normal matching result
is available, so it can never block restaurant matching.
"""

from __future__ import annotations

from hashlib import sha256
import json
import os
import re
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .localization import tabelog_label_zh_hant


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen3.6-27b"
MAX_FACT_VALUE = 240
ADVICE_OUTPUT_VERSION = "zh-Hant-v3"
CHINESE_NUMBER_RE = re.compile(r"[零〇○一二三四五六七八九兩两十百千萬万億亿點点]+")
CHINESE_DIGITS = {
    "零": "0",
    "〇": "0",
    "○": "0",
    "一": "1",
    "二": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
    "兩": "2",
    "两": "2",
}
CHINESE_UNITS = {"十": 10, "百": 100, "千": 1_000, "萬": 10_000, "万": 10_000, "億": 100_000_000, "亿": 100_000_000}
ALLOWED_FACT_KEYS = frozenset(
    {
        "restaurant_name",
        "area",
        "cuisine",
        "tabelog_rating",
        "tabelog_review_count",
        "lunch_price",
        "dinner_price",
        "reservation_status",
        "has_online_reservation",
        "payment_available",
        "hyakumeiten_years",
        "michelin_distinction",
        "michelin_green_star",
    }
)


def _text(value: Any, limit: int = MAX_FACT_VALUE) -> str:
    return " ".join(str(value or "").split())[:limit]


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _chinese_numeral_to_ascii(value: str) -> str:
    """Normalize Chinese-number runs in model output to ASCII digits.

    This protects factual address, price, rating, review-count and year details
    even when a model interprets "traditional Chinese" as a request to spell
    digits out in Chinese.
    """
    if not value:
        return value
    if "點" in value or "点" in value:
        integer, decimal = re.split(r"[點点]", value, maxsplit=1)
        normalized_integer = _chinese_numeral_to_ascii(integer)
        normalized_decimal = "".join(CHINESE_DIGITS.get(char, char) for char in decimal)
        return f"{normalized_integer}.{normalized_decimal}"
    if all(char in CHINESE_DIGITS for char in value):
        return "".join(CHINESE_DIGITS[char] for char in value)

    total = 0
    section = 0
    number = 0
    for char in value:
        if char in CHINESE_DIGITS:
            number = int(CHINESE_DIGITS[char])
            continue
        unit = CHINESE_UNITS.get(char)
        if unit is None:
            return value
        if unit >= 10_000:
            total += (section + number) * unit
            section = 0
            number = 0
        else:
            section += (number or 1) * unit
            number = 0
    return str(total + section + number)


def _normalize_display_numbers(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        # 「百名店」是獎項名稱，不是要顯示的數量。
        if match.group(0) == "百" and value[match.end() :].startswith("名店"):
            return "百"
        return _chinese_numeral_to_ascii(match.group(0))

    return CHINESE_NUMBER_RE.sub(replace, value)


def sanitize_advice_facts(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and bound client-supplied advice facts."""
    if not isinstance(value, Mapping):
        raise ValueError("用餐建議資料格式不正確")
    cuisine_raw = value.get("cuisine", [])
    if isinstance(cuisine_raw, str):
        cuisine_raw = [cuisine_raw]
    if not isinstance(cuisine_raw, list):
        cuisine_raw = []
    years_raw = value.get("hyakumeiten_years", [])
    if not isinstance(years_raw, list):
        years_raw = []
    years = sorted(
        {
            year
            for year in (_optional_int(item) for item in years_raw)
            if year is not None and 1990 <= year <= 2100
        },
        reverse=True,
    )[:8]
    facts: dict[str, Any] = {
        "restaurant_name": _text(value.get("restaurant_name"), 120),
        "area": _text(value.get("area")),
        "cuisine": [
            tabelog_label_zh_hant(_text(item, 80))
            for item in cuisine_raw
            if _text(item, 80)
        ][:4],
        "tabelog_rating": _optional_float(value.get("tabelog_rating")),
        "tabelog_review_count": _optional_int(value.get("tabelog_review_count")),
        "lunch_price": _text(value.get("lunch_price")),
        "dinner_price": _text(value.get("dinner_price")),
        "reservation_status": _text(value.get("reservation_status"), 40),
        "has_online_reservation": (
            None
            if "has_online_reservation" not in value
            or value.get("has_online_reservation") is None
            else bool(value.get("has_online_reservation"))
        ),
        "payment_available": (
            None
            if "payment_available" not in value or value.get("payment_available") is None
            else bool(value.get("payment_available"))
        ),
        "hyakumeiten_years": years,
        "michelin_distinction": _text(value.get("michelin_distinction"), 80),
        "michelin_green_star": (
            None
            if "michelin_green_star" not in value
            or value.get("michelin_green_star") is None
            else bool(value.get("michelin_green_star"))
        ),
    }
    cleaned = {
        key: item
        for key, item in facts.items()
        if key in ALLOWED_FACT_KEYS and item not in ("", [], None)
    }
    if not cleaned.get("restaurant_name"):
        raise ValueError("找不到可用的用餐建議資料")
    return cleaned


def advice_facts(
    place: Mapping[str, Any],
    candidate: Mapping[str, Any],
    michelin: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return the bounded, review-free facts permitted in an advice prompt."""
    payment = candidate.get("payment")
    reservation_status = _text(candidate.get("reservation_status"))
    genres = candidate.get("genres", [])
    if isinstance(genres, str):
        genres = [genres]
    if not isinstance(genres, list):
        genres = []
    hyakumeiten = candidate.get("hyakumeiten", [])
    if not isinstance(hyakumeiten, list):
        hyakumeiten = []
    return sanitize_advice_facts(
        {
            "restaurant_name": _text(candidate.get("name") or place.get("name"), 120),
            "area": _text(candidate.get("address") or place.get("address")),
            "cuisine": [_text(item, 80) for item in genres if _text(item, 80)][:4],
            "tabelog_rating": candidate.get("rating"),
            "tabelog_review_count": candidate.get("review_count"),
            "lunch_price": _text(candidate.get("lunch_price")),
            "dinner_price": _text(candidate.get("dinner_price")),
            "reservation_status": reservation_status,
            "has_online_reservation": bool(candidate.get("reservation_url")),
            "payment_available": bool(payment) if payment else None,
            "hyakumeiten_years": [
                item.get("year")
                for item in hyakumeiten
                if isinstance(item, Mapping)
            ],
            "michelin_distinction": _text((michelin or {}).get("distinction_label")),
            "michelin_green_star": bool((michelin or {}).get("green_star")),
        }
    )


def advice_cache_key_from_facts(facts: Mapping[str, Any]) -> str:
    """Stable cache key bound to the exact facts used for dining advice."""
    payload = json.dumps(
        {"version": ADVICE_OUTPUT_VERSION, "facts": facts},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def advice_cache_key(
    place: Mapping[str, Any],
    candidate: Mapping[str, Any],
    michelin: Mapping[str, Any] | None,
) -> str:
    """Stable cache key bound to the exact facts used for dining advice."""
    return advice_cache_key_from_facts(advice_facts(place, candidate, michelin))


def _validate_advice(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("AI 回傳格式不正確")

    def clean_list(key: str, max_items: int, max_length: int) -> list[str]:
        items = value.get(key, [])
        if not isinstance(items, list):
            return []
        return [_text(item, max_length) for item in items if _text(item, max_length)][:max_items]

    summary = _normalize_display_numbers(_text(value.get("summary"), 220))
    if not summary:
        raise ValueError("AI 未產生用餐建議")
    result = {
        "headline": _normalize_display_numbers(_text(value.get("headline"), 60)) or "用餐建議",
        "summary": summary,
        "best_for": [_normalize_display_numbers(item) for item in clean_list("best_for", 3, 48)],
        "cautions": [_normalize_display_numbers(item) for item in clean_list("cautions", 2, 60)],
        "evidence": [_normalize_display_numbers(item) for item in clean_list("evidence", 4, 72)],
    }
    return result


class GroqDiningAdvisor:
    """Small dependency-free client for an optional Groq-backed dining summary."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 12,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _request_body(self, facts: Mapping[str, Any]) -> dict[str, Any]:
        """Build a model-compatible JSON-mode request without exposing reasoning."""
        is_qwen = self.model.startswith("qwen/")
        instructions = (
            "你是 MeshiLens 的用餐建議助手。只可根據提供的 JSON 結構化資料，以繁體中文"
            "輸出 JSON 物件：headline、summary、best_for、cautions、evidence。說明請以繁體中文"
            "為主；店名與必要的專有名詞可保留原文。"
            "所有數字、地址番地、年份、評分、評論數與金額一律使用半形阿拉伯數字 0-9；不可"
            "使用中文數字（例如必須寫 3.68、1,405、2024、1,000～1,999）。"
            "輸入可能含日文 Tabelog 標籤，僅可將其理解後翻譯為繁中，不可原樣抄寫。"
            "不得假設菜色、口味、排隊、人潮、服務品質、營業狀態或評論意見；資料不足時要"
            "明確說明。headline 與 summary 必須是字串；best_for、cautions、evidence 必須是"
            "字串陣列，最多分別 3、2、4 項。summary 最多 100 字，evidence 只能重述輸入中"
            "可驗證的事實。只輸出 JSON，不要 Markdown 或其他文字。"
        )
        return {
            "model": self.model,
            # This short structured summary needs deterministic JSON, not a reasoning trace.
            # Qwen supports none/default; GPT-OSS supports low/medium/high.
            "reasoning_effort": "none" if is_qwen else "low",
            "reasoning_format": "hidden",
            "temperature": 0.6 if is_qwen else 0.2,
            "max_completion_tokens": 700,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{instructions}\n\n店家結構化資料："
                        f"{json.dumps(facts, ensure_ascii=False, separators=(',', ':'))}"
                    ),
                },
            ],
        }

    def _decoded_completion(self, facts: Mapping[str, Any]) -> Any:
        request_body = self._request_body(facts)
        request = Request(
            GROQ_API_URL,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "MeshiLens/0.5 (+https://meshilens.vercel.app)",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise RuntimeError("AI 服務驗證失敗，請檢查伺服器設定") from exc
            if exc.code == 429:
                raise RuntimeError("AI 暫時忙碌，請稍後再試") from exc
            raise RuntimeError("AI 用餐建議暫時無法取得") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError("AI 服務連線逾時，請稍後再試") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("AI 回傳格式異常，請稍後再試") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("AI 回傳格式異常，請稍後再試") from exc

    @staticmethod
    def _output_error(exc: ValueError) -> RuntimeError:
        message = str(exc)
        if "未產生用餐建議" in message:
            return RuntimeError("AI 回傳缺少建議摘要，請稍後再試")
        return RuntimeError("AI 回傳內容未符合格式，請稍後再試")

    def summarize_facts(self, facts: Mapping[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("AI 用餐建議尚未設定")
        decoded = self._decoded_completion(facts)
        try:
            return _validate_advice(decoded)
        except ValueError as exc:
            raise self._output_error(exc) from exc

    def summarize(
        self,
        place: Mapping[str, Any],
        candidate: Mapping[str, Any],
        michelin: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return self.summarize_facts(advice_facts(place, candidate, michelin))


def advice_response_from_facts(
    advisor: GroqDiningAdvisor,
    facts: Mapping[str, Any],
) -> dict[str, Any]:
    """Shape returned by the API, including provenance for the UI."""
    return {
        "advice": advisor.summarize_facts(facts),
        "model": advisor.model,
        "source": "MeshiLens 結構化店家資料（非評論摘要）",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def advice_response(
    advisor: GroqDiningAdvisor,
    place: Mapping[str, Any],
    candidate: Mapping[str, Any],
    michelin: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Shape returned by the API, including provenance for the UI."""
    return advice_response_from_facts(
        advisor, advice_facts(place, candidate, michelin)
    )
