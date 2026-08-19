const plannerRoot = document.getElementById("planner-root");
const plannerStatus = document.getElementById("planner-status");
const plannerVersion = document.getElementById("planner-version");
const Planner = globalThis.MeshiLensPlanner;
const { PLANNER_STORAGE_KEY, createPlannerStore } = globalThis.MeshiLensPlannerStore;
const { buildSharePayload, buildShareUrl } = globalThis.MeshiLensPlannerShare;
const plannerStore = createPlannerStore();
let plannerState = Planner.createPlannerState();
let statusTimer = null;

plannerVersion.textContent = `v${chrome.runtime.getManifest().version}`;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function plannerButton(label, className = "") {
  const button = element("button", `planner-button ${className}`.trim(), label);
  button.type = "button";
  return button;
}

function setStatus(message, kind = "", sticky = false) {
  clearTimeout(statusTimer);
  plannerStatus.textContent = message || "";
  plannerStatus.className = `planner-status${message ? " is-visible" : ""}${kind ? ` is-${kind}` : ""}`;
  if (message && !sticky) {
    statusTimer = setTimeout(() => setStatus(""), 3200);
  }
}

function plannerId(prefix) {
  const value = globalThis.crypto?.randomUUID?.()
    || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `${prefix}-${value}`;
}

function activeTrip() {
  return plannerState.trips.find((trip) => trip.id === plannerState.activeTripId) || null;
}

function activeGroup(trip = activeTrip()) {
  return trip?.groups.find((group) => group.id === plannerState.activeGroupId) || null;
}

async function mutate(transform, message = "已儲存在這台電腦") {
  try {
    plannerState = await plannerStore.update(transform);
    render();
    if (message) setStatus(message, "success");
    return plannerState;
  } catch (error) {
    setStatus(error?.message || "暫時無法儲存行程", "error", true);
    return plannerState;
  }
}

function panel(title, note = "") {
  const section = element("section", "planner-panel");
  const heading = element("div", "planner-section-title");
  heading.append(element("h2", "", title));
  if (note) heading.append(element("span", "", note));
  section.append(heading);
  return section;
}

function emptyTripsView() {
  const section = panel("建立第一個行程");
  section.append(element(
    "p",
    "planner-empty",
    "行程與候選店只會保存在這台電腦。先命名行程，再從 Google Maps 加入店家。",
  ));
  const form = element("form", "planner-form");
  const input = document.createElement("input");
  input.name = "tripName";
  input.maxLength = 120;
  input.placeholder = "例如：東京五天";
  input.required = true;
  const submit = plannerButton("建立行程");
  submit.type = "submit";
  form.append(input, submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = input.value.trim();
    if (!name) return;
    void mutate((state) => Planner.createTrip(state, {
      id: plannerId("trip"),
      name,
    }), "行程已建立");
  });
  section.append(form);
  return section;
}

function tripControls(trip) {
  const section = panel("目前行程", `${plannerState.trips.length} 個行程`);
  const row = element("div", "planner-trip-row");
  const select = document.createElement("select");
  select.setAttribute("aria-label", "選擇行程");
  for (const item of plannerState.trips) {
    const option = element("option", "", item.name);
    option.value = item.id;
    option.selected = item.id === trip.id;
    select.append(option);
  }
  select.addEventListener("change", () => {
    void mutate((state) => Planner.setActiveTarget(state, select.value, null), "");
  });
  const add = plannerButton("新增", "is-secondary");
  add.title = "新增行程";
  add.addEventListener("click", () => {
    const name = window.prompt("新行程名稱", "日本美食行程")?.trim();
    if (!name) return;
    void mutate((state) => Planner.createTrip(state, { id: plannerId("trip"), name }), "行程已建立");
  });
  const rename = plannerButton("改名", "is-quiet");
  rename.title = "重新命名行程";
  rename.addEventListener("click", () => {
    const name = window.prompt("行程名稱", trip.name)?.trim();
    if (!name || name === trip.name) return;
    void mutate((state) => Planner.renameTrip(state, trip.id, name), "行程名稱已更新");
  });
  row.append(select, add, rename);
  section.append(row);
  if (plannerState.trips.length > 1 || (!trip.inbox.length && !trip.groups.length)) {
    const remove = plannerButton("刪除這個行程", "is-danger planner-delete-trip");
    remove.addEventListener("click", () => {
      if (!window.confirm(`確定刪除「${trip.name}」？此動作無法復原。`)) return;
      void mutate((state) => Planner.deleteTrip(state, trip.id), "行程已刪除");
    });
    section.append(remove);
  }
  return section;
}

