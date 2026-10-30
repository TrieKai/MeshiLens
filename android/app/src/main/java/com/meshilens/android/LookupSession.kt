package com.meshilens.android

/**
 * One place lookup, mirroring `lookup()` in extension/content.js: `/michelin`
 * and `/match` run in parallel, then Michelin is re-checked once with the
 * Tabelog identity when the first try misses.
 *
 * Callbacks arrive through [main], so all state is only touched on that thread.
 */
class LookupSession(
    private val place: PlaceSnapshot,
    private val client: LookupClient,
    private val background: (Runnable) -> Unit,
    private val main: (Runnable) -> Unit,
    private val onState: (CardState) -> Unit,
) {
    private var cancelled = false
    private var match: MatchResult? = null
    private var matchError: String? = null
    private var selected: TabelogCandidate? = null
    private var michelin: MichelinEntry? = null
    private var michelinDone = false
    private val refinedUrls = mutableSetOf<String>()

    fun start() {
        onState(CardState.Loading(place.name))
        fetch({ client.michelin(place) }) { result ->
            michelinDone = true
            michelin = michelin ?: result.getOrNull()
            publish()
            refineMichelin()
        }
        fetch({ client.match(place) }) { result ->
            result
                .onSuccess {
                    match = it
                    selected = it.selected
                    michelin = michelin ?: it.michelin
                }
                .onFailure { matchError = messageFor(it) }
            publish()
            refineMichelin()
        }
    }

    /** The user picked another candidate from 「核對 Tabelog 配對結果」. */
    fun select(candidate: TabelogCandidate) {
        if (cancelled || match == null) return
        selected = candidate
        publish()
        refineMichelin()
    }

    fun cancel() {
        cancelled = true
    }

    private fun publish() {
        val result = match
        val error = matchError
        onState(
            when {
                result != null -> CardState.Ready(place.name, result, selected, michelin)
                error != null -> CardState.Failed(place.name, error, michelin)
                else -> CardState.Loading(place.name, michelin)
            },
        )
    }

    private fun refineMichelin() {
        val candidate = selected ?: return
        if (!michelinDone || michelin != null || !refinedUrls.add(candidate.url)) return
        fetch({ client.michelin(place, candidate) }) { result ->
            val found = result.getOrNull() ?: return@fetch
            michelin = found
            publish()
        }
    }

    private fun <T> fetch(work: () -> T, done: (Result<T>) -> Unit) {
        background(
            Runnable {
                val result = runCatching(work)
                main(Runnable { if (!cancelled) done(result) })
            },
        )
    }

    private fun messageFor(error: Throwable): String =
        (error as? LookupException)?.message ?: "查詢失敗，請稍後再試"
}
