const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/japan.js");

const { classifyJapanPlace } = globalThis.MeshiLensJapan;

test("classifies explicit Japanese signals as japan", () => {
  assert.equal(classifyJapanPlace({ phone: "+81 3-1234-5678" }), "japan");
  assert.equal(classifyJapanPlace({ address: "〒150-0001 東京都渋谷区" }), "japan");
  assert.equal(classifyJapanPlace({ address: "Osaka, Japan" }), "japan");
  assert.equal(
    classifyJapanPlace({ tabelog_url: "https://tabelog.com/tokyo/A1303/A130301/13000001/" }),
    "japan",
  );
});

test("uses only exact place coordinates for a negative decision", () => {
  assert.equal(
    classifyJapanPlace({ latitude: 40.7128, longitude: -74.006, coordinates_source: "viewport" }),
    "unknown",
  );
  assert.equal(
    classifyJapanPlace({ latitude: 40.7128, longitude: -74.006, coordinates_source: "place" }),
    "not_japan",
  );
});

test("coordinates inside Japan do not prove a place is Japanese", () => {
  assert.equal(
    classifyJapanPlace({ latitude: 35.6762, longitude: 139.6503, coordinates_source: "place" }),
    "unknown",
  );
  assert.equal(classifyJapanPlace({ name: "訊號不足" }), "unknown");
});
