const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/planner_share.js");

const {
  buildSharePayload,
  encodeSharePayload,
  decodeSharePayload,
  buildShareUrl,
  openMapsUrl,
} = globalThis.MeshiLensPlannerShare;

function compressedFragmentForJson(value) {
  const bytes = Buffer.from(JSON.stringify(value), "utf8");
  const dictionary = new Map();
  const codes = [];
  let nextCode = 256;
  let phrase = String.fromCharCode(bytes[0]);
  for (let index = 1; index < bytes.length; index += 1) {
    const character = String.fromCharCode(bytes[index]);
    const combined = phrase + character;
    if (dictionary.has(combined)) {
      phrase = combined;
      continue;
    }
    codes.push(phrase.length === 1 ? phrase.charCodeAt(0) : dictionary.get(phrase));
    if (nextCode <= 65_535) dictionary.set(combined, nextCode++);
    phrase = character;
  }
  codes.push(phrase.length === 1 ? phrase.charCodeAt(0) : dictionary.get(phrase));
  const encoded = Buffer.alloc(3 + codes.length * 2);
  encoded.set([0x4d, 0x4c, 0x01]);
  codes.forEach((code, index) => encoded.writeUInt16BE(code, 3 + index * 2));
  return encoded.toString("base64url");
}

test("builds a compact trip payload containing only primary and backup choices", () => {
  const state = {
    version: 1,
    activeTripId: "trip",
    activeGroupId: "dinner",
    trips: [{
      id: "trip",
      name: "東京五天",
      inbox: [{ id: "unused", name: "未分類店家" }],
      groups: [{
        id: "dinner",
        name: "銀座週六晚餐",
        anchor: { name: "銀座站", latitude: 35.67, longitude: 139.76 },
        date: "2026-10-17",
        meal: "dinner",
        primaryId: "a",
        backupId: "b",
        restaurants: [
          {
            id: "a",
            name: "甲壽司",
            mapsUrl: "https://www.google.com/maps/place/A",
            address: "東京都中央區",
            rating: 3.9,
            michelinLabel: "一星",
            latitude: 35.6717,
            longitude: 139.7649,
            station: "銀座站",
          },
          {
            id: "b",
            name: "乙壽司",
            mapsUrl: "https://www.google.com/maps/place/B",
            address: "東京都中央區",
            rating: 3.7,
            michelinLabel: "",
            station: "東銀座站",
          },
          { id: "c", name: "未選店家", mapsUrl: "https://www.google.com/maps/place/C" },
        ],
      }],
    }],
  };

  assert.deepEqual(buildSharePayload(state, "trip"), {
    v: 1,
    title: "東京五天",
    groups: [{
      name: "銀座週六晚餐",
      anchor: "銀座站",
      date: "2026-10-17",
      meal: "dinner",
      primary: {
        name: "甲壽司",
        mapsUrl: "https://www.google.com/maps/place/A",
        rating: 3.9,
        michelinLabel: "一星",
        latitude: 35.6717,
        longitude: 139.7649,
      },
      backup: {
        name: "乙壽司",
        mapsUrl: "https://www.google.com/maps/place/B",
        rating: 3.7,
        michelinLabel: "",
        latitude: null,
        longitude: null,
      },
    }],
  });
});

test("encodes and decodes a sanitized share payload in the URL fragment", () => {
  const encoded = encodeSharePayload({
    v: 1,
    title: "東京五天",
    groups: [{
      name: "銀座晚餐",
      anchor: "銀座站",
      date: "2026-10-17",
      meal: "dinner",
      primary: {
        name: "甲壽司",
        mapsUrl: "javascript:alert(1)",
        address: "東京都中央區",
        rating: 3.9,
        michelinLabel: "一星",
        station: "銀座站",
        ignored: "不應分享",
      },
      backup: null,
    }],
    ignored: "不應分享",
  });

  assert.match(encoded, /^[A-Za-z0-9_-]+$/);
  assert.deepEqual(decodeSharePayload(`#${encoded}`), {
    v: 1,
    title: "東京五天",
    groups: [{
      name: "銀座晚餐",
      anchor: "銀座站",
      date: "2026-10-17",
      meal: "dinner",
      primary: {
        name: "甲壽司",
        mapsUrl: "",
        rating: 3.9,
        michelinLabel: "一星",
        latitude: null,
        longitude: null,
      },
      backup: null,
    }],
  });
  assert.equal(decodeSharePayload("#not-json"), null);
});

