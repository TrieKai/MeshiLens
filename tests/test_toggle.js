const assert = require("node:assert/strict");
const test = require("node:test");

test("toggle persists state and skips health checks while disabled", async () => {
  const listeners = {};
  const elements = Object.fromEntries(
    ["api-url", "status", "enabled", "enabled-state", "save"].map((id) => [
      id,
      {
        checked: false,
        className: "",
        textContent: "",
        value: id === "api-url" ? "https://meshilens.vercel.app/api" : "",
        addEventListener(type, listener) {
          listeners[`${id}:${type}`] = listener;
        },
      },
    ]),
  );
  const saved = [];
  let healthChecks = 0;
  global.document = { getElementById: (id) => elements[id] };
  global.chrome = {
    runtime: {
      async sendMessage() {
        healthChecks += 1;
        return { ok: true };
      },
    },
    storage: {
      local: {
        async get(defaults) {
          return { ...defaults, enabled: false };
        },
        async set(value) {
          saved.push(value);
        },
      },
    },
  };

  require("../extension/popup.js");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(elements.enabled.checked, false);
  assert.equal(elements.status.className, "status paused");
  assert.equal(healthChecks, 0);

  elements.enabled.checked = true;
  await listeners["enabled:change"]();
  assert.deepEqual(saved.at(-1), { enabled: true });
  assert.equal(elements["enabled-state"].textContent, "已啟用");
  assert.equal(healthChecks, 1);
});
