package com.meshilens.android

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL

/**
 * Calls the MeshiLens cloud API (`DEFAULT_API_URL` in extension/settings.js).
 *
 * Responses are cached briefly in memory so leaving and re-opening the same
 * place in Maps never repeats a request.
 */
class MeshiLensApi(
    private val userAgent: String,
    private val baseUrl: String = DEFAULT_API_URL,
) : LookupClient {
    private val cache = LookupCache(maxEntries = 60, ttlMillis = CACHE_TTL_MS)

    override fun match(place: PlaceSnapshot): MatchResult =
        LookupJson.matchResult(JSONObject(cachedPost("/match", "match|${place.cacheKey}", LookupJson.placePayload(place))))

    override fun michelin(place: PlaceSnapshot, tabelog: TabelogCandidate?): MichelinEntry? {
        val key = "michelin|${place.cacheKey}|${tabelog?.url.orEmpty()}"
        return LookupJson.michelinResult(JSONObject(cachedPost("/michelin", key, LookupJson.placePayload(place, tabelog))))
    }

    private fun cachedPost(path: String, key: String, body: JSONObject): String =
        cache.get(key) ?: post(path, body).also { cache.put(key, it) }

    private fun post(path: String, body: JSONObject): String {
        val connection = (URL(baseUrl + path).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = READ_TIMEOUT_MS
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", userAgent)
        }
        try {
            connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            val json = runCatching { JSONObject(text) }.getOrNull()
            if (status !in 200..299) {
                throw LookupException(LookupJson.errorMessage(json).ifEmpty { "MeshiLens 服務回傳 $status" })
            }
            if (json == null) throw LookupException("MeshiLens 服務回應格式不正確")
            return text
        } catch (error: SocketTimeoutException) {
            throw LookupException("Tabelog 查詢逾時，請稍後再試")
        } catch (error: IOException) {
            throw LookupException("無法連上 MeshiLens 服務，請檢查網路")
        } finally {
            connection.disconnect()
        }
    }

    companion object {
        const val DEFAULT_API_URL = "https://meshilens.vercel.app/api"
        private const val CONNECT_TIMEOUT_MS = 10_000
        private const val READ_TIMEOUT_MS = 35_000
        private const val CACHE_TTL_MS = 30 * 60 * 1000L
    }
}