function groupNavigation(trip, group) {
  const section = panel("用餐場合", "每組最多比較 5 家");
  const tabs = element("nav", "planner-tabs");
  tabs.setAttribute("aria-label", "用餐場合");
  const inbox = element("button", "planner-tab", `待分類 ${trip.inbox.length}`);
  inbox.type = "button";
  inbox.setAttribute("aria-current", String(!group));
  inbox.addEventListener("click", () => {
    void mutate((state) => Planner.setActiveTarget(state, trip.id, null), "");
  });
  tabs.append(inbox);
  for (const item of trip.groups) {
    const tab = element("button", "planner-tab", `${item.name} ${item.restaurants.length}`);
    tab.type = "button";
    tab.setAttribute("aria-current", String(item.id === group?.id));
    tab.addEventListener("click", () => {
      void mutate((state) => Planner.setActiveTarget(state, trip.id, item.id), "");
    });
    tabs.append(tab);
  }
  section.append(tabs);

  const form = element("form", "planner-new-group");
  const input = document.createElement("input");
  input.maxLength = 120;
  input.placeholder = "例如：銀座週六晚餐";
  input.setAttribute("aria-label", "新用餐場合名稱");
  const add = plannerButton("新增餐次");
  add.type = "submit";
  form.append(input, add);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = input.value.trim();
    if (!name) return;
    void mutate((state) => Planner.createGroup(state, trip.id, {
      id: plannerId("meal"),
      name,
      intent: "destination",
    }), "用餐場合已建立");
  });
  section.append(form);
  return section;
}

function restaurantMeta(restaurant, rankedItem = null, group = null) {
  const values = [];
  if (Number.isFinite(restaurant.rating)) values.push(`Tabelog ${restaurant.rating.toFixed(2)}`);
  if (Number.isFinite(restaurant.reviewCount)) values.push(`${restaurant.reviewCount.toLocaleString("zh-TW")} 則評論`);
  const price = group?.meal === "dinner" ? restaurant.dinnerPrice : restaurant.lunchPrice;
  if (price) values.push(price);
  if (Number.isFinite(rankedItem?.distanceKm)) {
    values.push(rankedItem.distanceKm < 0.05
      ? "集合點附近"
      : `距集合點約 ${Math.round(rankedItem.distanceKm * 10) / 10} 公里`);
  }
  if (restaurant.michelinLabel) values.push(`Michelin ${restaurant.michelinLabel}`);
  if (restaurant.hyakumeitenYears?.length) values.push(`百名店 ×${restaurant.hyakumeitenYears.length}`);
  if (restaurant.station) values.push(restaurant.station);
  return values.join(" · ");
}

function restaurantLinks(restaurant) {
  const links = element("div", "planner-links");
  if (restaurant.mapsUrl) {
    const maps = element("a", "", "在 Maps 開啟 ↗");
    maps.href = restaurant.mapsUrl;
    maps.target = "_blank";
    maps.rel = "noopener noreferrer";
    links.append(maps);
  }
  if (restaurant.tabelogUrl) {
    const tabelog = element("a", "", "在 Tabelog 開啟 ↗");
    tabelog.href = restaurant.tabelogUrl;
    tabelog.target = "_blank";
    tabelog.rel = "noopener noreferrer";
    links.append(tabelog);
  }
  return links;
}

