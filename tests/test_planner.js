const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/planner.js");

const {
  createPlannerState,
  createTrip,
  createGroup,
  restaurantFromMatch,
  addRestaurant,
  moveRestaurant,
  rankGroup,
  chooseRestaurant,
  updateGroup,
  removeRestaurant,
  deleteGroup,
  setActiveTarget,
  renameTrip,
  deleteTrip,
} = globalThis.MeshiLensPlanner;

test("creates a named trip with an active unclassified inbox", () => {
  const state = createTrip(createPlannerState(), {
    id: "trip-tokyo",
    name: "東京五天",
    now: 1_700_000_000_000,
  });

  assert.deepEqual(state, {
    version: 1,
    activeTripId: "trip-tokyo",
    activeGroupId: null,
    trips: [
      {
        id: "trip-tokyo",
        name: "東京五天",
        createdAt: 1_700_000_000_000,
        updatedAt: 1_700_000_000_000,
        inbox: [],
        groups: [],
      },
    ],
  });
});

test("adds a matched restaurant to the active meal and refreshes duplicates", () => {
  const withTrip = createTrip(createPlannerState(), { id: "trip", name: "東京", now: 10 });
  const withGroup = createGroup(withTrip, "trip", { id: "meal", name: "晚餐", now: 20 });
  const restaurant = restaurantFromMatch({
    place: {
      name: "銀座 鮨青木",
      address: "東京都中央區銀座",
      maps_url: "https://www.google.com/maps/place/Ginza+Aoki/data=!3d35.1!4d139.2",
      latitude: 35.1,
      longitude: 139.2,
    },
    candidate: {
      name: "銀座 鮨青木",
      url: "https://tabelog.com/tokyo/A1301/A130101/12345/",
      rating: 3.82,
      review_count: 640,
      genres: ["壽司"],
      dinner_price: "￥20,000～￥29,999",
      station: "銀座站",
      confidence: "high",
      reservation_url: "https://example.com/reserve",
      hyakumeiten: [{ year: 2025 }],
    },
    michelin: { distinction_label: "一星", green_star: false },
  });

  const first = addRestaurant(withGroup, "trip", "meal", restaurant, { now: 30 });
  const refreshed = addRestaurant(first, "trip", "meal", { ...restaurant, rating: 3.85 }, { now: 40 });
  const saved = refreshed.trips[0].groups[0].restaurants;

  assert.equal(saved.length, 1);
  assert.deepEqual(saved[0], { ...restaurant, rating: 3.85 });
  assert.equal(saved[0].id, "https://www.google.com/maps/place/Ginza+Aoki");
  assert.equal(refreshed.trips[0].updatedAt, 40);
});

test("keeps absent restaurant facts unknown instead of turning them into zero", () => {
  const restaurant = restaurantFromMatch({
    place: {
      name: "資料未完整的店",
      maps_url: "https://www.google.com/maps/place/Unknown",
      latitude: null,
      longitude: null,
    },
    candidate: {
      name: "資料未完整的店",
      rating: null,
      review_count: null,
      latitude: null,
      longitude: null,
    },
  });

  assert.equal(restaurant.rating, null);
  assert.equal(restaurant.reviewCount, null);
  assert.equal(restaurant.latitude, null);
  assert.equal(restaurant.longitude, null);
});

test("limits each meal comparison to five restaurants", () => {
  let state = createTrip(createPlannerState(), { id: "trip", name: "東京", now: 1 });
  state = createGroup(state, "trip", { id: "meal", name: "晚餐", now: 2 });
  for (let index = 1; index <= 6; index += 1) {
    state = addRestaurant(state, "trip", "meal", {
      id: `restaurant-${index}`,
      name: `店家 ${index}`,
      matchStatus: "ready",
    }, { now: index + 2 });
  }

  assert.deepEqual(
    state.trips[0].groups[0].restaurants.map((item) => item.id),
    ["restaurant-1", "restaurant-2", "restaurant-3", "restaurant-4", "restaurant-5"],
  );
});

test("moves a restaurant from the inbox into a meal comparison", () => {
  let state = createTrip(createPlannerState(), { id: "trip", name: "東京", now: 1 });
  state = createGroup(state, "trip", { id: "meal", name: "午餐", now: 2 });
  state = addRestaurant(state, "trip", null, {
    id: "sushi",
    name: "壽司店",
    matchStatus: "ready",
  }, { now: 3 });
  state = moveRestaurant(state, "trip", "sushi", null, "meal", { now: 4 });

  assert.deepEqual(state.trips[0].inbox, []);
  assert.deepEqual(state.trips[0].groups[0].restaurants.map((item) => item.id), ["sushi"]);
  assert.equal(state.activeGroupId, "meal");
});

