const assert = require("node:assert/strict");
const test = require("node:test");

test("toggle persists state and skips health checks while disabled", async () => {
  const listeners = {};
  const elements = Object.fromEntries(
    ["api-url", "status", "enabled", "enabled-state", "save", "version"].map((id) => [
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
  const themeButtons = ["#bf3a2b", "#a65314", "#2f7658", "#35649a", "#71549a"].map(
    (color) => ({
      dataset: { themeColor: color },
      pressed: "false",
      addEventListener(type, listener) {
        listeners[`theme:${color}:${type}`] = listener;
      },
      setAttribute(name, value) {
        if (name === "aria-pressed") this.pressed = value;
      },
    }),
  );
  const rootStyles = {};
  const saved = [];
  let healthChecks = 0;
  global.document = {
    documentElement: {
      style: {
        setProperty(name, value) {
          rootStyles[name] = value;
        },
      },
    },
    getElementById: (id) => elements[id],
    querySelectorAll: () => themeButtons,
  };
  global.chrome = {
    runtime: {
      getManifest() {
        return { version: "0.4.5" };
      },
      async sendMessage() {
        healthChecks += 1;
        return { ok: true };
      },
    },
    storage: {
      local: {
        async get(defaults) {
          return { ...defaults, enabled: false, themeColor: "#35649a" };
        },
        async set(value) {
          saved.push(value);
        },
      },
    },
  };

  require("../extension/settings.js");
  require("../extension/popup.js");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(elements.version.textContent, "v0.4.5");
  assert.equal(elements.enabled.checked, false);
  assert.equal(elements.status.className, "status paused");
  assert.equal(healthChecks, 0);
  assert.equal(rootStyles["--ml-accent"], "#35649a");
  assert.equal(themeButtons[3].pressed, "true");

  await listeners["theme:#71549a:click"]();
  assert.deepEqual(saved.at(-1), { themeColor: "#71549a" });
  assert.equal(rootStyles["--ml-accent"], "#71549a");

  elements.enabled.checked = true;
  await listeners["enabled:change"]();
  assert.deepEqual(saved.at(-1), { enabled: true });
  assert.equal(elements["enabled-state"].textContent, "已啟用");
  assert.equal(healthChecks, 1);
});
