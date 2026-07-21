const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/runtime.js");

const {
  isExtensionContextValid,
  isExtensionContextInvalidatedError,
  safeRuntimeSendMessage,
  softRuntimeSendMessage,
  safeStorageLocalGet,
  safeStorageLocalSet,
} = globalThis.MeshiLensRuntime;

test("detects valid and invalid extension contexts", () => {
  assert.equal(isExtensionContextValid({ runtime: { id: "abc" } }), true);
  assert.equal(isExtensionContextValid({ runtime: {} }), false);
  assert.equal(isExtensionContextValid({}), false);
  assert.equal(isExtensionContextValid(null), false);
  assert.equal(
    isExtensionContextValid({
      get runtime() {
        throw new Error("Extension context invalidated.");
      },
    }),
    false,
  );
});

test("recognizes extension context invalidated errors", () => {
  assert.equal(
    isExtensionContextInvalidatedError(new Error("Extension context invalidated.")),
    true,
  );
  assert.equal(
    isExtensionContextInvalidatedError({ message: "Uncaught Error: Extension context invalidated." }),
    true,
  );
  assert.equal(isExtensionContextInvalidatedError(new Error("network failed")), false);
  assert.equal(isExtensionContextInvalidatedError(null), false);
});

test("safeRuntimeSendMessage rejects sync invalidated throws without uncaught", async () => {
  const chromeApi = {
    runtime: {
      id: "abc",
      sendMessage() {
        throw new Error("Extension context invalidated.");
      },
    },
  };
  await assert.rejects(
    () => safeRuntimeSendMessage({ type: "PING" }, chromeApi),
    (error) => error.invalidated === true && /invalidated/i.test(error.message),
  );
});

test("safeRuntimeSendMessage skips when runtime id is already gone", async () => {
  await assert.rejects(
    () => safeRuntimeSendMessage({ type: "PING" }, { runtime: {} }),
    (error) => error.invalidated === true,
  );
});

test("safeRuntimeSendMessage forwards successful responses", async () => {
  const chromeApi = {
    runtime: {
      id: "abc",
      async sendMessage(message) {
        return { ok: true, echo: message.type };
      },
    },
  };
  assert.deepEqual(await safeRuntimeSendMessage({ type: "HEALTH" }, chromeApi), {
    ok: true,
    echo: "HEALTH",
  });
});

test("softRuntimeSendMessage swallows invalidated errors", async () => {
  const syncThrow = {
    runtime: {
      id: "abc",
      sendMessage() {
        throw new Error("Extension context invalidated.");
      },
    },
  };
  assert.equal(await softRuntimeSendMessage({ type: "CANCEL" }, syncThrow), false);
  assert.equal(await softRuntimeSendMessage({ type: "CANCEL" }, { runtime: {} }), false);

  const ok = {
    runtime: {
      id: "abc",
      async sendMessage() {
        return { ok: true };
      },
    },
  };
  assert.equal(await softRuntimeSendMessage({ type: "CANCEL" }, ok), true);
});

test("safe storage helpers mark invalidated errors", async () => {
  await assert.rejects(
    () => safeStorageLocalGet({ enabled: true }, { runtime: {} }),
    (error) => error.invalidated === true,
  );
  await assert.rejects(
    () => safeStorageLocalSet({ enabled: false }, { runtime: {} }),
    (error) => error.invalidated === true,
  );

  const chromeApi = {
    runtime: { id: "abc" },
    storage: {
      local: {
        async get(defaults) {
          return { ...defaults, enabled: false };
        },
        async set() {},
        get throws() {
          throw new Error("Extension context invalidated.");
        },
      },
    },
  };
  assert.deepEqual(await safeStorageLocalGet({ enabled: true }, chromeApi), {
    enabled: false,
  });
  await safeStorageLocalSet({ enabled: true }, chromeApi);

  const throwingGet = {
    runtime: { id: "abc" },
    storage: {
      local: {
        get() {
          throw new Error("Extension context invalidated.");
        },
        set() {
          throw new Error("Extension context invalidated.");
        },
      },
    },
  };
  await assert.rejects(
    () => safeStorageLocalGet({ enabled: true }, throwingGet),
    (error) => error.invalidated === true,
  );
  await assert.rejects(
    () => safeStorageLocalSet({ enabled: false }, throwingGet),
    (error) => error.invalidated === true,
  );
});
