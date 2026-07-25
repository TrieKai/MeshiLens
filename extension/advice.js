(() => {
  const ADVICE_CACHE_TTL_MS = 24 * 60 * 60 * 1000;
  const ADVICE_CACHE_VERSION = "zh-Hant-v4";
  const CHINESE_NUMBER_PATTERN = /[零〇○一二三四五六七八九兩两十百千萬万億亿點点]+/g;
  const CHINESE_DIGITS = { "零": "0", "〇": "0", "○": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "兩": "2", "两": "2" };
  const CHINESE_UNITS = { "十": 10, "百": 100, "千": 1000, "萬": 10000, "万": 10000, "億": 100000000, "亿": 100000000 };

  function chineseNumeralToAscii(value) {
    if (value.includes("點") || value.includes("点")) {
      const [integer, decimal = ""] = value.split(/[點点]/, 2);
      return `${chineseNumeralToAscii(integer)}.${[...decimal].map((char) => CHINESE_DIGITS[char] || char).join("")}`;
    }
    if ([...value].every((char) => CHINESE_DIGITS[char] != null)) {
      return [...value].map((char) => CHINESE_DIGITS[char]).join("");
    }
    let total = 0;
    let section = 0;
    let number = 0;
    for (const char of value) {
      if (CHINESE_DIGITS[char] != null) {
        number = Number(CHINESE_DIGITS[char]);
        continue;
      }
      const unit = CHINESE_UNITS[char];
      if (!unit) return value;
      if (unit >= 10000) {
        total += (section + number) * unit;
        section = 0;
        number = 0;
      } else {
        section += (number || 1) * unit;
        number = 0;
      }
    }
    return String(total + section + number);
  }

  function normalizeAdviceNumbers(value) {
    const normalizeText = (text) => String(text || "").replace(CHINESE_NUMBER_PATTERN, (match, offset, source) => {
      if (match === "百" && source.slice(offset + match.length).startsWith("名店")) return match;
      return chineseNumeralToAscii(match);
    });
    if (!value || typeof value !== "object") return value;
    return {
      ...value,
      headline: normalizeText(value.headline),
      summary: normalizeText(value.summary),
      best_for: Array.isArray(value.best_for) ? value.best_for.map(normalizeText) : value.best_for,
      cautions: Array.isArray(value.cautions) ? value.cautions.map(normalizeText) : value.cautions,
      evidence: Array.isArray(value.evidence) ? value.evidence.map(normalizeText) : value.evidence,
    };
  }

  function adviceErrorMessage(value) {
    const message = String(value || "");
    const safeMessages = [
      "AI 暫時忙碌，請稍後再試",
      "AI 服務連線逾時，請稍後再試",
      "AI 回傳格式異常，請稍後再試",
      "AI 回傳內容未符合格式，請稍後再試",
      "AI 服務驗證失敗，請檢查伺服器設定",
    ];
    return safeMessages.find((item) => message.includes(item)) || "AI 建議暫時無法取得，請稍後再試";
  }

  function adviceFacts(place, candidate, michelin) {
    const genres = Array.isArray(candidate?.genres)
      ? candidate.genres
      : typeof candidate?.genres === "string"
        ? [candidate.genres]
        : [];
    const cuisine = genres
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .slice(0, 4);
    const hyakumeitenYears = [
      ...new Set(
        (Array.isArray(candidate?.hyakumeiten) ? candidate.hyakumeiten : [])
          .map((item) => Number(item?.year))
          .filter((year) => Number.isInteger(year))
      ),
    ]
      .sort((a, b) => b - a)
      .slice(0, 8);
    const payment = candidate?.payment;
    const facts = {
      restaurant_name: String(candidate?.name || place?.name || "").trim(),
      area: String(candidate?.address || place?.address || "").trim(),
      cuisine,
      tabelog_rating: candidate?.rating ?? null,
      tabelog_review_count: candidate?.review_count ?? null,
      lunch_price: String(candidate?.lunch_price || "").trim(),
      dinner_price: String(candidate?.dinner_price || "").trim(),
      reservation_status: String(candidate?.reservation_status || "").trim(),
      has_online_reservation: Boolean(candidate?.reservation_url),
      payment_available: payment ? Boolean(payment) : null,
      hyakumeiten_years: hyakumeitenYears,
      michelin_distinction: String(michelin?.distinction_label || "").trim(),
      michelin_green_star: Boolean(michelin?.green_star),
    };
    return Object.fromEntries(
      Object.entries(facts).filter(([, value]) => {
        if (value == null || value === "") return false;
        if (Array.isArray(value) && value.length === 0) return false;
        return true;
      })
    );
  }

  function advicePayload(place, candidate, michelin) {
    if (!place || !candidate?.name) return null;
    const facts = adviceFacts(place, candidate, michelin);
    if (!facts.restaurant_name) return null;
    return { facts };
  }

  function adviceCacheKey(place, candidate, michelin) {
    return JSON.stringify({ version: ADVICE_CACHE_VERSION, facts: adviceFacts(place, candidate, michelin) });
  }

  function cachedAdvice(entry, cacheKey, now = Date.now()) {
    if (!entry || entry.key !== cacheKey || !entry.advice || !entry.savedAt) return null;
    return now - entry.savedAt <= ADVICE_CACHE_TTL_MS ? entry.advice : null;
  }

  globalThis.MeshiLensAdvice = {
    ADVICE_CACHE_TTL_MS,
    ADVICE_CACHE_VERSION,
    advicePayload,
    adviceFacts,
    adviceCacheKey,
    adviceErrorMessage,
    cachedAdvice,
    normalizeAdviceNumbers,
  };
})();
