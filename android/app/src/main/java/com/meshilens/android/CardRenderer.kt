package com.meshilens.android

import android.content.Context
import android.graphics.Typeface
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import kotlin.math.roundToInt

/**
 * Builds the card body for a [CardState]: Michelin, Tabelog score, 百名店 and
 * the candidate check list, laid out like the extension's content card.
 */
class CardRenderer(private val context: Context, private val actions: Actions) {

    interface Actions {
        fun openUrl(url: String)
        fun select(candidate: TabelogCandidate)
        fun retry()
    }

    private var lastPlaceName = ""
    private var showCandidates = false

    fun render(body: LinearLayout, state: CardState) {
        if (state.placeName != lastPlaceName) {
            lastPlaceName = state.placeName
            showCandidates = false
        }
        body.removeAllViews()
        when (state) {
            is CardState.Loading -> {
                state.michelin?.let { body.addSpaced(michelinSection(it)) }
                body.addSpaced(status(CardText.LOADING))
            }
            is CardState.NeedsDetails -> body.addSpaced(status(CardText.NEEDS_DETAILS))
            is CardState.Failed -> {
                state.michelin?.let { body.addSpaced(michelinSection(it)) }
                body.addSpaced(status(state.message))
                body.addSpaced(button("重試", filled = true) { actions.retry() })
            }
            is CardState.Ready -> renderReady(body, state)
        }
    }

    /** A plain message without lookup actions (e.g. a share without a Maps link). */
    fun renderMessage(body: LinearLayout, message: String) {
        body.removeAllViews()
        body.addSpaced(status(message))
    }

    private fun renderReady(body: LinearLayout, state: CardState.Ready) {
        state.michelin?.let { body.addSpaced(michelinSection(it)) }
        val selected = state.selected
        val alternatives = CardText.alternatives(state.result, selected)
        if (selected == null) {
            val error = state.result.tabelogError
            val message = when {
                error.isNotEmpty() -> "Tabelog：$error"
                alternatives.isEmpty() -> CardText.NOT_FOUND_NO_CANDIDATES
                else -> CardText.NOT_FOUND
            }
            body.addSpaced(status(message))
        } else {
            body.addSpaced(scoreRow(selected))
            if (selected.isRelocated) body.addSpaced(caption("此為 Tabelog 標示的移轉前資料。", R.color.ml_michelin_text))
            val awards = CardText.hyakumeitenLines(selected.hyakumeiten)
            if (awards.isNotEmpty()) body.addSpaced(awardSection(awards))
            val info = CardText.infoRows(selected)
            if (info.isNotEmpty()) body.addSpaced(infoSection(info))
            body.addSpaced(caption(CardText.certainty(selected)))
            body.addSpaced(footer(selected, state.result.cached))
        }
        if (alternatives.isNotEmpty()) addCandidates(body, state, alternatives, collapsible = selected != null)
    }

    private fun michelinSection(michelin: MichelinEntry): View = column(R.drawable.bg_michelin, dp(12)).apply {
        addView(text("MICHELIN GUIDE · 目前收錄", 11f, R.color.ml_michelin_text, bold = true))
        val badges = row()
        badges.addView(badge(michelin.distinctionLabel, R.drawable.bg_badge, R.color.ml_badge_text).apply {
            if (michelin.url.isNotEmpty()) setOnClickListener { actions.openUrl(michelin.url) }
        })
        if (michelin.greenStar) {
            badges.addView(badge("米其林綠星", R.drawable.bg_green_badge, R.color.ml_green_text), marginStart(dp(6)))
        }
        addSpaced(badges, dp(8))
        val details = CardText.michelinDetails(michelin)
        if (details.isNotEmpty()) addSpaced(text(details, 12f, R.color.ml_michelin_text), dp(6))
    }

    private fun scoreRow(candidate: TabelogCandidate): View = row().apply {
        gravity = Gravity.CENTER_VERTICAL
        addView(text(CardText.score(candidate), 32f, R.color.ml_ink, bold = true))
        val meta = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        meta.addView(text(candidate.name.ifEmpty { "未命名店家" }, 15f, R.color.ml_ink, bold = true).apply { maxLines = 2 })
        meta.addView(text("Tabelog · ${CardText.reviewCount(candidate)}", 12f, R.color.ml_muted))
        addView(meta, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { marginStart = dp(14) })
    }

    private fun awardSection(lines: List<String>): View = column(R.drawable.bg_award, dp(12)).apply {
        addView(text("Tabelog 百名店", 11f, R.color.ml_award_text, bold = true))
        lines.forEach { addSpaced(text(it, 13f, R.color.ml_award_text), dp(4)) }
    }

