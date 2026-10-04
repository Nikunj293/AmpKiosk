package com.amp.kiosk

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Relaunches the kiosk app after the tablet reboots, so a power cut or a
 * nightly restart doesn't leave it sitting on the regular Android lock
 * screen with nobody around to unlock it.
 *
 * Some custom ROMs restrict BOOT_COMPLETED for apps that haven't been
 * opened at least once since install/update - if this doesn't fire on a
 * fresh install, just open the app manually once and it should work on
 * every reboot after that.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action == Intent.ACTION_BOOT_COMPLETED) {
            val launch = Intent(context, MainActivity::class.java)
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(launch)
        }
    }
}
