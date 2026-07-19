importScripts("cache.js");

const DEFAULT_API_URL = "https://meshilens.vercel.app/api";
const LEGACY_LOCAL_API_URL = "http://127.0.0.1:18765";
const {
  getCachedLookup,
  setCachedLookup,
} = globalThis.MeshiLensCache;

/** @type {Map<string, AbortController>} */
const lookupControllers = new Map();

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

async function apiUrl() {
  const settings = await chrome.storage.local.get({ apiUrl: DEFAULT_API_URL });
  let value = settings.apiUrl.replace(/\/$/, "");
  if (value === LEGACY_LOCAL_API_URL) {
    value = DEFAULT_API_URL;
    await chrome.storage.local.set({ apiUrl: value });
  }
  if (!isAllowedApiUrl(value)) {
    return DEFAULT_API_URL;
  }
  return value;
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

async function matchMichelin(place, signal) {
  const cached = await getCachedLookup("michelin", place);
  if (cached) return cached;
  const data = await request("/michelin", {
    method: "POST",
    body: JSON.stringify(placePayload(place)),
    signal,
  });
  await setCachedLookup("michelin", place, data);
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
        ? beginLookup(sender, "michelin")
        : null;

  const work = message.type === "HEALTH_CHECK"
    ? request("/health")
    : chrome.storage.local.get({ enabled: true }).then(({ enabled }) => {
        if (!enabled) throw new Error("MeshiLens 已停用");
        if (message.type === "MATCH_MICHELIN") {
          return matchMichelin(message.place, active.controller.signal);
        }
        if (message.type === "GET_DINING_ADVICE") {
          return request("/advice", {
            method: "POST",
            body: JSON.stringify(message.payload),
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
