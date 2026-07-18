const CARD_ID = "meshilens-card";
const ADDRESS_PREFIX = /^(地址|住所|address)\s*[:：]?\s*/i;
const PHONE_PREFIX = /^(電話|電話番号|phone)\s*[:：]?\s*/i;
const { foodSignalsFromLabels, isFoodPlace } = globalThis.MeshiLensCategory;
const { coordinatesFromMapsUrl } = globalThis.MeshiLensMaps;
const { DEFAULT_THEME_COLOR, normalizeThemeColor } = globalThis.MeshiLensSettings;
const { buildTimelineEntries, shouldShowTimeline } = globalThis.MeshiLensTimeline;
const { advicePayload, adviceCacheKey, cachedAdvice } = globalThis.MeshiLensAdvice;
let activePlaceKey = "";
let lookupSequence = 0;
let debounceTimer = null;
let extensionEnabled = false;
let themeColor = DEFAULT_THEME_COLOR;

function labeledValue(selectors, prefix) {
  for (const selector of selectors) {
    const element = document.querySelector(selector);
    if (!element) continue;
    const raw = element.getAttribute("aria-label") || element.textContent || "";
    const value = raw.replace(prefix, "").trim();
    if (value) return value;
  }
  return "";
}

function tabelogUrlFromPage() {
  const links = document.querySelectorAll('main a[href*="tabelog.com/"], [role="main"] a[href*="tabelog.com/"]');
  for (const link of links) {
    if (link.closest(`#${CARD_ID}`)) continue;
    const match = link.href.match(
      /^https:\/\/tabelog\.com\/(?:en\/|tw\/|cn\/|kr\/)?([a-z0-9-]+\/A\d+\/A\d+\/\d+)\//i,
    );
    if (match) return `https://tabelog.com/${match[1]}/`;
  }
  return "";
}

function officialWebsiteFromPage(detailPanel) {
  const links = detailPanel?.querySelectorAll(
    'a[data-item-id="authority"][href], a[aria-label^="網站:"][href], a[aria-label^="Website:"][href]',
  ) || [];
  for (const link of links) {
    try {
      const url = new URL(link.href);
      if (url.protocol === "http:" || url.protocol === "https:") return url.href;
    } catch {
      // Ignore malformed Maps links and keep checking the remaining website buttons.
    }
  }
  return "";
}

function diningSignals(detailPanel) {
  const labels = Array.from(
    detailPanel?.querySelectorAll('button, [role="tab"], [aria-label]') || [],
    (element) => [element.getAttribute("aria-label"), element.textContent]
      .filter(Boolean),
  ).flat();
  return foodSignalsFromLabels(labels);
}

function extractPlace() {
  const title = document.querySelector("h1.DUwDvf, h1.fontHeadlineLarge");
  const name = title?.textContent?.trim() || "";
  if (!name) return null;
  const detailPanel = title.closest('main, [role="main"]');
  const category = detailPanel
    ?.querySelector('button[jsaction$=".category"], button.DkEaL')
    ?.textContent?.trim() || "";
  if (!isFoodPlace({ category, ...diningSignals(detailPanel) })) return null;
  const alternateName = document.querySelector("h2.bwoZTb")?.textContent?.trim() || "";
  const address = labeledValue(
    ['button[data-item-id="address"]', '[data-item-id="address"]'],
    ADDRESS_PREFIX,
  );
  const phone = labeledValue(
    ['button[data-item-id^="phone:tel:"]', '[data-item-id^="phone:"]'],
    PHONE_PREFIX,
  );
  return {
    name,
    category,
    alternate_name: alternateName,
    address,
    phone,
    website: officialWebsiteFromPage(detailPanel),
    tabelog_url: tabelogUrlFromPage(),
    ...coordinatesFromMapsUrl(location.href),
    title,
  };
}

