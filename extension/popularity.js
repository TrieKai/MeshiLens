(() => {
  const POPULARITY_CACHE_VERSION = "popularity-v2";

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
        tier: ["top5", "top10", "top20"].includes(tag?.tier) ? tag.tier : "top20",
        sourceUrl: String(tag?.source_url || "").trim().slice(0, 500),
      }))
      .filter((tag) => tag.label && Number.isInteger(tag.rank) && tag.rank >= 1 && tag.rank <= 20);
  }

  function popularityBadgeText(tag) {
    const cutoff = tag.tier === "top5" ? "5" : tag.tier === "top10" ? "10" : "20";
    return `${tag.label} TOP ${cutoff}`;
  }

  globalThis.MeshiLensPopularity = {
    POPULARITY_CACHE_VERSION,
    popularityPayload,
    popularityTags,
    popularityBadgeText,
  };
})();
