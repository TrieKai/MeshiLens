"""Opt-in public Tabelog review theme summaries (experimental).

Independent from the facts-only /advice path. Review bodies are held only in
process memory for the Groq call, then discarded. Caches store the summary only.
"""

from __future__ import annotations

from hashlib import sha256
import json
import logging
import os
import re
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .advice import DEFAULT_MODEL, GROQ_API_URL
from .cache import DEFAULT_REVIEW_INSIGHTS_TTL_SECONDS as _CACHE_TTL
from .provider import canonical_restaurant_url


LOGGER = logging.getLogger("meshilens.review_insights")

PROMPT_VERSION = "review-insights-v1"
DEFAULT_REVIEW_INSIGHTS_TTL_SECONDS = _CACHE_TTL
MIN_REVIEWS = 5
MAX_REVIEWS = 20
MAX_CHARS_PER_REVIEW = 480
MAX_TOTAL_CHARS = 9_000
SOURCE_NOTE = "僅分析一頁公開評論，可能不完整"

_REVIEW_ITEM_SELECTORS = ("div.rvw-item", "li.rvw-item", "div.js-rvw-item")
_COMMENT_SELECTORS = (
    "div.rvw-item__rvw-comment",
    "div.rvw-item__comment",
    "p.rvw-item__rvw-comment",
    ".rvw-item__rvw-comment",
)
_TITLE_SELECTORS = ("p.rvw-item__rvw-title", ".rvw-item__rvw-title")
_AUTHOR_SELECTORS = (
    "a.rvw-item__rvwr-name",
    ".rvw-item__rvwr-name",
    ".rvw-item__name",
)


def review_list_url(restaurant_url: str) -> str:
    """Convert a canonical restaurant URL into the first public review-list page."""
    canonical = canonical_restaurant_url(restaurant_url)
    if not canonical:
        raise ValueError("不是合法的 Tabelog 店家 URL")
    return f"{canonical.rstrip('/')}/dtlrvwlst/"


