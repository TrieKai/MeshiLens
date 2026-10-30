package com.meshilens.android

import org.json.JSONArray
import org.json.JSONObject

/** JSON shapes shared with extension/background.js and src/meshi_lens/service.py. */
object LookupJson {

    /** Same fields and length limits as `placePayload` / `tabelogPayload` in background.js. */
    fun placePayload(place: PlaceSnapshot, tabelog: TabelogCandidate? = null): JSONObject {
        val payload = JSONObject()
            .put("name", place.name.take(200))
            .put("alternate_name", "")
            .put("address", place.address.take(500))
            .put("phone", place.phone.take(50))
            .put("website", place.website.take(500))
            .put("tabelog_url", "")
            .put("latitude", place.latitude ?: JSONObject.NULL)
            .put("longitude", place.longitude ?: JSONObject.NULL)
            .put("coordinates_source", if (place.exactCoordinates) "place" else "")
        val hintName = tabelog?.name?.trim().orEmpty()
        if (tabelog != null && hintName.isNotEmpty()) {
            payload.put(
                "tabelog",
                JSONObject()
                    .put("name", hintName.take(200))
                    .put("phone", tabelog.phone.trim().take(50))
                    .put("website", tabelog.website.trim().take(500))
                    .put("latitude", tabelog.latitude ?: JSONObject.NULL)
                    .put("longitude", tabelog.longitude ?: JSONObject.NULL),
            )
        }
        return payload
    }

    fun matchResult(json: JSONObject): MatchResult = MatchResult(
        selected = json.optJSONObject("selected")?.let(::candidate),
        candidates = json.optJSONArray("candidates").objects().map(::candidate),
        michelin = json.optJSONObject("michelin")?.let(::michelin),
        tabelogError = json.text("tabelog_error"),
        cached = json.optBoolean("cached"),
    )

    fun michelinResult(json: JSONObject): MichelinEntry? = json.optJSONObject("michelin")?.let(::michelin)

    fun errorMessage(json: JSONObject?): String = json?.text("error").orEmpty()

    private fun candidate(json: JSONObject) = TabelogCandidate(
        name = json.text("name"),
        rating = json.number("rating"),
        reviewCount = json.number("review_count")?.toInt(),
        url = json.text("url"),
        address = json.text("address"),
        phone = json.text("phone"),
        website = json.text("website"),
        latitude = json.number("latitude"),
        longitude = json.number("longitude"),
        genres = json.optJSONArray("genres").strings(),
        station = json.text("station"),
        lunchPrice = json.text("lunch_price"),
        dinnerPrice = json.text("dinner_price"),
        closedDays = json.text("closed_days"),
        confidence = json.text("confidence"),
        matchReasons = json.optJSONArray("match_reasons").strings(),
        hyakumeiten = json.optJSONArray("hyakumeiten").objects().map(::hyakumeiten),
        isRelocated = json.optBoolean("is_relocated"),
    )

    private fun michelin(json: JSONObject) = MichelinEntry(
        name = json.text("name"),
        url = json.text("url"),
        distinctionLabel = json.text("distinction_label").ifEmpty { "米其林指南入選" },
        greenStar = json.optBoolean("green_star"),
        cuisine = json.text("cuisine"),
        price = json.text("price"),
        location = json.text("location"),
    )

    private fun hyakumeiten(json: JSONObject) = HyakumeitenSelection(
        year = json.number("year")?.toInt()?.takeIf { it > 0 },
        category = json.text("category"),
        area = json.text("area"),
        label = json.text("label"),
        url = json.text("url"),
    )

    // Android's org.json turns JSON null into the string "null" in optString, so read raw values.
    private fun JSONObject.text(key: String): String =
        if (isNull(key)) "" else opt(key)?.toString()?.trim().orEmpty()

    private fun JSONObject.number(key: String): Double? {
        if (isNull(key)) return null
        val value = when (val raw = opt(key)) {
            is Number -> raw.toDouble()
            is String -> raw.trim().toDoubleOrNull()
            else -> null
        }
        return value?.takeIf { it.isFinite() }
    }

    private fun JSONArray?.objects(): List<JSONObject> =
        if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }

    private fun JSONArray?.strings(): List<String> =
        if (this == null) {
            emptyList()
        } else {
            (0 until length()).mapNotNull { index ->
                if (isNull(index)) null else opt(index)?.toString()?.trim()?.takeIf { it.isNotEmpty() }
            }
        }
}
