package com.meshilens.android

import android.view.accessibility.AccessibilityNodeInfo

/** Adapts a live accessibility node to the [UiNode] view that [MapsPlaceReader] parses. */
class AccessibilityUiNode(private val node: AccessibilityNodeInfo) : UiNode {
    override val viewId: String get() = node.viewIdResourceName.orEmpty()
    override val text: String get() = node.text?.toString().orEmpty()
    override val description: String get() = node.contentDescription?.toString().orEmpty()
    override val childCount: Int get() = node.childCount

    override fun child(index: Int): UiNode? = node.getChild(index)?.let(::AccessibilityUiNode)
}
