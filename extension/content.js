const CARD_ID = "meshilens-card";
const LIST_HINT_ID = "meshilens-list-hint";
const ADDRESS_PREFIX = /^(地址|住所|address)\s*[:：]?\s*/i;
const PHONE_PREFIX = /^(電話|電話番号|phone)\s*[:：]?\s*/i;
const { foodSignalsFromLabels, isFoodCategory, isFoodPlace } = globalThis.MeshiLensCategory;
const { coordinatesFromMapsUrl } = globalThis.MeshiLensMaps;
const { classifyJapanPlace } = globalThis.MeshiLensJapan;
const { DEFAULT_THEME_COLOR, normalizeThemeColor } = globalThis.MeshiLensSettings;
const { buildTimelineEntries, shouldShowTimeline } = globalThis.MeshiLensTimeline;
const { advicePayload, adviceCacheKey, cachedAdvice } = globalThis.MeshiLensAdvice;
const {
  BUTTON_LABEL,
  CARD_TITLE,
  UNAVAILABLE_LABEL,
  reviewInsightsPayload,
  reviewInsightsCacheKey,
  cachedReviewInsights,
  beginReviewInsightsFlight,
  clearReviewInsightsFlight,
} = globalThis.MeshiLensReviewInsights;
const { roundCoord } = globalThis.MeshiLensCache;
const { DETAIL_MODE, LIST_MODE, mapsUiMode } = globalThis.MeshiLensUiMode;
const {
  MAX_LIST_CARDS,
  cleanListPlaceName,
  listPlaceNameFromHref,
  listCardKey,
  listCoordinatesFromHref,
  badgeText,
  listCardsNeedingLookup,
  listBatchCoversKeys,
  rememberListBadgeResult,
} = globalThis.MeshiLensListBadges;
const {
  isExtensionContextValid,
  isExtensionContextInvalidatedError,
  safeRuntimeSendMessage,
  softRuntimeSendMessage,
  safeStorageLocalGet,
  safeStorageLocalSet,
} = globalThis.MeshiLensRuntime;
let activePlaceKey = "";
let lookupSequence = 0;
let listBatchSequence = 0;
let listAbortController = null;
let listInFlightKeys = null;
let listBadgeCache = new Map();
let detailDebounceTimer = null;
let listDebounceTimer = null;
let listScrollTimer = null;
let extensionEnabled = false;
let themeColor = DEFAULT_THEME_COLOR;
let extensionAlive = true;
let pageObserver = null;

function handleInvalidatedContext() {
  if (!extensionAlive) return;
  extensionAlive = false;
  lookupSequence += 1;
  listBatchSequence += 1;
  listAbortController?.abort();
  listAbortController = null;
  listInFlightKeys = null;
  clearTimeout(detailDebounceTimer);
  clearTimeout(listDebounceTimer);
  clearTimeout(listScrollTimer);
  detailDebounceTimer = null;
  listDebounceTimer = null;
  listScrollTimer = null;
  pageObserver?.disconnect();
  pageObserver = null;
}

function ensureExtensionAlive() {
  if (!extensionAlive) return false;
  if (isExtensionContextValid()) return true;
  handleInvalidatedContext();
  return false;
}

function notePossibleInvalidation(error) {
  if (!extensionAlive) return true;
  if (error?.invalidated || isExtensionContextInvalidatedError(error) || !isExtensionContextValid()) {
    handleInvalidatedContext();
    return true;
  }
  return false;
}

function detailTitle() {
  return document.querySelector("h1.DUwDvf, h1.fontHeadlineLarge");
}

