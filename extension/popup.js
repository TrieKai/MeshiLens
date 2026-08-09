const input = document.getElementById("api-url");
const status = document.getElementById("status");
const enabledInput = document.getElementById("enabled");
const enabledState = document.getElementById("enabled-state");
const version = document.getElementById("version");
const themeButtons = [...document.querySelectorAll("[data-theme-color]")];
const {
  DEFAULT_API_URL,
  DEFAULT_THEME_COLOR,
  isAllowedApiUrl,
  normalizeApiUrl,
  normalizeThemeColor,
} = globalThis.MeshiLensSettings;
let checkSequence = 0;

version.textContent = `v${chrome.runtime.getManifest().version}`;

function renderTheme(value) {
  const color = normalizeThemeColor(value);
  document.documentElement.style.setProperty("--ml-accent", color);
  for (const button of themeButtons) {
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.themeColor.toLowerCase() === color),
    );
  }
  return color;
}

async function check() {
  const sequence = ++checkSequence;
  if (!enabledInput.checked) {
    status.className = "status paused";
    status.textContent = "MeshiLens 已暫停，不會查詢店家資料";
    return;
  }
  status.className = "status checking";
  status.textContent = "正在檢查 MeshiLens 服務…";
  try {
    const response = await chrome.runtime.sendMessage({ type: "HEALTH_CHECK" });
    if (sequence !== checkSequence || !enabledInput.checked) return;
    status.className = `status ${response?.ok ? "online" : "offline"}`;
    status.textContent = response?.ok ? "MeshiLens 服務運作中" : response?.error || "無法連線";
  } catch (error) {
    if (sequence !== checkSequence || !enabledInput.checked) return;
    status.className = "status offline";
    status.textContent = error?.message || "無法連線";
  }
}

function renderEnabled(enabled) {
  enabledInput.checked = enabled;
  enabledState.textContent = enabled ? "已啟用" : "已暫停";
}

chrome.storage.local.get({
  apiUrl: DEFAULT_API_URL,
  enabled: true,
  themeColor: DEFAULT_THEME_COLOR,
}).then(async ({ apiUrl, enabled, themeColor }) => {
  const value = normalizeApiUrl(apiUrl);
  if (value !== apiUrl) await chrome.storage.local.set({ apiUrl: value });
  input.value = value;
  renderEnabled(enabled);
  renderTheme(themeColor);
  check();
});

for (const button of themeButtons) {
  button.addEventListener("click", async () => {
    const themeColor = renderTheme(button.dataset.themeColor);
    await chrome.storage.local.set({ themeColor });
  });
}

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
