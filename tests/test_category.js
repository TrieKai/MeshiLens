const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/category.js");

const { isFoodCategory } = globalThis.MeshiLensCategory;

test("accepts dining categories across supported Maps languages", () => {
  for (const category of [
    "日式咖哩餐廳",
    "麵包店",
    "うなぎ料理店",
    "Japanese restaurant",
    "Coffee shop",
    "카페",
  ]) {
    assert.equal(isFoodCategory(category), true, category);
  }
});

test("rejects non-dining and missing categories", () => {
  for (const category of [
    "觀景台",
    "飯店",
    "便利商店",
    "咖啡機專賣店",
    "Barber shop",
    "美術館",
    "",
    null,
  ]) {
    assert.equal(isFoodCategory(category), false, String(category));
  }
});
