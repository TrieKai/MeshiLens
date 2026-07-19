importScripts("cache.js");

const DEFAULT_API_URL = "https://meshilens.vercel.app/api";
const LEGACY_LOCAL_API_URL = "http://127.0.0.1:18765";
const {
  getCachedLookup,
  setCachedLookup,
  tabelogCacheSuffix,
} = globalThis.MeshiLensCache;

/** @type {Map<string, AbortController>} */
const lookupControllers = new Map();

/** @type {{ apiUrl: string, enabled: boolean } | null} */
let cachedSettings = null;
/** @type {Promise<{ apiUrl: string, enabled: boolean }> | null} */
let settingsReady = null;

function isAllowedApiUrl(value) {
  try {
    const parsed = new URL(value);
    const isLocal =
      parsed.protocol === "http:" && ["127.0.0.1", "localhost"].includes(parsed.hostname);
    const isMeshiLensCloud =
      parsed.protocol === "https:" &&
      parsed.hostname === "meshilens.vercel.app" &&
      parsed.pathname === "/api";
    return isLocal || isMeshiLensCloud;
  } catch {
    return false;
  }
}

function normalizeApiUrl(value) {
  let apiUrl = String(value || DEFAULT_API_URL).replace(/\/$/, "");
  if (apiUrl === LEGACY_LOCAL_API_URL) apiUrl = DEFAULT_API_URL;
  if (!isAllowedApiUrl(apiUrl)) return DEFAULT_API_URL;
  return apiUrl;
}

async function loadSettings() {
  const settings = await chrome.storage.local.get({
    apiUrl: DEFAULT_API_URL,
    enabled: true,
  });
  const apiUrl = normalizeApiUrl(settings.apiUrl);
  if (apiUrl !== String(settings.apiUrl || "").replace(/\/$/, "")) {
    chrome.storage.local.set({ apiUrl }).catch(() => {});
  }
  cachedSettings = {
    apiUrl,
    enabled: settings.enabled !== false,
  };
  return cachedSettings;
}

function ensureSettings() {
  if (cachedSettings) return Promise.resolve(cachedSettings);
  if (!settingsReady) {
    settingsReady = loadSettings().finally(() => {
      settingsReady = null;
    });
  }
  return settingsReady;
}

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") return;
  if (!cachedSettings) {
    if (changes.apiUrl || changes.enabled) ensureSettings();
    return;
  }
  if (changes.apiUrl) {
    cachedSettings.apiUrl = normalizeApiUrl(changes.apiUrl.newValue);
  }
  if (changes.enabled) {
    cachedSettings.enabled = changes.enabled.newValue !== false;
  }
});

async function apiUrl() {
  return (await ensureSettings()).apiUrl;
}

function tabId(sender) {
  if (sender?.tab?.id != null) return String(sender.tab.id);
  return "popup";
}

function lookupKey(sender, kind) {
  return `${tabId(sender)}:${kind}`;
}

function abortLookup(key) {
  const previous = lookupControllers.get(key);
  if (previous) {
    previous.abort();
    lookupControllers.delete(key);
  }
}

function abortTabLookups(sender) {
  const prefix = `${tabId(sender)}:`;
  for (const key of [...lookupControllers.keys()]) {
    if (key.startsWith(prefix)) abortLookup(key);
  }
}

function beginLookup(sender, kind) {
  const key = lookupKey(sender, kind);
  abortLookup(key);
  const controller = new AbortController();
  lookupControllers.set(key, controller);
  return { key, controller };
}

function endLookup(key, controller) {
  if (lookupControllers.get(key) === controller) {
    lookupControllers.delete(key);
  }
}

async function request(path, options = {}) {
  const timeoutController = new AbortController();
  const timer = setTimeout(() => timeoutController.abort(), 35000);
  const upstream = options.signal;
  const onUpstreamAbort = () => timeoutController.abort();
  if (upstream) {
    if (upstream.aborted) timeoutController.abort();
    else upstream.addEventListener("abort", onUpstreamAbort, { once: true });
  }
  try {
    const response = await fetch(`${await apiUrl()}${path}`, {
      ...options,
      signal: timeoutController.signal,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || `本機服務回傳 ${response.status}`);
    }
    return payload;
  } catch (error) {
    if (error.name === "AbortError") {
      if (upstream?.aborted) {
        const cancelled = new Error("查詢已取消");
        cancelled.name = "AbortError";
        cancelled.cancelled = true;
        throw cancelled;
      }
      throw new Error("Tabelog 查詢逾時，請稍後再試");
    }
    if (error instanceof TypeError) {
      throw new Error("無法連上 MeshiLens 服務，請檢查 API 設定");
    }
    throw error;
  } finally {
    clearTimeout(timer);
    if (upstream) upstream.removeEventListener("abort", onUpstreamAbort);
  }
}

