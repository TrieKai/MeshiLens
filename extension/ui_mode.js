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
   * M2 list badges use the snapshot-only Michelin batch API.  At most 10
   * viewport-visible cards are sent with href/name keys and only !3d…!4d
   * coordinates.  The list flow never queries Tabelog, AI, or Redis directly.
   */
  globalThis.MeshiLensUiMode = { LIST_MODE, DETAIL_MODE, MAP_MODE, mapsUiMode };
})();
