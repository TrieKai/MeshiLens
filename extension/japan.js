(() => {
  // This is deliberately only a negative geographic guard.  Being inside this
  // broad range does not prove a place is in Japan.
  const JAPAN_BOUNDS = { minLatitude: 20, maxLatitude: 46.5, minLongitude: 122, maxLongitude: 154.5 };
  const JAPAN_POSTCODE_PATTERN = /〒\s*\d{3}\s*[-‐‑–—]?\s*\d{4}/u;
  const JAPAN_PHONE_PATTERN = /(?:^|[^\d])\+81(?:[\s()-]|\d)/;
  const JAPAN_ADDRESS_PATTERN = /\bJapan\b|日本|北海道|(?:東京都|京都府|大阪府)|(?:青森|岩手|宮城|秋田|山形|福島|茨城|栃木|群馬|埼玉|千葉|神奈川|新潟|富山|石川|福井|山梨|長野|岐阜|静岡|愛知|三重|滋賀|兵庫|奈良|和歌山|鳥取|島根|岡山|広島|山口|徳島|香川|愛媛|高知|福岡|佐賀|長崎|熊本|大分|宮崎|鹿児島|沖縄)県/u;

  function isJapanTabelogUrl(value) {
    try {
      const url = new URL(String(value || ""));
      return url.protocol === "https:"
        && url.hostname === "tabelog.com"
        && /^\/[a-z0-9-]+\/A\d+\/A\d+\/\d+\//i.test(url.pathname);
    } catch {
      return false;
    }
  }

  function hasJapanSignal(place) {
    const address = String(place?.address || "");
    return isJapanTabelogUrl(place?.tabelog_url)
      || JAPAN_PHONE_PATTERN.test(String(place?.phone || ""))
      || JAPAN_POSTCODE_PATTERN.test(address)
      || JAPAN_ADDRESS_PATTERN.test(address);
  }

  function hasExactCoordinates(place) {
    return place?.coordinates_source === "place" || place?.exact_coordinates === true;
  }

  function exactCoordinatesOutsideJapan(place) {
    if (!hasExactCoordinates(place)) return false;
    const latitude = Number(place?.latitude);
    const longitude = Number(place?.longitude);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return false;
    return latitude < JAPAN_BOUNDS.minLatitude
      || latitude > JAPAN_BOUNDS.maxLatitude
      || longitude < JAPAN_BOUNDS.minLongitude
      || longitude > JAPAN_BOUNDS.maxLongitude;
  }

  function classifyJapanPlace(place) {
    if (hasJapanSignal(place)) return "japan";
    if (exactCoordinatesOutsideJapan(place)) return "not_japan";
    return "unknown";
  }

  globalThis.MeshiLensJapan = {
    JAPAN_BOUNDS,
    isJapanTabelogUrl,
    hasJapanSignal,
    hasExactCoordinates,
    exactCoordinatesOutsideJapan,
    classifyJapanPlace,
  };
})();