function currentMapsUiMode() {
  return mapsUiMode({
    hasDetailTitle: Boolean(detailTitle()),
    hasResultsFeed: Boolean(document.querySelector('[role="feed"]')),
  });
}

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
  const title = detailTitle();
  const name = title?.textContent?.trim() || "";
  if (!name) return null;
  const detailPanel = title.closest('main, [role="main"]');
  const category = detailPanel
    ?.querySelector('button[jsaction$=".category"], button.DkEaL')
    ?.textContent?.trim() || "";
  // Known dining categories skip the heavy button/aria-label scan.
  if (!isFoodCategory(category) && !isFoodPlace({ category, ...diningSignals(detailPanel) })) {
    return null;
  }
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
    roundCoord(place.latitude),
    roundCoord(place.longitude),
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
  const mountWidth = mount?.getBoundingClientRect().width ?? 0;
  if (mount && mountWidth >= 280 && mountWidth <= 700) {
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
  const reviewInsights = card.querySelector(".meshilens-review-insights");
  const footer = card.querySelector(".meshilens-footer");
  if (reviewInsights) reviewInsights.before(section);
  else if (footer) footer.before(section);
  else card.append(section);
}

function reviewInsightsView(state, candidate) {
  const section = element("section", "meshilens-review-insights");
  section.setAttribute("aria-label", CARD_TITLE);

  const heading = element("div", "meshilens-review-insights-heading");
  heading.append(element("span", "meshilens-review-insights-title", CARD_TITLE));
  heading.append(element("span", "meshilens-review-insights-badge", "實驗／公開評論"));
  section.append(heading);

  if (!state || state.status === "idle") {
    const button = element("button", "meshilens-review-insights-button", BUTTON_LABEL);
    button.type = "button";
    section.append(button);
    return section;
  }

  if (state.status === "loading") {
    section.append(element("div", "meshilens-review-insights-pending", "正在整理公開評論主題…"));
    return section;
  }

  if (state.status === "error") {
    section.append(element("div", "meshilens-review-insights-pending", UNAVAILABLE_LABEL));
    if (candidate?.url) {
      const link = element("a", "meshilens-link", "在 Tabelog 開啟 ↗");
      link.href = candidate.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      section.append(link);
    }
    return section;
  }

  const insights = state.insights;
  if (!insights?.summary) return null;
  section.append(element("div", "meshilens-review-insights-summary", insights.summary));
  const addList = (label, values, className) => {
    if (!values?.length) return;
    const group = element("div", `meshilens-review-insights-group ${className}`);
    group.append(element("span", "meshilens-review-insights-label", label));
    group.append(element("span", "meshilens-review-insights-values", values.join(" · ")));
    section.append(group);
  };
  addList("常見好評", insights.positive_themes, "is-positive");
  addList("留意", insights.cautions, "is-cautions");
  const meta = [];
  if (insights.sample_size) meta.push(`樣本 ${insights.sample_size} 則`);
  if (insights.source_note) meta.push(insights.source_note);
  if (meta.length) {
    section.append(element("div", "meshilens-review-insights-note", meta.join(" · ")));
  }
  return section;
}

function syncReviewInsights(card) {
  const existing = card.querySelector(".meshilens-review-insights");
  const selected = card._meshilensSelected;
  if (!selected?.url || !reviewInsightsPayload(selected)) {
    existing?.remove();
    return;
  }
  const section = reviewInsightsView(card._meshilensReviewInsights || { status: "idle" }, selected);
  if (!section) {
    existing?.remove();
    return;
  }
  section.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.classList.contains("meshilens-review-insights-button")) {
      event.preventDefault();
      void runReviewInsights(card, selected, card._meshilensSequence);
    }
  });
  if (existing) {
    existing.replaceWith(section);
    return;
  }
  const footer = card.querySelector(".meshilens-footer");
  const advice = card.querySelector(".meshilens-advice");
  if (advice) advice.after(section);
  else if (footer) footer.before(section);
  else card.append(section);
}

