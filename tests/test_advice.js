const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/advice.js");

const {
  ADVICE_CACHE_TTL_MS,
  ADVICE_CACHE_VERSION,
  adviceErrorMessage,
  advicePayload,
  adviceCacheKey,
  cachedAdvice,
  normalizeAdviceNumbers,
} = globalThis.MeshiLensAdvice;

test("builds a facts-only advice request after a selected candidate exists", () => {
  const place = { name: "清水屋", address: "茨城県潮来市", title: { tagName: "H1" } };
  const candidate = {
    name: "清水屋",
    url: "https://tabelog.com/example/",
    rating: 3.5,
    review_count: 100,
  };
  assert.deepEqual(advicePayload(place, candidate, null), {
    facts: {
      restaurant_name: "清水屋",
      area: "茨城県潮来市",
      tabelog_rating: 3.5,
      tabelog_review_count: 100,
      has_online_reservation: false,
      michelin_green_star: false,
    },
  });
  assert.equal(advicePayload(place, null, null), null);
});

test("advice cache TTL is 24 hours", () => {
  assert.equal(ADVICE_CACHE_TTL_MS, 24 * 60 * 60 * 1000);
  assert.equal(ADVICE_CACHE_VERSION, "zh-Hant-v4");
  assert.equal(adviceErrorMessage("AI 暫時忙碌，請稍後再試"), "AI 暫時忙碌，請稍後再試");
  assert.equal(adviceErrorMessage("AI 回傳含日文，請稍後再試"), "AI 回傳含日文，請稍後再試");
  assert.equal(adviceErrorMessage("unexpected"), "AI 建議暫時無法取得，請稍後再試");
});

test("normalizes Chinese numerals in advice returned by an older server or cache", () => {
  assert.deepEqual(
    normalizeAdviceNumbers({
      summary: "東池袋二丁目五七之二，三点六八分",
      evidence: ["評論數一千四百零五則", "二零二四年百名店"],
    }),
    {
      summary: "東池袋2丁目57之2，3.68分",
      evidence: ["評論數1405則", "2024年百名店"],
      headline: "",
      best_for: undefined,
      cautions: undefined,
    },
  );
});

test("invalidates advice cache when restaurant facts change", () => {
  const place = { name: "清水屋", address: "茨城県潮来市" };
  const candidate = {
    name: "清水屋",
    address: "茨城県潮来市",
    rating: 3.5,
    review_count: 100,
    dinner_price: "￥10,000～￥14,999",
    genres: ["割烹・小料理"],
    reservation_status: "available",
    hyakumeiten: [{ year: 2025 }],
  };
  const key = adviceCacheKey(place, candidate, null);
  const entry = { key, savedAt: 1_000, advice: { summary: "測試" } };
  assert.deepEqual(cachedAdvice(entry, key, 2_000), entry.advice);
  assert.equal(
    cachedAdvice(entry, adviceCacheKey(place, { ...candidate, rating: 3.6 }, null), 2_000),
    null
  );
  assert.equal(
    cachedAdvice(entry, adviceCacheKey(place, { ...candidate, dinner_price: "￥15,000～￥19,999" }, null), 2_000),
    null
  );
  assert.equal(
    cachedAdvice(entry, adviceCacheKey(place, { ...candidate, genres: ["寿司"] }, null), 2_000),
    null
  );
});

test("reuses advice cache when facts are unchanged", () => {
  const place = { name: "清水屋" };
  const candidate = {
    name: "清水屋",
    rating: 3.5,
    review_count: 100,
    url: "https://tabelog.com/example/",
  };
  const key = adviceCacheKey(place, candidate, { distinction_label: "必比登推介" });
  const sameKey = adviceCacheKey(
    place,
    { ...candidate, confidence: "high", score: 99 },
    { distinction_label: "必比登推介", url: "https://guide.michelin.com/other" }
  );
  assert.equal(key, sameKey);
  const entry = { key, savedAt: 1_000, advice: { summary: "測試" } };
  assert.deepEqual(cachedAdvice(entry, sameKey, 2_000), entry.advice);
});

test("expires advice cache after TTL", () => {
  const place = { name: "清水屋" };
  const candidate = { name: "清水屋", rating: 3.5 };
  const key = adviceCacheKey(place, candidate, null);
  const entry = { key, savedAt: 1_000, advice: { summary: "測試" } };
  assert.deepEqual(cachedAdvice(entry, key, 1_000 + ADVICE_CACHE_TTL_MS), entry.advice);
  assert.equal(cachedAdvice(entry, key, 1_000 + ADVICE_CACHE_TTL_MS + 1), null);
});
