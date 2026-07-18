(() => {
  function hyakumeitenLabel(selection) {
    const category = [selection?.category, selection?.area].filter(Boolean).join(" ");
    return category ? `百名店 · ${category}` : "百名店";
  }

  function buildTimelineEntries(michelin, hyakumeiten = []) {
    const entries = [];
    if (michelin) {
      const distinction = michelin.distinction_label || "入選";
      const label = michelin.green_star
        ? `Michelin ${distinction} · 綠星`
        : `Michelin ${distinction}`;
      entries.push({
        kind: "michelin",
        year: Number.POSITIVE_INFINITY,
        year_label: "現在",
        label,
        meta: "目前收錄",
        url: michelin.url || "",
        current: true,
      });
    }

    const seen = new Set();
    for (const selection of hyakumeiten || []) {
      const year = Number(selection?.year) || 0;
      const url = selection?.url || "";
      const label = hyakumeitenLabel(selection);
      const key = `${year}|${label}|${url}`;
      if (seen.has(key)) continue;
      seen.add(key);
      entries.push({
        kind: "hyakumeiten",
        year,
        year_label: year ? String(year) : "",
        label,
        meta: "Tabelog 選出",
        url,
        title: selection?.label || label,
        current: false,
      });
    }

    entries.sort((left, right) => {
      if (left.kind === "michelin" && right.kind !== "michelin") return -1;
      if (right.kind === "michelin" && left.kind !== "michelin") return 1;
      return right.year - left.year;
    });
    return entries;
  }

  function shouldShowTimeline(entries) {
    return (entries || []).some((entry) => entry.kind === "hyakumeiten");
  }

  globalThis.MeshiLensTimeline = {
    buildTimelineEntries,
    shouldShowTimeline,
  };
})();
