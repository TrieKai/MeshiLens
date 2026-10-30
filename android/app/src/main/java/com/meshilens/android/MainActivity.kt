package com.meshilens.android

import android.accessibilityservice.AccessibilityServiceInfo
import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.view.accessibility.AccessibilityManager
import android.widget.TextView

/** Setup screen: explains the floating card, its single permission, and share mode. */
class MainActivity : Activity() {
    private lateinit var statusTitle: TextView
    private lateinit var statusBody: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        SystemBars.pad(window, findViewById(R.id.main_content))
        statusTitle = findViewById(R.id.main_status_title)
        statusBody = findViewById(R.id.main_status_body)
        findViewById<TextView>(R.id.main_version).text = getString(R.string.main_version, AppServices.versionName(this))
        findViewById<View>(R.id.main_open_accessibility).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        findViewById<View>(R.id.main_open_app_info).setOnClickListener {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", packageName, null)))
        }
        val openMaps = findViewById<View>(R.id.main_open_maps)
        val mapsIntent = packageManager.getLaunchIntentForPackage(MapsPlaceReader.MAPS_PACKAGE)
        openMaps.visibility = if (mapsIntent == null) View.GONE else View.VISIBLE
        openMaps.setOnClickListener { mapsIntent?.let(::startActivity) }
    }

    override fun onResume() {
        super.onResume()
        val enabled = isServiceEnabled()
        statusTitle.setText(if (enabled) R.string.main_status_on else R.string.main_status_off)
        statusBody.setText(if (enabled) R.string.main_status_on_body else R.string.main_status_off_body)
    }

    private fun isServiceEnabled(): Boolean {
        val manager = getSystemService(AccessibilityManager::class.java) ?: return false
        return manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK).any {
            val info = it.resolveInfo.serviceInfo
            info.packageName == packageName && info.name == MapsAccessibilityService::class.java.name
        }
    }
}
