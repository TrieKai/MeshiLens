const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/category.js");

const { foodSignalsFromLabels, isFoodCategory, isFoodPlace } = globalThis.MeshiLensCategory;

test("accepts dining categories across supported Maps languages", () => {
  for (const category of [
    "日式咖哩餐廳",
    "咖啡店",
    "麵包店",
    "拉麵店",
    "餅店",
    "三明治店",
    "うなぎ料理店",
    "Japanese restaurant",
    "Coffee shop",
    "카페",
  ]) {
    assert.equal(isFoodCategory(category), true, category);
  }
});

test("accepts unknown Maps categories when strong dining signals are present", () => {
  assert.equal(isFoodPlace({ category: "新型態商家", hasMenu: true }), true);
  assert.equal(isFoodPlace({ category: "新型態商家", hasPerPersonPrice: true }), true);
  assert.equal(isFoodPlace({ category: "新型態商家", offersDineIn: true }), true);
});

test("recognizes the dining labels observed on Maps place pages", () => {
  assert.deepEqual(
    foodSignalsFromLabels([
      "菜單",
      "價格範圍，每人 ¥1,000-2,000，86 人回報",
      "提供內用",
    ]),
    { hasMenu: true, hasPerPersonPrice: true, offersDineIn: true },
  );
  assert.equal(foodSignalsFromLabels(["禁止內用"]).offersDineIn, false);
});

test("still rejects non-dining places without dining signals", () => {
  assert.equal(isFoodPlace({ category: "觀景台" }), false);
  assert.equal(isFoodPlace({ category: "便利商店" }), false);
  assert.equal(isFoodPlace(), false);
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
