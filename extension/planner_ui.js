const plannerRoot = document.getElementById("planner-root");
const plannerStatus = document.getElementById("planner-status");
const plannerVersion = document.getElementById("planner-version");
const Planner = globalThis.MeshiLensPlanner;
const { PLANNER_STORAGE_KEY, createPlannerStore } = globalThis.MeshiLensPlannerStore;
const { buildSharePayload, buildShareUrl } = globalThis.MeshiLensPlannerShare;
const plannerStore = createPlannerStore();
const INTENT_OPTIONS = [
  ["destination", "專程去", "最值得專程去"],
  ["nearby", "附近吃", "附近快速吃"],
  ["budget", "控預算", "控制預算"],
];

let plannerState = Planner.createPlannerState();
let statusTimer = null;
let renamingTrip = false;
let addingTrip = false;
let addingMeal = false;
let settingsOpen = false;
let shareUrl = "";

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

async function mutate(transform, message = "") {
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

function startTrip(state, name) {
  const tripId = plannerId("trip");
  const withTrip = Planner.createTrip(state, { id: tripId, name });
  return Planner.ensureActiveMeal(withTrip, tripId, {
    id: plannerId("meal"),
    name: "第一餐",
  });
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
  const section = panel("建立行程");
  section.append(element(
    "p",
    "planner-empty",
    "先幫這趟旅行取個名字，再到 Google Maps 按「加入比較」。候選店會直接進入第一餐。",
  ));
  const form = element("form", "planner-form");
  const input = document.createElement("input");
  input.name = "tripName";
  input.maxLength = 120;
  input.placeholder = "例如：東京五天";
  input.required = true;
  const submit = plannerButton("開始比較");
  submit.type = "submit";
  form.append(input, submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = input.value.trim();
    if (!name) return;
    void mutate((state) => startTrip(state, name), "行程已建立");
  });
  section.append(form);
  return section;
}

function tripBar(trip) {
  const section = element("section", "planner-trip-bar");
  if (renamingTrip || addingTrip) {
    const form = element("form", "planner-inline-form");
    const input = document.createElement("input");
    input.maxLength = 120;
    input.required = true;
    input.value = addingTrip ? "" : trip.name;
    input.placeholder = addingTrip ? "新行程名稱" : "行程名稱";
    const save = plannerButton(addingTrip ? "建立" : "儲存");
    save.type = "submit";
    const cancel = plannerButton("取消", "is-quiet");
    cancel.addEventListener("click", () => {
      renamingTrip = false;
      addingTrip = false;
      render();
    });
    form.append(input, save, cancel);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const name = input.value.trim();
      if (!name) return;
      const wasAdding = addingTrip;
      renamingTrip = false;
      addingTrip = false;
      void mutate((state) => (wasAdding
        ? startTrip(state, name)
        : Planner.renameTrip(state, trip.id, name)
      ), wasAdding ? "行程已建立" : "行程名稱已更新");
    });
    section.append(form);
    queueMicrotask(() => input.focus());
    return section;
  }

  const select = document.createElement("select");
  select.setAttribute("aria-label", "選擇行程");
  for (const item of plannerState.trips) {
    const option = element("option", "", item.name);
    option.value = item.id;
    option.selected = item.id === trip.id;
    select.append(option);
  }
  select.addEventListener("change", () => {
    shareUrl = "";
    void mutate((state) => {
      const nextTrip = state.trips.find((item) => item.id === select.value);
      return Planner.setActiveTarget(state, select.value, nextTrip?.groups[0]?.id || null);
    });
  });
  const rename = plannerButton("改名", "is-quiet");
  rename.addEventListener("click", () => {
    renamingTrip = true;
    addingTrip = false;
    render();
  });
  const add = plannerButton("＋", "is-secondary");
  add.title = "新增行程";
  add.setAttribute("aria-label", "新增行程");
  add.addEventListener("click", () => {
    addingTrip = true;
    renamingTrip = false;
    render();
  });
  section.append(select, rename, add);
  return section;
}

