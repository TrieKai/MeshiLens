const shareRoot = document.getElementById("share-root");
const MAX_DECOMPRESSED_BYTES = 100_000;

function text(value, limit = 240) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, limit);
}

function webUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch {
    return "";
  }
}

function choice(value) {
  if (!value?.name) return null;
  return {
    name: text(value.name, 160),
    mapsUrl: webUrl(value.mapsUrl),
    rating: Number.isFinite(value.rating) ? value.rating : null,
    michelinLabel: text(value.michelinLabel, 80),
  };
}

function sanitizePayload(value) {
  if (!value || value.v !== 1 || !text(value.title, 120) || !Array.isArray(value.groups)) return null;
  const groups = [];
  for (const item of value.groups.slice(0, 12)) {
    const primary = choice(item?.primary);
    const backup = choice(item?.backup);
    if (!primary && !backup) continue;
    groups.push({
      name: text(item?.name, 120),
      anchor: text(item?.anchor, 120),
      date: /^\d{4}-\d{2}-\d{2}$/.test(String(item?.date || "")) ? String(item.date) : "",
      meal: ["lunch", "dinner"].includes(item?.meal) ? item.meal : "",
      primary,
      backup,
    });
  }
  return { v: 1, title: text(value.title, 120), groups };
}

function lzwDecompress(bytes) {
  if (!bytes.length || bytes.length % 2 !== 0) throw new Error("invalid compressed trip");
  const codes = [];
  for (let index = 0; index < bytes.length; index += 2) {
    codes.push((bytes[index] << 8) | bytes[index + 1]);
  }
  const dictionary = [];
  let nextCode = 256;
  let phrase = String.fromCharCode(codes[0]);
  let output = phrase;
  for (let index = 1; index < codes.length; index += 1) {
    const code = codes[index];
    const entry = code < 256
      ? String.fromCharCode(code)
      : dictionary[code] || (code === nextCode ? phrase + phrase[0] : "");
    if (!entry) throw new Error("invalid compressed trip");
    if (output.length + entry.length > MAX_DECOMPRESSED_BYTES) {
      throw new Error("compressed trip is too large");
    }
    output += entry;
    if (nextCode <= 65_535) dictionary[nextCode++] = phrase + entry[0];
    phrase = entry;
  }
  return Uint8Array.from(output, (character) => character.charCodeAt(0));
}

function decodePayload(fragment) {
  try {
    const encoded = String(fragment || "").replace(/^#/, "");
    if (!encoded || encoded.length > 20_000) return null;
    const base64 = encoded.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - base64.length % 4) % 4);
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const jsonBytes = bytes[0] === 0x4d && bytes[1] === 0x4c && bytes[2] === 0x01
      ? lzwDecompress(bytes.slice(3))
      : bytes;
    const decoded = JSON.parse(new TextDecoder().decode(jsonBytes));
    const expanded = Array.isArray(decoded) && Array.isArray(decoded[2])
      ? {
          v: decoded[0],
          title: decoded[1],
          groups: decoded[2].map((group) => ({
            name: group?.[0],
            anchor: group?.[1],
            date: group?.[2],
            meal: group?.[3] === "l" ? "lunch" : group?.[3] === "d" ? "dinner" : "",
            primary: Array.isArray(group?.[4]) ? {
              name: group[4][0],
              mapsUrl: group[4][1],
              rating: group[4][2],
              michelinLabel: group[4][3],
            } : null,
            backup: Array.isArray(group?.[5]) ? {
              name: group[5][0],
              mapsUrl: group[5][1],
              rating: group[5][2],
              michelinLabel: group[5][3],
            } : null,
          })),
        }
      : decoded;
    return sanitizePayload(expanded);
  } catch {
    return null;
  }
}

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = value;
  return node;
}

function choiceCard(item, role) {
  const card = element("article", `share-choice${role === "首選" ? " is-primary" : ""}`);
  card.append(element("div", "share-role", role));
  card.append(element("h3", "", item.name));
  const meta = [
    Number.isFinite(item.rating) ? `Tabelog ${item.rating.toFixed(2)}` : "",
    item.michelinLabel ? `Michelin ${item.michelinLabel}` : "",
  ].filter(Boolean).join(" · ");
  if (meta) card.append(element("div", "share-meta", meta));
  if (item.mapsUrl) {
    const link = element("a", "share-map-link", "在 Google Maps 開啟");
    link.href = item.mapsUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    card.append(link);
  }
  return card;
}

function renderShare() {
  const payload = decodePayload(location.hash);
  if (!payload || !payload.groups.length) {
    const message = element(
      "section",
      "share-message is-error",
      "這個行程連結無效或沒有已選定的餐廳。請回到 MeshiLens 重新產生分享連結。",
    );
    shareRoot.replaceChildren(message);
    return;
  }
  document.title = `${payload.title}｜MeshiLens`;
  const title = element("h1", "share-title", payload.title);
  const summary = element("p", "share-summary", `${payload.groups.length} 個用餐場合 · 首選與備案`);
  const groups = element("div", "share-groups");
  for (const item of payload.groups) {
    const section = element("section", "share-group");
    section.append(element("h2", "", item.name || "用餐安排"));
    const context = [
      item.date,
      item.meal === "lunch" ? "午餐" : item.meal === "dinner" ? "晚餐" : "",
      item.anchor ? `集合點：${item.anchor}` : "",
    ].filter(Boolean).join(" · ");
    if (context) section.append(element("div", "share-context", context));
    const choices = element("div", "share-choices");
    if (item.primary) choices.append(choiceCard(item.primary, "首選"));
    if (item.backup) choices.append(choiceCard(item.backup, "備案"));
    section.append(choices);
    groups.append(section);
  }
  shareRoot.replaceChildren(title, summary, groups);
}

window.addEventListener("hashchange", renderShare);
renderShare();