function inboxRestaurantCard(trip, restaurant) {
  const card = element("article", "planner-restaurant");
  card.append(element("h3", "planner-restaurant-name", restaurant.name));
  const meta = restaurantMeta(restaurant);
  if (meta) card.append(element("div", "planner-restaurant-meta", meta));
  if (restaurant.matchStatus === "pending") {
    card.append(element("div", "planner-restaurant-meta", "正在配對 Tabelog 與 Michelin…"));
  } else if (restaurant.matchStatus === "error") {
    card.append(element("div", "planner-restaurant-meta", "配對暫時失敗，仍可保留 Maps 店家。"));
  }
  card.append(restaurantLinks(restaurant));
  if (trip.groups.length) {
    const moveRow = element("div", "planner-inbox-move");
    const select = document.createElement("select");
    select.setAttribute("aria-label", `將 ${restaurant.name} 移到用餐場合`);
    for (const group of trip.groups) {
      const option = element("option", "", `${group.name}（${group.restaurants.length}/5）`);
      option.value = group.id;
      option.disabled = group.restaurants.length >= Planner.MAX_GROUP_RESTAURANTS;
      select.append(option);
    }
    const move = plannerButton("移入", "is-secondary");
    move.disabled = ![...select.options].some((option) => !option.disabled);
    move.addEventListener("click", () => {
      void mutate((state) => Planner.moveRestaurant(
        state,
        trip.id,
        restaurant.id,
        null,
        select.value,
      ), "已移入用餐場合");
    });
    moveRow.append(select, move);
    card.append(moveRow);
  }
  const remove = plannerButton("從行程移除", "is-quiet");
  remove.addEventListener("click", () => {
    void mutate((state) => Planner.removeRestaurant(state, trip.id, null, restaurant.id), "候選店已移除");
  });
  card.append(remove);
  return card;
}

function inboxView(trip) {
  const section = panel("待分類", `${trip.inbox.length}/20`);
  if (!trip.inbox.length) {
    section.append(element(
      "p",
      "planner-empty",
      "從 Google Maps 搜尋結果或 MeshiLens 單店卡按「加入比較」，候選店會出現在目前餐次；尚未選餐次時則先放在這裡。",
    ));
    return section;
  }
  const list = element("div", "planner-restaurant-list");
  for (const restaurant of trip.inbox) list.append(inboxRestaurantCard(trip, restaurant));
  section.append(list);
  return section;
}