async function runReviewInsights(card, candidate, sequence) {
  const payload = reviewInsightsPayload(candidate);
  if (!payload) return;
  const key = reviewInsightsCacheKey(candidate);
  card._meshilensReviewInsightsKey = key;
  card._meshilensReviewInsights = { status: "loading" };
  syncReviewInsights(card);

  try {
    if (!ensureExtensionAlive()) return;
    const insights = await beginReviewInsightsFlight(key, async () => {
      const stored = await safeStorageLocalGet({ reviewInsightsCache: {} });
      const cache = stored.reviewInsightsCache || {};
      const cached = cachedReviewInsights(cache[key], key);
      if (cached) return cached;

      const response = await safeRuntimeSendMessage({
        type: "GET_REVIEW_INSIGHTS",
        payload,
      });
      if (response?.cancelled) {
        const cancelled = new Error("查詢已取消");
        cancelled.cancelled = true;
        throw cancelled;
      }
      if (!response?.ok) throw new Error(response?.error || UNAVAILABLE_LABEL);
      if (!response.data?.available || !response.data?.insights?.summary) {
        throw new Error(UNAVAILABLE_LABEL);
      }
      const nextInsights = response.data.insights;
      const nextCache = {
        ...cache,
        [key]: { key, savedAt: Date.now(), insights: nextInsights },
      };
      const entries = Object.entries(nextCache)
        .sort(([, a], [, b]) => b.savedAt - a.savedAt)
        .slice(0, 100);
      await safeStorageLocalSet({ reviewInsightsCache: Object.fromEntries(entries) });
      return nextInsights;
    });

    if (sequence === lookupSequence && card.isConnected && card._meshilensReviewInsightsKey === key) {
      card._meshilensReviewInsights = { insights };
      syncReviewInsights(card);
    }
  } catch (error) {
    if (notePossibleInvalidation(error) || error?.cancelled) {
      clearReviewInsightsFlight(key);
      return;
    }
    if (sequence === lookupSequence && card.isConnected && card._meshilensReviewInsightsKey === key) {
      card._meshilensReviewInsights = { status: "error" };
      syncReviewInsights(card);
    }
  }
}

async function loadAdvice(card, place, candidate, michelin, sequence) {
  // Michelin can arrive after the Tabelog result.  Start the AI request with the
  // first complete restaurant match and keep it in the background; otherwise a
  // late Michelin response would restart the pending AI card and make the UI
  // feel slower (as well as sending a duplicate request).
  const requestKey = candidate.url || candidate.name;
  if (card._meshilensAdviceRequestKey === requestKey) return;
  card._meshilensAdviceRequestKey = requestKey;
  const payload = advicePayload(place, candidate, michelin);
  if (!payload) return;
  const key = adviceCacheKey(place, candidate, michelin);
  card._meshilensAdviceKey = key;
  card._meshilensAdvice = { status: "loading" };
  syncAdvice(card);
  try {
    if (!ensureExtensionAlive()) return;
    const stored = await safeStorageLocalGet({ diningAdviceCache: {} });
    const cache = stored.diningAdviceCache || {};
    const cached = cachedAdvice(cache[key], key);
    if (cached) {
      if (sequence === lookupSequence && card.isConnected && card._meshilensAdviceKey === key) {
        card._meshilensAdvice = { advice: cached };
        syncAdvice(card);
      }
      return;
    }
    const response = await safeRuntimeSendMessage({ type: "GET_DINING_ADVICE", payload });
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
    await safeStorageLocalSet({ diningAdviceCache: Object.fromEntries(entries) });
    if (sequence === lookupSequence && card.isConnected && card._meshilensAdviceKey === key) {
      card._meshilensAdvice = { advice };
      syncAdvice(card);
    }
  } catch (error) {
    if (notePossibleInvalidation(error)) return;
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
    card._meshilensReviewInsights = { status: "idle" };
    syncReviewInsights(card);
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
      card._meshilensAdviceRequestKey = "";
      clearReviewInsightsFlight(card._meshilensReviewInsightsKey);
      softRuntimeSendMessage({ type: "CANCEL_REVIEW_INSIGHTS" }).then((ok) => {
        if (!ok && !isExtensionContextValid()) handleInvalidatedContext();
      });
      card._meshilensReviewInsights = { status: "idle" };
      card._meshilensReviewInsightsKey = "";
      const resultWithMichelin = {
        ...result,
        michelin: card._meshilensMichelin || result.michelin || null,
      };
      card.replaceChildren(...preservedNodes, selectedView(candidate, resultWithMichelin));
      syncAdvice(card);
      syncReviewInsights(card);
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
      if (!card._meshilensMichelin && card._meshilensPlace) {
        refineMichelinWithTabelog(
          card,
          card._meshilensPlace,
          candidate,
          card._meshilensSequence,
        );
      }
    });
    list.append(button);
  }
  toggle.addEventListener("click", () => {
    const hidden = list.classList.toggle("meshilens-hidden");
    toggle.textContent = hidden ? `查看候選店家（${result.candidates.length}）` : "收起候選店家";
  });
  card.append(toggle, list);
}

