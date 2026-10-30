package com.meshilens.android

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import kotlin.math.roundToInt

/**
 * Share mode: Google Maps → 分享 → MeshiLens opens this bottom sheet.
 *
 * It needs no accessibility permission, but Maps only shares the name and a
 * short link: without the phone or Japanese address the match is usually weak,
 * so the card lists candidates for the user to confirm.
 */
class ShareActivity : Activity() {
    private lateinit var body: LinearLayout
    private lateinit var title: TextView
    private lateinit var renderer: CardRenderer
    private var session: LookupSession? = null
    private var request = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_share)
        body = findViewById(R.id.share_body)
        title = findViewById(R.id.share_title)
        findViewById<MaxHeightScrollView>(R.id.share_scroll).maxHeight =
            (resources.displayMetrics.heightPixels * 0.7f).roundToInt()
        findViewById<View>(R.id.share_root).setOnClickListener { finish() }
        findViewById<View>(R.id.share_close).setOnClickListener { finish() }
        SystemBars.pad(window, findViewById(R.id.share_sheet), includeTop = false)
        renderer = CardRenderer(this, object : CardRenderer.Actions {
            override fun openUrl(url: String) = openExternal(url)

            override fun select(candidate: TabelogCandidate) {
                session?.select(candidate)
            }

            override fun retry() = handle(intent)
        })
        handle(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handle(intent)
    }

    override fun onDestroy() {
        session?.cancel()
        request += 1
        super.onDestroy()
    }

    private fun handle(intent: Intent?) {
        session?.cancel()
        val current = ++request
        val shared = SharedMapsLink.parse(
            text = intent?.getStringExtra(Intent.EXTRA_TEXT),
            title = (intent?.getCharSequenceExtra(Intent.EXTRA_TITLE) ?: intent?.getStringExtra(Intent.EXTRA_SUBJECT))?.toString(),
        )
        if (shared == null) {
            title.text = ""
            renderer.renderMessage(body, "沒有讀到 Google 地圖連結。請在 Google 地圖店家頁按「分享」，再選「MeshiLens」。")
            return
        }
        title.text = shared.name
        renderer.render(body, CardState.Loading(shared.name))
        val userAgent = AppServices.userAgent(this)
        AppServices.network.execute {
            val place = runCatching { SharedMapsLink.placeFrom(shared, ShortLinkResolver.resolve(shared.url, userAgent)) }
            AppServices.main.post {
                if (current != request || isDestroyed) return@post
                val resolved = place.getOrElse { error ->
                    val message = (error as? LookupException)?.message ?: "無法讀取 Google 地圖連結"
                    renderer.render(body, CardState.Failed(shared.name, message))
                    return@post
                }
                if (resolved == null) {
                    renderer.renderMessage(body, "讀不到店名，請改從 Google 地圖店家頁分享。")
                    return@post
                }
                title.text = resolved.name
                startLookup(resolved)
            }
        }
    }

    private fun startLookup(place: PlaceSnapshot) {
        session = AppServices.session(this, place) { state ->
            if (!isDestroyed) renderer.render(body, state)
        }.also { it.start() }
    }

    private fun openExternal(url: String) {
        if (!url.startsWith("https://")) return
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (error: ActivityNotFoundException) {
            // No browser installed; nothing else to open the link with.
        }
    }
}
