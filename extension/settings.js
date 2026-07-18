(() => {
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

  globalThis.MeshiLensSettings = {
    DEFAULT_THEME_COLOR,
    THEME_COLORS,
    normalizeThemeColor,
  };
})();
