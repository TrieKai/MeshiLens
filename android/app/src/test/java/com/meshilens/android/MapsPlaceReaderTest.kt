package com.meshilens.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MapsPlaceReaderTest {
    @Test
    fun halfSheetHasNameCategoryAndOnlyAnAddressHint() {
        val reading = MapsPlaceReader.read(MapsFixtures.halfSheet())!!

        assertEquals(MapsFixtures.NAME, reading.name)
        assertEquals("拉麵店", reading.category)
        assertEquals("", reading.address)
        assertEquals("", reading.phone)
        assertTrue(reading.addressHint.startsWith("Jinnan, 1 Chome"))
        assertTrue(reading.isFood)
    }

    @Test
    fun expandedSheetReadsTheLocalisedAddressRow() {
        val reading = MapsPlaceReader.read(MapsFixtures.expandedSheet())!!

        assertEquals(MapsFixtures.NAME, reading.name)
        assertEquals(MapsFixtures.ROMANISED_ADDRESS, reading.address)
        assertEquals("", reading.localAddress)
    }

    @Test
    fun scrolledSheetReadsJapaneseAddressPhoneAndWebsite() {
        val reading = MapsPlaceReader.read(MapsFixtures.scrolledSheet())!!

        assertEquals(MapsFixtures.NAME, reading.name)
        assertEquals("", reading.category)
        assertEquals(MapsFixtures.ROMANISED_ADDRESS, reading.address)
        assertEquals(MapsFixtures.LOCAL_ADDRESS, reading.localAddress)
        assertEquals(MapsFixtures.PHONE, reading.phone)
        assertEquals("https://ichiran.com", reading.website)
        // The category row scrolled away, but the 菜單 tab still marks a food place.
        assertTrue(reading.isFood)
    }

    @Test
    fun ratingsAndTheSearchBoxNeverReachTheReading() {
        for (tree in listOf(MapsFixtures.halfSheet(), MapsFixtures.expandedSheet(), MapsFixtures.scrolledSheet())) {
            val reading = MapsPlaceReader.read(tree).toString()
            assertFalse(reading, reading.contains("星級"))
            assertFalse(reading, reading.contains("5,307"))
            assertFalse(reading, reading.contains("Tokyo 150-0041日本"))
        }
    }

    @Test
    fun stripsBidiMarksAroundPhoneNumbers() {
        val wrapped = "\u202a${MapsFixtures.PHONE}\u202c"
        val reading = MapsPlaceReader.read(MapsFixtures.scrolledSheet(phone = wrapped))!!

        assertEquals(MapsFixtures.PHONE, reading.phone)
    }

    @Test
    fun nonFoodPlacesAreMarked() {
        val reading = MapsPlaceReader.read(MapsFixtures.landmarkSheet())!!

        assertEquals("東京鐵塔", reading.name)
        assertFalse(reading.isFood)
    }

    @Test
    fun noPlaceSheetMeansNoReading() {
        assertNull(MapsPlaceReader.read(MapsFixtures.mapOnly()))
    }
}
