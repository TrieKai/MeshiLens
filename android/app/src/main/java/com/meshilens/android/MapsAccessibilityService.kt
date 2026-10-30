package com.meshilens.android

import android.accessibilityservice.AccessibilityService
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo

/**
 * Watches the Google Maps place sheet and keeps the floating card in sync.
 *
 * Events only arrive from Google Maps (see `maps_accessibility_service.xml`).
 * Readings are debounced so scrolling the sheet causes one read, and
 * [PlaceTracker] keeps lookups to about one per place.
 */
class MapsAccessibilityService : AccessibilityService() {
    private val handler = Handler(Looper.getMainLooper())
    private val tracker = PlaceTracker()
    private var card: FloatingCard? = null
    private var session: LookupSession? = null
    private var lastPlace: PlaceSnapshot? = null
    private var pendingSince = 0L

    private val readPlace = Runnable {
        pendingSince = 0L
        readCurrentPlace()
    }

    // Events stop once Maps leaves the screen, so poll the window list while the card shows.
    private val watchMaps = object : Runnable {
        override fun run() {
            val card = card ?: return
            if (!card.isAttached) return
            if (mapsVisible() == false) card.hide() else handler.postDelayed(this, WATCH_INTERVAL_MS)
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        card = FloatingCard(this, object : CardRenderer.Actions {
            override fun openUrl(url: String) = openExternal(url)

            override fun select(candidate: TabelogCandidate) {
                session?.select(candidate)
            }

            override fun retry() {
                lastPlace?.let(::startLookup)
            }
        })
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event?.packageName?.toString() != MapsPlaceReader.MAPS_PACKAGE) return
        val now = SystemClock.uptimeMillis()
        if (pendingSince == 0L) pendingSince = now
        handler.removeCallbacks(readPlace)
        // Wait for the sheet to settle, but read at least every MAX_READ_WAIT_MS while it animates.
        handler.postDelayed(readPlace, if (now - pendingSince >= MAX_READ_WAIT_MS) 0L else READ_DELAY_MS)
    }

    override fun onInterrupt() = Unit

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        session?.cancel()
        card?.clear()
        card = null
        super.onDestroy()
    }

    private fun readCurrentPlace() {
        val card = card ?: return
        val root = mapsRoot() ?: return
        val reading = try {
            MapsPlaceReader.read(AccessibilityUiNode(root))
        } catch (error: RuntimeException) {
            // Nodes go stale while Maps redraws; the next event reads again.
            return
        }
        when (val decision = tracker.update(reading, SystemClock.uptimeMillis())) {
            PlaceTracker.Decision.Hide -> {
                cancelSession()
                lastPlace = null
                card.clear()
            }
            is PlaceTracker.Decision.NeedsDetails -> {
                cancelSession()
                card.show(CardState.NeedsDetails(decision.name))
                decision.recheckInMillis?.let { handler.postDelayed(readPlace, it + RECHECK_MARGIN_MS) }
            }
            is PlaceTracker.Decision.Lookup -> startLookup(decision.place)
            PlaceTracker.Decision.Unchanged -> card.reshow()
        }
        if (card.isAttached) {
            handler.removeCallbacks(watchMaps)
            handler.postDelayed(watchMaps, WATCH_INTERVAL_MS)
        }
    }

    private fun startLookup(place: PlaceSnapshot) {
        cancelSession()
        lastPlace = place
        session = AppServices.session(this, place) { state ->
            card?.show(state)
            if (state is CardState.Ready) tracker.onResult(place, state.result.selected?.isConfident == true)
        }.also { it.start() }
    }

    private fun cancelSession() {
        session?.cancel()
        session = null
    }

    private fun mapsRoot(): AccessibilityNodeInfo? {
        val fromWindows = runCatching { windows }.getOrNull().orEmpty()
            .asSequence()
            .filter { it.type == AccessibilityWindowInfo.TYPE_APPLICATION }
            .mapNotNull { it.root }
            .firstOrNull { it.packageName?.toString() == MapsPlaceReader.MAPS_PACKAGE }
        return fromWindows ?: rootInActiveWindow?.takeIf { it.packageName?.toString() == MapsPlaceReader.MAPS_PACKAGE }
    }

    /** Only the package name of each app window is read; `null` when the list is unavailable. */
    private fun mapsVisible(): Boolean? {
        val list = runCatching { windows }.getOrNull()
        if (list.isNullOrEmpty()) return null
        return list.any {
            it.type == AccessibilityWindowInfo.TYPE_APPLICATION &&
                it.root?.packageName?.toString() == MapsPlaceReader.MAPS_PACKAGE
        }
    }

    private fun openExternal(url: String) {
        if (!url.startsWith("https://")) return
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (error: ActivityNotFoundException) {
            // No browser installed; nothing else to open the link with.
        }
    }

    private companion object {
        const val READ_DELAY_MS = 450L
        const val MAX_READ_WAIT_MS = 1500L
        const val WATCH_INTERVAL_MS = 1200L
        const val RECHECK_MARGIN_MS = 100L
    }
}
