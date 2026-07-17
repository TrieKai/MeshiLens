const DEFAULT_API_URL = "http://127.0.0.1:18765";
const input = document.getElementById("api-url");
const status = document.getElementById("status");

async function check() {
  status.className = "status checking";
  status.textContent = "正在檢查本機服務…";
  const response = await chrome.runtime.sendMessage({ type: "HEALTH_CHECK" });
  status.className = `status ${response?.ok ? "online" : "offline"}`;
  status.textContent = response?.ok ? "本機服務運作中" : response?.error || "無法連線";
}

chrome.storage.local.get({ apiUrl: DEFAULT_API_URL }).then(({ apiUrl }) => {
  input.value = apiUrl;
  check();
});

document.getElementById("save").addEventListener("click", async () => {
  const value = input.value.trim().replace(/\/$/, "");
  if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(value)) {
    status.className = "status offline";
    status.textContent = "MVP 僅允許本機 HTTP 網址";
    return;
  }
  await chrome.storage.local.set({ apiUrl: value });
  await check();
});
