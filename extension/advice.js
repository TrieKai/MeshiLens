(() => {
  const ADVICE_CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000;

  function advicePayload(place, candidate, michelin) {
    if (!place || !candidate?.name) return null;
    return { place, candidate, michelin: michelin || null };
  }

  function adviceCacheKey(candidate, michelin) {
    const hyakumeiten = (candidate?.hyakumeiten || [])
      .map((item) => item?.year)
      .filter(Boolean)
      .join(",");
    return [
      candidate?.url,
      candidate?.rating,
      candidate?.review_count,
      candidate?.reservation_status,
      candidate?.reservation_url,
      hyakumeiten,
      michelin?.url,
      michelin?.distinction_label,
      michelin?.green_star,
    ].join("|");
  }

  function cachedAdvice(entry, cacheKey, now = Date.now()) {
    if (!entry || entry.key !== cacheKey || !entry.advice || !entry.savedAt) return null;
    return now - entry.savedAt <= ADVICE_CACHE_TTL_MS ? entry.advice : null;
  }

  globalThis.MeshiLensAdvice = { ADVICE_CACHE_TTL_MS, advicePayload, adviceCacheKey, cachedAdvice };
})();
