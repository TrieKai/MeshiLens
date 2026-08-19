(() => {
  const PLANNER_STORAGE_KEY = "plannerState";

  function createPlannerStore(storageArea = globalThis.chrome?.storage?.local) {
    if (!storageArea?.get || !storageArea?.set) {
      throw new Error("找不到瀏覽器本機儲存空間");
    }
    let queue = Promise.resolve();

    async function load() {
      const empty = globalThis.MeshiLensPlanner.createPlannerState();
      const result = await storageArea.get({ [PLANNER_STORAGE_KEY]: empty });
      return globalThis.MeshiLensPlanner.sanitizePlannerState(result?.[PLANNER_STORAGE_KEY]);
    }

    async function save(state) {
      const safeState = globalThis.MeshiLensPlanner.sanitizePlannerState(state);
      await storageArea.set({ [PLANNER_STORAGE_KEY]: safeState });
      return safeState;
    }

    function update(transform) {
      const operation = queue.then(async () => {
        const current = await load();
        const next = transform(current) || current;
        return save(next);
      });
      queue = operation.catch(() => {});
      return operation;
    }

    return { load, save, update };
  }

  globalThis.MeshiLensPlannerStore = {
    PLANNER_STORAGE_KEY,
    createPlannerStore,
  };
})();
