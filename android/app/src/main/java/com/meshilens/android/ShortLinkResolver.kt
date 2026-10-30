package com.meshilens.android

import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Expands a maps.app.goo.gl share link by reading its redirects only; the
 * Google Maps page itself is never fetched.
 */
object ShortLinkResolver {
    private const val MAX_REDIRECTS = 5
    private const val TIMEOUT_MS = 10_000

    fun resolve(url: String, userAgent: String): String {
        var current = url
        repeat(MAX_REDIRECTS) {
            if (!SharedMapsLink.isShortLink(current)) return current
            current = nextLocation(current, userAgent)
        }
        if (SharedMapsLink.isShortLink(current)) throw LookupException("無法展開 Google 地圖短網址")
        return current
    }

    private fun nextLocation(url: String, userAgent: String): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = false
            connectTimeout = TIMEOUT_MS
            readTimeout = TIMEOUT_MS
            setRequestProperty("User-Agent", userAgent)
        }
        try {
            val status = connection.responseCode
            val location = connection.getHeaderField("Location")
            if (status !in 300..399 || location.isNullOrBlank()) {
                throw LookupException("無法展開 Google 地圖短網址（$status）")
            }
            val next = URL(URL(url), location).toString()
            if (!next.startsWith("https://")) throw LookupException("Google 地圖連結格式不正確")
            return next
        } catch (error: IOException) {
            throw LookupException("無法連上 Google 地圖，請檢查網路")
        } finally {
            connection.disconnect()
        }
    }
}
