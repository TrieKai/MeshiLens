package com.meshilens.android

import java.util.Locale

/** Card wording shared by the floating card and share mode; mirrors extension/content.js. */
object CardText {
    const val BRAND = "MeshiLens"
    const val SOURCE = "Tabelog 日本語版"
    const val LOADING = "正在查詢 Tabelog 與 Michelin…"
    const val NEEDS_DETAILS = "把 Google 地圖的店家資訊往上滑，看到電話或日文地址後就會比對。"
    const val NOT_FOUND = "找不到可信的 Tabelog 店家，請從候選結果選擇。"
    const val NOT_FOUND_NO_CANDIDATES = "找不到 Tabelog 店家。"
    const val CANDIDATE_NOTE = "這些是同一店的可能配對，不是推薦店家。"

    fun pill(state: CardState): String = when (state) {
        is CardState.Loading -> "查詢中…"
        is CardState.NeedsDetails -> "上滑店家資訊後比對"
        is CardState.Failed -> "查詢失敗 · 點開重試"
        is CardState.Ready -> readyPill(state)
    }

    private fun readyPill(state: CardState.Ready): String {
        val selected = state.selected
        val parts = mutableListOf(if (selected != null) "Tabelog ${score(selected)}" else "Tabelog 未配對")
        state.michelin?.let { parts += it.distinctionLabel }
        if (selected != null && selected.hyakumeiten.isNotEmpty()) parts += "百名店"
        if (selected != null && !selected.isConfident) parts += "待確認"
        return parts.joinToString(" · ")
    }

    fun score(candidate: TabelogCandidate): String =
        candidate.rating?.let { String.format(Locale.ROOT, "%.2f", it) } ?: "—"

    fun reviewCount(candidate: TabelogCandidate): String =
        candidate.reviewCount?.let { "$it 則評論" } ?: "評論數未提供"

    fun certainty(candidate: TabelogCandidate): String {
        val lead = if (candidate.isConfident) "高信心配對" else "請確認是否為同一家店"
        return (listOf(lead) + candidate.matchReasons).joinToString(" · ")
    }

    fun confidenceLabel(confidence: String): String = when (confidence) {
        "high" -> "高信心"
        "medium" -> "待確認"
        else -> "低信心"
    }

    fun michelinDetails(michelin: MichelinEntry): String =
        listOf(michelin.cuisine, michelin.price, michelin.location).filter { it.isNotBlank() }.joinToString(" · ")

    /** Mirrors timeline.js: newest selection first, duplicates dropped. */
    fun hyakumeitenLines(selections: List<HyakumeitenSelection>): List<String> = selections
        .distinctBy { "${it.year}|${hyakumeitenLabel(it)}|${it.url}" }
        .sortedByDescending { it.year ?: 0 }
        .map { listOfNotNull(it.year?.toString(), hyakumeitenLabel(it)).joinToString(" ") }

    private fun hyakumeitenLabel(selection: HyakumeitenSelection): String {
        val category = listOf(selection.category, selection.area).filter { it.isNotBlank() }.joinToString(" ")
        return if (category.isEmpty()) "百名店" else "百名店 · $category"
    }

    fun infoRows(candidate: TabelogCandidate): List<Pair<String, String>> = listOf(
        "料理類型" to candidate.genres.joinToString("、"),
        "最近車站" to candidate.station,
        "午餐價位" to candidate.lunchPrice,
        "晚餐價位" to candidate.dinnerPrice,
        "公休日" to candidate.closedDays,
    ).filter { it.second.isNotBlank() }

    /**
     * Mirrors `alternativeCandidates` in similar.js: other plausible listings of the same store.
     * With nothing selected (typical in share mode, which lacks the phone) low matches are
     * listed too, since the right store is often among them and the user can compare addresses.
     */
    fun alternatives(result: MatchResult, selected: TabelogCandidate?): List<TabelogCandidate> {
        if (selected == null) return result.candidates
        val selectedUrl = canonicalTabelogUrl(selected.url)
        return result.candidates.filter { it.confidence != "low" && canonicalTabelogUrl(it.url) != selectedUrl }
    }

    private fun canonicalTabelogUrl(value: String): String = value
        .trim()
        .removeSuffix("/")
        .lowercase(Locale.ROOT)
        .replace(Regex("""tabelog\.com/(?:en|tw|cn|kr)/"""), "tabelog.com/")
}
