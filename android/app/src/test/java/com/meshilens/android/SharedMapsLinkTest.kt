package com.meshilens.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedMapsLinkTest {
    private val resolved = "https://www.google.com/maps/place/%E4%B8%80%E8%98%AD+%E6%BE%80%E8%B0%B7%E5%BA%97," +
        "+%E6%97%A5%E6%9C%AC%E3%80%92150-0041+Tokyo,+Shibuya,+Jinnan,+1+Chome%E2%88%9222%E2%88%927/" +
        "data=!4m6!3m5!1s0x60188ca8bdbc0715:0x1!8m2!3d35.6612!4d139.7009!16s%2Fg%2F1tdq0x5q?entry=tts"

    @Test
    fun parsesNameAndShortLinkFromMapsShareText() {
        val shared = SharedMapsLink.parse("一蘭 澀谷店\nhttps://maps.app.goo.gl/AbCdEf123")!!

        assertEquals("一蘭 澀谷店", shared.name)
        assertEquals("https://maps.app.goo.gl/AbCdEf123", shared.url)
        assertTrue(SharedMapsLink.isShortLink(shared.url))
    }

    @Test
    fun takesTheNameFromTheShareTitleWhenTheTextIsOnlyALink() {
        // What Google Maps actually shares: EXTRA_TEXT is the bare link, EXTRA_TITLE the name.
        val shared = SharedMapsLink.parse("https://maps.app.goo.gl/AbCdEf123", title = " 一蘭 澀谷店 ")!!
        val resolved = "https://www.google.com/maps/place/" +
            "%E4%B8%80%E8%98%AD+%E6%BE%80%E8%B0%B7%E5%BA%97+%E5%B2%A9%E6%9C%AC%E3%83%93%E3%83%AB+B1F+1+Chome-22-7+Jinnan," +
            "+Shibuya,+Tokyo+150-0041%E6%97%A5%E6%9C%AC/data=!4m2!3m1!1s0x60188ca8bdbc0715:0x1?utm_source=mstt_1&entry=gps"

        val place = SharedMapsLink.placeFrom(shared, resolved)!!

        assertEquals("一蘭 澀谷店", place.name)
        assertEquals("岩本ビル B1F 1 Chome-22-7 Jinnan, Shibuya, Tokyo 150-0041日本", place.address)
        assertNull(place.latitude)
    }

    @Test
    fun ignoresTextWithoutAGoogleMapsLink() {
        assertNull(SharedMapsLink.parse("看看這家 https://example.com/maps/place/x"))
        assertNull(SharedMapsLink.parse("一蘭 澀谷店"))
        assertNull(SharedMapsLink.parse(null))
        assertFalse(SharedMapsLink.isShortLink("http://maps.app.goo.gl/AbCdEf123"))
    }

    @Test
    fun buildsTheIdentityFromTheResolvedPlaceUrl() {
        val shared = SharedMapsLink.parse("一蘭 澀谷店 https://maps.app.goo.gl/AbCdEf123")!!

        val place = SharedMapsLink.placeFrom(shared, resolved)!!

        assertEquals("一蘭 澀谷店", place.name)
        assertEquals("日本〒150-0041 Tokyo, Shibuya, Jinnan, 1 Chome−22−7", place.address)
        assertEquals(35.6612, place.latitude!!, 0.0)
        assertEquals(139.7009, place.longitude!!, 0.0)
        assertTrue(place.exactCoordinates)
    }

    @Test
    fun fallsBackToTheUrlLabelWhenOnlyALinkWasShared() {
        val shared = SharedMapsLink.parse(resolved)!!

        val place = SharedMapsLink.placeFrom(shared, resolved)!!

        assertEquals("一蘭 澀谷店", place.name)
        assertTrue(place.address.startsWith("日本〒150-0041"))
    }

    @Test
    fun readsTheQueryParameterFormToo() {
        val shared = SharedMapsLink.Shared(name = "", url = "", otherLines = emptyList())

        val place = SharedMapsLink.placeFrom(shared, "https://maps.google.com/?q=%E4%B8%80%E8%98%AD,+%E6%9D%B1%E4%BA%AC%E9%83%BD&ftid=0x1:0x2")!!

        assertEquals("一蘭", place.name)
        assertEquals("東京都", place.address)
        assertFalse(place.exactCoordinates)
    }
}
