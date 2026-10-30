package com.meshilens.android

import android.content.Context
import android.util.AttributeSet
import android.widget.ScrollView

/** A ScrollView that wraps its content until [maxHeight], then scrolls. */
class MaxHeightScrollView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : ScrollView(context, attrs) {
    var maxHeight = 0
        set(value) {
            field = value
            requestLayout()
        }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val heightSpec = if (maxHeight > 0) MeasureSpec.makeMeasureSpec(maxHeight, MeasureSpec.AT_MOST) else heightMeasureSpec
        super.onMeasure(widthMeasureSpec, heightSpec)
    }
}
