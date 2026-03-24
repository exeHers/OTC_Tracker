# Pocket Option ↔ OTC Tracker (browser helper)

## Current setup (recommended)

Trade tracking uses **Firefox + Tampermonkey** and the **local receiver** built into the desktop app (`127.0.0.1:5051`). No SSID/API is required for this path.

### 1. Desktop app

1. Start **`tracker_gui.py`** (double-click or `python tracker_gui.py`).
2. The receiver starts **automatically** in the background on port **5051**.
3. Open the **Auto Track** tab:
   - **Collection ON** — saves trades that **close while this is ON** (state is saved to disk and stays on until you turn it off).
   - **Collection OFF** — the browser helper may still run, but **nothing is written** to your journal.
4. Each time you switch **OFF → ON**, a **new session** starts so **old rows already on Pocket Option’s list are not imported** (no history backfill).

### 2. Tampermonkey script

1. Install **Tampermonkey** in **Firefox**.
2. Create a new script and paste the contents of **`userscripts/PocketOption-Trade-Logger.user.js`** from this project.
3. Save and open Pocket Option. The script polls **`/tracking-status`** and only POSTs to **`/trade-event`** when **Collection** is **ON** in the app.

### 3. Accuracy & data

- Trades are stored in **`trades.csv`** with extra columns (`payout`, `direction`, `duration_sec`, `source`, `trade_id`) for any market/timeframe Pocket Option shows in the deals list.
- **History** tab uses **daily dividers** (grouped by date) and shows **B** = browser / **M** = manual.
- **Delete today** — removes all trades for **today’s calendar date**.
- **Clear selected** — removes chosen rows (not divider lines).
- **Wipe all data** — clears trades, resets collection state (Collection OFF), and resets basic config.

### 4. Endpoints (for debugging)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `http://127.0.0.1:5051/tracking-status` | `{ enabled, session_id, session_started_at_utc }` |
| POST | `http://127.0.0.1:5051/tracking-session` | `{"enabled": true\|false}` — same as the GUI toggle |
| POST | `http://127.0.0.1:5051/trade-event` | JSON trade (only accepted when Collection is ON and after session start) |

---

## Legacy: Pocket Option API / SSID (optional)

The codebase may still include **API-style** helpers for advanced use. That path uses a **WebSocket auth message** (sometimes called “SSID”) from the browser Network tab, **not** a normal site cookie.

If you use the **API** route, install:

```bash
pip install pocketoptionapi-async
```

Then follow library docs for session/auth. The **desktop GUI no longer exposes** an SSID panel; browser helper + Collection toggle is the supported tracking flow.
