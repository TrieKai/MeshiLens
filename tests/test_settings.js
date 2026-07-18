const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/settings.js");

test("theme colors only accept the five supported choices", () => {
  const { DEFAULT_THEME_COLOR, THEME_COLORS, normalizeThemeColor } = global.MeshiLensSettings;
  assert.equal(THEME_COLORS.length, 5);
  assert.equal(normalizeThemeColor("#35649A"), "#35649a");
  assert.equal(normalizeThemeColor("hotpink"), DEFAULT_THEME_COLOR);
});
