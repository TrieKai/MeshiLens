const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/settings.js");

test("theme colors only accept the five supported choices", () => {
  const { DEFAULT_THEME_COLOR, THEME_COLORS, normalizeThemeColor } = global.MeshiLensSettings;
  assert.equal(THEME_COLORS.length, 5);
  assert.equal(normalizeThemeColor("#35649A"), "#35649a");
  assert.equal(normalizeThemeColor("hotpink"), DEFAULT_THEME_COLOR);
});

test("keeps the documented local API URL instead of migrating it to cloud", () => {
  const {
    DEFAULT_API_URL,
    isAllowedApiUrl,
    normalizeApiUrl,
  } = global.MeshiLensSettings;
  assert.equal(
    normalizeApiUrl("http://127.0.0.1:18765"),
    "http://127.0.0.1:18765",
  );
  assert.equal(
    normalizeApiUrl("http://localhost:18765/"),
    "http://localhost:18765",
  );
  assert.equal(normalizeApiUrl("https://attacker.example/api"), DEFAULT_API_URL);
  assert.equal(isAllowedApiUrl("file:///tmp/server"), false);
});
