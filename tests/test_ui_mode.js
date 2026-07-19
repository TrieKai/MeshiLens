const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/ui_mode.js");

const {
  DETAIL_MODE,
  LIST_MODE,
  MAP_MODE,
  mapsUiMode,
} = globalThis.MeshiLensUiMode;

test("identifies a search results sidebar without treating it as a place detail", () => {
  assert.equal(mapsUiMode({ hasDetailTitle: false, hasResultsFeed: true }), LIST_MODE);
});

test("prioritizes a place detail when its result feed remains in the DOM", () => {
  assert.equal(mapsUiMode({ hasDetailTitle: true, hasResultsFeed: true }), DETAIL_MODE);
});

test("keeps a plain map view separate from search results", () => {
  assert.equal(mapsUiMode({ hasDetailTitle: false, hasResultsFeed: false }), MAP_MODE);
});
