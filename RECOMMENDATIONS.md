# OTC Tracker — Feature & improvement ideas

Suggestions you can add later (not already in the app). Pick what fits your workflow.

---

## Trading & data

- **Note/tag per trade** — Optional one-line note when logging (e.g. "revenge", "clean setup"). Store with the trade and show in history; filter or search by tag.
- **Streak counter** — Show current win or loss streak (e.g. "3W" or "2L") on the dashboard so you see runs at a glance.
- **Session timer** — How long you’ve been trading today (start when you log first trade, or a manual "Start session" button). Helps with discipline.
- **Per-asset stats** — In Extras or a small panel: which assets you trade most, win rate and P&L per asset (e.g. OTC vs others).
- **Date-range filter in history** — Besides "All" and "Today", add "This week" or a custom date range so you can review specific periods.
- **Import from CSV** — Let desktop/mobile import a CSV (same format as export) to merge data from another device or backup.

---

## UX & polish

- **Sound or haptic on log** — Short sound or vibration when you log a trade (optional, toggle in Extras) so you get quick feedback without looking.
- **Backup & restore** — Export full app data (trades, goal, theme, currency, update URL) as one JSON file, and "Restore from file" to load it. Good for moving between devices or saving a snapshot.
- **Simple P&L chart** — A small chart (e.g. session or daily P&L over time, or cumulative) so you see the curve, not just numbers. Could be desktop-first (e.g. in GUI) then mobile.
- **Weekly/monthly summary** — Optional screen or export: total trades, win rate, total P&L, best/worst day for the last 7 or 30 days.

---

## Mobile (APK) specific

- **Android home-screen widget** — A small widget showing e.g. today’s session mali or "X trades today" so you don’t have to open the app.
- **Optional app lock** — PIN or biometric lock when opening the app (Capacitor plugin), so only you can see your data.
- **Reminder notification** — Optional "Remind me to log" after X minutes of no trades, so you don’t forget to log sessions.

---

## Desktop specific

- **Minimize to tray** — Run in system tray with a "Log trade" quick action so the window doesn’t have to stay open.
- **Global hotkey** — e.g. Ctrl+Shift+T to open "Log trade" or focus the app from anywhere.

---

## Sync & multi-device (bigger)

- **Cloud sync** — Sync trades (and optionally goal/settings) across desktop and mobile via a simple backend or cloud storage (e.g. Firebase, or a file in Dropbox/Google Drive). Would need account or link code and conflict rules.

---

**Tip:** When you add a feature, keep mobile and desktop in sync: implement in `tracker_mobile.html` and desktop (e.g. `tracker_gui.py` / `tracker.py`), then copy `tracker_mobile.html` to `www/index.html` and run `npx cap sync` before building the APK.
