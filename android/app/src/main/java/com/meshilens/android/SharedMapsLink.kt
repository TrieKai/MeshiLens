package com.meshilens.android

import java.net.URLDecoder

/**
 * Parses what Google Maps shares into a lookup identity: the text is only a
 * maps.app.goo.gl link, and the place name travels separately as the share title.
 */
object SharedMapsLink {
    data class Shared(val name: String, val url: String, val otherLines: List<String>)

    private val URL_PATTERN = Regex("""https?://[^\s<>"'「」]+""")
    private val SHORT_LINK_HOSTS = setOf("maps.app.goo.gl", "goo.gl", "g.co")
    private val GOOGLE_HOST = Regex("""^(?:(?:www|maps)\.)?google\.(?:com|co\.jp|com\.tw)$""")
    private val PLACE_COORDINATES = Regex("""!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)""")
    private val LABEL_SEPARATOR = Regex("""^[\s,，、]+""")

    fun parse(text: String?, title: String? = null): Shared? {
        val value = text?.trim().orEmpty()
        val url = URL_PATTERN.find(value)?.value?.trimEnd('.', ',', ')', '，', '。') ?: return null
        if (!isShortLink(url) && !isGoogleMapsUrl(url)) return null
        val lines = value.replace(url, "\n").lines().map { it.trim() }.filter { it.isNotEmpty() }
        val name = title?.trim().orEmpty().ifEmpty { lines.firstOrNull().orEmpty() }
        return Shared(name = name, url = url, otherLines = lines.filter { it != name })
    }

    fun isShortLink(url: String): Boolean = url.startsWith("https://") && host(url) in SHORT_LINK_HOSTS

    fun isGoogleMapsUrl(url: String): Boolean {
        if (!url.startsWith("https://")) return false
        val host = host(url)
        return GOOGLE_HOST.matches(host) && (host.startsWith("maps.") || path(url).startsWith("maps"))
    }

    /**
     * The resolved link looks like `google.com/maps/place/<店名+地址>/data=…`; the label
     * joins name and address without a separator, so the shared name splits them.
     */
    fun placeFrom(shared: Shared, resolvedUrl: String): PlaceSnapshot? {
        val label = placeLabel(resolvedUrl)
        val name = shared.name.ifEmpty { label.substringBefore(",").trim() }
        if (name.isEmpty()) return null
        val address = when {
            label.startsWith(name) -> label.removePrefix(name).replaceFirst(LABEL_SEPARATOR, "").trim()
            label.contains(",") -> label.substringAfter(",").trim()
            else -> ""
        }.ifEmpty { shared.otherLines.firstOrNull { JapanPlace.hasJapanSignal(it, "") }.orEmpty() }
        val coordinates = PLACE_COORDINATES.findAll(resolvedUrl).lastOrNull()?.groupValues
        val latitude = coordinates?.get(1)?.toDoubleOrNull()
        val longitude = coordinates?.get(2)?.toDoubleOrNull()
        return PlaceSnapshot(
            name = name,
            address = address,
            latitude = latitude,
            longitude = longitude,
            exactCoordinates = latitude != null && longitude != null,
        )
    }

    private fun placeLabel(url: String): String {
        val path = path(url)
        val segment = when {
            path.startsWith("maps/place/") -> path.removePrefix("maps/place/").substringBefore('/')
            else -> query(url)["q"].orEmpty()
        }
        return runCatching { URLDecoder.decode(segment, "UTF-8") }.getOrDefault("").trim()
    }

    private fun host(url: String): String =
        url.substringAfter("://", "").substringBefore('/').substringBefore('?').substringBefore('#').lowercase()

    private fun path(url: String): String =
        url.substringAfter("://", "").substringAfter('/', "").substringBefore('?').substringBefore('#')

    private fun query(url: String): Map<String, String> = url
        .substringAfter('?', "")
        .substringBefore('#')
        .split('&')
        .filter { it.contains('=') }
        .associate { it.substringBefore('=') to it.substringAfter('=') }
}
