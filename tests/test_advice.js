const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/advice.js");

const { advicePayload, adviceCacheKey, cachedAdvice } = globalThis.MeshiLensAdvice;

test("builds a compact advice request only after a selected candidate exists", () => {
  const place = { name: "清水屋" };
  const candidate = { name: "清水屋", url: "https://tabelog.com/example/" };
  assert.deepEqual(advicePayload(place, candidate, null), { place, candidate, michelin: null });
  assert.equal(advicePayload(place, null, null), null);
});

test("invalidates advice cache when restaurant facts change", () => {
  const candidate = { url: "https://tabelog.com/example/", rating: 3.5, review_count: 100 };
  const key = adviceCacheKey(candidate, null);
  const entry = { key, savedAt: 1_000, advice: { summary: "測試" } };
  assert.deepEqual(cachedAdvice(entry, key, 2_000), entry.advice);
  assert.equal(cachedAdvice(entry, adviceCacheKey({ ...candidate, rating: 3.6 }, null), 2_000), null);
});
