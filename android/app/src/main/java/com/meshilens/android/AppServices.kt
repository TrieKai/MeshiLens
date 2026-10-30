package com.meshilens.android

import android.content.Context
import android.os.Handler
import android.os.Looper
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/** Process-wide API client and threads, shared by the floating card and share mode. */
object AppServices {
    private var api: MeshiLensApi? = null

    val main: Handler by lazy { Handler(Looper.getMainLooper()) }

    // Each lookup needs at most two requests at once (`/match` with `/michelin`).
    val network: ExecutorService by lazy { Executors.newFixedThreadPool(3) }

    @Synchronized
    fun api(context: Context): MeshiLensApi = api ?: MeshiLensApi(userAgent(context)).also { api = it }

    fun userAgent(context: Context): String = "MeshiLens-Android/${versionName(context)}"

    fun versionName(context: Context): String = runCatching {
        context.packageManager.getPackageInfo(context.packageName, 0).versionName
    }.getOrNull().orEmpty()

    fun session(context: Context, place: PlaceSnapshot, onState: (CardState) -> Unit): LookupSession =
        LookupSession(
            place = place,
            client = api(context),
            background = { network.execute(it) },
            main = { main.post(it) },
            onState = onState,
        )
}
