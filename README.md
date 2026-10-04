# Amp Kiosk (Android)

A minimal Android wrapper around the Amp dashboard: one fullscreen WebView
instance, nothing else. Specifically made for old and very low-end devices/tablets to give them another life.

Targets Android 10 (API 29), works down to API 24, and has no dependency
on Google Play Services.

## What's in this project

```
AmpKiosk/
  app/
    src/main/
      AndroidManifest.xml
      java/com/amp/kiosk/MainActivity.kt   - the fullscreen WebView shell
      java/com/amp/kiosk/BootReceiver.kt   - relaunches on reboot
      res/...
    build.gradle
  build.gradle
  settings.gradle
  gradle.properties
```

There's no Gradle wrapper checked in (the wrapper jar is a binary file,
not something worth hand-rolling as text) - Android Studio generates it
automatically the first time you open the project. If you'd rather build
from the command line without Android Studio, run `gradle wrapper` once
inside this folder (needs Gradle installed), which creates `gradlew` /
`gradlew.bat` for you.

## 1. Build the APK

**No local install at all (recommended if you're short on disk space or
time) — let GitHub build it for you:**

This project includes `.github/workflows/build-apk.yml`, which builds the
APK on GitHub's servers whenever you push the code. You never install
Android Studio, a JDK, or the Android SDK on your own machine - just a
browser.

1. Create a free account at [github.com](https://github.com) if you don't
   have one.
2. Click **+ → New repository** (top right). Any name, public or private,
   no need to add a README/license - just create it.
3. On the empty repo's page, click **uploading an existing file** (or
   **Add file → Upload files**).
4. Drag the *entire unzipped `AmpKiosk` folder* onto the upload area
   (Chrome/Edge support dragging a whole folder, not just individual
   files - make sure `.github/workflows/build-apk.yml` shows up in the
   file list before committing; GitHub sometimes hides dotfolders from
   the preview but still uploads them).
5. Scroll down, click **Commit changes**.
6. Click the **Actions** tab at the top of the repo. You should see a
   "Build APK" run start automatically (a few seconds after the commit)
   or already in progress. Click into it.
7. Wait for it to finish (a green checkmark, usually 3-5 minutes).
8. Scroll to the bottom of that run's page to **Artifacts**, and click
   **AmpKiosk-debug-apk** to download it. It downloads as a `.zip` -
   unzip it to get `app-debug.apk`.
9. Transfer that APK to the tablet (see step 3 below).

If the run fails instead of going green, click into it to see which step
errored, and paste that here - it's almost always a version-pinning
mismatch in the workflow file that's a one-line fix.

**With Android Studio, if you'd rather build locally anyway:**
1. File → Open → select the `AmpKiosk` folder.
2. Let it sync (first sync downloads the Gradle wrapper + dependencies).
3. Build → Build Bundle(s)/APK(s) → Build APK(s).
4. The APK lands in `app/build/outputs/apk/debug/app-debug.apk`.

**From the command line, without Android Studio** (lighter than the full
IDE - just a JDK + the Android SDK *command-line tools* package, which is
a few hundred MB rather than Android Studio's multi-GB install):
1. Install a JDK 17 (e.g. [Temurin](https://adoptium.net/)).
2. Download the ["command line tools only"](https://developer.android.com/studio#command-tools)
   package from the bottom of that page (not the full Android Studio
   download) and unzip it somewhere.
3. Use its `sdkmanager` to install just what this project needs:
   `sdkmanager "platforms;android-33" "build-tools;33.0.2" "platform-tools"`
4. From the `AmpKiosk` folder: `gradle wrapper` (needs Gradle installed
   separately, or use a portable Gradle distribution), then
   `./gradlew assembleDebug`.

This is still more setup than the GitHub Actions route above, so it's
only worth it if you specifically want an offline/local build.

## 2. Install it on the tablet

Enable Developer Options on the tablet (Settings → About tablet → tap
"Build number" 7 times), then turn on USB debugging. Then, from your
computer with the tablet plugged in:

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

No USB cable handy? Copy the APK onto the tablet (USB storage, or `adb
push` + a file manager) and open it there - you'll need to allow
"install from unknown sources" the first time.

## 3. First launch

The app has no server address baked in - on first open it asks for one,
e.g.:

```
http://192.168.1.50:8080
```

That's the address of whatever machine is running `server.py` on your
network (use its LAN IP, not `127.0.0.1` - `127.0.0.1` on the tablet
means the tablet itself). The address is saved, so this only happens
once.

To change it later: the dashboard itself has no visible settings button
by design, so **tap the top-left corner of the screen five times quickly**
to reopen the prompt. From there you can also jump to Android's own
Settings app, or exit the kiosk entirely.

## 4. Making it feel like an actual kiosk

None of these are required for the app to work - they're optional
hardening if this tablet is going to sit on a wall permanently.

**Keep it pinned to one screen (recommended, no special permissions):**
Settings → Security (wording varies by ROM) → turn on **Screen pinning**.
The app tries to pin itself automatically on launch once this is turned
on; if it's off, the app still runs fine, it just won't resist someone
swiping to recents or pulling down notifications.

**Make it the default home screen (optional, not recommended if you use your device for multiple purposes):** the manifest already
declares the `HOME` category, so Android will ask "Use Amp Kiosk as your
Home app?" the next time you press the home button, or you can set it
directly in Settings → Apps → Default apps → Home app. This means the
tablet boots straight into the dashboard instead of the normal launcher.
If you don't want that, delete the `<category
android:name="android.intent.category.HOME" />` line from
`AndroidManifest.xml` before building - the app still works as a normal
launcher icon either way.

**Survive reboots:** `BootReceiver` relaunches the app automatically
after the tablet restarts. Some custom ROMs block `BOOT_COMPLETED` for
apps that have never been opened - if a fresh install doesn't auto-start
after a reboot, open the app by hand once and every reboot after that
should work.

**Escape hatch:** five-tap the top-left corner → "Exit kiosk" unpins the screen
and closes the app, or "Device settings" jumps straight to Android
Settings without closing the app. Worth testing both once after setup,
especially if you've also set the app as the default Home app, so you
know how to get back out if you ever need to.

## Notes

- The app talks to your server over plain HTTP by design
  (`usesCleartextTraffic="true"`) - that's fine for a LAN-only Flask
  process, but don't point this at anything over the open internet as-is.
- If the server process restarts or the tablet briefly loses Wi-Fi, the
  WebView retries on its own every few seconds rather than sitting on a
  dead page - no manual refresh needed.
- This does **not** use Android's device-owner / full enterprise kiosk
  mode (that requires provisioning the tablet with no existing accounts
  and a dedicated device-admin policy). Screen pinning covers the common
  case; device-owner mode is a further step if you ever need the status
  bar fully locked down too.