function groupEditor(trip, group) {
  const section = panel("比較條件", group.restaurants.length >= 3 ? "可以開始決定" : "建議加入 3–5 家");
  const form = element("form", "planner-form planner-group-form");
  const grid = element("div", "planner-form-grid");

  const nameField = element("label", "planner-field is-wide");
  nameField.append(element("span", "", "用餐場合"));
  const name = document.createElement("input");
  name.name = "name";
  name.maxLength = 120;
  name.required = true;
  name.value = group.name;
  nameField.append(name);

  const dateField = element("label", "planner-field");
  dateField.append(element("span", "", "日期（選填）"));
  const date = document.createElement("input");
  date.type = "date";
  date.name = "date";
  date.value = group.date;
  dateField.append(date);

  const mealField = element("label", "planner-field");
  mealField.append(element("span", "", "餐期"));
  const meal = document.createElement("select");
  meal.name = "meal";
  for (const [value, label] of [["", "未指定"], ["lunch", "午餐"], ["dinner", "晚餐"]]) {
    const option = element("option", "", label);
    option.value = value;
    option.selected = value === group.meal;
    meal.append(option);
  }
  mealField.append(meal);

  const intentField = element("label", "planner-field");
  intentField.append(element("span", "", "這餐最重視"));
  const intent = document.createElement("select");
  intent.name = "intent";
  for (const [value, label] of [
    ["destination", "最值得專程去"],
    ["nearby", "附近快速吃"],
    ["budget", "控制預算"],
  ]) {
    const option = element("option", "", label);
    option.value = value;
    option.selected = value === group.intent;
    intent.append(option);
  }
  intentField.append(intent);

  const budgetField = element("label", "planner-field");
  budgetField.append(element("span", "", "每人預算上限（日圓）"));
  const budget = document.createElement("input");
  budget.type = "number";
  budget.name = "budgetMax";
  budget.min = "0";
  budget.step = "500";
  budget.placeholder = "選填";
  budget.value = Number.isFinite(group.budgetMax) ? String(group.budgetMax) : "";
  budgetField.append(budget);

  const anchorField = element("div", "planner-field is-wide");
  anchorField.append(element("span", "", "集合點"));
  const anchorRow = element("div", "planner-anchor-row");
  const anchor = document.createElement("input");
  anchor.name = "anchorName";
  anchor.maxLength = 120;
  anchor.placeholder = "先在 Maps 開啟飯店、車站或景點";
  anchor.value = group.anchor?.name || "";
  const useMap = plannerButton("使用目前 Maps", "is-secondary");
  useMap.addEventListener("click", async () => {
    useMap.disabled = true;
    try {
      const response = await chrome.runtime.sendMessage({ type: "GET_MAP_CONTEXT" });
      if (!response?.ok || !Number.isFinite(response.context?.latitude) || !Number.isFinite(response.context?.longitude)) {
        throw new Error(response?.error || "目前 Maps 沒有可用的位置");
      }
      const nextAnchor = {
        name: response.context.name || "目前地圖位置",
        latitude: response.context.latitude,
        longitude: response.context.longitude,
      };
      await mutate((state) => Planner.updateGroup(state, trip.id, group.id, {
        name: name.value,
        date: date.value,
        meal: meal.value,
        intent: intent.value,
        budgetMax: budget.value,
        anchor: nextAnchor,
      }), "集合點已從 Maps 更新");
    } catch (error) {
      setStatus(error?.message || "暫時無法讀取 Maps 位置", "error");
    } finally {
      useMap.disabled = false;
    }
  });
  anchorRow.append(anchor, useMap);
  anchorField.append(anchorRow);
  anchorField.append(element(
    "p",
    "planner-help",
    group.anchor && Number.isFinite(group.anchor.latitude)
      ? "已保存座標；你可以修改集合點顯示名稱。"
      : "「附近快速吃」需要先從目前 Maps 畫面取得集合點座標。",
  ));

  grid.append(nameField, dateField, mealField, intentField, budgetField, anchorField);
  form.append(grid);
  const save = plannerButton("儲存比較條件");
  save.type = "submit";
  form.append(save);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void mutate((state) => Planner.updateGroup(state, trip.id, group.id, {
      name: name.value,
      date: date.value,
      meal: meal.value,
      intent: intent.value,
      budgetMax: budget.value,
      anchor: {
        name: anchor.value,
        latitude: group.anchor?.latitude,
        longitude: group.anchor?.longitude,
      },
    }), "比較條件已更新");
  });
  section.append(form);
  const remove = plannerButton("刪除這個用餐場合", "is-danger");
  remove.addEventListener("click", () => {
    if (!window.confirm(`刪除「${group.name}」？候選店會移回待分類。`)) return;
    void mutate((state) => Planner.deleteGroup(state, trip.id, group.id), "候選店已移回待分類");
  });
  section.append(remove);
  return section;
}

