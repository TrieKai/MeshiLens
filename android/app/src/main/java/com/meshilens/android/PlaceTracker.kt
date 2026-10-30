package com.meshilens.android

/**
 * Collects what the Maps sheet has shown for the current place and decides when
 * it is worth one low-frequency lookup.
 *
 * The half-open sheet usually shows only the name; the address, phone and
 * Japanese address rows appear once the user scrolls, so fields are merged per
 * place name and a lookup waits for an identity Tabelog can actually match.
 */
class PlaceTracker(
    private val maxLookupsPerPlace: Int = 3,
    private val romanisedAddressWaitMillis: Long = 2_500L,
) {

    sealed interface Decision {
        /** No food place in Japan is open in Maps. */
        data object Hide : Decision

        /**
         * Probably a restaurant in Japan, but nothing matchable is visible yet.
         * When [recheckInMillis] is set, read again then even without new events.
         */
        data class NeedsDetails(val name: String, val recheckInMillis: Long? = null) : Decision

        data class Lookup(val place: PlaceSnapshot) : Decision

        /** Same place as before; keep whatever the card shows. */
        data object Unchanged : Decision
    }

    private var name = ""
    private var address = ""
    private var localAddress = ""
    private var phone = ""
    private var website = ""
    private var addressHint = ""
    private var isFood = false
    private var romanisedSince: Long? = null
    private var lastLookupKey = ""
    private var lookups = 0
    private var settled = false

    fun update(reading: PlaceReading?, nowMillis: Long): Decision {
        if (reading == null) {
            reset("")
            return Decision.Hide
        }
        if (reading.name != name) reset(reading.name)
        address = reading.address.ifEmpty { address }
        localAddress = reading.localAddress.ifEmpty { localAddress }
        phone = reading.phone.ifEmpty { phone }
        website = reading.website.ifEmpty { website }
        addressHint = reading.addressHint.ifEmpty { addressHint }
        // The category row scrolls away with the header, so remember it per place.
        isFood = isFood || reading.isFood

        if (!isFood || JapanPlace.hasForeignPhone(phone)) return Decision.Hide
        if (address.isEmpty() && localAddress.isEmpty() && phone.isEmpty()) {
            return if (JapanPlace.mayBeJapan(addressHint)) Decision.NeedsDetails(name) else Decision.Hide
        }
        if (!JapanPlace.hasJapanSignal("$address $localAddress", phone)) return Decision.Hide

        // A romanised address ("Tokyo, Shibuya, Jinnan…") rarely matches Tabelog's Japanese
        // one; the phone or Japanese address row is usually one short scroll further down.
        val matchable = phone.isNotEmpty() || localAddress.isNotEmpty() || JapanPlace.isLocalScriptAddress(address)
        if (!matchable) {
            val since = romanisedSince ?: nowMillis.also { romanisedSince = it }
            val remaining = romanisedAddressWaitMillis - (nowMillis - since)
            if (remaining > 0) return Decision.NeedsDetails(name, recheckInMillis = remaining)
        }

        // Tabelog lists Japanese addresses, so the Japanese-script line matches far better.
        val place = PlaceSnapshot(name = name, address = localAddress.ifEmpty { address }, phone = phone, website = website)
        if (settled || place.cacheKey == lastLookupKey || lookups >= maxLookupsPerPlace) return Decision.Unchanged
        lastLookupKey = place.cacheKey
        lookups += 1
        return Decision.Lookup(place)
    }

    /** A confident match ends lookups for this place even if more rows appear later. */
    fun onResult(place: PlaceSnapshot, confident: Boolean) {
        if (confident && place.name == name) settled = true
    }

    private fun reset(newName: String) {
        name = newName
        address = ""
        localAddress = ""
        phone = ""
        website = ""
        addressHint = ""
        isFood = false
        romanisedSince = null
        lastLookupKey = ""
        lookups = 0
        settled = false
    }
}
