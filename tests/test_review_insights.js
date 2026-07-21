const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/review_insights.js");

const {
  REVIEW_INSIGHTS_CACHE_TTL_MS,
  BUTTON_LABEL,
  CARD_TITLE,
  UNAVAILABLE_LABEL,
  reviewInsightsPayload,
  reviewInsightsCacheKey,
  cachedReviewInsights,
  beginReviewInsightsFlight,
  clearReviewInsightsFlight,
  hasReviewInsightsFlight,
} = globalThis.MeshiLensReviewInsights;

test("builds URL-only review insights payload from selected candidate", () => {
  const candidate = {
    name: "清水屋",
    url: "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
    rating: 3.5,
  };
  assert.deepEqual(reviewInsightsPayload(candidate), {
    tabelog_url: "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
    restaurant_name: "清水屋",
  });
  assert.equal(reviewInsightsPayload({ name: "清水屋" }), null);
  assert.equal(
    reviewInsightsPayload({
      name: "清水屋",
      url: "https://maps.google.com/place",
    }),
    null
  );
});

test("exposes button and card labels without a consent gate", () => {
  assert.equal(BUTTON_LABEL, "分析公開評論");
  assert.equal(CARD_TITLE, "評論實驗摘要");
  assert.equal(UNAVAILABLE_LABEL, "暫時無法取得");
  assert.equal(globalThis.MeshiLensReviewInsights.shouldPromptConsent, undefined);
  assert.equal(globalThis.MeshiLensReviewInsights.CONSENT_MESSAGE, undefined);
});

test("review insights cache TTL is 7 days and keyed by tabelog url", () => {
  assert.equal(REVIEW_INSIGHTS_CACHE_TTL_MS, 7 * 24 * 60 * 60 * 1000);
  const candidate = {
    name: "清水屋",
    url: "https://tabelog.com/ibaraki/A0804/A080401/8000477/",
  };
  const key = reviewInsightsCacheKey(candidate);
  const entry = {
    key,
    savedAt: 1_000,
    insights: { summary: "測試摘要", sample_size: 6 },
  };
  assert.deepEqual(cachedReviewInsights(entry, key, 2_000), entry.insights);
  assert.equal(
    cachedReviewInsights(entry, key, 1_000 + REVIEW_INSIGHTS_CACHE_TTL_MS + 1),
    null
  );
  assert.equal(
    cachedReviewInsights(
      entry,
      "https://tabelog.com/tokyo/A1301/A130101/13000000/",
      2_000
    ),
    null
  );
});

test("single-flight reuses the in-progress request for the same store", async () => {
  let starts = 0;
  const key = "https://tabelog.com/ibaraki/A0804/A080401/8000477/";
  clearReviewInsightsFlight(key);
  const work = () =>
    beginReviewInsightsFlight(key, async () => {
      starts += 1;
      await new Promise((resolve) => setTimeout(resolve, 20));
      return { summary: "ok" };
    });
  const [a, b] = await Promise.all([work(), work()]);
  assert.equal(starts, 1);
  assert.deepEqual(a, b);
  assert.equal(hasReviewInsightsFlight(key), false);
});

test("clearing flights allows a later request to start again", async () => {
  const key = "https://tabelog.com/ibaraki/A0804/A080401/8000478/";
  clearReviewInsightsFlight(key);
  let resolveFirst;
  const firstGate = new Promise((resolve) => {
    resolveFirst = resolve;
  });
  const first = beginReviewInsightsFlight(key, async () => {
    await firstGate;
    return { summary: "first" };
  });
  assert.equal(hasReviewInsightsFlight(key), true);
  clearReviewInsightsFlight(key);
  assert.equal(hasReviewInsightsFlight(key), false);
  resolveFirst();
  await first;
  const second = await beginReviewInsightsFlight(key, async () => ({ summary: "second" }));
  assert.equal(second.summary, "second");
});