function tabelogHint(candidate) {
  if (!candidate?.name) return null;
  return {
    name: candidate.name,
    phone: candidate.phone || "",
    website: candidate.website || "",
    latitude: candidate.latitude ?? null,
    longitude: candidate.longitude ?? null,
  };
}

async function refineMichelinWithTabelog(card, place, candidate, sequence) {
  if (!candidate || card._meshilensMichelin) return;
  try {
    if (!ensureExtensionAlive()) return;
    const response = await safeRuntimeSendMessage({
      type: "MATCH_MICHELIN",
      place,
      tabelog: tabelogHint(candidate),
    });
    if (sequence !== lookupSequence || !card.isConnected || !response?.ok) return;
    if (response.data?.michelin) updateMichelin(card, response.data.michelin);
  } catch (error) {
    notePossibleInvalidation(error);
    // Optional refinement; keep the card usable without Michelin.
  }
}

async function lookup(place) {
  if (!ensureExtensionAlive()) return;
  try {
    await safeRuntimeSendMessage({ type: "CANCEL_LOOKUP" });
  } catch (error) {
    if (notePossibleInvalidation(error)) return;
    // Ignore when the service worker is waking up.
  }
  const sequence = ++lookupSequence;
  const card = mountCard(place);
  card._meshilensPlace = place;
  card._meshilensSequence = sequence;
  renderStatus(card, "正在查詢 Tabelog 與 Michelin…");
  const michelinRequest = safeRuntimeSendMessage({ type: "MATCH_MICHELIN", place })
    .then((response) => {
      if (sequence !== lookupSequence || !card.isConnected || !response?.ok) return;
      if (response.data?.michelin) updateMichelin(card, response.data.michelin);
    })
    .catch((error) => {
      notePossibleInvalidation(error);
    });
  try {
    const response = await safeRuntimeSendMessage({ type: "MATCH_PLACE", place });
    if (sequence !== lookupSequence || !card.isConnected) return;
    if (response?.cancelled) return;
    if (!response?.ok) throw new Error(response?.error || "查詢失敗");
    renderResult(card, response.data);
    if (response.data.selected) {
      loadAdvice(card, place, response.data.selected, card._meshilensMichelin || null, sequence);
    }
    await michelinRequest;
    if (response.data.selected && !card._meshilensMichelin) {
      await refineMichelinWithTabelog(card, place, response.data.selected, sequence);
    }
  } catch (error) {
    if (notePossibleInvalidation(error)) return;
    if (sequence !== lookupSequence || !card.isConnected) return;
    renderResult(card, {
      candidates: [],
      michelin: card._meshilensMichelin,
      source: "Tabelog 日本語版",
      tabelog_error: error.message || "Tabelog 查詢失敗",
    });
    await michelinRequest;
  }
}

function removeListHint() {
  document.getElementById(LIST_HINT_ID)?.remove();
}

