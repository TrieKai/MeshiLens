const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/timeline.js");

const { buildTimelineEntries, shouldShowTimeline } = globalThis.MeshiLensTimeline;

test("puts current Michelin above hyakumeiten years", () => {
  const entries = buildTimelineEntries(
    {
      distinction_label: "一星",
      url: "https://guide.michelin.com/example",
      green_star: false,
    },
    [
      {
        year: 2021,
        category: "日本料理",
        area: "WEST",
        url: "https://award.tabelog.com/hyakumeiten/japanese_west/2021/",
      },
      {
        year: 2025,
        category: "日本料理",
        area: "WEST",
        url: "https://award.tabelog.com/hyakumeiten/japanese_west/2025/",
      },
      {
        year: 2023,
        category: "日本料理",
        area: "WEST",
        url: "https://award.tabelog.com/hyakumeiten/japanese_west/2023/",
      },
    ],
  );

  assert.equal(shouldShowTimeline(entries), true);
  assert.deepEqual(
    entries.map((entry) => [entry.kind, entry.year_label, entry.label]),
    [
      ["michelin", "現在", "Michelin 一星"],
      ["hyakumeiten", "2025", "百名店 · 日本料理 WEST"],
      ["hyakumeiten", "2023", "百名店 · 日本料理 WEST"],
      ["hyakumeiten", "2021", "百名店 · 日本料理 WEST"],
    ],
  );
});

test("hides timeline when only Michelin is present", () => {
  const entries = buildTimelineEntries({ distinction_label: "必比登", url: "https://example.com" });
  assert.equal(shouldShowTimeline(entries), false);
});

test("keeps hyakumeiten-only timeline without Michelin", () => {
  const entries = buildTimelineEntries(null, [
    { year: 2024, category: "燒肉", url: "https://award.tabelog.com/hyakumeiten/yakiniku/2024/" },
  ]);
  assert.equal(shouldShowTimeline(entries), true);
  assert.equal(entries.length, 1);
  assert.equal(entries[0].kind, "hyakumeiten");
});

test("deduplicates identical hyakumeiten rows", () => {
  const selection = {
    year: 2025,
    category: "壽司",
    url: "https://award.tabelog.com/hyakumeiten/sushi/2025/",
  };
  const entries = buildTimelineEntries(null, [selection, selection]);
  assert.equal(entries.length, 1);
});