function placeKey(place) {
  return [
    place.name,
    place.category,
    place.alternate_name,
    place.address,
    place.phone,
    place.website,
    place.latitude,
    place.longitude,
    place.tabelog_url,
  ].join("|");
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function mountCard(place) {
  document.getElementById(CARD_ID)?.remove();
  const card = element("section");
  card.id = CARD_ID;
  card.setAttribute("aria-label", "Tabelog 評分");
  card.style.setProperty("--ml-accent", themeColor);

  const titleBlock = place.title?.closest("div");
  const mount = titleBlock?.parentElement;
  if (mount && mount.getBoundingClientRect().width >= 280 && mount.getBoundingClientRect().width <= 700) {
    titleBlock.insertAdjacentElement("afterend", card);
  } else {
    card.classList.add("meshilens-floating");
    document.body.append(card);
  }
  return card;
}

function renderStatus(card, message) {
  card.replaceChildren();
  const header = element("div", "meshilens-header");
  header.append(element("span", "meshilens-brand", "MeshiLens"));
  header.append(element("span", "meshilens-source", "Tabelog 日本語版"));
  card.append(header, element("div", "meshilens-status", message));
}

function michelinView(michelin) {
  if (!michelin) return null;
  const section = element("section", "meshilens-michelin");
  const heading = element("div", "meshilens-michelin-heading");
  heading.append(element("span", "meshilens-michelin-source", "MICHELIN GUIDE"));
  heading.append(element("span", "meshilens-michelin-current", "目前收錄"));
  section.append(heading);

  const awards = element("div", "meshilens-michelin-awards");
  const link = element("a", "meshilens-michelin-badge", michelin.distinction_label);
  link.href = michelin.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  awards.append(link);
  if (michelin.green_star) {
    awards.append(element("span", "meshilens-green-star", "米其林綠星"));
  }
  section.append(awards);

  const details = [michelin.cuisine, michelin.price, michelin.location]
    .filter(Boolean)
    .join(" · ");
  if (details) section.append(element("div", "meshilens-michelin-details", details));
  return section;
}

function adviceView(state) {
  const section = element("section", "meshilens-advice");
  section.setAttribute("aria-label", "AI 用餐建議");
  const heading = element("div", "meshilens-advice-heading");
  heading.append(element("span", "meshilens-advice-title", "AI 用餐建議"));
  heading.append(element("span", "meshilens-advice-source", "非評論摘要"));
  section.append(heading);

  if (state?.status === "loading") {
    section.append(element("div", "meshilens-advice-pending", "正在整理店家資訊…"));
    return section;
  }
  if (state?.status === "error") {
    section.append(element("div", "meshilens-advice-pending", "AI 建議暫時無法取得"));
    return section;
  }
  const advice = state?.advice;
  if (!advice?.summary) return null;
  section.append(element("div", "meshilens-advice-headline", advice.headline || "用餐建議"));
  section.append(element("div", "meshilens-advice-summary", advice.summary));
  const addList = (label, values, className) => {
    if (!values?.length) return;
    const group = element("div", `meshilens-advice-group ${className}`);
    group.append(element("span", "meshilens-advice-label", label));
    const list = element("span", "meshilens-advice-values", values.join(" · "));
    group.append(list);
    section.append(group);
  };
  addList("適合", advice.best_for, "is-best-for");
  addList("留意", advice.cautions, "is-cautions");
  if (advice.evidence?.length) {
    section.append(element("div", "meshilens-advice-evidence", `依據：${advice.evidence.join(" · ")}`));
  }
  return section;
}

function syncAdvice(card) {
  const existing = card.querySelector(".meshilens-advice");
  const section = adviceView(card._meshilensAdvice);
  if (!section) {
    existing?.remove();
    return;
  }
  if (existing) {
    existing.replaceWith(section);
    return;
  }
  const footer = card.querySelector(".meshilens-footer");
  if (footer) footer.before(section);
  else card.append(section);
}

async function loadAdvice(card, place, candidate, michelin, sequence) {
  const payload = advicePayload(place, candidate, michelin);
  if (!payload) return;
  const key = adviceCacheKey(candidate, michelin);
  card._meshilensAdviceKey = key;
  card._meshilensAdvice = { status: "loading" };
  syncAdvice(card);
  try {
    const stored = await chrome.storage.local.get({ diningAdviceCache: {} });
    const cache = stored.diningAdviceCache || {};
    const cached = cachedAdvice(cache[key], key);
    if (cached) {
      if (sequence === lookupSequence && card.isConnected && card._meshilensAdviceKey === key) {
        card._meshilensAdvice = { advice: cached };
        syncAdvice(card);
      }
      return;
    }
    const response = await chrome.runtime.sendMessage({ type: "GET_DINING_ADVICE", payload });
    if (!response?.ok) throw new Error(response?.error || "AI 建議暫時無法取得");
    const advice = response.data?.advice;
    if (!response.data?.available) {
      if (sequence === lookupSequence && card.isConnected && card._meshilensAdviceKey === key) {
        card._meshilensAdvice = null;
        syncAdvice(card);
      }
      return;
    }
    if (!advice?.summary) throw new Error("AI 建議暫時無法取得");
    const nextCache = { ...cache, [key]: { key, savedAt: Date.now(), advice } };
    const entries = Object.entries(nextCache).sort(([, a], [, b]) => b.savedAt - a.savedAt).slice(0, 100);
    await chrome.storage.local.set({ diningAdviceCache: Object.fromEntries(entries) });
    if (sequence === lookupSequence && card.isConnected && card._meshilensAdviceKey === key) {
      card._meshilensAdvice = { advice };
      syncAdvice(card);
    }
  } catch {
    if (sequence === lookupSequence && card.isConnected && card._meshilensAdviceKey === key) {
      card._meshilensAdvice = { status: "error" };
      syncAdvice(card);
    }
  }
}

function timelineView(entries) {
  if (!shouldShowTimeline(entries)) return null;
  const section = element("section", "meshilens-timeline");
  section.setAttribute("aria-label", "店家時間線");
  section.append(element("div", "meshilens-timeline-title", "店家時間線"));
  const list = element("ol", "meshilens-timeline-list");
  for (const entry of entries) {
    const item = element("li", "meshilens-timeline-item");
    if (entry.current) item.classList.add("is-current");
    if (entry.kind === "michelin") item.classList.add("is-michelin");
    item.append(element("span", "meshilens-timeline-year", entry.year_label || ""));
    const body = element("div", "meshilens-timeline-body");
    if (entry.url) {
      const link = element("a", "meshilens-timeline-label", entry.label);
      link.href = entry.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      if (entry.title) link.title = entry.title;
      body.append(link);
    } else {
      body.append(element("div", "meshilens-timeline-label", entry.label));
    }
    if (entry.meta) body.append(element("div", "meshilens-timeline-meta", entry.meta));
    item.append(body);
    list.append(item);
  }
  section.append(list);
  return section;
}

function syncTimeline(card) {
  const existing = card.querySelector(".meshilens-timeline");
  const selected = card._meshilensSelected;
  if (!selected) {
    existing?.remove();
    return;
  }
  const entries = buildTimelineEntries(
    card._meshilensMichelin,
    selected.hyakumeiten || [],
  );
  const section = timelineView(entries);
  if (!section) {
    existing?.remove();
    return;
  }
  if (existing) {
    existing.replaceWith(section);
    return;
  }
  const scoreRow = card.querySelector(".meshilens-score-row");
  if (scoreRow) scoreRow.after(section);
}

function updateMichelin(card, michelin) {
  card._meshilensMichelin = michelin || null;
  const existing = card.querySelector(".meshilens-michelin");
  if (!michelin) {
    existing?.remove();
    syncTimeline(card);
    return;
  }
  const section = michelinView(michelin);
  if (existing) {
    existing.replaceWith(section);
  } else {
    const header = card.querySelector(".meshilens-header");
    if (header) header.after(section);
  }
  syncTimeline(card);
  if (card._meshilensSelected && card._meshilensPlace) {
    loadAdvice(card, card._meshilensPlace, card._meshilensSelected, michelin, card._meshilensSequence);
  }
}

function selectedView(candidate, result) {
  const container = document.createDocumentFragment();
  const row = element("div", "meshilens-score-row");
  row.append(element("div", "meshilens-score", candidate.rating ?? "—"));
  const meta = element("div");
  meta.append(element("div", "meshilens-stars", "★★★★★"));
  meta.append(
    element(
      "div",
      "meshilens-count",
      candidate.review_count != null ? `${candidate.review_count} 則評論` : "評論數未提供",
    ),
  );
  row.append(meta);
  container.append(row);
  const timeline = timelineView(
    buildTimelineEntries(result.michelin, candidate.hyakumeiten || []),
  );
  if (timeline) container.append(timeline);

  const reservationStatus = candidate.reservation_url
    ? "online"
    : candidate.reservation_status || "unknown";
  if (reservationStatus === "online") {
    const reservation = element("a", "meshilens-reservation", "可網路預約 ↗");
    reservation.href = candidate.reservation_url;
    reservation.target = "_blank";
    reservation.rel = "noopener noreferrer";
    container.append(reservation);
  } else if (reservationStatus === "available") {
    container.append(element("div", "meshilens-reservation-available", "可預約"));
  }

  const details = element("details", "meshilens-details");
  details.append(element("summary", "", "更多 Tabelog 資訊"));
  const info = element("div", "meshilens-info");
  const addInfo = (label, value) => {
    if (!value) return;
    const row = element("div", "meshilens-info-row");
    row.append(element("span", "meshilens-info-label", label));
    row.append(element("span", "meshilens-info-value", value));
    info.append(row);
  };
  addInfo("料理類型", candidate.genres?.join("、"));
  addInfo("最近車站", candidate.station);
  addInfo("午餐價位", candidate.lunch_price);
  addInfo("晚餐價位", candidate.dinner_price);
  addInfo("公休日", candidate.closed_days);
  const reservationLabels = {
    online: "可網路預約",
    available: "可預約",
    unavailable: "不接受預約",
  };
  addInfo("預約", reservationLabels[reservationStatus]);
  const paymentLabel = (section) => {
    if (!section || section.accepted === undefined) return "";
    if (!section.accepted) return "不可使用";
    return section.details || "可使用";
  };
  addInfo("信用卡", paymentLabel(candidate.payment?.cards));
  addInfo("電子支付", paymentLabel(candidate.payment?.electronic_money));
  addInfo("QR 支付", paymentLabel(candidate.payment?.qr_code));
  if (
    candidate.payment?.details &&
    !candidate.payment?.cards &&
    !candidate.payment?.electronic_money &&
    !candidate.payment?.qr_code
  ) {
    addInfo("付款方式", candidate.payment.details);
  }
  addInfo("電話", candidate.phone);
  addInfo("地址", candidate.address);
  addInfo("營業時間", candidate.business_hours);
  if (info.childElementCount) {
    details.append(info);
    container.append(details);
  }
  const certainty = candidate.confidence === "high" ? "高信心配對" : "請確認是否為同一家店";
  const reasons = [certainty, ...(candidate.match_reasons || [])].join(" · ");
  container.append(element("div", "meshilens-reasons", reasons));

  const footer = element("div", "meshilens-footer");
  const link = element("a", "meshilens-link", "在 Tabelog 開啟 ↗");
  link.href = candidate.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  footer.append(link);
  footer.append(element("span", "meshilens-fetched", result.cached ? "快取資料" : "剛剛更新"));
  container.append(footer);
  return container;
}

function renderResult(card, result) {
  card.replaceChildren();
  const header = element("div", "meshilens-header");
  header.append(element("span", "meshilens-brand", "MeshiLens"));
  header.append(element("span", "meshilens-source", result.source || "Tabelog 日本語版"));
  card.append(header);

  const michelinData = result.michelin || card._meshilensMichelin || null;
  card._meshilensMichelin = michelinData;
  const resultWithMichelin = { ...result, michelin: michelinData };
  const michelin = michelinView(michelinData);
  if (michelin) card.append(michelin);

  const selected = result.selected;
  card._meshilensSelected = selected || null;
  if (!selected) {
    const message = result.tabelog_error
      ? `Tabelog：${result.tabelog_error}`
      : "找不到可信的 Tabelog 店家，請從候選結果選擇。";
    card.append(element("div", "meshilens-status", message));
  } else {
    card.append(selectedView(selected, resultWithMichelin));
    syncAdvice(card);
  }

  if (!result.candidates?.length) return;
  const toggle = element("button", "meshilens-toggle", `查看候選店家（${result.candidates.length}）`);
  toggle.type = "button";
  const list = element("div", "meshilens-candidates meshilens-hidden");
  for (const candidate of result.candidates) {
    const button = element("button", "meshilens-candidate");
    button.type = "button";
    const top = element("span", "meshilens-candidate-top");
    top.append(element("span", "meshilens-candidate-name", candidate.name || "未命名店家"));
    if (candidate.is_hyakumeiten) {
      const count = candidate.hyakumeiten?.length || 1;
      top.append(element("span", "meshilens-candidate-award", count > 1 ? `百名店 ×${count}` : "百名店"));
    }
    top.append(element("span", "meshilens-candidate-score", `配對 ${candidate.score}%`));
    button.append(top);
    button.append(element("span", "meshilens-candidate-address", candidate.address || "地址未提供"));
    button.addEventListener("click", () => {
      const headerNode = card.querySelector(".meshilens-header");
      const michelinNode = card.querySelector(".meshilens-michelin");
      const preservedNodes = [headerNode, michelinNode].filter(Boolean);
      card._meshilensSelected = candidate;
      card._meshilensAdvice = null;
      const resultWithMichelin = {
        ...result,
        michelin: card._meshilensMichelin || result.michelin || null,
      };
      card.replaceChildren(...preservedNodes, selectedView(candidate, resultWithMichelin));
      syncAdvice(card);
      card.append(toggle, list);
      list.classList.add("meshilens-hidden");
      toggle.textContent = `查看候選店家（${result.candidates.length}）`;
      loadAdvice(
        card,
        card._meshilensPlace,
        candidate,
        card._meshilensMichelin || result.michelin || null,
        card._meshilensSequence,
      );
    });
    list.append(button);
  }
  toggle.addEventListener("click", () => {
    const hidden = list.classList.toggle("meshilens-hidden");
    toggle.textContent = hidden ? `查看候選店家（${result.candidates.length}）` : "收起候選店家";
  });
  card.append(toggle, list);
}

async function lookup(place) {
  const sequence = ++lookupSequence;
  const card = mountCard(place);
  card._meshilensPlace = place;
  card._meshilensSequence = sequence;
  renderStatus(card, "正在查詢 Tabelog 與 Michelin…");
  const michelinRequest = chrome.runtime.sendMessage({ type: "MATCH_MICHELIN", place })
    .then((response) => {
      if (sequence !== lookupSequence || !card.isConnected || !response?.ok) return;
      if (response.data?.michelin) updateMichelin(card, response.data.michelin);
    })
    .catch(() => {});
  try {
    const response = await chrome.runtime.sendMessage({ type: "MATCH_PLACE", place });
    if (sequence !== lookupSequence || !card.isConnected) return;
    if (!response?.ok) throw new Error(response?.error || "查詢失敗");
    renderResult(card, response.data);
    if (response.data.selected) {
      loadAdvice(card, place, response.data.selected, card._meshilensMichelin || null, sequence);
    }
  } catch (error) {
    if (sequence !== lookupSequence || !card.isConnected) return;
    renderResult(card, {
      candidates: [],
      michelin: card._meshilensMichelin,
      source: "Tabelog 日本語版",
      tabelog_error: error.message || "Tabelog 查詢失敗",
    });
  }
  await michelinRequest;
}

function scan() {
  clearTimeout(debounceTimer);
  if (!extensionEnabled) {
    activePlaceKey = "";
    document.getElementById(CARD_ID)?.remove();
    return;
  }
  debounceTimer = setTimeout(() => {
    const place = extractPlace();
    if (!place) {
      activePlaceKey = "";
      document.getElementById(CARD_ID)?.remove();
      return;
    }
    const key = placeKey(place);
    if (key === activePlaceKey && document.getElementById(CARD_ID)) return;
    activePlaceKey = key;
    lookup(place);
  }, 500);
}

new MutationObserver((mutations) => {
  const pageChanged = mutations.some((mutation) => {
    const target = mutation.target instanceof Element ? mutation.target : mutation.target.parentElement;
    return !target?.closest(`#${CARD_ID}`);
  });
  if (pageChanged) scan();
}).observe(document.body, { childList: true, subtree: true });
window.addEventListener("popstate", scan);

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") return;
  if (changes.themeColor) {
    themeColor = normalizeThemeColor(changes.themeColor.newValue);
    document.getElementById(CARD_ID)?.style.setProperty("--ml-accent", themeColor);
  }
  if (changes.enabled) {
    extensionEnabled = changes.enabled.newValue !== false;
    activePlaceKey = "";
    if (!extensionEnabled) {
      lookupSequence += 1;
      clearTimeout(debounceTimer);
      document.getElementById(CARD_ID)?.remove();
      return;
    }
    scan();
  }
});

chrome.storage.local.get({ enabled: true, themeColor: DEFAULT_THEME_COLOR }).then(({ enabled, themeColor: savedThemeColor }) => {
  extensionEnabled = enabled;
  themeColor = normalizeThemeColor(savedThemeColor);
  scan();
});
