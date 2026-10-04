package com.amp.kiosk

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.graphics.Color
import android.os.Bundle
import android.provider.Settings
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import androidx.appcompat.app.AppCompatActivity

/**
 * A single-purpose kiosk shell: one fullscreen WebView pointed at the Amp
 * dashboard (server.py + index.html, served from wherever that Flask
 * process is running on your network). The app itself has no UI of its
 * own - it just hosts the page, keeps the screen awake, stays fullscreen,
 * and reloads on its own if the connection to the server drops.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var prefs: SharedPreferences

    private var tapCount = 0
    private var lastTapAt = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        hideSystemBars()

        webView = WebView(this)
        setContentView(webView)
        configureWebView()
        installSettingsGesture()

        val savedUrl = prefs.getString(KEY_URL, null)
        if (savedUrl.isNullOrBlank()) {
            promptForUrl()
        } else {
            webView.loadUrl(savedUrl)
        }

        tryPinScreen()
    }

    @SuppressLint("SetJavaScriptEnabled", "ClickableViewAccessibility")
    private fun configureWebView() {
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            mediaPlaybackRequiresUserGesture = false
            cacheMode = WebSettings.LOAD_DEFAULT
            builtInZoomControls = false
            displayZoomControls = false
            setSupportZoom(false)
        }
        webView.setBackgroundColor(Color.BLACK)
        webView.overScrollMode = View.OVER_SCROLL_NEVER
        webView.isHapticFeedbackEnabled = false

        // Swallow long-press (text-selection / "open in new tab" popups) -
        // nothing on a fixed kiosk display should ever need them.
        webView.setOnLongClickListener { true }

        webView.webChromeClient = WebChromeClient()
        webView.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame != false) {
                    // Nobody's sitting at this tablet to hit refresh if the
                    // server machine is mid-reboot or the network blips -
                    // just keep trying.
                    view?.postDelayed({ view.reload() }, RETRY_DELAY_MS)
                }
            }
        }
    }

    /**
     * The kiosk page has no visible settings affordance by design, so five
     * quick taps in the top-left corner (an area nothing in the dashboard
     * UI uses) reopens the server-address prompt.
     */
    private fun installSettingsGesture() {
        webView.setOnTouchListener { _, event ->
            if (event.action == MotionEvent.ACTION_DOWN &&
                event.x < CORNER_HOTSPOT_PX && event.y < CORNER_HOTSPOT_PX
            ) {
                val now = System.currentTimeMillis()
                tapCount = if (now - lastTapAt < TAP_WINDOW_MS) tapCount + 1 else 1
                lastTapAt = now
                if (tapCount >= TAPS_TO_OPEN_SETTINGS) {
                    tapCount = 0
                    promptForUrl()
                }
            }
            false // never actually consume the touch - the page still gets it
        }
    }

    private fun promptForUrl() {
        val input = EditText(this)
        input.hint = "http://192.168.1.50:8080"
        prefs.getString(KEY_URL, null)?.let { input.setText(it) }

        AlertDialog.Builder(this)
            .setTitle("Amp server address")
            .setMessage("Enter the address of the machine running server.py.")
            .setView(input)
            .setCancelable(false)
            .setPositiveButton("Load") { _, _ ->
                val url = input.text.toString().trim()
                if (url.isNotEmpty()) {
                    prefs.edit().putString(KEY_URL, url).apply()
                    webView.loadUrl(url)
                }
            }
            .setNeutralButton("Device settings") { _, _ ->
                startActivity(Intent(Settings.ACTION_SETTINGS))
            }
            .setNegativeButton("Exit kiosk") { _, _ ->
                try { stopLockTask() } catch (e: IllegalStateException) { /* wasn't pinned */ }
                finishAndRemoveTask()
            }
            .show()
    }

    /**
     * Screen pinning (Android's built-in "lock to this app") keeps the
     * person on this one screen without needing device-owner provisioning.
     * It has to be turned on once by hand first, in Settings > Security >
     * screen pinning (wording varies by ROM) - until then this just fails
     * quietly and the app runs as a normal unpinned app.
     */
    private fun tryPinScreen() {
        try {
            startLockTask()
        } catch (e: SecurityException) {
            // Screen pinning isn't enabled yet - not fatal.
        } catch (e: IllegalStateException) {
            // Already pinned, or pinning isn't available on this ROM.
        }
    }

    private fun hideSystemBars() {
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_FULLSCREEN
            )
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemBars()
    }

    @Deprecated("Deprecated in Java", ReplaceWith("super.onBackPressed()"))
    override fun onBackPressed() {
        // Intentionally does nothing: this is a fixed kiosk display, not a
        // browser someone should be able to back out of with one tap.
    }

    override fun onDestroy() {
        try { stopLockTask() } catch (e: IllegalStateException) { /* wasn't pinned */ }
        webView.destroy()
        super.onDestroy()
    }

    companion object {
        private const val PREFS_NAME = "amp_kiosk"
        private const val KEY_URL = "server_url"
        private const val RETRY_DELAY_MS = 3000L
        private const val CORNER_HOTSPOT_PX = 150
        private const val TAP_WINDOW_MS = 600L
        private const val TAPS_TO_OPEN_SETTINGS = 5
    }
}
