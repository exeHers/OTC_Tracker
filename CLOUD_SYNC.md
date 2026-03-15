# Cloud sync (Google Drive / OneDrive)

The app uses a **single JSON file** that you store in a folder that syncs with Google Drive or OneDrive. Same format on desktop and mobile.

---

## Sync file

- **Filename:** e.g. `otc_tracker_sync.json` (any name is fine).
- **Contents:** trades, daily goal, theme, currency, and a timestamp.
- **Where:** Any folder that your PC syncs with Drive or OneDrive (e.g. `C:\Users\You\OneDrive\OTC Tracker\otc_tracker_sync.json` or your Google Drive folder).

---

## Desktop (PC)

1. Open the app → **Extras** tab → **Cloud sync (Drive / OneDrive)**.
2. Click **Browse…** and choose a file **inside** your OneDrive or Google Drive folder (create the file if needed, e.g. `otc_tracker_sync.json`).
3. Click **Save path**.
4. **Upload to sync file** — writes your current trades and settings to that file. Drive/OneDrive will then sync it to the cloud.
5. **Download from sync file** — reads the file and overwrites local data (e.g. after you added trades on your phone and the file synced to the PC).

---

## Mobile (APK)

1. Open the app → **Extras** → **Cloud sync**.
2. **Export sync file** — downloads `otc_tracker_sync.json` to your device. Save or share it into **Google Drive** or **OneDrive** (e.g. use “Save to Drive” or move it into a synced folder).
3. **Import sync file** — tap it, then choose the sync file. You can pick a file from **Downloads** or, if your file picker supports it, from **Google Drive** or **OneDrive** (open the app, find the file, select it). Your local data is replaced by the file’s contents.

---

## Typical flow

- **PC → Phone:** On PC, **Upload to sync file**. Wait for Drive/OneDrive to sync. On phone, open Drive/OneDrive, open the sync file (or use a file picker that can browse Drive), then in the app tap **Import sync file** and select that file.
- **Phone → PC:** On phone, **Export sync file**, save the downloaded file to Drive or OneDrive. After sync, on PC click **Download from sync file** in the app (the path must already point to that file in the synced folder).

No account or API keys are needed; you only use your normal Drive or OneDrive folder and the app’s Export/Import and Upload/Download actions.
