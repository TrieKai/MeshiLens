const DEFAULT_API_URL = "https://meshilens.vercel.app/api";
const LEGACY_LOCAL_API_URL = "http://127.0.0.1:18765";
const input = document.getElementById("api-url");
const status = document.getElementById("status");
const enabledInput = document.getElementById("enabled");
const enabledState = document.getElementById("enabled-state");
let checkSequence = 0;

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

async function check() {
  const sequence = ++checkSequence;
  if (!enabledInput.checked) {
    status.className = "status paused";
    status.textContent = "MeshiLens 已暫停，不會查詢店家資料";
    return;
  }
  status.className = "status checking";
  status.textContent = "正在檢查本機服務…";
  const response = await chrome.runtime.sendMessage({ type: "HEALTH_CHECK" });
  if (sequence !== checkSequence || !enabledInput.checked) return;
  status.className = `status ${response?.ok ? "online" : "offline"}`;
  status.textContent = response?.ok ? "本機服務運作中" : response?.error || "無法連線";
}

function renderEnabled(enabled) {
  enabledInput.checked = enabled;
  enabledState.textContent = enabled ? "已啟用" : "已暫停";
}

chrome.storage.local.get({ apiUrl: DEFAULT_API_URL, enabled: true }).then(async ({ apiUrl, enabled }) => {
  const value = apiUrl === LEGACY_LOCAL_API_URL ? DEFAULT_API_URL : apiUrl;
  if (value !== apiUrl) await chrome.storage.local.set({ apiUrl: value });
  input.value = value;
  renderEnabled(enabled);
  check();
});

enabledInput.addEventListener("change", async () => {
  const enabled = enabledInput.checked;
  renderEnabled(enabled);
  await chrome.storage.local.set({ enabled });
  check();
});

document.getElementById("save").addEventListener("click", async () => {
  const value = input.value.trim().replace(/\/$/, "");
  if (!isAllowedApiUrl(value)) {
    status.className = "status offline";
    status.textContent = "請使用 MeshiLens 雲端網址或本機 HTTP 網址";
    return;
  }
  await chrome.storage.local.set({ apiUrl: value });
  await check();
});
