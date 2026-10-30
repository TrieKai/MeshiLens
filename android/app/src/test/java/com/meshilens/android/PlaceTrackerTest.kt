package com.meshilens.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PlaceTrackerTest {
    private fun read(tree: FakeNode) = MapsPlaceReader.read(tree)

    @Test
    fun asksToScrollUntilSomethingMatchableIsVisible() {
        val tracker = PlaceTracker()

        assertEquals(
            PlaceTracker.Decision.NeedsDetails(MapsFixtures.NAME),
            tracker.update(read(MapsFixtures.halfSheet()), nowMillis = 0),
        )
        val waiting = tracker.update(read(MapsFixtures.expandedSheet()), nowMillis = 1_000)
        assertEquals(PlaceTracker.Decision.NeedsDetails(MapsFixtures.NAME, recheckInMillis = 2_500), waiting)
    }

    @Test
    fun looksUpWithTheJapaneseAddressAndPhoneOnce() {
        val tracker = PlaceTracker()
        tracker.update(read(MapsFixtures.expandedSheet()), nowMillis = 0)

        val decision = tracker.update(read(MapsFixtures.scrolledSheet()), nowMillis = 500)

        val place = (decision as PlaceTracker.Decision.Lookup).place
        assertEquals(MapsFixtures.NAME, place.name)
        assertEquals(MapsFixtures.LOCAL_ADDRESS, place.address)
        assertEquals(MapsFixtures.PHONE, place.phone)
        assertEquals("https://ichiran.com", place.website)
        assertEquals(PlaceTracker.Decision.Unchanged, tracker.update(read(MapsFixtures.scrolledSheet()), nowMillis = 900))
        // Scrolling back up keeps the merged identity instead of looking up again.
        assertEquals(PlaceTracker.Decision.Unchanged, tracker.update(read(MapsFixtures.halfSheet()), nowMillis = 1_200))
    }

    @Test
    fun fallsBackToTheRomanisedAddressAfterWaiting() {
        val tracker = PlaceTracker()
        tracker.update(read(MapsFixtures.expandedSheet()), nowMillis = 10_000)

        val decision = tracker.update(read(MapsFixtures.expandedSheet()), nowMillis = 12_600)

        assertEquals(MapsFixtures.ROMANISED_ADDRESS, (decision as PlaceTracker.Decision.Lookup).place.address)
    }

    @Test
    fun aWeakMatchRetriesWhenMoreRowsAppearButAConfidentOneStops() {
        val tracker = PlaceTracker(romanisedAddressWaitMillis = 0)
        val first = tracker.update(read(MapsFixtures.expandedSheet()), nowMillis = 0) as PlaceTracker.Decision.Lookup
        tracker.onResult(first.place, confident = false)

        val second = tracker.update(read(MapsFixtures.scrolledSheet()), nowMillis = 100)
        assertTrue(second is PlaceTracker.Decision.Lookup)
        tracker.onResult((second as PlaceTracker.Decision.Lookup).place, confident = true)

        val other = MapsFixtures.scrolledSheet(phone = "+81 3-0000-0000")
        assertEquals(PlaceTracker.Decision.Unchanged, tracker.update(read(other), nowMillis = 200))
    }

    @Test
    fun hidesPlacesOutsideJapanAndNonFoodPlaces() {
        val tracker = PlaceTracker()

        assertEquals(PlaceTracker.Decision.Hide, tracker.update(read(MapsFixtures.taipeiSheet()), nowMillis = 0))
        assertEquals(PlaceTracker.Decision.Hide, tracker.update(read(MapsFixtures.landmarkSheet()), nowMillis = 0))
        assertEquals(PlaceTracker.Decision.Hide, tracker.update(read(MapsFixtures.mapOnly()), nowMillis = 0))
    }

    @Test
    fun foreignPhoneNumbersNeverLookUp() {
        val tracker = PlaceTracker()

        val decision = tracker.update(read(MapsFixtures.scrolledSheet(phone = "+886 2 2321 8928")), nowMillis = 0)

        assertEquals(PlaceTracker.Decision.Hide, decision)
    }

    @Test
    fun aNewPlaceStartsOver() {
        val tracker = PlaceTracker()
        tracker.update(read(MapsFixtures.scrolledSheet()), nowMillis = 0)
        tracker.update(read(MapsFixtures.mapOnly()), nowMillis = 100)

        assertTrue(tracker.update(read(MapsFixtures.scrolledSheet()), nowMillis = 200) is PlaceTracker.Decision.Lookup)
    }
}
