package com.meshilens.android

/** What the MeshiLens card shows for one Maps place. */
sealed interface CardState {
    val placeName: String

    data class Loading(override val placeName: String, val michelin: MichelinEntry? = null) : CardState

    /** The sheet has not shown an address or phone yet, so nothing was looked up. */
    data class NeedsDetails(override val placeName: String) : CardState

    data class Failed(
        override val placeName: String,
        val message: String,
        val michelin: MichelinEntry? = null,
    ) : CardState

    data class Ready(
        override val placeName: String,
        val result: MatchResult,
        val selected: TabelogCandidate?,
        val michelin: MichelinEntry?,
    ) : CardState
}
