package com.meshilens.android

/** What the Google Maps place sheet currently shows about one store. */
data class PlaceReading(
    val name: String,
    val category: String = "",
    /** Address row as Maps localises it, e.g. `日本〒150-0041 Tokyo, Shibuya, …`. */
    val address: String = "",
    /** Japanese-script address Maps lists under the address row, e.g. `〒150-0041 東京都渋谷区…`. */
    val localAddress: String = "",
    val phone: String = "",
    val website: String = "",
    /** Address fragment from the directions/call buttons; only a hint that the place is in Japan. */
    val addressHint: String = "",
    val isFood: Boolean = false,
)

/**
 * Reads the store identity from the Google Maps app's place sheet.
 *
 * Only the title, category, address, phone and website rows are used; star
 * ratings and review text are never collected (see AGENTS.md).
 */
object MapsPlaceReader {
    const val MAPS_PACKAGE = "com.google.android.apps.maps"

    private const val MAX_NODES = 2500
    private const val MAX_DEPTH = 80
    private const val MAX_NAME_LENGTH = 120
    private const val MAX_SIGNAL_LABEL_LENGTH = 40
    private const val LOCAL_ADDRESS_LOOKAHEAD = 8

    private const val PLACE_SHEET_ID = "place_page_view"
    private const val PLACE_CARD_ID = "business_place_card"
    private const val COLLAPSED_HEADER_ID = "card_stack_header"
    // The search box echoes the query and the map surface holds no store details.
    private val SKIPPED_SUBTREE_IDS = setOf("search_omnibox_container", "map_frame")

    private val ADDRESS_LABEL = Regex("""^(?:地址|住所|address|주소)\s*[:：]\s*""", RegexOption.IGNORE_CASE)
    private val PHONE_LABEL = Regex(
        """^(?:電話號碼|电话号码|電話番号|電話|电话|phone(?:\s+number)?|전화(?:번호)?)\s*[:：]\s*""",
        RegexOption.IGNORE_CASE,
    )
    private val WEBSITE_LABEL = Regex("""^(?:網站|网站|ウェブサイト|website|웹사이트)\s*[:：]\s*""", RegexOption.IGNORE_CASE)
    private val ANY_LABEL = Regex("""^[^\s:：]{1,8}\s*[:：]""")
    private val SEPARATOR = Regex("""^[\s·・•|,，]*$""")
    private val INVISIBLE_MARKS = Regex("""[\u200e\u200f\u202a-\u202e\u2066-\u2069]""")
    private val WHITESPACE = Regex("""[\s\u00a0\u2007\u202f]+""")
    private val URL_SCHEME = Regex("""^https?://""", RegexOption.IGNORE_CASE)

    fun read(root: UiNode): PlaceReading? {
        val nodes = flatten(root)
        if (nodes.none { it.id == PLACE_SHEET_ID || it.id == PLACE_CARD_ID }) return null
        val name = titleIn(nodes, PLACE_CARD_ID) ?: titleIn(nodes, COLLAPSED_HEADER_ID) ?: return null

        val addressIndex = nodes.indexOfFirst { ADDRESS_LABEL.containsMatchIn(it.description) }
        val address = if (addressIndex >= 0) labelValue(nodes[addressIndex].description, ADDRESS_LABEL) else ""
        val category = categoryIn(nodes, name)
        val signalLabels = nodes
            .flatMap { listOf(it.text, it.description) }
            .filter { it.isNotEmpty() && it.length <= MAX_SIGNAL_LABEL_LENGTH }

        return PlaceReading(
            name = name,
            category = category,
            address = address,
            localAddress = if (addressIndex >= 0) localAddressAfter(nodes, addressIndex) else "",
            phone = nodes.firstNotNullOfOrNull { labelValueOrNull(it.description, PHONE_LABEL) }.orEmpty(),
            website = websiteUrl(nodes.firstNotNullOfOrNull { labelValueOrNull(it.description, WEBSITE_LABEL) }.orEmpty()),
            addressHint = addressHint(nodes, name),
            isFood = FoodCategory.isFoodPlace(category, signalLabels),
        )
    }

    private class FlatNode(val id: String, val text: String, val description: String) {
        /** Index just past this node's subtree in the pre-order list. */
        var end = 0
    }

    private fun flatten(root: UiNode): List<FlatNode> {
        val nodes = ArrayList<FlatNode>()
        fun visit(node: UiNode, depth: Int) {
            if (nodes.size >= MAX_NODES || depth > MAX_DEPTH) return
            val id = node.viewId.substringAfter(":id/", "")
            if (id in SKIPPED_SUBTREE_IDS) return
            val flat = FlatNode(id, clean(node.text), clean(node.description))
            nodes += flat
            for (index in 0 until node.childCount) {
                node.child(index)?.let { visit(it, depth + 1) }
            }
            flat.end = nodes.size
        }
        visit(root, 0)
        return nodes
    }

    private fun subtree(nodes: List<FlatNode>, id: String): List<FlatNode> {
        val start = nodes.indexOfFirst { it.id == id }
        return if (start < 0) emptyList() else nodes.subList(start + 1, nodes[start].end)
    }

    /** The place title is the first text in the card; Maps also mirrors it into the description. */
    private fun titleIn(nodes: List<FlatNode>, id: String): String? {
        val texts = subtree(nodes, id).filter { it.text.isNotEmpty() && !SEPARATOR.matches(it.text) }
        val title = texts.firstOrNull { it.text == it.description } ?: texts.firstOrNull()
        return title?.text?.takeIf { it.length <= MAX_NAME_LENGTH }
    }

    private fun categoryIn(nodes: List<FlatNode>, name: String): String =
        subtree(nodes, PLACE_CARD_ID)
            .map { it.text }
            .firstOrNull { it.isNotEmpty() && it != name && FoodCategory.isFoodCategory(it) }
            .orEmpty()

    private fun localAddressAfter(nodes: List<FlatNode>, addressIndex: Int): String {
        val from = nodes[addressIndex].end
        return nodes.subList(from, minOf(nodes.size, from + LOCAL_ADDRESS_LOOKAHEAD))
            .map { it.text }
            .firstOrNull { it.isNotEmpty() && JapanPlace.isLocalScriptAddress(it) && !ANY_LABEL.containsMatchIn(it) }
            .orEmpty()
    }

    private fun addressHint(nodes: List<FlatNode>, name: String): String {
        val marker = "$name, "
        return nodes.firstOrNull { it.description.contains(marker) }?.description?.substringAfter(marker).orEmpty()
    }

    private fun labelValueOrNull(value: String, label: Regex): String? =
        if (label.containsMatchIn(value)) labelValue(value, label).ifEmpty { null } else null

    private fun labelValue(value: String, label: Regex): String = value.replaceFirst(label, "").trim()

    /** `/michelin` only compares http(s) URLs, and Maps shows the bare domain. */
    private fun websiteUrl(value: String): String = when {
        value.isEmpty() || value.contains(' ') -> ""
        URL_SCHEME.containsMatchIn(value) -> value
        else -> "https://$value"
    }

    private fun clean(value: String): String = value.replace(INVISIBLE_MARKS, "").replace(WHITESPACE, " ").trim()
}
