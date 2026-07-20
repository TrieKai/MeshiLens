(() => {
  const MAX_LIST_CARDS = 10;

  function normalizeListText(value) {
    return String(value || "")
      .normalize("NFKC")
      .toLocaleLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  /*
   * Maps visited-result chrome appends a localized suffix after a middle dot,
   * e.g. "Noeud.TOKYO·開啟過的連結" / "Noeud.TOKYO·Opened link".  Strip from
   * the last · so matching stays language-agnostic.  Trailing decorative dots
   * like "La Biographie···" keep the full name because the suffix is empty.
   */
  function cleanListPlaceName(value) {
    const name = String(value || "").replace(/\s+/g, " ").trim();
    if (!name) return "";
    const index = name.lastIndexOf("·");
    if (index <= 0) return name;
    const head = name.slice(0, index).trim();
    const tail = name.slice(index + 1).trim();
    return head && tail ? head : name;
  }

  function listPlaceNameFromHref(value) {
    try {
      const url = new URL(String(value || ""), location.origin);
      const match = url.pathname.match(/\/maps\/place\/([^/]+)/);
      if (!match) return "";
      return decodeURIComponent(match[1].replace(/\+/g, " ")).trim();
    } catch {
      return "";
    }
  }

  function normalizedPlaceHref(value) {
    try {
      const url = new URL(String(value || ""), location.origin);
      // Keep only /maps/place/<slug>; Maps often mutates /data=!… trailers on click.
      const match = url.pathname.match(/^(\/maps\/place\/[^/]+)/);
      const path = (match ? match[1] : url.pathname).replace(/\/$/, "");
      return `${url.origin}${path}`;
    } catch {
      return String(value || "").split(/[?#]/, 1)[0].trim();
    }
  }

  function listCardKey({ href, name }) {
    const cleaned = cleanListPlaceName(name) || String(name || "").trim();
    return `${normalizedPlaceHref(href)}|${normalizeListText(cleaned)}`;
  }

  function listCoordinatesFromHref(value) {
    const matches = Array.from(
      String(value || "").matchAll(/!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/g),
    );
    const match = matches[matches.length - 1];
    return match
      ? { latitude: Number(match[1]), longitude: Number(match[2]) }
      : { latitude: null, longitude: null };
  }

  function badgeText(badge) {
    if (!badge?.label) return "";
    return badge.green_star ? `${badge.label} · 綠星` : badge.label;
  }

  function listCardsNeedingLookup(cards, cache) {
    return (cards || []).filter((card) => card?.key && !cache?.has(card.key));
  }

  function listBatchCoversKeys(pendingKeys, neededCards) {
    if (!pendingKeys || typeof pendingKeys.has !== "function") return false;
    return (neededCards || []).every((card) => card?.key && pendingKeys.has(card.key));
  }

  function rememberListBadgeResult(cache, result) {
    if (!cache || !result?.key) return false;
    if (result.status === "matched" && result.badge) {
      cache.set(result.key, result.badge);
      return true;
    }
    if (result.status === "no_match") {
      cache.set(result.key, null);
      return true;
    }
    return false;
  }

  globalThis.MeshiLensListBadges = {
    MAX_LIST_CARDS,
    normalizeListText,
    cleanListPlaceName,
    listPlaceNameFromHref,
    normalizedPlaceHref,
    listCardKey,
    listCoordinatesFromHref,
    badgeText,
    listCardsNeedingLookup,
    listBatchCoversKeys,
    rememberListBadgeResult,
  };
})();
