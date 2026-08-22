(() => {
  const SHARE_VERSION = 1;
  const DEFAULT_SHARE_BASE_URL = "https://meshilens.vercel.app/landing/share.html";
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

  function finiteCoord(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function isSpecificMapsUrl(value) {
    try {
      const url = new URL(String(value || ""));
      if (url.protocol !== "https:" && url.protocol !== "http:") return false;
      const body = `${url.pathname}${url.search}${url.hash}`;
      return /!3d-?\d/.test(body)
        || /\/@-?\d+(?:\.\d+)?,-?\d+/.test(body)
        || url.searchParams.has("cid")
        || url.searchParams.has("query_place_id")
        || url.searchParams.get("api") === "1"
        || /\/data=/.test(url.pathname);
    } catch {
      return false;
    }
  }

  function openMapsUrl(value = {}) {
    const mapsUrl = webUrl(value.mapsUrl);
    if (mapsUrl && isSpecificMapsUrl(mapsUrl)) return mapsUrl;
    const name = text(value.name, 160);
    const latitude = finiteCoord(value.latitude);
    const longitude = finiteCoord(value.longitude);
    const query = name && latitude !== null && longitude !== null
      ? `${name} ${latitude},${longitude}`
      : name || (latitude !== null && longitude !== null ? `${latitude},${longitude}` : "");
    if (!query) return mapsUrl;
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
  }

  function choice(value) {
    if (!value?.name) return null;
    return {
      name: text(value.name, 160),
      mapsUrl: webUrl(value.mapsUrl),
      rating: Number.isFinite(value.rating) ? value.rating : null,
      michelinLabel: text(value.michelinLabel, 80),
      latitude: finiteCoord(value.latitude),
      longitude: finiteCoord(value.longitude),
      reason: text(value.reason, 80),
    };
  }

  function buildSharePayload(state, tripId) {
    const trip = state?.trips?.find((item) => item.id === tripId);
    if (!trip) return null;
    const groups = [];
    for (const group of Array.isArray(trip.groups) ? trip.groups : []) {
      const ranked = globalThis.MeshiLensPlanner?.rankGroup?.(group) || [];
      const reasons = new Map(ranked.map((item) => [item.restaurant.id, item.advantages?.[0] || ""]));
      const primaryRestaurant = group.restaurants?.find((item) => item.id === group.primaryId);
      const backupRestaurant = group.restaurants?.find((item) => item.id === group.backupId);
      const primary = choice(primaryRestaurant
        ? { ...primaryRestaurant, reason: reasons.get(primaryRestaurant.id) }
        : null);
      const backup = choice(backupRestaurant
        ? { ...backupRestaurant, reason: reasons.get(backupRestaurant.id) }
        : null);
      if (!primary && !backup) continue;
      groups.push({
        name: text(group.name, 120),
        anchor: text(group.anchor?.name, 120),
        date: /^\d{4}-\d{2}-\d{2}$/.test(String(group.date || "")) ? String(group.date) : "",
        meal: ["lunch", "dinner"].includes(group.meal) ? group.meal : "",
        primary,
        backup,
      });
    }
    return { v: SHARE_VERSION, title: text(trip.name, 120), groups };
  }

  function mealConclusion(group) {
    const primary = text(group?.primary?.name, 160);
    const backup = text(group?.backup?.name, 160);
    if (primary && backup) return `這一餐：${primary}，備案 ${backup}`;
    if (primary) return `這一餐：${primary}`;
    if (backup) return `這一餐備案：${backup}`;
    return "";
  }

  function sanitizeSharePayload(value) {
    if (!value || value.v !== SHARE_VERSION) return null;
    const title = text(value.title, 120);
    if (!title || !Array.isArray(value.groups)) return null;
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
    return { v: SHARE_VERSION, title, groups };
  }

  function base64UrlEncodeBytes(bytes) {
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  function base64UrlDecodeBytes(value) {
    const base64 = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - base64.length % 4) % 4);
    const binary = atob(padded);
    return Uint8Array.from(binary, (character) => character.charCodeAt(0));
  }

  function lzwCompress(bytes) {
    if (!bytes.length) return new Uint8Array();
    const dictionary = new Map();
    const codes = [];
    let nextCode = 256;
    let phrase = String.fromCharCode(bytes[0]);
    for (let index = 1; index < bytes.length; index += 1) {
      const character = String.fromCharCode(bytes[index]);
      const combined = phrase + character;
      if (dictionary.has(combined)) {
        phrase = combined;
        continue;
      }
      codes.push(phrase.length === 1 ? phrase.charCodeAt(0) : dictionary.get(phrase));
      if (nextCode <= 65_535) dictionary.set(combined, nextCode++);
      phrase = character;
    }
    codes.push(phrase.length === 1 ? phrase.charCodeAt(0) : dictionary.get(phrase));
    const result = new Uint8Array(codes.length * 2);
    codes.forEach((code, index) => {
      result[index * 2] = code >>> 8;
      result[index * 2 + 1] = code & 0xff;
    });
    return result;
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

  function compactChoice(value) {
    if (!value) return null;
    const row = [
      value.name,
      value.mapsUrl,
      value.rating,
      value.michelinLabel,
      value.latitude,
      value.longitude,
      value.reason || "",
    ];
    while (row.length > 4 && (row[row.length - 1] === "" || row[row.length - 1] == null)) {
      row.pop();
    }
    return row;
  }

  function compactPayload(value) {
    return [
      value.v,
      value.title,
      value.groups.map((group) => [
        group.name,
        group.anchor,
        group.date,
        group.meal === "lunch" ? "l" : group.meal === "dinner" ? "d" : "",
        compactChoice(group.primary),
        compactChoice(group.backup),
      ]),
    ];
  }

  function expandChoice(value) {
    if (!Array.isArray(value)) return null;
    return {
      name: value[0],
      mapsUrl: value[1],
      rating: value[2],
      michelinLabel: value[3],
      latitude: value[4],
      longitude: value[5],
      reason: value[6],
    };
  }

  function expandPayload(value) {
    if (!Array.isArray(value) || !Array.isArray(value[2])) return value;
    return {
      v: value[0],
      title: value[1],
      groups: value[2].map((group) => ({
        name: group?.[0],
        anchor: group?.[1],
        date: group?.[2],
        meal: group?.[3] === "l" ? "lunch" : group?.[3] === "d" ? "dinner" : "",
        primary: expandChoice(group?.[4]),
        backup: expandChoice(group?.[5]),
      })),
    };
  }

  function encodeSharePayload(payload) {
    const safePayload = sanitizeSharePayload(payload);
    if (!safePayload) return "";
    const jsonBytes = new TextEncoder().encode(JSON.stringify(compactPayload(safePayload)));
    const compressed = lzwCompress(jsonBytes);
    const bytes = new Uint8Array(compressed.length + 3);
    bytes.set([0x4d, 0x4c, 0x01]);
    bytes.set(compressed, 3);
    return base64UrlEncodeBytes(bytes);
  }

  function decodeSharePayload(fragment) {
    try {
      const encoded = String(fragment || "").replace(/^#/, "");
      if (!encoded || encoded.length > 20_000) return null;
      const bytes = base64UrlDecodeBytes(encoded);
      const jsonBytes = bytes[0] === 0x4d && bytes[1] === 0x4c && bytes[2] === 0x01
        ? lzwDecompress(bytes.slice(3))
        : bytes;
      const decoded = JSON.parse(new TextDecoder().decode(jsonBytes));
      return sanitizeSharePayload(expandPayload(decoded));
    } catch {
      return null;
    }
  }

  function buildShareUrl(payload, baseUrl = DEFAULT_SHARE_BASE_URL) {
    const encoded = encodeSharePayload(payload);
    if (!encoded) return "";
    try {
      const url = new URL(String(baseUrl || DEFAULT_SHARE_BASE_URL));
      if (url.protocol !== "https:" && url.protocol !== "http:") return "";
      url.hash = encoded;
      return url.href;
    } catch {
      return "";
    }
  }

  globalThis.MeshiLensPlannerShare = {
    SHARE_VERSION,
    DEFAULT_SHARE_BASE_URL,
    buildSharePayload,
    sanitizeSharePayload,
    encodeSharePayload,
    decodeSharePayload,
    buildShareUrl,
    openMapsUrl,
    mealConclusion,
  };
})();