function placePayload(place) {
  return {
    name: String(place?.name || "").slice(0, 200),
    alternate_name: String(place?.alternate_name || "").slice(0, 200),
    address: String(place?.address || "").slice(0, 500),
    phone: String(place?.phone || "").slice(0, 50),
    website: String(place?.website || "").slice(0, 500),
    tabelog_url: String(place?.tabelog_url || "").slice(0, 300),
    latitude: place?.latitude ?? null,
    longitude: place?.longitude ?? null,
  };
}

function tabelogPayload(tabelog) {
  if (!tabelog || typeof tabelog !== "object") return null;
  const name = String(tabelog.name || "").trim().slice(0, 200);
  if (!name) return null;
  return {
    name,
    phone: String(tabelog.phone || "").trim().slice(0, 50),
    website: String(tabelog.website || "").trim().slice(0, 500),
    latitude: tabelog.latitude ?? null,
    longitude: tabelog.longitude ?? null,
  };
}

function adviceFactsPayload(payload) {
  const facts = payload?.facts;
  if (!facts || typeof facts !== "object" || Array.isArray(facts)) return null;
  const restaurantName = String(facts.restaurant_name || "").trim().slice(0, 120);
  if (!restaurantName) return null;
  return { facts };
}

async function matchPlace(place, signal) {
  const cached = await getCachedLookup("match", place);
  if (cached) return cached;
  const data = await request("/match", {
    method: "POST",
    body: JSON.stringify(placePayload(place)),
    signal,
  });
  await setCachedLookup("match", place, data);
  return data;
}

async function matchMichelin(place, signal, tabelog = null) {
  const hint = tabelogPayload(tabelog);
  const suffix = tabelogCacheSuffix(hint);
  const cached = await getCachedLookup("michelin", place, { suffix });
  if (cached) return cached;
  const body = placePayload(place);
  if (hint) body.tabelog = hint;
  const data = await request("/michelin", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
  await setCachedLookup("michelin", place, data, { suffix });
  if (hint && data?.michelin) {
    await setCachedLookup("michelin", place, data);
  }
  return data;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message) return false;

  if (message.type === "CANCEL_LOOKUP") {
    abortTabLookups(sender);
    sendResponse({ ok: true, cancelled: true });
    return false;
  }

  if (!["MATCH_PLACE", "MATCH_MICHELIN", "GET_DINING_ADVICE", "HEALTH_CHECK"].includes(message.type)) {
    return false;
  }

  const active =
    message.type === "MATCH_PLACE"
      ? beginLookup(sender, "match")
      : message.type === "MATCH_MICHELIN"
        ? beginLookup(sender, message.tabelog ? "michelin_tabelog" : "michelin")
        : null;

  const work = message.type === "HEALTH_CHECK"
    ? request("/health")
    : ensureSettings().then((settings) => {
        if (!settings.enabled) throw new Error("MeshiLens 已停用");
        if (message.type === "MATCH_MICHELIN") {
          return matchMichelin(message.place, active.controller.signal, message.tabelog);
        }
        if (message.type === "GET_DINING_ADVICE") {
          const payload = adviceFactsPayload(message.payload);
          if (!payload) throw new Error("找不到可用的用餐建議資料");
          return request("/advice", {
            method: "POST",
            body: JSON.stringify(payload),
          });
        }
        return matchPlace(message.place, active.controller.signal);
      });

  work
    .then((data) => sendResponse({ ok: true, data }))
    .catch((error) => {
      if (error?.cancelled || error?.name === "AbortError") {
        sendResponse({ ok: false, cancelled: true, error: error.message || "查詢已取消" });
        return;
      }
      sendResponse({ ok: false, error: error.message || "查詢失敗" });
    })
    .finally(() => {
      if (active) endLookup(active.key, active.controller);
    });
  return true;
});
