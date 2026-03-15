# Build the OTC Tracker mobile app (Android)

The tracker is set up with **Capacitor** so you can build a real **.apk** and install it like any Android app.

## What’s in place

- **www/** – Web app used by the APK. Keep it in sync with `tracker_mobile.html` (copy to `www/index.html` after edits). No PWA “Add to Home screen” — the app is distributed as an APK.
- **android/** – Android project (added by Capacitor).
- **package.json** – npm project and Capacitor dependencies.
- **capacitor.config.json** – App id `com.otctracker.app`, name “OTC Tracker”, web dir `www`.

## Requirements

- **Node.js** (v18 or newer): [nodejs.org](https://nodejs.org)
- **Android Studio**: [developer.android.com/studio](https://developer.android.com/studio) (for building the APK and/or running an emulator)
- **JDK 17** (usually installed with Android Studio)

---

## Step-by-step guide (Android Studio)

Use this the first time and whenever you want a fully up-to-date APK.

### Step 1: One-time setup (terminal)

1. Open a terminal (PowerShell or Command Prompt).
2. Go to the project folder:
   ```bash
   cd "c:\Users\donov\Desktop\Trading Journal"
   ```
3. Install Node dependencies (only needed once):
   ```bash
   npm install
   ```
4. Copy the web app into the Android project:
   ```bash
   npx cap sync
   ```
5. Open the **Android** project in Android Studio:
   ```bash
   npx cap open android
   ```
   This opens Android Studio with the `android` folder (not the whole Trading Journal folder). That’s correct.

### Step 2: In Android Studio (first time)

1. Wait for **Gradle sync** to finish (bottom status bar). If it asks to install anything (SDK, NDK, etc.), accept.
2. Pick a device:
   - **Real phone:** Connect via USB, turn on **Developer options** and **USB debugging**, then choose your device in the device dropdown at the top.
   - **Emulator:** **Tools → Device Manager**, create a virtual device if needed, then select it in the dropdown.
3. Build and run:
   - Click the green **Run** button (or **Run → Run 'app'**).
   - Android Studio will build the APK, install it on the device/emulator, and launch the app.

You now have a working APK. The file is also on your PC at:
`android\app\build\outputs\apk\debug\app-debug.apk`.

### Step 3: When you change something — how updates get into the APK

- **You change the app’s content (HTML/JS/CSS):**  
  Edit `tracker_mobile.html` in your project (or edit `www/index.html`). Then:
  1. If you edited `tracker_mobile.html`, copy it over: copy `tracker_mobile.html` to `www/index.html` (overwrite).
  2. In a terminal (from the project root):
     ```bash
     cd "c:\Users\donov\Desktop\Trading Journal"
     npx cap sync
     ```
  3. In Android Studio: **Build → Build Bundle(s) / APK(s) → Build APK(s)** (or just click **Run** again).  
  The new APK will include your changes.

- **You change something only in Android Studio** (e.g. app name, icon, Android manifest, Kotlin/Java code):  
  No need to run `cap sync`. Just **Build → Build APK(s)** or **Run** in Android Studio. The APK will include those changes.

So: **web app changes → sync with `npx cap sync` → then build/run in Android Studio.** Android-only changes → build/run in Android Studio.

### Step 4: Install the APK on another phone

- Copy `android\app\build\outputs\apk\debug\app-debug.apk` to the phone (USB, email, cloud, etc.) and open it to install, or
- Connect the phone by USB (with USB debugging on) and click **Run** in Android Studio to install and launch.

### Step 5 (optional): Signed APK for sharing or Play Store

1. In Android Studio: **Build → Generate Signed Bundle / APK**.
2. Choose **APK** (or **Android App Bundle** for Play Store).
3. Create a new keystore or use an existing one, set passwords and alias.
4. Pick **release** and finish. The signed APK will be in `android\app\release\` (or the path shown in the wizard).

---

## Build the APK

### 1. Install dependencies (once)

```bash
cd "c:\Users\donov\Desktop\Trading Journal"
npm install
```

### 2. Sync web app into the Android project

Whenever you change files in **www/** (or copy a new version of `tracker_mobile.html` to `www/index.html`):

```bash
npx cap sync
```

### 3. Open the Android project and build

**Quickest way (no Android Studio):** From the project root, run:

```bash
cd android
gradlew.bat assembleDebug
```

The debug APK is at `android/app/build/outputs/apk/debug/app-debug.apk`. Use Android Studio when you need signed or release builds.

**Using Android Studio:** Run:

```bash
npx cap open android
```

Android Studio will open. Then:

- **Build APK:** Menu **Build → Build Bundle(s) / APK(s) → Build APK(s)**. The APK will be under `android/app/build/outputs/apk/` (e.g. `app-debug.apk`).
- **Run on device/emulator:** Click the green Run button (device or emulator must be selected).

### 4. Install the APK on your phone

- Copy `android/app/build/outputs/apk/debug/app-debug.apk` to your phone (USB, cloud, etc.) and open it to install, or
- With the phone connected via USB and USB debugging enabled, use **Run** in Android Studio to install and launch.

## Updating the app after changing the HTML

If you edit **tracker_mobile.html** in the main folder:

1. Copy it into the app’s web folder:
   - Copy `tracker_mobile.html` to `www/index.html` (overwrite).
2. Sync and reopen (or just sync if Android Studio is already open):
   ```bash
   npx cap sync
   npx cap open android
   ```
3. Build/run again from Android Studio.

## Optional: release (signed) APK

For a release build (e.g. for Play Store or to share):

1. In Android Studio: **Build → Generate Signed Bundle / APK**.
2. Create or use a keystore and follow the wizard to produce a signed APK or AAB.

---

**Summary:** Run `npm install` once, then use `npx cap sync` and `npx cap open android` to build and run the OTC Tracker as a native Android app.