    private fun infoSection(rows: List<Pair<String, String>>): View = column(null, 0).apply {
        rows.forEach { (label, value) ->
            val line = row()
            line.addView(text(label, 12f, R.color.ml_muted), LinearLayout.LayoutParams(dp(64), ViewGroup.LayoutParams.WRAP_CONTENT))
            line.addView(text(value, 13f, R.color.ml_ink), LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addSpaced(line, dp(4))
        }
    }

    private fun footer(candidate: TabelogCandidate, cached: Boolean): View = row().apply {
        gravity = Gravity.CENTER_VERTICAL
        if (candidate.url.isNotEmpty()) addView(button("在 Tabelog 開啟 ↗", filled = true) { actions.openUrl(candidate.url) })
        addView(View(context), LinearLayout.LayoutParams(0, 1, 1f))
        addView(text(if (cached) "快取資料" else "剛剛更新", 11f, R.color.ml_muted))
    }

    /** With nothing selected the list is the main content, so it is shown open. */
    private fun addCandidates(
        body: LinearLayout,
        state: CardState.Ready,
        candidates: List<TabelogCandidate>,
        collapsible: Boolean,
    ) {
        if (collapsible) {
            val label = if (showCandidates) "收起 Tabelog 配對結果" else "核對 Tabelog 配對結果（${candidates.size}）"
            body.addSpaced(button(label, filled = false) {
                showCandidates = !showCandidates
                render(body, state)
            })
            if (!showCandidates) return
        }
        body.addSpaced(caption(CardText.CANDIDATE_NOTE))
        candidates.forEach { candidate ->
            val item = column(R.drawable.bg_candidate, dp(10)).apply {
                isClickable = true
                isFocusable = true
                setOnClickListener { actions.select(candidate) }
                val tags = buildList {
                    if (candidate.hyakumeiten.isNotEmpty()) add("百名店")
                    if (candidate.isRelocated) add("已搬遷")
                    add(CardText.confidenceLabel(candidate.confidence))
                    candidate.rating?.let { add("Tabelog ${CardText.score(candidate)}") }
                }
                addView(text(candidate.name.ifEmpty { "未命名店家" }, 13f, R.color.ml_ink, bold = true))
                addView(text(tags.joinToString(" · "), 12f, R.color.ml_accent))
                addView(text(candidate.address.ifEmpty { "地址未提供" }, 12f, R.color.ml_muted))
            }
            body.addSpaced(item, dp(6))
        }
    }

    private fun status(message: String): TextView = text(message, 14f, R.color.ml_ink)

    private fun caption(message: String, color: Int = R.color.ml_muted): TextView = text(message, 12f, color)

    private fun button(label: String, filled: Boolean, onClick: () -> Unit): TextView =
        text(label, 13f, if (filled) android.R.color.white else R.color.ml_accent, bold = true).apply {
            setBackgroundResource(if (filled) R.drawable.bg_button else R.drawable.bg_button_outline)
            gravity = Gravity.CENTER
            minHeight = dp(40)
            setPadding(dp(16), dp(8), dp(16), dp(8))
            isClickable = true
            isFocusable = true
            setOnClickListener { onClick() }
        }

    private fun badge(label: String, background: Int, color: Int): TextView =
        text(label, 13f, color, bold = true).apply {
            setBackgroundResource(background)
            setPadding(dp(10), dp(4), dp(10), dp(4))
        }

    private fun text(value: String, sizeSp: Float, color: Int, bold: Boolean = false): TextView =
        TextView(context).apply {
            text = value
            setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
            setTextColor(context.getColor(color))
            setLineSpacing(0f, 1.15f)
            ellipsize = TextUtils.TruncateAt.END
            if (bold) typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }

    private fun row(): LinearLayout = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }

    private fun column(background: Int?, padding: Int): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        background?.let(::setBackgroundResource)
        setPadding(padding, padding, padding, padding)
    }

    private fun LinearLayout.addSpaced(view: View, top: Int = dp(10)) {
        val params = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        if (view is TextView && view.background != null) params.width = ViewGroup.LayoutParams.WRAP_CONTENT
        if (childCount > 0) params.topMargin = top
        addView(view, params)
    }

    private fun marginStart(value: Int) = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.WRAP_CONTENT,
        ViewGroup.LayoutParams.WRAP_CONTENT,
    ).apply { marginStart = value }

    private fun dp(value: Int): Int = (value * context.resources.displayMetrics.density).roundToInt()
}
