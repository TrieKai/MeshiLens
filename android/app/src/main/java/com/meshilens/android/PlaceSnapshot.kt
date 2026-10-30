package com.meshilens.android

import java.util.Locale

/** Store identity sent to `/match` and `/michelin`; it never carries ratings or reviews. */
data class PlaceSnapshot(
    val name: String,
    val address: String = "",
    val phone: String = "",
    val website: String = "",
    val latitude: Double? = null,
    val longitude: Double? = null,
    val exactCoordinates: Boolean = false,
) {
    val cacheKey: String
        get() = listOf(name, address, phone, website, coordinate(latitude), coordinate(longitude)).joinToString("|")

    private fun coordinate(value: Double?): String = value?.let { String.format(Locale.ROOT, "%.5f", it) }.orEmpty()
}
