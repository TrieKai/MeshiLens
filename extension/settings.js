(() => {
  const DEFAULT_API_URL = "https://meshilens.vercel.app/api";
  const THEME_COLORS = Object.freeze([
    Object.freeze({ name: "赤紅", value: "#bf3a2b" }),
    Object.freeze({ name: "橙色", value: "#a65314" }),
    Object.freeze({ name: "綠色", value: "#2f7658" }),
    Object.freeze({ name: "藍色", value: "#35649a" }),
    Object.freeze({ name: "紫色", value: "#71549a" }),
  ]);
  const DEFAULT_THEME_COLOR = THEME_COLORS[0].value;

  function normalizeThemeColor(value) {
    const normalized = String(value || "").toLowerCase();
    return THEME_COLORS.some((theme) => theme.value === normalized)
      ? normalized
      : DEFAULT_THEME_COLOR;
  }

  function isAllowedApiUrl(value) {
    try {
      const parsed = new URL(String(value || ""));
      const isCleanBase =
        !parsed.username
        && !parsed.password
        && !parsed.search
        && !parsed.hash;
      const isLocal =
        parsed.protocol === "http:"
        && ["127.0.0.1", "localhost"].includes(parsed.hostname)
        && parsed.pathname === "/";
      const isMeshiLensCloud =
        parsed.protocol === "https:"
        && parsed.hostname === "meshilens.vercel.app"
        && parsed.pathname === "/api";
      return isCleanBase && (isLocal || isMeshiLensCloud);
    } catch {
      return false;
    }
  }

  function normalizeApiUrl(value) {
    const normalized = String(value || DEFAULT_API_URL).replace(/\/+$/, "");
    return isAllowedApiUrl(normalized) ? normalized : DEFAULT_API_URL;
  }

  globalThis.MeshiLensSettings = {
    DEFAULT_API_URL,
    DEFAULT_THEME_COLOR,
    THEME_COLORS,
    isAllowedApiUrl,
    normalizeApiUrl,
    normalizeThemeColor,
  };
})();
