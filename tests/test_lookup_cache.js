const assert = require("node:assert/strict");
const test = require("node:test");

require("../extension/cache.js");

const {
  LOOKUP_CACHE_TTL_MS,
  MATCH_LOOKUP_CACHE_TTL_MS,
  lookupTtlMs,
  roundCoord,
  placeCacheKey,
  tabelogCacheSuffix,
  lookupCacheKey,
  cachedLookupEntry,
  getCachedLookup,
  setCachedLookup,
  clearMemoryLookupCache,
} = globalThis.MeshiLensCache;

test("rounds coordinates to reduce Maps jitter cache misses", () => {
  assert.equal(roundCoord(35.681236123), "35.68124");
  assert.equal(roundCoord(139.767124999), "139.76712");
  assert.equal(roundCoord(null), "");
  assert.equal(roundCoord(undefined), "");
  assert.equal(roundCoord(""), "");
});

test("place cache key ignores tiny coordinate changes", () => {
  const left = placeCacheKey({
    name: "清水屋",
    phone: "0299-64-2011",
    latitude: 35.6812361,
    longitude: 139.7671241,
  });
  const right = placeCacheKey({
    name: "清水屋",
    phone: "0299-64-2011",
    latitude: 35.6812364,
    longitude: 139.7671244,
  });
  assert.equal(left, right);
  assert.equal(lookupCacheKey("match", left), `match:${left}`);
});

test("lookup cache TTL follows the server for each kind", () => {
  assert.equal(lookupTtlMs("match-v2"), 6 * 60 * 60 * 1000);
  assert.equal(lookupTtlMs("michelin"), 24 * 60 * 60 * 1000);
  assert.equal(lookupTtlMs("similar"), 12 * 60 * 60 * 1000);
  assert.equal(lookupTtlMs("popularity"), 24 * 60 * 60 * 1000);
  assert.equal(LOOKUP_CACHE_TTL_MS.michelin, 24 * 60 * 60 * 1000);
  assert.equal(MATCH_LOOKUP_CACHE_TTL_MS, 6 * 60 * 60 * 1000);
});

test("lookup cache entry expires after TTL", () => {
  const key = "match:demo";
  const entry = { key, savedAt: 1_000, data: { matched: true } };
  const ttl = lookupTtlMs("match");
  assert.deepEqual(cachedLookupEntry(entry, key, 1_000 + ttl), { matched: true });
  assert.equal(cachedLookupEntry(entry, key, 1_000 + ttl + 1), null);
  assert.equal(cachedLookupEntry(entry, "other", 1_500), null);
});

test("michelin lookup cache outlives the match TTL", () => {
  const key = "michelin:demo";
  const entry = { key, savedAt: 1_000, data: { michelin: { distinction_label: "一星" } } };
  assert.deepEqual(
    cachedLookupEntry(entry, key, 1_000 + lookupTtlMs("match") + 1),
    { michelin: { distinction_label: "一星" } },
  );
  assert.equal(
    cachedLookupEntry(entry, key, 1_000 + lookupTtlMs("michelin") + 1),
    null,
  );
});

test("memory lookup cache stores match results", async () => {
  clearMemoryLookupCache();
  const place = { name: "清水屋", latitude: 36.17527, longitude: 139.83725 };
  assert.equal(await getCachedLookup("match", place, 5_000), null);
  await setCachedLookup("match", place, { matched: true, selected: { name: "清水屋" } }, 5_000);
  const cached = await getCachedLookup("match", place, 6_000);
  assert.equal(cached.matched, true);
  assert.equal(cached.cached, true);
  assert.equal(await getCachedLookup("match", place, 5_000 + lookupTtlMs("match") + 1), null);
});

test("tabelog-assisted michelin cache uses a separate suffix", async () => {
  clearMemoryLookupCache();
  const place = { name: "Shimizuya", latitude: 35.65, longitude: 139.7 };
  const tabelog = { name: "清水屋", phone: "03-1111-2222" };
  const suffix = tabelogCacheSuffix(tabelog);
  assert.match(suffix, /^tg:清水屋:/);
  await setCachedLookup("michelin", place, { michelin: null }, { now: 1_000 });
  await setCachedLookup(
    "michelin",
    place,
    { michelin: { distinction_label: "一星" } },
    { now: 1_000, suffix },
  );
  assert.equal((await getCachedLookup("michelin", place, { now: 2_000 })).michelin, null);
  assert.equal(
    (await getCachedLookup("michelin", place, { now: 2_000, suffix })).michelin.distinction_label,
    "一星",
  );
});