function positionListHint(hint, feed) {
  const rect = feed.getBoundingClientRect();
  if (rect.width < 80 || rect.height < 40) {
    hint.hidden = true;
    return;
  }
  hint.hidden = false;
  hint.style.top = `${Math.max(10, rect.top + 10)}px`;
  hint.style.left = `${rect.left + 12}px`;
  hint.style.width = `${Math.min(360, Math.max(180, rect.width - 24))}px`;
}

function showListHint() {
  if (currentMapsUiMode() !== LIST_MODE) return;
  const feed = document.querySelector('[role="feed"]');
  if (!feed) {
    removeListHint();
    return;
  }
  let hint = document.getElementById(LIST_HINT_ID);
  if (!hint) {
    hint = element("section", "meshilens-list-hint", "點選店家可查看 MeshiLens");
    hint.id = LIST_HINT_ID;
    hint.setAttribute("aria-label", "MeshiLens 提示");
    document.body.append(hint);
  }
  hint.style.setProperty("--ml-accent", themeColor);
  positionListHint(hint, feed);
}

function removeListBadges() {
  document.querySelectorAll(".meshilens-list-badge").forEach((badge) => badge.remove());
  document.querySelectorAll(".meshilens-list-card").forEach((card) => {
    card.classList.remove("meshilens-list-card");
  });
}

function clearListBadgeState() {
  cancelListBadgeLookup();
  listBadgeCache = new Map();
  removeListBadges();
}

function pauseListPresentation() {
  // Keep cache while detail is open. Maps often rebuilds feed articles on
  // click, so remount badges from cache whenever the feed is still present.
  cancelListBadgeLookup();
  removeListHint();
  remountListBadgesFromCache();
}

function cancelListBadgeLookup() {
  listBatchSequence += 1;
  listAbortController?.abort();
  listAbortController = null;
  listInFlightKeys = null;
  if (!extensionAlive) return;
  softRuntimeSendMessage({ type: "CANCEL_MICHELIN_BATCH" }).then((ok) => {
    if (!ok && !isExtensionContextValid()) handleInvalidatedContext();
  });
}

function pruneDetachedListBadges() {
  document.querySelectorAll(".meshilens-list-badge").forEach((badge) => {
    if (!badge.isConnected || !badge.parentElement?.isConnected) badge.remove();
  });
}

function syncListBadge(card) {
  if (!card?.mount?.isConnected) return;
  const existing = [...card.mount.querySelectorAll(".meshilens-list-badge")];
  for (const node of existing) {
    if (node.dataset.meshilensListKey !== card.key) node.remove();
  }
  if (!listBadgeCache.has(card.key)) return;
  const badge = listBadgeCache.get(card.key);
  if (!badge) return;
  if (existing.some((node) => node.isConnected && node.dataset.meshilensListKey === card.key)) {
    card.mount.classList.add("meshilens-list-card");
    return;
  }
  mountListBadge(card, badge);
}

function collectListCards({ visibleOnly = true, limit = MAX_LIST_CARDS } = {}) {
  const feed = document.querySelector('[role="feed"]');
  if (!feed) return [];
  const feedRect = feed.getBoundingClientRect();
  const top = Math.max(0, feedRect.top);
  const bottom = Math.min(window.innerHeight, feedRect.bottom);
  const seen = new Set();
  const cards = [];
  for (const link of feed.querySelectorAll('a[href*="/maps/place/"]')) {
    const href = link.href || link.getAttribute("href") || "";
    const rawName = link.textContent?.trim() || link.getAttribute("aria-label")?.trim() || "";
    const name = cleanListPlaceName(rawName) || listPlaceNameFromHref(href);
    const mount = link.closest('[role="article"]') || link.parentElement;
    if (!name || !href || !mount) continue;
    if (visibleOnly) {
      const rect = mount.getBoundingClientRect();
      if (rect.bottom <= top || rect.top >= bottom) continue;
    }
    const key = listCardKey({ href, name });
    if (seen.has(key)) continue;
    seen.add(key);
    const coordinates = listCoordinatesFromHref(href);
    cards.push({ key, name, href, ...coordinates, exact_coordinates: true, mount });
    if (cards.length === limit) break;
  }
  return cards;
}

