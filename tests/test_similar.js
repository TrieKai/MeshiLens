const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/similar.js");

const { MAX_RECOMMENDATIONS, similarPayload } = globalThis.MeshiLensSimilar;

test("builds a bounded similar-restaurant request from selected Tabelog facts", () => {
  assert.equal(MAX_RECOMMENDATIONS, 3);
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

test("does not request similar restaurants without Tabelog URL or cuisine", () => {
  assert.equal(similarPayload({ name: "鮨 みなと", genres: ["寿司"] }), null);
  assert.equal(similarPayload({ name: "鮨 みなと", url: "https://tabelog.com/example/" }), null);
});
