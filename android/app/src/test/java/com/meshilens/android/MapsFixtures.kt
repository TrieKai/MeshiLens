package com.meshilens.android

/** In-memory [UiNode] tree for tests. */
class FakeNode(
    override val viewId: String = "",
    override val text: String = "",
    override val description: String = "",
    private val children: List<FakeNode> = emptyList(),
) : UiNode {
    override val childCount: Int get() = children.size

    override fun child(index: Int): UiNode? = children.getOrNull(index)
}

fun group(id: String, vararg children: FakeNode) =
    FakeNode(viewId = "${MapsPlaceReader.MAPS_PACKAGE}:id/$id", children = children.toList())

fun node(text: String = "", desc: String = "", children: List<FakeNode> = emptyList()) =
    FakeNode(text = text, description = desc, children = children)

/**
 * Trimmed from real Google Maps (zh-TW) UI dumps of 一蘭 澀谷店 on a Pixel 6a.
 * The rating line is kept on purpose to prove it never reaches a reading.
 */
object MapsFixtures {
    const val NAME = "一蘭 澀谷店"
    const val ROMANISED_ADDRESS = "日本〒150-0041 Tokyo, Shibuya, Jinnan, 1 Chome−22−7 岩本ビル B1F"
    const val LOCAL_ADDRESS = "〒150-0041 東京都渋谷区神南１丁目２２−7 岩本ビル B1F"
    const val PHONE = "+81 50-1808-2546"

    private fun omnibox() = group(
        "search_omnibox_container",
        node(desc = "一蘭 澀谷店 岩本ビル B1F 1 Chome-22-7 Jinnan, Shibuya, Tokyo 150-0041日本"),
    )

    private fun actionButtons() = group(
        "recycler_view",
        node(desc = "規劃前往一蘭 澀谷店, Jinnan, 1 Chome−22−7 岩本ビル B1F的路線"),
        node(text = "致電", desc = "撥號至「一蘭 澀谷店, Jinnan, 1 Chome−22−7 岩本ビル B1F」"),
        node(text = "分享", desc = "分享「一蘭 澀谷店」"),
    )

    private fun placeCard() = group(
        "business_place_card",
        node(text = NAME, desc = NAME),
        node(desc = "以日文播放"),
        node(text = "4.4 星級 (5,307)"),
        node(text = "拉麵店"),
        node(text = " · "),
        node(text = " · ¥1,000-2,000", desc = "¥1,000 到 ¥2,000"),
        node(text = "24 小時營業"),
    )

    private fun addressRow() = node(desc = "地址：$ROMANISED_ADDRESS", children = listOf(node(text = ROMANISED_ADDRESS)))

    /** The sheet as it first opens: name, category and buttons, no detail rows. */
    fun halfSheet() = group(
        "gmmactivity_root_layout",
        group("place_page_view", group("place_nested_scroll_view", placeCard(), actionButtons())),
        omnibox(),
    )

    /** Fully expanded sheet: the address row has just come into view at the bottom. */
    fun expandedSheet() = group(
        "gmmactivity_root_layout",
        group(
            "place_page_view",
            group(
                "place_nested_scroll_view",
                placeCard(),
                actionButtons(),
                node(text = "總覽", desc = "總覽"),
                node(text = "菜單", desc = "菜單"),
                node(text = "評論", desc = "評論"),
                group("recycler_view", node(text = "24 小時營業", desc = "營業時間：24 小時營業"), addressRow()),
            ),
            group("card_stack_header", node(desc = "儲存"), node(desc = "分享"), node(desc = "關閉")),
        ),
        omnibox(),
    )

    /** Scrolled further: the card header is gone, the detail rows are all visible. */
    fun scrolledSheet(phone: String = PHONE) = group(
        "gmmactivity_root_layout",
        group(
            "place_page_view",
            group(
                "place_nested_scroll_view",
                node(text = "總覽", desc = "總覽"),
                node(text = "菜單", desc = "菜單"),
                node(text = "評論", desc = "評論"),
                group(
                    "recycler_view",
                    node(text = "24 小時營業", desc = "營業時間：24 小時營業"),
                    addressRow(),
                    node(desc = "啟用以展開資訊"),
                    node(text = LOCAL_ADDRESS),
                    node(desc = "以日文播放"),
                    node(text = "位於： Nataraj Harajuku"),
                    node(desc = "網站：ichiran.com", children = listOf(node(text = "ichiran.com"))),
                    node(desc = "電話號碼：$phone", children = listOf(node(text = phone))),
                ),
            ),
            group("card_stack_header", node(text = NAME, desc = NAME), node(desc = "以日文播放"), node(desc = "儲存")),
            actionButtons(),
        ),
        omnibox(),
    )

    fun taipeiSheet() = group(
        "gmmactivity_root_layout",
        group(
            "place_page_view",
            group(
                "business_place_card",
                node(text = "鼎泰豐 信義店", desc = "鼎泰豐 信義店"),
                node(text = "4.4 星級 (20,000)"),
                node(text = "台灣菜餐廳"),
            ),
            node(desc = "地址：110台北市信義區信義路二段194號", children = listOf(node(text = "110台北市信義區信義路二段194號"))),
            node(desc = "電話號碼：02 2321 8928"),
        ),
    )

    fun landmarkSheet() = group(
        "gmmactivity_root_layout",
        group(
            "place_page_view",
            group("business_place_card", node(text = "東京鐵塔", desc = "東京鐵塔"), node(text = "觀光勝地")),
            node(desc = "地址：日本〒105-0011 Tokyo, Minato City, Shibakoen, 4 Chome−2−8"),
        ),
    )

    fun mapOnly() = group("gmmactivity_root_layout", group("map_frame"), omnibox())
}