function visibleListCards() {
  return collectListCards({ visibleOnly: true, limit: MAX_LIST_CARDS });
}

function remountListBadgesFromCache() {
  if (!extensionEnabled || !listBadgeCache.size) return;
  if (!document.querySelector('[role="feed"]')) return;
  pruneDetachedListBadges();
  // Detail mode may keep the feed off-screen or rebuild nodes; do not require
  // viewport intersection when restoring cached badges.
  for (const card of collectListCards({ visibleOnly: false, limit: 30 })) {
    syncListBadge(card);
  }
}

function mountListBadge(card, badge) {
  const text = badgeText(badge);
  if (!text || !card.mount?.isConnected) return;
  card.mount.classList.add("meshilens-list-card");
  const node = element(badge.url ? "a" : "span", "meshilens-list-badge", text);
  node.dataset.meshilensListKey = card.key;
  node.setAttribute("aria-label", `Michelin Guide：${text}`);
  if (badge.url) {
    node.href = badge.url;
    node.target = "_blank";
    node.rel = "noopener noreferrer";
  }
  card.mount.append(node);
}

async function loadListBadges() {
  if (!ensureExtensionAlive()) return;
  const mode = currentMapsUiMode();
  if (mode === DETAIL_MODE) {
    remountListBadgesFromCache();
    return;
  }
  if (mode !== LIST_MODE) return;
  pruneDetachedListBadges();
  const cards = visibleListCards();
  for (const card of cards) syncListBadge(card);
  const japanCards = cards.filter((card) => classifyJapanPlace(card) === "japan");
  const missing = listCardsNeedingLookup(japanCards, listBadgeCache);
  if (!missing.length) return;
  if (listBatchCoversKeys(listInFlightKeys, missing)) return;

  cancelListBadgeLookup();
  if (!ensureExtensionAlive()) return;
  const controller = new AbortController();
  listAbortController = controller;
  listInFlightKeys = new Set(missing.map((card) => card.key));
  const sequence = ++listBatchSequence;
  try {
    const response = await safeRuntimeSendMessage({
      type: "MATCH_MICHELIN_BATCH",
      cards: missing.map(({ mount, ...card }) => card),
    });
    if (
      controller.signal.aborted
      || sequence !== listBatchSequence
      || currentMapsUiMode() !== LIST_MODE
      || !response?.ok
    ) return;
    for (const result of response.data?.results || []) {
      rememberListBadgeResult(listBadgeCache, result);
    }
    for (const card of visibleListCards()) syncListBadge(card);
  } catch (error) {
    notePossibleInvalidation(error);
    // List mode remains silent when the optional badge request fails.
  } finally {
    if (listAbortController === controller) {
      listAbortController = null;
      listInFlightKeys = null;
    }
  }
}

function scheduleListBadges(delay = 350) {
  clearTimeout(listDebounceTimer);
  listDebounceTimer = setTimeout(() => {
    if (!ensureExtensionAlive()) return;
    if (currentMapsUiMode() !== LIST_MODE) return;
    activePlaceKey = "";
    document.getElementById(CARD_ID)?.remove();
    showListHint();
    loadListBadges();
  }, delay);
}

function scanDetail() {
  if (!ensureExtensionAlive()) return;
  const place = extractPlace();
  if (!place || classifyJapanPlace(place) !== "japan") {
    activePlaceKey = "";
    document.getElementById(CARD_ID)?.remove();
    return;
  }
  const key = placeKey(place);
  if (key === activePlaceKey && document.getElementById(CARD_ID)) return;
  activePlaceKey = key;
  lookup(place);
}

