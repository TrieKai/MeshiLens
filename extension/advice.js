(() => {
  const ADVICE_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

  function advicePayload(place, candidate, michelin) {
    if (!place || !candidate?.name) return null;
    return { place, candidate, michelin: michelin || null };
  }

  function adviceFacts(place, candidate, michelin) {
    const genres = Array.isArray(candidate?.genres)
      ? candidate.genres
      : typeof candidate?.genres === "string"
        ? [candidate.genres]
        : [];
    const cuisine = genres
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .slice(0, 4);
    const hyakumeitenYears = [
      ...new Set(
        (Array.isArray(candidate?.hyakumeiten) ? candidate.hyakumeiten : [])
          .map((item) => Number(item?.year))
          .filter((year) => Number.isInteger(year))
      ),
    ]
      .sort((a, b) => b - a)
      .slice(0, 8);
    const payment = candidate?.payment;
    const facts = {
      restaurant_name: String(candidate?.name || place?.name || "").trim(),
      area: String(candidate?.address || place?.address || "").trim(),
      cuisine,
      tabelog_rating: candidate?.rating ?? null,
      tabelog_review_count: candidate?.review_count ?? null,
      lunch_price: String(candidate?.lunch_price || "").trim(),
      dinner_price: String(candidate?.dinner_price || "").trim(),
      reservation_status: String(candidate?.reservation_status || "").trim(),
      has_online_reservation: Boolean(candidate?.reservation_url),
      payment_available: payment ? Boolean(payment) : null,
      hyakumeiten_years: hyakumeitenYears,
      michelin_distinction: String(michelin?.distinction_label || "").trim(),
      michelin_green_star: Boolean(michelin?.green_star),
    };
    return Object.fromEntries(
      Object.entries(facts).filter(([, value]) => {
        if (value == null || value === "") return false;
        if (Array.isArray(value) && value.length === 0) return false;
        return true;
      })
    );
  }

  function adviceCacheKey(place, candidate, michelin) {
    return JSON.stringify(adviceFacts(place, candidate, michelin));
  }

  function cachedAdvice(entry, cacheKey, now = Date.now()) {
    if (!entry || entry.key !== cacheKey || !entry.advice || !entry.savedAt) return null;
    return now - entry.savedAt <= ADVICE_CACHE_TTL_MS ? entry.advice : null;
  }

  globalThis.MeshiLensAdvice = {
    ADVICE_CACHE_TTL_MS,
    advicePayload,
    adviceFacts,
    adviceCacheKey,
    cachedAdvice,
  };
})();
