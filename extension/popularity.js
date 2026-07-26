(() => {
  const POPULARITY_CACHE_VERSION = "popularity-v1";

  function popularityPayload(candidate) {
    if (!candidate || typeof candidate !== "object") return null;
    const name = String(candidate.name || "").trim().slice(0, 200);
    const url = String(candidate.url || "").trim().slice(0, 300);
    if (!name || !/^https:\/\/tabelog\.com\/[a-z-]+\/A\d+\/A\d+\/\d+\/?$/i.test(url)) return null;
    return { selected: { name, url } };
  }

  function popularityTags(value) {
    const tags = Array.isArray(value?.tags) ? value.tags : [];
    return tags
      .map((tag) => ({
        label: String(tag?.label || "").trim().slice(0, 30),
        rank: Number.parseInt(tag?.rank, 10),
        tier: tag?.tier === "top5" ? "top5" : "top10",
        sourceUrl: String(tag?.source_url || "").trim().slice(0, 500),
      }))
      .filter((tag) => tag.label && Number.isInteger(tag.rank) && tag.rank >= 1 && tag.rank <= 10);
  }

  function popularityBadgeText(tag) {
    return `${tag.label} TOP ${tag.tier === "top5" ? "5" : "10"}`;
  }

  globalThis.MeshiLensPopularity = {
    POPULARITY_CACHE_VERSION,
    popularityPayload,
    popularityTags,
    popularityBadgeText,
  };
})();
