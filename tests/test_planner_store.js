const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/planner.js");
require("../extension/planner_store.js");

const { createTrip } = globalThis.MeshiLensPlanner;
const { PLANNER_STORAGE_KEY, createPlannerStore } = globalThis.MeshiLensPlannerStore;

function memoryStorage(initial = {}) {
  let values = structuredClone(initial);
  return {
    async get(defaults) {
      return { ...structuredClone(defaults), ...structuredClone(values) };
    },
    async set(next) {
      values = { ...values, ...structuredClone(next) };
    },
    snapshot() {
      return structuredClone(values);
    },
  };
}

test("persists planner updates through the browser storage boundary", async () => {
  const storage = memoryStorage();
  const store = createPlannerStore(storage);

  const saved = await store.update((state) => createTrip(state, {
    id: "trip-tokyo",
    name: "東京五天",
    now: 100,
  }));
  const reloaded = await createPlannerStore(storage).load();

  assert.deepEqual(reloaded, saved);
  assert.deepEqual(storage.snapshot()[PLANNER_STORAGE_KEY], saved);
});

test("discards malformed planner data loaded from browser storage", async () => {
  const storage = memoryStorage({
    [PLANNER_STORAGE_KEY]: {
      version: 1,
      activeTripId: "missing",
      activeGroupId: "bad",
      trips: [{ id: "", name: "", inbox: "not-an-array", groups: null }],
    },
  });

  assert.deepEqual(await createPlannerStore(storage).load(), {
    version: 1,
    activeTripId: null,
    activeGroupId: null,
    trips: [],
  });
});
