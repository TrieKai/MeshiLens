(() => {
  const REVIEW_INSIGHTS_CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000;
  const BUTTON_LABEL = "分析公開評論";
  const CARD_TITLE = "評論實驗摘要";
  const UNAVAILABLE_LABEL = "暫時無法取得";

  const inflightByUrl = new Map();

  function reviewInsightsPayload(candidate) {
    const tabelogUrl = String(candidate?.url || "").trim();
    const restaurantName = String(candidate?.name || "").trim();
    if (!tabelogUrl || !restaurantName) return null;
    if (!/^https?:\/\/([a-z0-9-]+\.)*tabelog\.com\//i.test(tabelogUrl)) return null;
    return {
      tabelog_url: tabelogUrl.slice(0, 300),
      restaurant_name: restaurantName.slice(0, 120),
    };
  }

  function reviewInsightsCacheKey(candidate) {
    const payload = reviewInsightsPayload(candidate);
    return payload ? payload.tabelog_url : "";
  }

  function cachedReviewInsights(entry, cacheKey, now = Date.now()) {
    if (!entry || entry.key !== cacheKey || !entry.insights || !entry.savedAt) return null;
    return now - entry.savedAt <= REVIEW_INSIGHTS_CACHE_TTL_MS ? entry.insights : null;
  }

  function beginReviewInsightsFlight(cacheKey, work) {
    if (!cacheKey) return work();
    const existing = inflightByUrl.get(cacheKey);
    if (existing) return existing;
    const pending = Promise.resolve()
      .then(work)
      .finally(() => {
        if (inflightByUrl.get(cacheKey) === pending) inflightByUrl.delete(cacheKey);
      });
    inflightByUrl.set(cacheKey, pending);
    return pending;
  }

  function clearReviewInsightsFlight(cacheKey) {
    if (cacheKey) inflightByUrl.delete(cacheKey);
  }

  function hasReviewInsightsFlight(cacheKey) {
    return Boolean(cacheKey && inflightByUrl.has(cacheKey));
  }

  globalThis.MeshiLensReviewInsights = {
    REVIEW_INSIGHTS_CACHE_TTL_MS,
    BUTTON_LABEL,
    CARD_TITLE,
    UNAVAILABLE_LABEL,
    reviewInsightsPayload,
    reviewInsightsCacheKey,
    cachedReviewInsights,
    beginReviewInsightsFlight,
    clearReviewInsightsFlight,
    hasReviewInsightsFlight,
  };
})();
