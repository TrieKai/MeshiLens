package com.meshilens.android

/** One Tabelog 百名店 selection, as returned in a candidate's `hyakumeiten` list. */
data class HyakumeitenSelection(
    val year: Int?,
    val category: String,
    val area: String,
    val label: String,
    val url: String,
)

/** A ranked Tabelog candidate from `/match`. */
data class TabelogCandidate(
    val name: String,
    val rating: Double?,
    val reviewCount: Int?,
    val url: String,
    val address: String = "",
    val phone: String = "",
    val website: String = "",
    val latitude: Double? = null,
    val longitude: Double? = null,
    val genres: List<String> = emptyList(),
    val station: String = "",
    val lunchPrice: String = "",
    val dinnerPrice: String = "",
    val closedDays: String = "",
    val confidence: String = "",
    val matchReasons: List<String> = emptyList(),
    val hyakumeiten: List<HyakumeitenSelection> = emptyList(),
    val isRelocated: Boolean = false,
) {
    val isConfident: Boolean get() = confidence == "high"
}

/** The current Michelin Guide Japan listing from `/michelin` or `/match`. */
data class MichelinEntry(
    val name: String,
    val url: String,
    val distinctionLabel: String,
    val greenStar: Boolean = false,
    val cuisine: String = "",
    val price: String = "",
    val location: String = "",
)

data class MatchResult(
    val selected: TabelogCandidate?,
    val candidates: List<TabelogCandidate>,
    val michelin: MichelinEntry?,
    val tabelogError: String = "",
    val cached: Boolean = false,
)

interface LookupClient {
    fun match(place: PlaceSnapshot): MatchResult

    /** `tabelog` re-checks Michelin with the matched Tabelog identity after a first miss. */
    fun michelin(place: PlaceSnapshot, tabelog: TabelogCandidate? = null): MichelinEntry?
}

/** A failure whose message can be shown on the card as-is. */
class LookupException(message: String) : Exception(message)