function mealTabs(trip, group) {
  const section = element("section", "planner-meals");
  const tabs = element("nav", "planner-tabs");
  tabs.setAttribute("aria-label", "餐次");
  if (trip.inbox.length || !group) {
    const inbox = element("button", "planner-tab", trip.inbox.length ? `待分類 ${trip.inbox.length}` : "待分類");
    inbox.type = "button";
    inbox.setAttribute("aria-current", String(!group));
    inbox.addEventListener("click", () => {
      shareUrl = "";
      addingMeal = false;
      void mutate((state) => Planner.setActiveTarget(state, trip.id, null));
    });
    tabs.append(inbox);
  }
  for (const item of trip.groups) {
    const tab = element("button", "planner-tab", `${item.name} ${item.restaurants.length}`);
    tab.type = "button";
    tab.setAttribute("aria-current", String(item.id === group?.id));
    tab.addEventListener("click", () => {
      shareUrl = "";
      addingMeal = false;
      void mutate((state) => Planner.setActiveTarget(state, trip.id, item.id));
    });
    tabs.append(tab);
  }
  const addTab = element("button", "planner-tab planner-tab-add", "＋ 餐次");
  addTab.type = "button";
  addTab.setAttribute("aria-pressed", String(addingMeal));
  addTab.addEventListener("click", () => {
    addingMeal = !addingMeal;
    render();
  });
  tabs.append(addTab);
  section.append(tabs);

  if (addingMeal) {
    const form = element("form", "planner-new-group");
    const input = document.createElement("input");
    input.maxLength = 120;
    input.placeholder = "例如：銀座週六晚餐";
    input.setAttribute("aria-label", "新餐次名稱");
    const add = plannerButton("新增");
    add.type = "submit";
    form.append(input, add);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const name = input.value.trim();
      if (!name) return;
      addingMeal = false;
      shareUrl = "";
      void mutate((state) => Planner.createGroup(state, trip.id, {
        id: plannerId("meal"),
        name,
        intent: "destination",
      }), "餐次已建立");
    });
    section.append(form);
    queueMicrotask(() => input.focus());
  }
  return section;
}

function restaurantMeta(restaurant, rankedItem = null, group = null) {
  const values = [];
  if (Number.isFinite(restaurant.rating)) values.push(`Tabelog ${restaurant.rating.toFixed(2)}`);
  if (Number.isFinite(restaurant.reviewCount)) values.push(`${restaurant.reviewCount.toLocaleString("zh-TW")} 則`);
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
    const maps = element("a", "", "Maps");
    maps.href = restaurant.mapsUrl;
    maps.target = "_blank";
    maps.rel = "noopener noreferrer";
    links.append(maps);
  }
  if (restaurant.tabelogUrl) {
    const tabelog = element("a", "", "Tabelog");
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
    select.setAttribute("aria-label", `將 ${restaurant.name} 移到餐次`);
    for (const group of trip.groups) {
      const option = element("option", "", `${group.name}（${group.restaurants.length}/5）`);
      option.value = group.id;
      option.disabled = group.restaurants.length >= Planner.MAX_GROUP_RESTAURANTS;
      select.append(option);
    }
    const move = plannerButton("移入這一餐", "is-secondary");
    move.disabled = ![...select.options].some((option) => !option.disabled);
    move.addEventListener("click", () => {
      void mutate((state) => Planner.moveRestaurant(
        state,
        trip.id,
        restaurant.id,
        null,
        select.value,
      ), "已移入餐次");
    });
    moveRow.append(select, move);
    card.append(moveRow);
  }
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "planner-text-action";
  remove.textContent = "從行程移除";
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
      "還沒決定哪一餐的店會放這裡。從餐次裡把店家移過來，或先新增一個餐次再從 Maps 加入。",
    ));
    return section;
  }
  const list = element("div", "planner-restaurant-list");
  for (const restaurant of trip.inbox) list.append(inboxRestaurantCard(trip, restaurant));
  section.append(list);
  return section;
}

