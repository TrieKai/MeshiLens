const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/maps.js");

const { coordinatesFromMapsUrl } = globalThis.MeshiLensMaps;

test("uses the last place coordinates when a Maps URL contains navigation history", () => {
  const url = [
    "https://www.google.com/maps/place/TsuruTonTan/",
    "!8m2!3d36.1645926!4d140.2474045",
    "!8m2!3d35.6584466!4d139.7021636",
  ].join("");
  assert.deepEqual(
    coordinatesFromMapsUrl(url),
    { latitude: 35.6584466, longitude: 139.7021636, coordinates_source: "place" },
  );
});

test("marks viewport coordinates so they cannot be treated as place coordinates", () => {
  assert.deepEqual(
    coordinatesFromMapsUrl("https://www.google.com/maps/@35.1,139.2,17z"),
    { latitude: 35.1, longitude: 139.2, coordinates_source: "viewport" },
  );
});
