(() => {
  const MAX_RECOMMENDATIONS = 3;
  const SIMILAR_CACHE_VERSION = "zh-Hant-v2";

  function canonicalTabelogUrl(value) {
    return String(value || "")
      .trim()
      .replace(/\/$/, "")
      .toLowerCase()
      .replace(/tabelog\.com\/(?:en|tw|cn|kr)\//, "tabelog.com/");
  }

  function alternativeCandidates(candidates, selected) {
    if (!Array.isArray(candidates)) return [];
    const selectedUrl = canonicalTabelogUrl(selected?.url);
    if (!selectedUrl) return candidates;
    return candidates.filter((candidate) => canonicalTabelogUrl(candidate?.url) !== selectedUrl);
  }

  function confidenceLabel(confidence) {
    if (confidence === "high") return "高信心";
    if (confidence === "medium") return "待確認";
    return "低信心";
  }

  function mapsSearchUrl(name, address = "") {
    const query = [name, address].map((value) => String(value || "").trim()).filter(Boolean).join(" ");
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
  }

  function similarPayload(candidate) {
    if (!candidate || typeof candidate !== "object") return null;
    const name = String(candidate.name || "").trim().slice(0, 200);
    const url = String(candidate.url || "").trim().slice(0, 300);
    const rawGenres = Array.isArray(candidate.genres)
      ? candidate.genres
      : typeof candidate.genres === "string"
        ? [candidate.genres]
        : [];
    const genres = rawGenres
      .map((item) => String(item || "").trim().slice(0, 80))
      .filter(Boolean)
      .slice(0, 4);
    if (!name || !url || !genres.length) return null;
    return {
      selected: {
        name,
        url,
        genres,
        station: String(candidate.station || "").trim().slice(0, 100),
        address: String(candidate.address || "").trim().slice(0, 500),
        lunch_price: String(candidate.lunch_price || "").trim().slice(0, 100),
        dinner_price: String(candidate.dinner_price || "").trim().slice(0, 100),
      },
    };
  }

  globalThis.MeshiLensSimilar = {
    MAX_RECOMMENDATIONS,
    SIMILAR_CACHE_VERSION,
    alternativeCandidates,
    confidenceLabel,
    mapsSearchUrl,
    similarPayload,
  };
})();
