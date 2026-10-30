package com.meshilens.android

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class CardTextTest {
    private val result = LookupJson.matchResult(JSONObject(LookupJsonTest.MATCH_RESPONSE))
    private val michelin = LookupJson.michelinResult(JSONObject(LookupJsonTest.MICHELIN_RESPONSE))

    @Test
    fun pillSummarisesEachState() {
        assertEquals("查詢中…", CardText.pill(CardState.Loading("店")))
        assertEquals("捲到「關於」後比對", CardText.pill(CardState.NeedsDetails("店")))
        assertEquals("Tabelog 3.21", CardText.pill(CardState.Ready("店", result, result.selected, null)))
        assertEquals("Tabelog 3.21 · 米其林一星", CardText.pill(CardState.Ready("店", result, result.selected, michelin)))
        assertEquals("Tabelog 未配對", CardText.pill(CardState.Ready("店", result, null, null)))
    }

    @Test
    fun pillFlagsUncertainMatchesAndHyakumeiten() {
        val alternative = result.candidates[2]

        assertEquals("Tabelog 3.40 · 百名店 · 待確認", CardText.pill(CardState.Ready("店", result, alternative, null)))
    }

    @Test
    fun hyakumeitenLinesAreNewestFirstWithoutDuplicates() {
        val selections = listOf(
            HyakumeitenSelection(2023, "拉麵", "TOKYO", "", "a"),
            HyakumeitenSelection(2025, "拉麵", "TOKYO", "", "b"),
            HyakumeitenSelection(2025, "拉麵", "TOKYO", "", "b"),
            HyakumeitenSelection(null, "", "", "", "c"),
        )

        assertEquals(
            listOf("2025 百名店 · 拉麵 TOKYO", "2023 百名店 · 拉麵 TOKYO", "百名店"),
            CardText.hyakumeitenLines(selections),
        )
    }

    @Test
    fun alternativesSkipTheSelectedListingAndLowMatches() {
        // The /tw/ URL variant of a listing still counts as the same store.
        val names = CardText.alternatives(result, result.selected).map { it.name }

        assertEquals(listOf("一蘭 渋谷スペイン坂店"), names)
    }

    @Test
    fun withNothingSelectedEvenLowMatchesAreOffered() {
        val names = CardText.alternatives(result, selected = null).map { it.confidence }

        assertEquals(listOf("high", "low", "medium"), names)
    }

    @Test
    fun certaintyAndInfoRowsMirrorTheExtension() {
        val selected = result.selected!!

        assertEquals("高信心配對 · 電話完全相同 · 地址高度相似", CardText.certainty(selected))
        assertEquals("649 則評論", CardText.reviewCount(selected))
        assertEquals(listOf("料理類型", "最近車站", "午餐價位", "晚餐價位"), CardText.infoRows(selected).map { it.first })
    }
}
