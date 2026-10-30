package com.meshilens.android

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Same cases as tests/test_category.js and tests/test_japan.js. */
class PlaceSignalsTest {
    @Test
    fun foodCategoriesInEveryMapsLanguage() {
        listOf("拉麵店", "日本料理餐廳", "Ramen restaurant", "Café", "ラーメン店", "居酒屋", "음식점").forEach {
            assertTrue(it, FoodCategory.isFoodCategory(it))
        }
        listOf("觀光勝地", "Museum", "駅", "").forEach {
            assertFalse(it, FoodCategory.isFoodCategory(it))
        }
    }

    @Test
    fun menuTabsAndDineInLabelsMarkFoodPlaces() {
        assertTrue(FoodCategory.isFoodPlace("", listOf("總覽", "菜單")))
        assertTrue(FoodCategory.isFoodPlace("", listOf("每人 ¥2,000-3,000")))
        assertTrue(FoodCategory.isFoodPlace("", listOf("提供內用")))
        assertFalse(FoodCategory.isFoodPlace("觀光勝地", listOf("總覽", "評論", "¥1,000 到 ¥2,000")))
    }

    @Test
    fun japanSignalsComeFromAddressOrPhone() {
        assertTrue(JapanPlace.hasJapanSignal(MapsFixtures.ROMANISED_ADDRESS, ""))
        assertTrue(JapanPlace.hasJapanSignal("1-22-7 Jinnan, Shibuya City, Tokyo 150-0041, Japan", ""))
        assertTrue(JapanPlace.hasJapanSignal("", MapsFixtures.PHONE))
        assertFalse(JapanPlace.hasJapanSignal("110台北市信義區信義路二段194號", "02 2321 8928"))
        assertTrue(JapanPlace.hasForeignPhone("+886 2 2321 8928"))
        assertFalse(JapanPlace.hasForeignPhone(MapsFixtures.PHONE))
    }

    @Test
    fun onlyJapaneseScriptAddressesCountAsMatchable() {
        assertTrue(JapanPlace.isLocalScriptAddress(MapsFixtures.LOCAL_ADDRESS))
        assertTrue(JapanPlace.isLocalScriptAddress("東京都渋谷区神南1-22-7"))
        assertFalse(JapanPlace.isLocalScriptAddress(MapsFixtures.ROMANISED_ADDRESS))
    }

    @Test
    fun buttonAddressFragmentsHintAtJapan() {
        assertTrue(JapanPlace.mayBeJapan("Jinnan, 1 Chome−22−7 岩本ビル B1F的路線"))
        assertFalse(JapanPlace.mayBeJapan("信義路二段194號的路線"))
    }
}