def validate_tabelog_restaurant_url(value: Any) -> str:
    """Accept only tabelog.com restaurant URLs; reject other hosts and shapes."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("找不到 Tabelog 店家 URL")
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in {"tabelog.com", "www.tabelog.com"}:
        raise ValueError("只接受 tabelog.com 店家 URL")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("只接受 tabelog.com 店家 URL")
    canonical = canonical_restaurant_url(raw)
    if not canonical:
        raise ValueError("不是合法的 Tabelog 店家 URL")
    return canonical


def _clean_text(value: Any, limit: int | None = None) -> str:
    text = " ".join(str(value or "").split())
    if limit is not None:
        return text[:limit]
    return text


def _element_text(node: Any) -> str:
    if node is None:
        return ""
    for tag in node.find_all(["a", "script", "style", "img", "noscript"]):
        tag.decompose()
    return _clean_text(node.get_text(" ", strip=True))


def parse_public_review_texts(html: str) -> list[str]:
    """Extract anonymized review bodies from a Tabelog review-list HTML page.

    Author names, photos, and links are discarded. Returns empty list when the
    markup cannot be recognized (caller should degrade gracefully).
    """
    if not html or not html.strip():
        return []
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover - gurume pulls bs4 in normal installs
        return []

    soup = BeautifulSoup(html, "lxml")
    items: list[Any] = []
    for selector in _REVIEW_ITEM_SELECTORS:
        found = soup.select(selector)
        if found:
            items = found
            break

    texts: list[str] = []
    for item in items:
        for selector in _AUTHOR_SELECTORS:
            for author in item.select(selector):
                author.decompose()
        for photo in item.select("img, picture, .rvw-item__photo, .rvw-item__img"):
            photo.decompose()

        title = ""
        for selector in _TITLE_SELECTORS:
            node = item.select_one(selector)
            if node:
                title = _element_text(node)
                if title:
                    break

        comment = ""
        for selector in _COMMENT_SELECTORS:
            node = item.select_one(selector)
            if node:
                comment = _element_text(node)
                if comment:
                    break
        if not comment:
            # Fallback: last meaningful paragraph-like block without identity chrome.
            for node in item.select("div, p"):
                classes = " ".join(node.get("class") or [])
                if any(
                    token in classes
                    for token in ("rvwr", "name", "date", "useful", "photo", "img")
                ):
                    continue
                candidate = _element_text(node)
                if len(candidate) >= 20:
                    comment = candidate
                    break

        body = _clean_text(f"{title}。{comment}" if title and comment else (comment or title))
        if len(body) < 12:
            continue
        texts.append(body)
    return texts


def bound_review_texts(
    texts: list[str],
    *,
    min_count: int = MIN_REVIEWS,
    max_count: int = MAX_REVIEWS,
    max_chars_per_review: int = MAX_CHARS_PER_REVIEW,
    max_total_chars: int = MAX_TOTAL_CHARS,
) -> list[str]:
    """Cap review count and total characters for the Groq prompt."""
    del min_count  # documented product floor; pages may legitimately have fewer
    bounded: list[str] = []
    total = 0
    for raw in texts:
        text = _clean_text(raw, max_chars_per_review)
        if not text:
            continue
        if total + len(text) > max_total_chars:
            remaining = max_total_chars - total
            if remaining < 40:
                break
            text = text[:remaining]
        bounded.append(text)
        total += len(text)
        if len(bounded) >= max_count:
            break
    return bounded


def sanitize_review_insights_request(payload: Mapping[str, Any]) -> dict[str, str]:
    tabelog_url = validate_tabelog_restaurant_url(payload.get("tabelog_url"))
    restaurant_name = _clean_text(payload.get("restaurant_name"), 120)
    if not restaurant_name:
        raise ValueError("找不到店家名稱")
    return {"tabelog_url": tabelog_url, "restaurant_name": restaurant_name}


def review_insights_cache_key(tabelog_url: str, *, model: str) -> str:
    payload = json.dumps(
        {
            "tabelog_url": tabelog_url,
            "model": model,
            "prompt_version": PROMPT_VERSION,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _validate_insights(value: Any, *, sample_size: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("AI 回傳格式不正確")

    def clean_list(key: str, max_items: int, max_length: int) -> list[str]:
        items = value.get(key, [])
        if not isinstance(items, list):
            return []
        return [
            _clean_text(item, max_length)
            for item in items
            if _clean_text(item, max_length)
        ][:max_items]

    summary = _clean_text(value.get("summary"), 280)
    if not summary:
        raise ValueError("AI 未產生評論實驗摘要")
    reported_size = value.get("sample_size", sample_size)
    try:
        size = int(reported_size)
    except (TypeError, ValueError):
        size = sample_size
    size = max(0, min(size, MAX_REVIEWS, sample_size or MAX_REVIEWS))
    return {
        "summary": summary,
        "positive_themes": clean_list("positive_themes", 5, 48),
        "cautions": clean_list("cautions", 4, 60),
        "sample_size": size if size else sample_size,
        "source_note": SOURCE_NOTE,
    }


class GroqReviewInsightsAdvisor:
    """Groq client that turns anonymized review snippets into theme JSON."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 18,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _request_body(
        self, restaurant_name: str, review_texts: list[str]
    ) -> dict[str, Any]:
        is_qwen = self.model.startswith("qwen/")
        instructions = (
            "你是 MeshiLens「公開評論實驗摘要」助手。只根據提供的匿名公開評論片段，"
            "以繁體中文輸出 JSON：summary、positive_themes、cautions、sample_size、"
            "source_note。禁止逐字引用評論原文、禁止提及作者名稱、禁止推測未出現的事實、"
            "禁止把單一評論當成整體結論；不足時要說明樣本有限。summary 為主題化概述"
            "（約 80–120 字）；positive_themes、cautions 為字串陣列，最多分別 5、4 項；"
            f'source_note 固定為「{SOURCE_NOTE}」；sample_size 為整數。只輸出 JSON。'
        )
        payload = {
            "restaurant_name": restaurant_name,
            "sample_size": len(review_texts),
            "anonymized_reviews": [
                {"index": index + 1, "text": text}
                for index, text in enumerate(review_texts)
            ],
        }
        return {
            "model": self.model,
            "reasoning_effort": "none" if is_qwen else "low",
            "reasoning_format": "hidden",
            "temperature": 0.4 if is_qwen else 0.2,
            "max_completion_tokens": 900,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{instructions}\n\n輸入資料："
                        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
                    ),
                }
            ],
        }

    def summarize(
        self, restaurant_name: str, review_texts: list[str]
    ) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("公開評論實驗摘要尚未設定")
        if not review_texts:
            raise RuntimeError("暫時無法取得公開評論")
        request_body = self._request_body(restaurant_name, review_texts)
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
            if exc.code == 429:
                raise RuntimeError("AI 暫時忙碌，請稍後再試") from exc
            raise RuntimeError("暫時無法取得公開評論實驗摘要") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("暫時無法取得公開評論實驗摘要") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
            return _validate_insights(
                json.loads(content), sample_size=len(review_texts)
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("暫時無法取得公開評論實驗摘要") from exc


def review_insights_response(
    advisor: GroqReviewInsightsAdvisor,
    *,
    restaurant_name: str,
    review_texts: list[str],
    tabelog_url: str,
) -> dict[str, Any]:
    insights = advisor.summarize(restaurant_name, review_texts)
    return {
        "insights": insights,
        "model": advisor.model,
        "source": "公開評論實驗摘要（非逐字引用）",
        "tabelog_url": tabelog_url,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


_HTTP_STATUS_RE = re.compile(r"\b(403|404|429|5\d\d)\b")


def classify_review_fetch_failure(exc: BaseException) -> str:
    """Map fetch failures to anonymous metric labels (never include body text)."""
    message = str(exc or "")
    lowered = message.lower()
    if "403" in message or "forbidden" in lowered:
        return "forbidden"
    if "404" in message:
        return "not_found"
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if _HTTP_STATUS_RE.search(message):
        return "http_error"
    return "fetch_error"
