package com.meshilens.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LookupCacheTest {
    @Test
    fun entriesExpireAfterTheTtl() {
        var now = 0L
        val cache = LookupCache(maxEntries = 4, ttlMillis = 1_000, clock = { now })
        cache.put("a", "1")

        now = 1_000
        assertEquals("1", cache.get("a"))
        now = 1_001
        assertNull(cache.get("a"))
    }

    @Test
    fun evictsTheLeastRecentlyUsedEntry() {
        val cache = LookupCache(maxEntries = 2, ttlMillis = 60_000, clock = { 0L })
        cache.put("a", "1")
        cache.put("b", "2")
        cache.get("a")
        cache.put("c", "3")

        assertEquals("1", cache.get("a"))
        assertNull(cache.get("b"))
        assertEquals("3", cache.get("c"))
    }
}