test("ranks destination dining by quality signals and explains the winner", () => {
  const group = {
    intent: "destination",
    meal: "dinner",
    anchor: { name: "東京站", latitude: 35.6812, longitude: 139.7671 },
    restaurants: [
      {
        id: "a",
        name: "名店壽司",
        rating: 3.9,
        reviewCount: 700,
        confidence: "high",
        michelinLabel: "一星",
        hyakumeitenYears: [2023, 2025],
        latitude: 35.66,
        longitude: 139.72,
        dinnerPrice: "￥20,000～￥29,999",
      },
      {
        id: "b",
        name: "車站食堂",
        rating: 3.55,
        reviewCount: 120,
        confidence: "high",
        michelinLabel: "",
        hyakumeitenYears: [],
        latitude: 35.6813,
        longitude: 139.7672,
        dinnerPrice: "￥1,000～￥1,999",
      },
    ],
  };

  const ranked = rankGroup(group);

  assert.deepEqual(ranked.map((item) => item.restaurant.id), ["a", "b"]);
  assert.deepEqual(ranked[0].advantages, [
    "Tabelog 評分最高（3.90）",
    "Michelin 一星",
    "百名店入選 2 年",
  ]);
});

test("ranks nearby dining from the meal anchor without hiding quality tradeoffs", () => {
  const ranked = rankGroup({
    intent: "nearby",
    meal: "lunch",
    anchor: { name: "集合點", latitude: 35, longitude: 139 },
    restaurants: [
      {
        id: "far",
        name: "遠方名店",
        rating: 4.05,
        reviewCount: 800,
        confidence: "high",
        latitude: 35.08,
        longitude: 139.08,
        lunchPrice: "￥10,000～￥14,999",
      },
      {
        id: "near",
        name: "集合點食堂",
        rating: 3.5,
        reviewCount: 100,
        confidence: "high",
        latitude: 35,
        longitude: 139,
        lunchPrice: "￥1,000～￥1,999",
      },
    ],
  });

  assert.deepEqual(ranked.map((item) => item.restaurant.id), ["near", "far"]);
  assert.equal(ranked[0].distanceKm, 0);
  assert.equal(ranked[0].advantages[0], "就在集合點附近");
  assert.equal(ranked[1].advantages.includes("Tabelog 評分最高（4.05）"), true);
});

test("ranks budget dining by the selected meal price and flags the budget ceiling", () => {
  const ranked = rankGroup({
    intent: "budget",
    meal: "dinner",
    budgetMax: 3_000,
    restaurants: [
      {
        id: "expensive",
        name: "高級料理",
        rating: 4.1,
        reviewCount: 900,
        confidence: "high",
        dinnerPrice: "￥20,000～￥29,999",
      },
      {
        id: "budget",
        name: "平價定食",
        rating: 3.55,
        reviewCount: 180,
        confidence: "high",
        dinnerPrice: "￥1,000～￥1,999",
      },
    ],
  });

  assert.deepEqual(ranked.map((item) => item.restaurant.id), ["budget", "expensive"]);
  assert.equal(ranked[0].priceYen, 1_000);
  assert.equal(ranked[0].advantages[0], "晚餐預算較輕（¥1,000 起）");
  assert.equal(ranked[1].cautions.includes("超過設定預算 ¥3,000"), true);
});

test("records distinct primary and backup choices for a meal", () => {
  let state = createTrip(createPlannerState(), { id: "trip", name: "東京", now: 1 });
  state = createGroup(state, "trip", { id: "meal", name: "晚餐", now: 2 });
  state = addRestaurant(state, "trip", "meal", { id: "a", name: "甲店" }, { now: 3 });
  state = addRestaurant(state, "trip", "meal", { id: "b", name: "乙店" }, { now: 4 });
  state = chooseRestaurant(state, "trip", "meal", "a", "primary", { now: 5 });
  state = chooseRestaurant(state, "trip", "meal", "b", "backup", { now: 6 });

  assert.equal(state.trips[0].groups[0].primaryId, "a");
  assert.equal(state.trips[0].groups[0].backupId, "b");

  const sameChoice = chooseRestaurant(state, "trip", "meal", "a", "backup", { now: 7 });
  assert.equal(sameChoice.trips[0].groups[0].primaryId, null);
  assert.equal(sameChoice.trips[0].groups[0].backupId, "a");
});

