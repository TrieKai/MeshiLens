const CARD_ID = "meshilens-card";
const ADDRESS_PREFIX = /^(地址|住所|address)\s*[:：]?\s*/i;
const PHONE_PREFIX = /^(電話|電話番号|phone)\s*[:：]?\s*/i;
const { foodSignalsFromLabels, isFoodPlace } = globalThis.MeshiLensCategory;
const { coordinatesFromMapsUrl } = globalThis.MeshiLensMaps;
let activePlaceKey = "";
let lookupSequence = 0;
let debounceTimer = null;

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
  const hyakumeiten = candidate.hyakumeiten || [];
  if (candidate.is_hyakumeiten && hyakumeiten.length) {
    const awards = element("div", "meshilens-awards");
    for (const selection of hyakumeiten) {
      const award = element("a", "meshilens-hyakumeiten");
      const category = [selection.category, selection.area].filter(Boolean).join(" ");
      award.textContent = `百名店 ${selection.year}${category ? ` · ${category}` : ""}`;
      award.href = selection.url;
      award.target = "_blank";
      award.rel = "noopener noreferrer";
      award.title = selection.label || award.textContent;
      awards.append(award);
    }
    container.append(awards);
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

  const selected = result.selected;
  if (!selected) {
    card.append(element("div", "meshilens-status", "找不到可信的 Tabelog 店家，請從候選結果選擇。"));
  } else {
    card.append(selectedView(selected, result));
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
      card.replaceChildren(headerNode, selectedView(candidate, result));
      card.append(toggle, list);
      list.classList.add("meshilens-hidden");
      toggle.textContent = `查看候選店家（${result.candidates.length}）`;
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
  renderStatus(card, "正在比對 Tabelog 店家…");
  try {
    const response = await chrome.runtime.sendMessage({ type: "MATCH_PLACE", place });
    if (sequence !== lookupSequence || !card.isConnected) return;
    if (!response?.ok) throw new Error(response?.error || "查詢失敗");
    renderResult(card, response.data);
  } catch (error) {
    if (sequence !== lookupSequence || !card.isConnected) return;
    renderStatus(card, error.message || "Tabelog 查詢失敗");
  }
}

function scan() {
  clearTimeout(debounceTimer);
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
scan();
