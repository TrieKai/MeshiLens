const assert = require("node:assert/strict");
const test = require("node:test");

globalThis.location = { origin: "https://www.google.com" };
require("../extension/list_badges.js");

const {
  MAX_LIST_CARDS,
  listCardKey,
  listCoordinatesFromHref,
  badgeText,
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
