package com.meshilens.android

import android.accessibilityservice.AccessibilityService
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.text.TextUtils
import android.util.TypedValue
import android.view.ContextThemeWrapper
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import kotlin.math.hypot
import kotlin.math.roundToInt

/**
 * The card drawn over Google Maps.
 *
 * It is an accessibility overlay, so it needs no "display over other apps"
 * permission; it never takes focus and only its own bounds receive touches,
 * which is why Maps stays fully usable underneath. Collapsed it is a small
 * draggable pill; tapping it expands the full card.
 */
class FloatingCard(service: AccessibilityService, actions: CardRenderer.Actions) {
    private val context: Context = ContextThemeWrapper(service, R.style.Theme_MeshiLens)
    private val windowManager = service.getSystemService(WindowManager::class.java)
    private val prefs = service.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private val metrics = context.resources.displayMetrics
    private val touchSlop = ViewConfiguration.get(context).scaledTouchSlop
    private val renderer = CardRenderer(context, actions)

    private val root = FrameLayout(context).apply {
        // Room for the elevation shadow inside the wrap-content window.
        setPadding(dp(8), dp(8), dp(8), dp(8))
        clipToPadding = false
    }
    private val pillLabel = label(13f, R.color.ml_ink, bold = true).apply {
        maxWidth = dp(250)
        maxLines = 1
        ellipsize = TextUtils.TruncateAt.END
    }
    private val pill = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setBackgroundResource(R.drawable.bg_pill)
        elevation = dp(6).toFloat()
        setPadding(dp(12), dp(9), dp(14), dp(9))
        addView(View(context).apply { setBackgroundResource(R.drawable.bg_dot) }, LinearLayout.LayoutParams(dp(9), dp(9)))
        addView(pillLabel, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            marginStart = dp(8)
        })
    }
    private val body = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(16), dp(2), dp(16), dp(16))
    }
    private val panel = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setBackgroundResource(R.drawable.bg_card)
        elevation = dp(8).toFloat()
        visibility = View.GONE
    }

    private val params = WindowManager.LayoutParams(
        ViewGroup.LayoutParams.WRAP_CONTENT,
        ViewGroup.LayoutParams.WRAP_CONTENT,
        WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
        PixelFormat.TRANSLUCENT,
    ).apply {
        gravity = Gravity.TOP or Gravity.END
        title = "MeshiLens"
    }

    private var state: CardState? = null
    private var expanded = false

    var isAttached = false
        private set

    init {
        val header = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(16), dp(10), dp(6), dp(2))
            addView(label(14f, R.color.ml_accent, bold = true).apply { text = CardText.BRAND })
            addView(
                label(11f, R.color.ml_muted).apply { text = CardText.SOURCE },
                LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { marginStart = dp(8) },
            )
            addView(label(13f, R.color.ml_accent, bold = true).apply {
                text = context.getString(R.string.card_collapse)
                setPadding(dp(12), dp(10), dp(12), dp(10))
                setOnClickListener { setExpanded(false) }
            })
        }
        header.setOnTouchListener(DragToMove())
        val scroll = MaxHeightScrollView(context).apply {
            maxHeight = (metrics.heightPixels * 0.55f).roundToInt()
            addView(body)
        }
        panel.addView(header)
        panel.addView(scroll)
        pill.setOnClickListener { setExpanded(true) }
        pill.setOnTouchListener(DragToMove())

        root.addView(pill)
        root.addView(panel, FrameLayout.LayoutParams(panelWidth(), ViewGroup.LayoutParams.WRAP_CONTENT))
    }

    /** A new place always starts collapsed so the card never covers the map unasked. */
    fun show(newState: CardState) {
        if (newState.placeName != state?.placeName) expanded = false
        state = newState
        bind()
        attach()
    }

    /** Shows the last state again after the user comes back to Maps. */
    fun reshow() {
        if (state != null) attach()
    }

    /** Leaves the screen but keeps the state (the user switched away from Maps). */
    fun hide() = detach()

    fun clear() {
        state = null
        expanded = false
        detach()
    }

    private fun bind() {
        val current = state ?: return
        pillLabel.text = CardText.pill(current)
        pill.contentDescription = "MeshiLens：${pillLabel.text}，點兩下展開"
        if (expanded) renderer.render(body, current)
        pill.visibility = if (expanded) View.GONE else View.VISIBLE
        panel.visibility = if (expanded) View.VISIBLE else View.GONE
        if (expanded) {
            params.x = 0
            params.y = minOf(savedY(), (metrics.heightPixels * 0.3f).roundToInt())
        } else {
            params.x = prefs.getInt(KEY_X, 0)
            params.y = savedY()
        }
        if (isAttached) windowManager.updateViewLayout(root, params)
    }

    private fun setExpanded(value: Boolean) {
        expanded = value
        bind()
    }

    private fun attach() {
        if (isAttached) return
        runCatching { windowManager.addView(root, params) }.onSuccess { isAttached = true }
    }

    private fun detach() {
        if (!isAttached) return
        runCatching { windowManager.removeViewImmediate(root) }
        isAttached = false
    }

    private fun savedY(): Int = prefs.getInt(KEY_Y, (metrics.heightPixels * 0.36f).roundToInt())

    private fun panelWidth(): Int = minOf(metrics.widthPixels - dp(24), dp(360))

    private fun label(sizeSp: Float, color: Int, bold: Boolean = false) = TextView(context).apply {
        setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
        setTextColor(context.getColor(color))
        if (bold) typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
    }

    private fun dp(value: Int): Int = (value * metrics.density).roundToInt()

    /** Drags the window; a touch that does not move is a click. Only the collapsed position is saved. */
    private inner class DragToMove : View.OnTouchListener {
        private var downX = 0f
        private var downY = 0f
        private var startX = 0
        private var startY = 0
        private var dragging = false

        @SuppressLint("ClickableViewAccessibility")
        override fun onTouch(view: View, event: MotionEvent): Boolean {
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX
                    downY = event.rawY
                    startX = params.x
                    startY = params.y
                    dragging = false
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - downX
                    val dy = event.rawY - downY
                    if (!dragging && hypot(dx, dy) > touchSlop) dragging = true
                    if (dragging && isAttached) {
                        // Gravity END measures x from the right edge.
                        params.x = (startX - dx).roundToInt().coerceIn(0, metrics.widthPixels - dp(80))
                        params.y = (startY + dy).roundToInt().coerceIn(0, metrics.heightPixels - dp(80))
                        windowManager.updateViewLayout(root, params)
                    }
                }
                MotionEvent.ACTION_UP -> {
                    if (dragging) {
                        if (!expanded) prefs.edit().putInt(KEY_X, params.x).putInt(KEY_Y, params.y).apply()
                    } else {
                        view.performClick()
                    }
                }
            }
            return true
        }
    }

    private companion object {
        const val PREFS = "floating_card"
        const val KEY_X = "pill_x"
        const val KEY_Y = "pill_y"
    }
}
