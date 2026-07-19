(() => {
  const MAX_LIST_CARDS = 10;

  function normalizeListText(value) {
    return String(value || "")
      .normalize("NFKC")
      .toLocaleLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function normalizedPlaceHref(value) {
    try {
      const url = new URL(String(value || ""), location.origin);
      return `${url.origin}${url.pathname}`.replace(/\/$/, "");
    } catch {
      return String(value || "").split(/[?#]/, 1)[0].trim();
    }
  }

  function listCardKey({ href, name }) {
    return `${normalizedPlaceHref(href)}|${normalizeListText(name)}`;
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

  globalThis.MeshiLensListBadges = {
    MAX_LIST_CARDS,
    normalizeListText,
    normalizedPlaceHref,
    listCardKey,
    listCoordinatesFromHref,
    badgeText,
  };
})();
