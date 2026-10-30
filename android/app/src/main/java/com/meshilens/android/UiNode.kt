package com.meshilens.android

/** The few node properties Maps parsing needs, so it can run against fakes in JVM tests. */
interface UiNode {
    val viewId: String
    val text: String
    val description: String
    val childCount: Int

    fun child(index: Int): UiNode?
}