function scan() {
  if (!ensureExtensionAlive()) return;
  clearTimeout(detailDebounceTimer);
  clearTimeout(listDebounceTimer);
  if (!extensionEnabled) {
    activePlaceKey = "";
    clearListBadgeState();
    removeListHint();
    document.getElementById(CARD_ID)?.remove();
    return;
  }

  const mode = currentMapsUiMode();
  if (mode === DETAIL_MODE) {
    pauseListPresentation();
    detailDebounceTimer = setTimeout(scanDetail, 500);
    return;
  }
  if (mode === LIST_MODE) {
    // List redraws are presentation-only: never cancel an in-flight detail lookup.
    scheduleListBadges(350);
    return;
  }

  activePlaceKey = "";
  clearListBadgeState();
  removeListHint();
  document.getElementById(CARD_ID)?.remove();
}

pageObserver = new MutationObserver((mutations) => {
  if (!ensureExtensionAlive()) return;
  const pageChanged = mutations.some((mutation) => {
    const changedNodes = [...mutation.addedNodes, ...mutation.removedNodes];
    const isMeshiLensUiChange = changedNodes.length > 0 && changedNodes.every(
      (node) => node instanceof Element
        && node.matches(`#${CARD_ID}, #${LIST_HINT_ID}, .meshilens-list-badge`),
    );
    if (isMeshiLensUiChange) return false;
    const target = mutation.target instanceof Element ? mutation.target : mutation.target.parentElement;
    return !target?.closest(`#${CARD_ID}, #${LIST_HINT_ID}, .meshilens-list-badge`);
  });
  if (pageChanged) scan();
});
pageObserver.observe(document.body, { childList: true, subtree: true });
window.addEventListener("popstate", () => {
  if (!ensureExtensionAlive()) return;
  scan();
});
window.addEventListener("scroll", () => {
  if (!ensureExtensionAlive() || !extensionEnabled || currentMapsUiMode() !== LIST_MODE) return;
  const hint = document.getElementById(LIST_HINT_ID);
  const feed = document.querySelector('[role="feed"]');
  if (hint && feed) positionListHint(hint, feed);
  clearTimeout(listScrollTimer);
  listScrollTimer = setTimeout(() => {
    if (!ensureExtensionAlive()) return;
    if (currentMapsUiMode() !== LIST_MODE) return;
    loadListBadges();
  }, 200);
}, true);

try {
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (!ensureExtensionAlive()) return;
    if (areaName !== "local") return;
    if (changes.themeColor) {
      themeColor = normalizeThemeColor(changes.themeColor.newValue);
      document.getElementById(CARD_ID)?.style.setProperty("--ml-accent", themeColor);
      document.getElementById(LIST_HINT_ID)?.style.setProperty("--ml-accent", themeColor);
    }
    if (changes.enabled) {
      extensionEnabled = changes.enabled.newValue !== false;
      activePlaceKey = "";
      if (!extensionEnabled) {
        lookupSequence += 1;
        clearTimeout(detailDebounceTimer);
        clearTimeout(listDebounceTimer);
        clearTimeout(listScrollTimer);
        softRuntimeSendMessage({ type: "CANCEL_LOOKUP" });
        clearListBadgeState();
        removeListHint();
        document.getElementById(CARD_ID)?.remove();
        return;
      }
      scan();
    }
  });
} catch (error) {
  notePossibleInvalidation(error);
}

safeStorageLocalGet({ enabled: true, themeColor: DEFAULT_THEME_COLOR })
  .then(({ enabled, themeColor: savedThemeColor }) => {
    if (!ensureExtensionAlive()) return;
    extensionEnabled = enabled;
    themeColor = normalizeThemeColor(savedThemeColor);
    scan();
  })
  .catch((error) => {
    notePossibleInvalidation(error);
  });
