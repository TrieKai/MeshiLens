package com.meshilens.android

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LookupJsonTest {
    @Test
    fun placePayloadMatchesTheExtensionShape() {
        val place = PlaceSnapshot(name = "一蘭 澀谷店", address = MapsFixtures.LOCAL_ADDRESS, phone = MapsFixtures.PHONE)

        val payload = LookupJson.placePayload(place)

        assertEquals(
            setOf("name", "alternate_name", "address", "phone", "website", "tabelog_url", "latitude", "longitude", "coordinates_source"),
            payload.keys().asSequence().toSet(),
        )
        assertTrue(payload.isNull("latitude"))
        assertEquals("", payload.getString("coordinates_source"))
        assertFalse(payload.has("tabelog"))
    }

    @Test
    fun placePayloadCarriesTheTabelogHintAndExactCoordinates() {
        val place = PlaceSnapshot(name = "x".repeat(300), latitude = 35.66, longitude = 139.70, exactCoordinates = true)
        val hint = TabelogCandidate(name = "一蘭 渋谷店", rating = 3.21, reviewCount = 649, url = "u", phone = "050-1808-2546")

        val payload = LookupJson.placePayload(place, hint)

        assertEquals(200, payload.getString("name").length)
        assertEquals("place", payload.getString("coordinates_source"))
        assertEquals("一蘭 渋谷店", payload.getJSONObject("tabelog").getString("name"))
        assertTrue(payload.getJSONObject("tabelog").isNull("latitude"))
    }

    @Test
    fun parsesAMatchResponse() {
        val result = LookupJson.matchResult(JSONObject(MATCH_RESPONSE))

        val selected = result.selected!!
        assertEquals("一蘭 渋谷店", selected.name)
        assertEquals(3.21, selected.rating!!, 0.0)
        assertEquals(649, selected.reviewCount)
        assertTrue(selected.isConfident)
        assertEquals(listOf("電話完全相同", "地址高度相似"), selected.matchReasons)
        assertEquals(listOf("ラーメン"), selected.genres)
        assertTrue(selected.hyakumeiten.isEmpty())
        assertEquals(3, result.candidates.size)
        assertEquals(2025, result.candidates[2].hyakumeiten.single().year)
        assertNull(result.michelin)
        assertEquals("", result.tabelogError)
    }

    @Test
    fun jsonNullsBecomeEmptyValues() {
        val result = LookupJson.matchResult(
            JSONObject("""{"selected": null, "candidates": [{"name": "店", "rating": null, "review_count": "12", "station": null}], "tabelog_error": null}"""),
        )

        assertNull(result.selected)
        assertNull(result.candidates.single().rating)
        assertEquals(12, result.candidates.single().reviewCount)
        assertEquals("", result.candidates.single().station)
        assertEquals("", result.tabelogError)
    }

    @Test
    fun parsesAMichelinResponse() {
        val michelin = LookupJson.michelinResult(JSONObject(MICHELIN_RESPONSE))!!

        assertEquals("米其林一星", michelin.distinctionLabel)
        assertTrue(michelin.greenStar)
        assertEquals("日本料理 · ¥¥¥¥ · 東京", CardText.michelinDetails(michelin))
        assertNull(LookupJson.michelinResult(JSONObject("""{"michelin": null, "cached": true}""")))
    }

    companion object {
        // Trimmed from a real /match response for 一蘭 澀谷店; the third candidate is made up.
        val MATCH_RESPONSE = """
            {
              "selected": {
                "name": "一蘭 渋谷店", "rating": 3.21, "review_count": 649,
                "url": "https://tabelog.com/tokyo/A1303/A130301/13001762/",
                "address": "東京都 渋谷区 神南1-22-7 岩本ビル　Ｂ１Ｆ", "phone": "050-1808-2546",
                "latitude": 35.66112621870795, "longitude": 139.70099237422724,
                "genres": ["ラーメン"], "station": "JR渋谷駅",
                "lunch_price": "￥1,000～￥1,999", "dinner_price": "￥1,000～￥1,999", "closed_days": "",
                "confidence": "high", "score": 100.0, "match_reasons": ["電話完全相同", "地址高度相似"],
                "is_hyakumeiten": false, "hyakumeiten": null, "is_relocated": false
              },
              "candidates": [
                {"name": "一蘭 渋谷店", "rating": 3.21, "url": "https://tabelog.com/tw/tokyo/A1303/A130301/13001762", "confidence": "high"},
                {"name": "一蘭 アトレ上野山下口店", "rating": 3.34, "url": "https://tabelog.com/tokyo/A1311/A131101/13005552/", "confidence": "low"},
                {"name": "一蘭 渋谷スペイン坂店", "rating": 3.40, "url": "https://tabelog.com/tokyo/A1303/A130301/13999999/", "confidence": "medium",
                 "hyakumeiten": [{"year": 2025, "category": "拉麵", "area": "TOKYO", "label": "百名店 2025 選出店", "url": "https://award.tabelog.com/hyakumeiten/ramen_tokyo/2025/"}]}
              ],
              "michelin": null, "matched": true, "needs_confirmation": false,
              "source": "Tabelog 日本語版", "tabelog_error": "", "cached": false
            }
        """.trimIndent()

        val MICHELIN_RESPONSE = """
            {"place": {}, "michelin": {"id": "1", "name": "示例", "url": "https://guide.michelin.com/tw/zh_TW/tokyo-region/tokyo/restaurant/example",
             "distinction": "ONE_STAR", "distinction_label": "米其林一星", "green_star": true,
             "cuisine": "日本料理", "price": "¥¥¥¥", "location": "東京"}, "cached": false}
        """.trimIndent()
    }
}
