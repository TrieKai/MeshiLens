const assert = require("node:assert/strict");
const test = require("node:test");

globalThis.location = { origin: "https://www.google.com" };
require("../extension/list_badges.js");

const {
  MAX_LIST_CARDS,
  cleanListPlaceName,
  listPlaceNameFromHref,
  listCardKey,
  listCoordinatesFromHref,
  badgeText,
  listCardsNeedingLookup,
  listBatchCoversKeys,
  rememberListBadgeResult,
} = globalThis.MeshiLensListBadges;

test("builds a stable list key from Maps href and name", () => {
  assert.equal(
    listCardKey({
      href: "https://www.google.com/maps/place/Example/?entry=ttu",
      name: " Example　Restaurant ",
    }),
    "https://www.google.com/maps/place/Example|example restaurant",
  );
});

test("keeps list keys stable when Maps mutates place data trailers", () => {
  const name = "Noeud.TOKYO";
  const before = listCardKey({
    href: "https://www.google.com/maps/place/Noeud.TOKYO/data=!4m7!3m6!1s0xabc",
    name,
  });
  const after = listCardKey({
    href: "https://www.google.com/maps/place/Noeud.TOKYO/data=!4m7!3m6!1s0xdef!8m2!3d35.6!4d139.7",
    name: "Noeud.TOKYO·開啟過的連結",
  });
  assert.equal(before, "https://www.google.com/maps/place/Noeud.TOKYO|noeud.tokyo");
  assert.equal(after, before);
});

test("strips Maps visited-link suffixes after the last middle dot", () => {
  assert.equal(cleanListPlaceName("Noeud.TOKYO·開啟過的連結"), "Noeud.TOKYO");
  assert.equal(cleanListPlaceName("Noeud.TOKYO·Opened link"), "Noeud.TOKYO");
  assert.equal(cleanListPlaceName("Noeud.TOKYO"), "Noeud.TOKYO");
  assert.equal(cleanListPlaceName("La Biographie···"), "La Biographie···");
  assert.equal(cleanListPlaceName(""), "");
});

test("falls back to the Maps place path when list text is empty", () => {
  assert.equal(
    listPlaceNameFromHref("https://www.google.com/maps/place/Noeud.TOKYO/data=!4m7"),
    "Noeud.TOKYO",
  );
  assert.equal(
    listPlaceNameFromHref("https://www.google.com/maps/place/%E5%AF%BF%E5%8F%B8/"),
    "寿司",
  );
});

test("uses only explicit place coordinates for list cards", () => {
  assert.deepEqual(
    listCoordinatesFromHref("https://www.google.com/maps/place/Example/!3d35.1!4d139.2"),
    { latitude: 35.1, longitude: 139.2 },
  );
  assert.deepEqual(
    listCoordinatesFromHref("https://www.google.com/maps/@35.1,139.2,17z"),
    { latitude: null, longitude: null },
  );
});

test("formats Michelin and green-star badges without an empty state", () => {
  assert.equal(badgeText({ label: "必比登推介", green_star: true }), "必比登推介 · 綠星");
  assert.equal(badgeText(null), "");
  assert.equal(MAX_LIST_CARDS, 10);
});

test("only requests badges that are missing from the session cache", () => {
  const cache = new Map([
    ["a", { label: "一星" }],
    ["b", null],
  ]);
  assert.deepEqual(
    listCardsNeedingLookup([{ key: "a" }, { key: "b" }, { key: "c" }], cache).map((card) => card.key),
    ["c"],
  );
});

test("reuses an in-flight batch that already covers needed keys", () => {
  const pending = new Set(["a", "b"]);
  assert.equal(listBatchCoversKeys(pending, [{ key: "a" }]), true);
  assert.equal(listBatchCoversKeys(pending, [{ key: "a" }, { key: "c" }]), false);
  assert.equal(listBatchCoversKeys(null, [{ key: "a" }]), false);
});

test("remembers matched and no-match list badge results", () => {
  const cache = new Map();
  assert.equal(
    rememberListBadgeResult(cache, {
      key: "hit",
      status: "matched",
      badge: { label: "必比登推介" },
    }),
    true,
  );
  assert.equal(
    rememberListBadgeResult(cache, { key: "miss", status: "no_match" }),
    true,
  );
  assert.equal(
    rememberListBadgeResult(cache, { key: "bad", status: "invalid" }),
    false,
  );
  assert.deepEqual(cache.get("hit"), { label: "必比登推介" });
  assert.equal(cache.get("miss"), null);
  assert.equal(cache.has("bad"), false);
});
