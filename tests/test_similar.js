const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/similar.js");

const {
  MAX_RECOMMENDATIONS,
  DEFAULT_VISIBLE_RECOMMENDATIONS,
  SIMILAR_CACHE_VERSION,
  alternativeCandidates,
  confidenceLabel,
  mapsSearchUrl,
  similarMapTargetPayload,
  similarDiagnosticsSummary,
  similarDisplayState,
  similarPayload,
  sortedSimilarRecommendations,
  visibleSimilarRecommendations,
} = globalThis.MeshiLensSimilar;

test("omits the selected Tabelog listing from manual candidate choices", () => {
  const selected = { url: "https://tabelog.com/tw/hyogo/A2803/A280303/28071372/" };
  const candidates = [
    { name: "麥當勞", url: "https://tabelog.com/hyogo/A2803/A280303/28071372/" },
    { name: "另一家店", url: "https://tabelog.com/hyogo/A2803/A280303/28000001/" },
  ];
  assert.deepEqual(alternativeCandidates(candidates, selected), [candidates[1]]);
});

test("does not show low-confidence Tabelog matches as manual choices", () => {
  const candidates = [
    { name: "低信心店", url: "https://tabelog.com/hyogo/A2803/A280303/28000001/", confidence: "low" },
    { name: "待確認店", url: "https://tabelog.com/hyogo/A2803/A280303/28000002/", confidence: "medium" },
  ];
  assert.deepEqual(alternativeCandidates(candidates, null), [candidates[1]]);
});

test("uses confidence labels and Google Maps place searches for UI links", () => {
  assert.equal(confidenceLabel("high"), "高信心");
  assert.equal(confidenceLabel("medium"), "待確認");
  assert.equal(confidenceLabel("low"), "低信心");
  assert.equal(
    mapsSearchUrl("鮨 みなと", "東京都中央区銀座"),
    "https://www.google.com/maps/search/?api=1&query=%E9%AE%A8%20%E3%81%BF%E3%81%AA%E3%81%A8%20%E6%9D%B1%E4%BA%AC%E9%83%BD%E4%B8%AD%E5%A4%AE%E5%8C%BA%E9%8A%80%E5%BA%A7",
  );
  assert.deepEqual(
    similarMapTargetPayload({ name: "MENSHO", url: "https://tabelog.com/tokyo/A1323/A132302/13203848/" }),
    { name: "MENSHO", url: "https://tabelog.com/tokyo/a1323/a132302/13203848/" },
  );
  assert.equal(similarMapTargetPayload({ name: "MENSHO", url: "https://example.com/" }), null);
});

test("builds a bounded similar-restaurant request from selected Tabelog facts", () => {
  assert.equal(MAX_RECOMMENDATIONS, 6);
  assert.equal(DEFAULT_VISIBLE_RECOMMENDATIONS, 3);
  assert.equal(SIMILAR_CACHE_VERSION, "nearby-v14");
  assert.deepEqual(
    similarPayload({
      name: "鮨 みなと",
      url: "https://tabelog.com/tokyo/A1301/A130101/1300001/",
      genres: ["寿司", "日本料理"],
      station: "銀座駅",
      address: "東京都中央区銀座",
      dinner_price: "￥20,000～￥29,999",
    }),
    {
      selected: {
        name: "鮨 みなと",
        url: "https://tabelog.com/tokyo/A1301/A130101/1300001/",
        genres: ["寿司", "日本料理"],
        station: "銀座駅",
        address: "東京都中央区銀座",
        lunch_price: "",
        dinner_price: "￥20,000～￥29,999",
      },
    },
  );
});

test("sorts already-loaded similar restaurants without another request", () => {
  const recommendations = [
    { name: "評論最多拉麵", similarity_score: 92, rating: 3.2, review_count: 500, genres: ["ラーメン"], genre_labels: ["拉麵"] },
    { name: "高分壽司", similarity_score: 71, rating: 3.9, review_count: 12, genres: ["寿司"], genre_labels: ["壽司"] },
    { name: "中分拉麵", similarity_score: 80, rating: 3.6, review_count: 100, genres: ["ラーメン"], genre_labels: ["拉麵"] },
  ];
  assert.deepEqual(
    sortedSimilarRecommendations(recommendations, "rating").map((item) => item.name),
    ["高分壽司", "中分拉麵", "評論最多拉麵"],
  );
  assert.deepEqual(
    visibleSimilarRecommendations(recommendations, { sort: "reviews", expanded: true }).map((item) => item.name),
    ["評論最多拉麵", "中分拉麵", "高分壽司"],
  );
});

test("does not request similar restaurants without Tabelog URL or cuisine", () => {
  assert.equal(similarPayload({ name: "鮨 みなと", genres: ["寿司"] }), null);
  assert.equal(similarPayload({ name: "鮨 みなと", url: "https://tabelog.com/example/" }), null);
});

test("keeps an explicit empty state and safe diagnostics when no nearby recommendation is verified", () => {
  const diagnostics = { search_scope: "銀座駅", returned_count: 5, unverified_location_count: 4, below_quality_count: 1 };
  assert.deepEqual(similarDisplayState([], diagnostics), { status: "empty", diagnostics });
  assert.deepEqual(similarDisplayState(null), { status: "empty", diagnostics: null });
  assert.deepEqual(
    similarDisplayState([{ name: "附近店家" }]),
    { status: "ready", recommendations: [{ name: "附近店家" }], diagnostics: null, sort: "recommended", expanded: false },
  );
  assert.equal(
    similarDiagnosticsSummary(diagnostics),
    "搜尋範圍：銀座駅；Tabelog 回傳 5 家；1 家未達相似度門檻。",
  );
  assert.equal(similarDiagnosticsSummary(null), "");
});