test("builds a share URL whose trip data stays after the fragment marker", () => {
  const payload = {
    v: 1,
    title: "東京",
    groups: [{
      name: "晚餐",
      anchor: "東京站",
      date: "",
      meal: "dinner",
      primary: {
        name: "甲店",
        mapsUrl: "https://www.google.com/maps/place/A",
        address: "",
        rating: 3.8,
        michelinLabel: "",
        station: "",
      },
      backup: null,
    }],
  };
  const encoded = encodeSharePayload(payload);

  assert.equal(
    buildShareUrl(payload, "https://example.com/share.html#old"),
    `https://example.com/share.html#${encoded}`,
  );
});

test("rejects a small fragment that expands beyond the share payload limit", () => {
  const encoded = compressedFragmentForJson({
    v: 1,
    title: "東京",
    groups: [{
      name: "晚餐",
      primary: { name: "甲店", mapsUrl: "https://www.google.com/maps/place/A" },
    }],
    padding: "A".repeat(200_000),
  });

  assert.equal(encoded.length < 20_000, true);
  assert.equal(decodeSharePayload(encoded), null);
});

test("keeps a full twelve-meal trip within local QR byte capacity", () => {
  const payload = {
    v: 1,
    title: "東京十二餐美食行程",
    groups: Array.from({ length: 12 }, (_, index) => ({
      name: `第 ${index + 1} 餐銀座晚餐`,
      anchor: "銀座站",
      date: "2026-10-17",
      meal: "dinner",
      primary: {
        name: "銀座 鮨青木",
        mapsUrl: "https://www.google.com/maps/place/Ginza+Aoki",
        address: "東京都中央區銀座六丁目",
        rating: 3.9,
        michelinLabel: "一星",
        station: "銀座站",
      },
      backup: {
        name: "銀座 久兵衛",
        mapsUrl: "https://www.google.com/maps/place/Ginza+Kyubey",
        address: "東京都中央區銀座八丁目",
        rating: 3.74,
        michelinLabel: "",
        station: "新橋站",
      },
    })),
  };

  assert.equal(buildShareUrl(payload).length <= 2_300, true);
});

test("opens truncated Maps place slugs by restaurant name instead of the English slug", () => {
  const fragment = [
    "TUwBAFsAMQAsACIA5gCIAJEA5wCaAIQA6ACMAKgA5QCfAI4A5wC-AI4A6QCjAJ8A6AChAIwA5wCo",
    "AIsAIgAsAFsAWwAiAOcArACsAOQAuACAAOUApACpAOYAmQCaAOkApACQARwAIgEwATIBHQAiAOMAgQ",
    "CTATYAoADjAIIAjwE7AIoBNgCoATsBOACBAIsBNgCkATYAggE2AKIBNgC-ACABNgCyATYAnwE2AKEB",
    "NgCqATYAiwDmAJwArADlALoAlwEwAGgAdAB0AHAAcwA6AC8ALwB3AWgALgBnAG8AbwBnAGwAZQAuAG",
    "MAbwBtAC8AbQBhAWMALwBwAGwAYQBjAGUALwBTAHAAZQBjAGkAYQBsAHQAeQArAFQAbwBuAGsAYQB0",
    "AHMAdQArAEEASgBJAE0AQQEcADMALgA0AQIAIgBdATQBNgCvAUwBNgCQAT4A5QCxARsBAgFgAWIBZA",
    "FmAWgAdwFqAWwBbgFwAXIBdAF2AXgBegF8AX4ASABhAXYAZwB1AHIAaQB5AGEBmAAuADYAMgGcAF0B",
    "yQBd",
  ].join("");
  const payload = decodeSharePayload(fragment);
  const primary = payload.groups[0].primary;
  const href = openMapsUrl(primary);

  assert.equal(primary.mapsUrl, "https://www.google.com/maps/place/Specialty+Tonkatsu+AJIMA");
  assert.match(href, /^https:\/\/www\.google\.com\/maps\/search\/\?api=1&query=/);
  assert.equal(
    decodeURIComponent(new URL(href).searchParams.get("query")),
    "こだわりとんかつあぢま ひたちなか本店",
  );
  assert.equal(
    openMapsUrl({
      name: "こだわりとんかつあぢま ひたちなか本店",
      mapsUrl: "https://www.google.com/maps/place/Specialty+Tonkatsu+AJIMA/data=!3d36.4!4d140.5",
    }),
    "https://www.google.com/maps/place/Specialty+Tonkatsu+AJIMA/data=!3d36.4!4d140.5",
  );
  assert.equal(
    decodeURIComponent(new URL(openMapsUrl({
      name: "はまぐり屋",
      latitude: 36.341,
      longitude: 140.446,
    })).searchParams.get("query")),
    "はまぐり屋 36.341,140.446",
  );
});
