package com.meshilens.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LookupSessionTest {
    private val place = PlaceSnapshot(name = "一蘭 澀谷店", address = MapsFixtures.LOCAL_ADDRESS, phone = MapsFixtures.PHONE)
    private val candidate = TabelogCandidate(name = "一蘭 渋谷店", rating = 3.21, reviewCount = 649, url = "https://tabelog.com/x/", confidence = "high")
    private val michelin = MichelinEntry(name = "一蘭", url = "https://guide.michelin.com/x", distinctionLabel = "必比登推介")

    private class FakeClient(
        private val match: () -> MatchResult,
        private val michelin: (TabelogCandidate?) -> MichelinEntry?,
    ) : LookupClient {
        val michelinCalls = mutableListOf<TabelogCandidate?>()

        override fun match(place: PlaceSnapshot): MatchResult = match()

        override fun michelin(place: PlaceSnapshot, tabelog: TabelogCandidate?): MichelinEntry? {
            michelinCalls += tabelog
            return michelin(tabelog)
        }
    }

    /** Runs background work only when [drain] is called, so ordering is explicit. */
    private class ManualQueue {
        private val tasks = ArrayDeque<Runnable>()

        fun post(task: Runnable) {
            tasks.addLast(task)
        }

        fun drain() {
            while (tasks.isNotEmpty()) tasks.removeFirst().run()
        }
    }

    private fun session(client: LookupClient, queue: ManualQueue, states: MutableList<CardState>) =
        LookupSession(place, client, background = queue::post, main = { it.run() }, onState = { states += it })

    @Test
    fun retriesMichelinWithTheTabelogIdentityAfterAMiss() {
        val client = FakeClient(
            match = { MatchResult(selected = candidate, candidates = listOf(candidate), michelin = null) },
            michelin = { hint -> if (hint == null) null else michelin },
        )
        val queue = ManualQueue()
        val states = mutableListOf<CardState>()

        session(client, queue, states).start()
        queue.drain()

        assertEquals(listOf(null, candidate), client.michelinCalls)
        val last = states.last() as CardState.Ready
        assertEquals(candidate, last.selected)
        assertEquals(michelin, last.michelin)
    }

    @Test
    fun aFailedMatchKeepsTheMichelinResult() {
        val client = FakeClient(match = { throw LookupException("Tabelog 查詢逾時，請稍後再試") }, michelin = { michelin })
        val queue = ManualQueue()
        val states = mutableListOf<CardState>()

        session(client, queue, states).start()
        queue.drain()

        assertEquals(CardState.Failed(place.name, "Tabelog 查詢逾時，請稍後再試", michelin), states.last())
    }

    @Test
    fun unexpectedErrorsGetAGenericMessage() {
        val client = FakeClient(match = { throw IllegalStateException("boom") }, michelin = { null })
        val queue = ManualQueue()
        val states = mutableListOf<CardState>()

        session(client, queue, states).start()
        queue.drain()

        assertEquals("查詢失敗，請稍後再試", (states.last() as CardState.Failed).message)
    }

    @Test
    fun cancelledSessionsStaySilent() {
        val client = FakeClient(match = { MatchResult(candidate, listOf(candidate), null) }, michelin = { michelin })
        val queue = ManualQueue()
        val states = mutableListOf<CardState>()

        val session = session(client, queue, states)
        session.start()
        session.cancel()
        queue.drain()

        assertEquals(listOf<CardState>(CardState.Loading(place.name)), states)
    }

    @Test
    fun selectingAnotherCandidateRepublishes() {
        val other = candidate.copy(name = "一蘭 渋谷スペイン坂店", url = "https://tabelog.com/y/", confidence = "medium")
        val client = FakeClient(match = { MatchResult(candidate, listOf(candidate, other), null) }, michelin = { null })
        val queue = ManualQueue()
        val states = mutableListOf<CardState>()

        val session = session(client, queue, states)
        session.start()
        queue.drain()
        session.select(other)
        queue.drain()

        assertEquals(other, (states.last() as CardState.Ready).selected)
        assertTrue(client.michelinCalls.contains(other))
    }
}