function decisionSummary(group) {
  const primary = group.restaurants.find((item) => item.id === group.primaryId);
  const backup = group.restaurants.find((item) => item.id === group.backupId);
  if (!primary && !backup) return null;
  const box = element("div", "planner-decision");
  if (primary) {
    const row = element("div", "planner-decision-row");
    row.append(document.createTextNode("首選："), element("strong", "", primary.name));
    box.append(row);
  }
  if (backup) {
    const row = element("div", "planner-decision-row");
    row.append(document.createTextNode("備案："), element("strong", "", backup.name));
    box.append(row);
  }
  return box;
}

function groupRestaurantCard(trip, group, rankedItem, index) {
  const restaurant = rankedItem.restaurant;
  const card = element("article", "planner-restaurant");
  if (restaurant.id === group.primaryId) card.classList.add("is-primary");
  if (restaurant.id === group.backupId) card.classList.add("is-backup");
  const top = element("div", "planner-restaurant-top");
  top.append(element("h3", "planner-restaurant-name", restaurant.name));
  const rankLabel = restaurant.id === group.primaryId
    ? "首選"
    : restaurant.id === group.backupId
      ? "備案"
      : index === 0 ? "條件建議" : `第 ${index + 1} 順位`;
  top.append(element("span", `planner-rank${index === 0 ? " is-recommended" : ""}`, rankLabel));
  card.append(top);
  const meta = restaurantMeta(restaurant, rankedItem, group);
  if (meta) card.append(element("div", "planner-restaurant-meta", meta));
  if (restaurant.matchStatus === "pending") {
    card.append(element("div", "planner-restaurant-meta", "正在補齊 Tabelog 與 Michelin 資訊…"));
  } else {
    const tags = element("div", "planner-tags");
    for (const advantage of rankedItem.advantages) tags.append(element("span", "planner-tag", advantage));
    for (const caution of rankedItem.cautions) tags.append(element("span", "planner-tag is-caution", caution));
    if (group.date || group.meal) {
      tags.append(element("span", "planner-tag is-caution", "營業時間請在出發前再次確認"));
    }
    if (tags.childElementCount) card.append(tags);
  }
  card.append(restaurantLinks(restaurant));
  const actions = element("div", "planner-actions");
  const primary = plannerButton(restaurant.id === group.primaryId ? "已選首選" : "設為首選");
  primary.disabled = restaurant.matchStatus === "pending";
  primary.addEventListener("click", () => {
    void mutate((state) => Planner.chooseRestaurant(
      state,
      trip.id,
      group.id,
      restaurant.id,
      "primary",
    ), "首選已更新");
  });
  const backup = plannerButton(restaurant.id === group.backupId ? "已選備案" : "設為備案", "is-secondary");
  backup.disabled = restaurant.matchStatus === "pending";
  backup.addEventListener("click", () => {
    void mutate((state) => Planner.chooseRestaurant(
      state,
      trip.id,
      group.id,
      restaurant.id,
      "backup",
    ), "備案已更新");
  });
  const move = plannerButton("移回待分類", "is-quiet");
  move.addEventListener("click", () => {
    void mutate((state) => Planner.moveRestaurant(
      state,
      trip.id,
      restaurant.id,
      group.id,
      null,
    ), "已移回待分類");
  });
  const remove = plannerButton("移除", "is-danger");
  remove.addEventListener("click", () => {
    void mutate((state) => Planner.removeRestaurant(
      state,
      trip.id,
      group.id,
      restaurant.id,
    ), "候選店已移除");
  });
  actions.append(primary, backup, move, remove);
  card.append(actions);
  return card;
}

function comparisonView(trip, group) {
  const section = panel("候選店比較", `${group.restaurants.length}/5`);
  const decision = decisionSummary(group);
  if (decision) section.append(decision);
  if (!group.restaurants.length) {
    section.append(element(
      "p",
      "planner-empty",
      "先讓這個餐次保持開啟，再到 Google Maps 搜尋結果勾選三至五家候選店。",
    ));
    return section;
  }
  const ranked = Planner.rankGroup(group);
  const list = element("div", "planner-restaurant-list");
  ranked.forEach((item, index) => list.append(groupRestaurantCard(trip, group, item, index)));
  section.append(list);
  return section;
}

