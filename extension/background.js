const DEFAULT_API_URL = "https://meshilens.vercel.app/api";
const LEGACY_LOCAL_API_URL = "http://127.0.0.1:18765";

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

async function request(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 35000);
  try {
    const response = await fetch(`${await apiUrl()}${path}`, {
      ...options,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || `本機服務回傳 ${response.status}`);
    }
    return payload;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Tabelog 查詢逾時，請稍後再試");
    }
    if (error instanceof TypeError) {
      throw new Error("無法連上 MeshiLens 服務，請檢查 API 設定");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || !["MATCH_PLACE", "HEALTH_CHECK"].includes(message.type)) {
    return false;
  }
  const work = message.type === "HEALTH_CHECK"
    ? request("/health")
    : chrome.storage.local.get({ enabled: true }).then(({ enabled }) => {
        if (!enabled) throw new Error("MeshiLens 已停用");
        return request("/match", {
          method: "POST",
          body: JSON.stringify({
            name: String(message.place?.name || "").slice(0, 200),
            alternate_name: String(message.place?.alternate_name || "").slice(0, 200),
            address: String(message.place?.address || "").slice(0, 500),
            phone: String(message.place?.phone || "").slice(0, 50),
            tabelog_url: String(message.place?.tabelog_url || "").slice(0, 300),
            latitude: message.place?.latitude ?? null,
            longitude: message.place?.longitude ?? null,
          }),
        });
      });
  work.then((data) => sendResponse({ ok: true, data })).catch((error) => {
    sendResponse({ ok: false, error: error.message || "查詢失敗" });
  });
  return true;
});