test("updates the active meal context used by comparison", () => {
  let state = createTrip(createPlannerState(), { id: "trip", name: "東京", now: 1 });
  state = createGroup(state, "trip", { id: "meal", name: "晚餐", now: 2 });
  state = updateGroup(state, "trip", "meal", {
    name: "銀座週六晚餐",
    anchor: { name: "銀座站", latitude: 35.6717, longitude: 139.7649 },
    date: "2026-10-17",
    meal: "dinner",
    intent: "budget",
    budgetMax: 8_000,
  }, { now: 3 });

  assert.deepEqual(
    {
      name: state.trips[0].groups[0].name,
      anchor: state.trips[0].groups[0].anchor,
      date: state.trips[0].groups[0].date,
      meal: state.trips[0].groups[0].meal,
      intent: state.trips[0].groups[0].intent,
      budgetMax: state.trips[0].groups[0].budgetMax,
    },
    {
      name: "銀座週六晚餐",
      anchor: { name: "銀座站", latitude: 35.6717, longitude: 139.7649 },
      date: "2026-10-17",
      meal: "dinner",
      intent: "budget",
      budgetMax: 8_000,
    },
  );
});

test("removes a restaurant and clears its meal choice", () => {
  let state = createTrip(createPlannerState(), { id: "trip", name: "東京", now: 1 });
  state = createGroup(state, "trip", { id: "meal", name: "晚餐", now: 2 });
  state = addRestaurant(state, "trip", "meal", { id: "a", name: "甲店" }, { now: 3 });
  state = addRestaurant(state, "trip", "meal", { id: "b", name: "乙店" }, { now: 4 });
  state = chooseRestaurant(state, "trip", "meal", "a", "primary", { now: 5 });
  state = removeRestaurant(state, "trip", "meal", "a", { now: 6 });

  assert.deepEqual(state.trips[0].groups[0].restaurants.map((item) => item.id), ["b"]);
  assert.equal(state.trips[0].groups[0].primaryId, null);
});

test("deleting a meal returns its candidates to the trip inbox", () => {
  let state = createTrip(createPlannerState(), { id: "trip", name: "東京", now: 1 });
  state = createGroup(state, "trip", { id: "meal", name: "晚餐", now: 2 });
  state = addRestaurant(state, "trip", "meal", { id: "a", name: "甲店" }, { now: 3 });
  state = addRestaurant(state, "trip", "meal", { id: "b", name: "乙店" }, { now: 4 });
  state = deleteGroup(state, "trip", "meal", { now: 5 });

  assert.deepEqual(state.trips[0].groups, []);
  assert.deepEqual(state.trips[0].inbox.map((item) => item.id), ["a", "b"]);
  assert.equal(state.activeGroupId, null);
});

test("renames, switches, and deletes local trips", () => {
  let state = createTrip(createPlannerState(), { id: "tokyo", name: "東京", now: 1 });
  state = createTrip(state, { id: "osaka", name: "大阪", now: 2 });
  state = createGroup(state, "tokyo", { id: "lunch", name: "午餐", now: 3 });
  state = setActiveTarget(state, "tokyo", "lunch");
  state = renameTrip(state, "tokyo", "東京五天", { now: 4 });

  assert.equal(state.activeTripId, "tokyo");
  assert.equal(state.activeGroupId, "lunch");
  assert.equal(state.trips[0].name, "東京五天");

  state = deleteTrip(state, "tokyo");
  assert.deepEqual(state.trips.map((trip) => trip.id), ["osaka"]);
  assert.equal(state.activeTripId, "osaka");
  assert.equal(state.activeGroupId, null);
});

test("creates and activates a meal comparison group", () => {
  const tripState = createTrip(createPlannerState(), {
    id: "trip-tokyo",
    name: "東京五天",
    now: 100,
  });
  const state = createGroup(tripState, "trip-tokyo", {
    id: "meal-ginza",
    name: "銀座週六晚餐",
    anchor: { name: "銀座站", latitude: 35.6717, longitude: 139.7649 },
    date: "2026-10-17",
    meal: "dinner",
    intent: "destination",
    budgetMax: 20_000,
    now: 200,
  });

  assert.equal(state.activeGroupId, "meal-ginza");
  assert.deepEqual(state.trips[0].groups[0], {
    id: "meal-ginza",
    name: "銀座週六晚餐",
    anchor: { name: "銀座站", latitude: 35.6717, longitude: 139.7649 },
    date: "2026-10-17",
    meal: "dinner",
    intent: "destination",
    budgetMax: 20_000,
    restaurants: [],
    primaryId: null,
    backupId: null,
    createdAt: 200,
    updatedAt: 200,
  });
});
