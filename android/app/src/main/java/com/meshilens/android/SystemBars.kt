package com.meshilens.android

import android.os.Build
import android.view.View
import android.view.Window
import android.view.WindowInsets

/** Pads a view by the system bars once the app targets edge-to-edge layouts. */
object SystemBars {
    fun pad(window: Window, view: View, includeTop: Boolean = true) {
        // Before Android 11 the default window already sits between the bars;
        // from Android 15 edge-to-edge is enforced for this targetSdk.
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.VANILLA_ICE_CREAM) {
            @Suppress("DEPRECATION")
            window.setDecorFitsSystemWindows(false)
        }
        val left = view.paddingLeft
        val top = view.paddingTop
        val right = view.paddingRight
        val bottom = view.paddingBottom
        view.setOnApplyWindowInsetsListener { target, insets ->
            val bars = insets.getInsets(WindowInsets.Type.systemBars())
            target.setPadding(
                left + bars.left,
                top + if (includeTop) bars.top else 0,
                right + bars.right,
                bottom + bars.bottom,
            )
            insets
        }
        view.requestApplyInsets()
    }
}