function groupSettings(trip, group) {
  const section = element("section", "planner-panel planner-settings-panel");
  const intentRow = element("div", "planner-intent");
  intentRow.setAttribute("role", "radiogroup");
  intentRow.setAttribute("aria-label", "這一餐最重視");
  for (const [value, shortLabel, fullLabel] of INTENT_OPTIONS) {
    const button = element("button", "planner-intent-chip", shortLabel);
    button.type = "button";
    button.title = fullLabel;
    button.setAttribute("aria-pressed", String(value === group.intent));
    button.addEventListener("click", () => {
      if (value === group.intent) return;
      void mutate((state) => Planner.updateGroup(state, trip.id, group.id, { intent: value }));
    });
    intentRow.append(button);
  }
  section.append(intentRow);
  const hint = group.intent === "nearby" && !Number.isFinite(group.anchor?.latitude)
    ? "「附近吃」需要集合點座標，請展開設定後用目前 Maps。"
    : group.intent === "budget"
      ? "排序會看午晚餐價位；沒有價位的店會標成未知。"
      : "排序看 Tabelog 評分、Michelin 與百名店，不顯示綜合分數。";
  section.append(element("p", "planner-help", hint));

  const details = document.createElement("details");
  details.className = "planner-settings";
  details.open = settingsOpen;
  details.addEventListener("toggle", () => {
    settingsOpen = details.open;
  });
  const summary = document.createElement("summary");
  const bits = [group.name];
  if (group.date) bits.push(group.date);
  if (group.meal === "lunch") bits.push("午餐");
  if (group.meal === "dinner") bits.push("晚餐");
  if (Number.isFinite(group.budgetMax)) bits.push(`預算 ¥${group.budgetMax.toLocaleString("en-US")}`);
  if (group.anchor?.name) bits.push(group.anchor.name);
  summary.textContent = bits.join(" · ");
  details.append(summary);

  const form = element("div", "planner-form planner-form-grid");
  const nameField = element("label", "planner-field is-wide");
  nameField.append(element("span", "", "餐次名稱"));
  const name = document.createElement("input");
  name.maxLength = 120;
  name.value = group.name;
  name.addEventListener("change", () => {
    const nextName = name.value.trim();
    if (!nextName || nextName === group.name) return;
    void mutate((state) => Planner.updateGroup(state, trip.id, group.id, { name: nextName }));
  });
  nameField.append(name);

  const dateField = element("label", "planner-field");
  dateField.append(element("span", "", "日期"));
  const date = document.createElement("input");
  date.type = "date";
  date.value = group.date;
  date.addEventListener("change", () => {
    void mutate((state) => Planner.updateGroup(state, trip.id, group.id, { date: date.value }));
  });
  dateField.append(date);

  const mealField = element("label", "planner-field");
  mealField.append(element("span", "", "餐期"));
  const meal = document.createElement("select");
  for (const [value, label] of [["", "未指定"], ["lunch", "午餐"], ["dinner", "晚餐"]]) {
    const option = element("option", "", label);
    option.value = value;
    option.selected = value === group.meal;
    meal.append(option);
  }
  meal.addEventListener("change", () => {
    void mutate((state) => Planner.updateGroup(state, trip.id, group.id, { meal: meal.value }));
  });
  mealField.append(meal);

  const budgetField = element("label", "planner-field is-wide");
  budgetField.append(element("span", "", "每人預算上限（日圓）"));
  const budget = document.createElement("input");
  budget.type = "number";
  budget.min = "0";
  budget.step = "500";
  budget.placeholder = "選填";
  budget.value = Number.isFinite(group.budgetMax) ? String(group.budgetMax) : "";
  budget.addEventListener("change", () => {
    void mutate((state) => Planner.updateGroup(state, trip.id, group.id, { budgetMax: budget.value }));
  });
  budgetField.append(budget);

  const anchorField = element("div", "planner-field is-wide");
  anchorField.append(element("span", "", "集合點"));
  const anchorRow = element("div", "planner-anchor-row");
  const anchor = document.createElement("input");
  anchor.maxLength = 120;
  anchor.placeholder = "顯示名稱，座標請用目前 Maps";
  anchor.value = group.anchor?.name || "";
  anchor.addEventListener("change", () => {
    void mutate((state) => Planner.updateGroup(state, trip.id, group.id, {
      anchor: {
        name: anchor.value,
        latitude: group.anchor?.latitude,
        longitude: group.anchor?.longitude,
      },
    }));
  });
  const useMap = plannerButton("用目前 Maps", "is-secondary");
  useMap.addEventListener("click", async () => {
    useMap.disabled = true;
    try {
      const response = await chrome.runtime.sendMessage({ type: "GET_MAP_CONTEXT" });
      if (!response?.ok || !Number.isFinite(response.context?.latitude) || !Number.isFinite(response.context?.longitude)) {
        throw new Error(response?.error || "目前 Maps 沒有可用的位置");
      }
      settingsOpen = true;
      await mutate((state) => Planner.updateGroup(state, trip.id, group.id, {
        anchor: {
          name: anchor.value.trim() || response.context.name || "目前地圖位置",
          latitude: response.context.latitude,
          longitude: response.context.longitude,
        },
      }), "集合點已更新");
    } catch (error) {
      setStatus(error?.message || "暫時無法讀取 Maps 位置", "error");
    } finally {
      useMap.disabled = false;
    }
  });
  anchorRow.append(anchor, useMap);
  anchorField.append(anchorRow);
  form.append(nameField, dateField, mealField, budgetField, anchorField);
  details.append(form);

  const remove = plannerButton("刪除這個餐次", "is-danger");
  remove.addEventListener("click", () => {
    if (!window.confirm(`刪除「${group.name}」？候選店會移到待分類。`)) return;
    settingsOpen = false;
    shareUrl = "";
    void mutate((state) => Planner.deleteGroup(state, trip.id, group.id), "候選店已移到待分類");
  });
  details.append(remove);
  section.append(details);
  return section;
}

