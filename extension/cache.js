(() => {
  const LOOKUP_CACHE_TTL_MS = 45 * 60 * 1000;
  const COORD_DECIMALS = 5;
  const STORAGE_KEY = "lookupResultCache";
  const memoryCache = new Map();

  function roundCoord(value, decimals = COORD_DECIMALS) {
    if (value === null || value === undefined || value === "") return "";
    const number = Number(value);
    if (!Number.isFinite(number)) return "";
    return number.toFixed(decimals);
  }

  function placeCacheKey(place, suffix = "") {
    const key = [
      String(place?.name || "").trim(),
      String(place?.alternate_name || "").trim(),
      String(place?.address || "").trim(),
      String(place?.phone || "").trim(),
      String(place?.website || "").trim(),
      String(place?.tabelog_url || "").trim(),
      roundCoord(place?.latitude),
      roundCoord(place?.longitude),
    ].join("|");
    return suffix ? `${key}|${suffix}` : key;
  }

  function tabelogCacheSuffix(tabelog) {
    if (!tabelog || typeof tabelog !== "object") return "";
    const name = String(tabelog.name || "").trim();
    if (!name) return "";
    return [
      "tg",
      name,
      String(tabelog.phone || "").trim(),
      String(tabelog.website || "").trim(),
      roundCoord(tabelog.latitude),
      roundCoord(tabelog.longitude),
    ].join(":");
  }

  function lookupCacheKey(kind, placeKey) {
    return `${kind}:${placeKey}`;
  }

  function readMemory(key, now = Date.now()) {
    const entry = memoryCache.get(key);
    if (!entry || !entry.savedAt || now - entry.savedAt > LOOKUP_CACHE_TTL_MS) {
      memoryCache.delete(key);
      return null;
    }
    return entry.data;
  }

  function writeMemory(key, data, now = Date.now()) {
    memoryCache.set(key, { savedAt: now, data });
  }

  function cachedLookupEntry(entry, cacheKey, now = Date.now()) {
    if (!entry || entry.key !== cacheKey || !entry.data || !entry.savedAt) return null;
    return now - entry.savedAt <= LOOKUP_CACHE_TTL_MS ? entry.data : null;
  }

  async function getCachedLookup(kind, place, options = {}) {
    const opts = typeof options === "number" ? { now: options } : options || {};
    const now = opts.now ?? Date.now();
    const placeKey = placeCacheKey(place, opts.suffix || "");
    const key = lookupCacheKey(kind, placeKey);
    const fromMemory = readMemory(key, now);
    if (fromMemory) return { ...fromMemory, cached: true };

    const storage = globalThis.chrome?.storage?.session;
    if (!storage?.get) return null;
    try {
      const stored = await storage.get({ [STORAGE_KEY]: {} });
      const cache = stored[STORAGE_KEY] || {};
      const data = cachedLookupEntry(cache[key], key, now);
      if (!data) return null;
      writeMemory(key, data, now);
      return { ...data, cached: true };
    } catch {
      return null;
    }
  }

  async function setCachedLookup(kind, place, data, options = {}) {
    if (!data || typeof data !== "object") return;
    const opts = typeof options === "number" ? { now: options } : options || {};
    const now = opts.now ?? Date.now();
    const placeKey = placeCacheKey(place, opts.suffix || "");
    const key = lookupCacheKey(kind, placeKey);
    const payload = { ...data, cached: false };
    writeMemory(key, payload, now);

    const storage = globalThis.chrome?.storage?.session;
    if (!storage?.get || !storage?.set) return;
    try {
      const stored = await storage.get({ [STORAGE_KEY]: {} });
      const cache = { ...(stored[STORAGE_KEY] || {}) };
      cache[key] = { key, savedAt: now, data: payload };
      const entries = Object.entries(cache)
        .filter(([, entry]) => entry && now - (entry.savedAt || 0) <= LOOKUP_CACHE_TTL_MS)
        .sort((left, right) => (right[1].savedAt || 0) - (left[1].savedAt || 0))
        .slice(0, 80);
      await storage.set({ [STORAGE_KEY]: Object.fromEntries(entries) });
    } catch {
      // Session storage may be unavailable in tests; memory Map still works.
    }
  }

  function clearMemoryLookupCache() {
    memoryCache.clear();
  }

  globalThis.MeshiLensCache = {
    LOOKUP_CACHE_TTL_MS,
    COORD_DECIMALS,
    roundCoord,
    placeCacheKey,
    tabelogCacheSuffix,
    lookupCacheKey,
    cachedLookupEntry,
    getCachedLookup,
    setCachedLookup,
    clearMemoryLookupCache,
  };
})();
