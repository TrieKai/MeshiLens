(() => {
  const LIST_MODE = "list";
  const DETAIL_MODE = "detail";
  const MAP_MODE = "map";

  function mapsUiMode({ hasDetailTitle, hasResultsFeed }) {
    if (hasDetailTitle) return DETAIL_MODE;
    if (hasResultsFeed) return LIST_MODE;
    return MAP_MODE;
  }

  /*
   * M2 Michelin batch API contract (not implemented):
   * The extension may send at most 5–10 currently visible result cards, keyed
   * primarily by normalized Maps place href and name, with !3d…!4d… coordinates
   * only when present. The API returns only high-confidence Michelin/Bib
   * distinctions; it must not look up Tabelog, request AI advice, or scroll Maps.
   * Redis is server-side and unavailable to the extension, so list badges need a
   * dedicated API instead of reading the existing cache.
   */
  globalThis.MeshiLensUiMode = { LIST_MODE, DETAIL_MODE, MAP_MODE, mapsUiMode };
})();