function decisionSummary(group) {
  const primary = group.restaurants.find((item) => item.id === group.primaryId);
  const backup = group.restaurants.find((item) => item.id === group.backupId);
  if (!primary && !backup) return null;
  const box = element("div", "planner-decision");
  if (primary) {
    const row = element("div", "planner-decision-row");
    row.append(document.createTextNode("首選 "), element("strong", "", primary.name));
    box.append(row);
  }
  if (backup) {
    const row = element("div", "planner-decision-row");
    row.append(document.createTextNode("備案 "), element("strong", "", backup.name));
    box.append(row);
  }
  return box;
}

function textAction(label, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "planner-text-action";
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function groupRestaurantCard(trip, group, rankedItem, index) {
  const restaurant = rankedItem.restaurant;
  const isPrimary = restaurant.id === group.primaryId;
  const isBackup = restaurant.id === group.backupId;
  const isSuggested = !group.primaryId && index === 0;
  const card = element("article", "planner-restaurant");
  if (isPrimary) card.classList.add("is-primary");
  if (isBackup) card.classList.add("is-backup");
  const top = element("div", "planner-restaurant-top");
  top.append(element("h3", "planner-restaurant-name", restaurant.name));
  const rankLabel = isPrimary ? "首選" : isBackup ? "備案" : isSuggested ? "建議" : "";
  if (rankLabel) {
    top.append(element(
      "span",
      `planner-rank${isPrimary || isSuggested ? " is-recommended" : ""}`,
      rankLabel,
    ));
  }
  card.append(top);
  const meta = restaurantMeta(restaurant, rankedItem, group);
  if (meta) card.append(element("div", "planner-restaurant-meta", meta));
  if (restaurant.matchStatus === "pending") {
    card.append(element("div", "planner-restaurant-meta", "正在補齊 Tabelog 與 Michelin 資訊…"));
  } else {
    const tags = element("div", "planner-tags");
    for (const advantage of rankedItem.advantages) tags.append(element("span", "planner-tag", advantage));
    for (const caution of rankedItem.cautions) tags.append(element("span", "planner-tag is-caution", caution));
    if (tags.childElementCount) card.append(tags);
  }
  card.append(restaurantLinks(restaurant));
  const actions = element("div", "planner-actions");
  const primary = plannerButton(isPrimary ? "已選首選" : "設為首選");
  primary.disabled = restaurant.matchStatus === "pending" || isPrimary;
  primary.addEventListener("click", () => {
    void mutate((state) => Planner.chooseRestaurant(
      state,
      trip.id,
      group.id,
      restaurant.id,
      "primary",
    ), "已設為首選");
  });
  const backup = plannerButton(isBackup ? "已選備案" : "設為備案", "is-secondary");
  backup.disabled = restaurant.matchStatus === "pending" || isBackup;
  backup.addEventListener("click", () => {
    void mutate((state) => Planner.chooseRestaurant(
      state,
      trip.id,
      group.id,
      restaurant.id,
      "backup",
    ), "已設為備案");
  });
  actions.append(primary, backup);
  card.append(actions);
  const extras = element("div", "planner-card-extras");
  extras.append(
    textAction("移到待分類", () => {
      void mutate((state) => Planner.moveRestaurant(
        state,
        trip.id,
        restaurant.id,
        group.id,
        null,
      ), "已移到待分類");
    }),
    textAction("移除", () => {
      void mutate((state) => Planner.removeRestaurant(
        state,
        trip.id,
        group.id,
        restaurant.id,
      ), "候選店已移除");
    }),
  );
  card.append(extras);
  return card;
}

function comparisonView(trip, group) {
  const count = group.restaurants.length;
  const section = panel("這一餐", `${count}/5`);
  const decision = decisionSummary(group);
  if (decision) section.append(decision);
  if (group.date || group.meal) {
    section.append(element("p", "planner-help", "營業時間請在出發前再確認一次。"));
  }
  if (!count) {
    section.append(element(
      "p",
      "planner-empty",
      "在 Google Maps 搜尋結果或店家頁按「加入比較」，店家會進入這一餐。一餐最多 5 家。",
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

function shareOutput(url) {
  const output = element("div", "planner-share-output");
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
  const open = plannerButton("預覽手機行程", "is-quiet");
  open.addEventListener("click", () => window.open(url, "_blank", "noopener,noreferrer"));
  const qr = element("div", "planner-qr");
  output.append(linkRow, open, qr);
  queueMicrotask(() => renderQr(qr, url));
  return output;
}

function shareView(trip) {
  const payload = buildSharePayload(plannerState, trip.id);
  const chosenGroups = payload?.groups?.length || 0;
  if (!chosenGroups) {
    const hint = element("p", "planner-share-hint", "選好首選或備案後，可以產生給手機看的精簡行程。");
    return hint;
  }
  const section = panel("傳到手機", `${chosenGroups} 餐已可分享`);
  const create = plannerButton(shareUrl ? "重新產生連結" : "產生分享連結與 QR Code");
  section.append(create);
  create.addEventListener("click", () => {
    const url = buildShareUrl(payload);
    if (!url) {
      setStatus("暫時無法產生分享連結", "error");
      return;
    }
    shareUrl = url;
    render();
  });
  if (shareUrl) section.append(shareOutput(shareUrl));
  return section;
}

function tripFooter(trip) {
  if (plannerState.trips.length <= 1 && (trip.inbox.length || trip.groups.length)) return null;
  const footer = element("div", "planner-footer");
  const remove = plannerButton("刪除這個行程", "is-danger");
  remove.addEventListener("click", () => {
    if (!window.confirm(`確定刪除「${trip.name}」？此動作無法復原。`)) return;
    shareUrl = "";
    renamingTrip = false;
    addingTrip = false;
    addingMeal = false;
    void mutate((state) => Planner.deleteTrip(state, trip.id), "行程已刪除");
  });
  footer.append(remove);
  return footer;
}

function render() {
  plannerRoot.replaceChildren();
  const trip = activeTrip();
  if (!trip) {
    renamingTrip = false;
    addingTrip = false;
    addingMeal = false;
    settingsOpen = false;
    shareUrl = "";
    plannerRoot.append(emptyTripsView());
    return;
  }
  if (!activeGroup(trip) && !trip.inbox.length && trip.groups.length) {
    void mutate((state) => Planner.setActiveTarget(state, trip.id, trip.groups[0].id));
    return;
  }
  const group = activeGroup(trip);
  plannerRoot.append(tripBar(trip), mealTabs(trip, group));
  if (group) {
    plannerRoot.append(groupSettings(trip, group), comparisonView(trip, group));
  } else {
    plannerRoot.append(inboxView(trip));
  }
  plannerRoot.append(shareView(trip));
  const footer = tripFooter(trip);
  if (footer) plannerRoot.append(footer);
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
