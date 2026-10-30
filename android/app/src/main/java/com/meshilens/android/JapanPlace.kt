package com.meshilens.android

/**
 * Mirrors the address and phone signals in extension/japan.js.
 *
 * The Maps app exposes no coordinates, so only a positive Japan signal starts a
 * lookup; places elsewhere never reach the MeshiLens API.
 */
object JapanPlace {
    private val POSTCODE = Regex("""〒\s*\d{3}\s*[-‐‑–—]?\s*\d{4}""")
    private val PHONE = Regex("""(?:^|[^\d])\+81(?:[\s()-]|\d)""")
    private val ADDRESS = Regex(
        """\bJapan\b|日本|北海道|(?:東京都|京都府|大阪府)|(?:青森|岩手|宮城|秋田|山形|福島|茨城|栃木|群馬|埼玉|""" +
            """千葉|神奈川|新潟|富山|石川|福井|山梨|長野|岐阜|静岡|愛知|三重|滋賀|兵庫|奈良|和歌山|鳥取|島根|""" +
            """岡山|広島|山口|徳島|香川|愛媛|高知|福岡|佐賀|長崎|熊本|大分|宮崎|鹿児島|沖縄)県""",
    )
    private val FOREIGN_PHONE = Regex("""^\+(?!81)\d""")
    private val LOCAL_SCRIPT_ADDRESS = Regex("""^〒\s*\d{3}|[都道府県].{0,12}?[市区町村郡]""")

    // Romanised block numbers and kana in a building name only hint at Japan; they
    // decide whether to ask the user to reveal the address, never whether to look up.
    private val ADDRESS_HINT = Regex("""\bChome\b|丁目|番地|〒|[ぁ-ゖァ-ヺ]""")

    fun hasJapanSignal(address: String, phone: String): Boolean =
        PHONE.containsMatchIn(phone) || POSTCODE.containsMatchIn(address) || ADDRESS.containsMatchIn(address)

    fun hasForeignPhone(phone: String): Boolean = FOREIGN_PHONE.containsMatchIn(phone.trim())

    /** A Japanese-script address (`〒…` or `東京都渋谷区…`), which Tabelog addresses can match. */
    fun isLocalScriptAddress(address: String): Boolean = LOCAL_SCRIPT_ADDRESS.containsMatchIn(address)

    fun mayBeJapan(addressHint: String): Boolean =
        ADDRESS_HINT.containsMatchIn(addressHint) || hasJapanSignal(addressHint, "")
}