function copyText(value, input) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(value);
  input.focus();
  input.select();
  document.execCommand("copy");
  return Promise.resolve();
}

function renderQr(container, url) {
  container.replaceChildren();
  try {
    if (!globalThis.QRCode) throw new Error("QR Code 元件未載入");
    new globalThis.QRCode(container, {
      text: url,
      width: 190,
      height: 190,
      colorDark: "#20242a",
      colorLight: "#fffdf9",
      correctLevel: globalThis.QRCode.CorrectLevel.M,
    });
  } catch {
    container.append(element("p", "planner-empty", "分享網址較長，請改用複製連結傳到手機。"));
  }
}

function shareView(trip) {
  const payload = buildSharePayload(plannerState, trip.id);
  const section = panel("帶到手機", "伺服器不保存行程");
  const chosenGroups = payload?.groups?.length || 0;
  section.append(element(
    "p",
    "planner-help",
    chosenGroups
      ? `已有 ${chosenGroups} 個餐次可分享；只包含首選、備案與 Maps 連結。`
      : "每個餐次至少選出首選或備案，才能產生精簡手機行程。",
  ));
  const create = plannerButton("產生手機分享連結與 QR Code");
  create.disabled = !chosenGroups;
  section.append(create);
  const output = element("div", "planner-share-output");
  section.append(output);
  create.addEventListener("click", () => {
    const url = buildShareUrl(payload);
    if (!url) {
      setStatus("暫時無法產生分享連結", "error");
      return;
    }
    output.replaceChildren();
    const linkRow = element("div", "planner-share-link");
    const input = document.createElement("input");
    input.readOnly = true;
    input.value = url;
    input.setAttribute("aria-label", "手機分享網址");
    const copy = plannerButton("複製", "is-secondary");
    copy.addEventListener("click", async () => {
      try {
        await copyText(url, input);
        setStatus("分享連結已複製", "success");
      } catch {
        setStatus("無法自動複製，請手動選取網址", "error");
      }
    });
    linkRow.append(input, copy);
    const open = plannerButton("先預覽手機行程", "is-quiet");
    open.addEventListener("click", () => window.open(url, "_blank", "noopener,noreferrer"));
    const qr = element("div", "planner-qr");
    output.append(linkRow, open, qr);
    renderQr(qr, url);
  });
  return section;
}

function render() {
  plannerRoot.replaceChildren();
  const trip = activeTrip();
  if (!trip) {
    plannerRoot.append(emptyTripsView());
    return;
  }
  const group = activeGroup(trip);
  plannerRoot.append(tripControls(trip), groupNavigation(trip, group));
  if (group) {
    plannerRoot.append(groupEditor(trip, group), comparisonView(trip, group));
  } else {
    plannerRoot.append(inboxView(trip));
  }
  plannerRoot.append(shareView(trip));
}

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") return;
  if (changes.themeColor) {
    const color = /^#[0-9a-f]{6}$/i.test(changes.themeColor.newValue)
      ? changes.themeColor.newValue
      : "#bf3a2b";
    document.documentElement.style.setProperty("--ml-accent", color);
  }
  if (changes[PLANNER_STORAGE_KEY]) {
    plannerState = Planner.sanitizePlannerState(changes[PLANNER_STORAGE_KEY].newValue);
    render();
  }
});

Promise.all([
  plannerStore.load(),
  chrome.storage.local.get({ themeColor: "#bf3a2b" }),
]).then(([state, settings]) => {
  plannerState = state;
  const color = /^#[0-9a-f]{6}$/i.test(settings.themeColor) ? settings.themeColor : "#bf3a2b";
  document.documentElement.style.setProperty("--ml-accent", color);
  render();
}).catch((error) => {
  setStatus(error?.message || "無法載入本機行程", "error", true);
  render();
});
