(() => {
  const MAX_RECOMMENDATIONS = 3;

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

  globalThis.MeshiLensSimilar = { MAX_RECOMMENDATIONS, similarPayload };
})();
