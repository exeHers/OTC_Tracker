# After Making Changes: GitHub + Android Studio

Use this every time you (or the assistant) change the project and you want to push to GitHub and/or build a new APK.

---

## 1. GitHub (push your changes)

Open **PowerShell** or **Command Prompt** and run:

```powershell
cd "c:\Users\donov\Desktop\Trading Journal"

git add .
git status
```
Check the list: you should **not** see `config.json`, `trades.csv`, or `node_modules`. If you do, they’re ignored and won’t be committed.

```powershell
git commit -m "Short description of what changed"
git push origin main
```

**Examples of commit messages:**  
- `Bump version to 1.0.2; fix sync instructions`  
- `Remove deprecated Gradle options`  
- `Update Extras tab layout`

If push asks for a password, use your **Personal Access Token** (not your GitHub password).

---

## 2. Android Studio (sync and build APK)

### A. Sync the web app (if you changed HTML/JS or the main app)

In the same folder:

```powershell
cd "c:\Users\donov\Desktop\Trading Journal"

copy tracker_mobile.html www\index.html
```
Type **Y** and Enter if it asks to overwrite.

```powershell
npx cap sync
```

*(If you only changed Android code (e.g. in the `android/` folder), you can skip the copy and `npx cap sync`.)*

### B. Open the Android project

1. In **Android Studio**: **File → Open**.
2. Select: `c:\Users\donov\Desktop\Trading Journal\android`
3. Wait for **Gradle sync** to finish.

### C. Build the APK

1. **Build → Build Bundle(s) / APK(s) → Build APK(s)**.
2. When the build finishes, click **locate** in the notification (or open the folder below).

**APK location:**  
`android\app\build\outputs\apk\debug\app-debug.apk`

### D. (Optional) Put the new APK on GitHub

1. On GitHub: **exeHers/OTC_Tracker → Releases**.
2. **Create a new release** (or **Edit** an existing one).
3. Set tag (e.g. `v1.0.2`) and title.
4. **Attach** the new `app-debug.apk` (drag and drop).
5. Publish.

---

## Quick reference

| What you did | GitHub | Android Studio |
|--------------|--------|----------------|
| Changed Python, HTML, or docs | `git add .` → `commit` → `push` | Copy `tracker_mobile.html` to `www/index.html` → `npx cap sync` → open `android` → Build APK(s) |
| Only changed files in `android/` | `git add .` → `commit` → `push` | Open `android` → Build APK(s) (no cap sync) |
| Only changed `version.json` or docs | `git add .` → `commit` → `push` | No build needed unless you want a new APK |
