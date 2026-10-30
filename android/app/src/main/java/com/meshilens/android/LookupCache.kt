package com.meshilens.android

/** Small LRU with expiry for API responses; the server keeps its own longer cache. */
class LookupCache(
    private val maxEntries: Int,
    private val ttlMillis: Long,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private class Entry(val value: String, val storedAt: Long)

    private val entries = object : LinkedHashMap<String, Entry>(16, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Entry>?): Boolean = size > maxEntries
    }

    @Synchronized
    fun get(key: String): String? {
        val entry = entries[key] ?: return null
        if (clock() - entry.storedAt > ttlMillis) {
            entries.remove(key)
            return null
        }
        return entry.value
    }

    @Synchronized
    fun put(key: String, value: String) {
        entries[key] = Entry(value, clock())
    }
}
