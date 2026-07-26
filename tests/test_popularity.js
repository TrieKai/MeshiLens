const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const test = require("node:test");

const context = { globalThis: {} };
vm.runInNewContext(fs.readFileSync("extension/popularity.js", "utf8"), context);
const popularity = context.globalThis.MeshiLensPopularity;

test("popularity payload only accepts canonical Tabelog restaurant URLs", () => {
  assert.equal(
    JSON.stringify(popularity.popularityPayload({ name: "店", url: "https://tabelog.com/tokyo/A1323/A132302/13276342/" })),
    JSON.stringify({ selected: { name: "店", url: "https://tabelog.com/tokyo/A1323/A132302/13276342/" } }),
  );
  assert.equal(popularity.popularityPayload({ name: "店", url: "https://example.com/store" }), null);
});

test("popularity tags keep only valid TOP 10 badges", () => {
  const tags = popularity.popularityTags({ tags: [
    { label: "最多預訂", rank: 3, tier: "top5", source_url: "https://tabelog.com/tw/tokyo/" },
    { label: "瀏覽最多", rank: 11 },
  ] });
  assert.equal(
    JSON.stringify(tags),
    JSON.stringify([{ label: "最多預訂", rank: 3, tier: "top5", sourceUrl: "https://tabelog.com/tw/tokyo/" }]),
  );
  assert.equal(popularity.popularityBadgeText(tags[0]), "最多預訂 TOP 5");
});
