(() => {
  const MAX_RECOMMENDATIONS = 3;
  const SIMILAR_CACHE_VERSION = "nearby-v13";

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
    return candidates.filter(
      (candidate) =>
        candidate?.confidence !== "low" &&
        (!selectedUrl || canonicalTabelogUrl(candidate?.url) !== selectedUrl),
    );
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

  function similarMapTargetPayload(recommendation) {
    const name = String(recommendation?.name || "").trim().slice(0, 200);
    const url = canonicalTabelogUrl(recommendation?.url);
    if (!name || !/^https:\/\/tabelog\.com\/[a-z-]+\/a\d+\/a\d+\/\d+$/.test(url)) return null;
    return { name, url: `${url}/` };
  }

  function similarDisplayState(recommendations, diagnostics = null) {
    return Array.isArray(recommendations) && recommendations.length
      ? { status: "ready", recommendations, diagnostics }
      : { status: "empty", diagnostics };
  }

  function similarDiagnosticsSummary(diagnostics) {
    if (!diagnostics || typeof diagnostics !== "object") return "";
    const count = (key) => Math.max(0, Number.parseInt(diagnostics[key], 10) || 0);
    const scope = String(diagnostics.search_scope || "").trim();
    const returned = count("returned_count");
    if (!returned) return scope ? `搜尋範圍：${scope}；Tabelog 未回傳候選店家。` : "Tabelog 未回傳候選店家。";
    const parts = [
      scope ? `搜尋範圍：${scope}` : "",
      `Tabelog 回傳 ${returned} 家`,
    ].filter(Boolean);
    const belowQuality = count("below_quality_count");
    if (belowQuality) parts.push(`${belowQuality} 家未達相似度門檻`);
    return `${parts.join("；")}。`;
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
    similarMapTargetPayload,
    similarDiagnosticsSummary,
    similarDisplayState,
    similarPayload,
  };
})();
