# Cloud Relay Tracking (Desktop + Mobile)

This adds a self-hosted relay so real Pocket Option trade events can be shared to mobile.
It also acts as a bot execution bridge when direct Pocket Option API integration is unavailable.

## 1) Run relay server

From project folder:

```bash
python cloud_relay_server.py
```

Relay defaults:

- Health: `http://<host>:8787/relay/health`
- Ingest: `POST http://<host>:8787/relay/trade-event`
- Fetch: `GET  http://<host>:8787/relay/trades?user_key=<key>&since_id=<event_id>`
- Bot queue (mobile): `POST /relay/bot-order`, `GET /relay/bot-orders?user_key=<key>&since_id=<order_id>`
- Bot execution result (helper -> relay): `POST /relay/bot-order-result`, `GET /relay/bot-results?user_key=<key>`

Security/ops env vars (optional but recommended):

- `RELAY_API_TOKEN` - require `X-Relay-Token` for ingest/fetch
- `RELAY_MAX_EVENTS` - max retained events (default `50000`)
- `RELAY_RETENTION_DAYS` - age-based cleanup window (default `30`)
- `RELAY_MAX_REQ_PER_MIN` - per-IP rate limit (default `180`)

Data is stored in `relay-data/events.jsonl`.

## 2) Configure mobile app

In mobile app -> `More` -> `Cloud relay (Auto Track)`:

- Set `Relay URL` (for example `https://your-domain.com`)
- Set `User key` (same key used by your event sender)
- Set `Relay token` if server uses `RELAY_API_TOKEN`
- Enable `Auto-sync relay while Auto Track is ON`
- Save settings, test relay, then toggle Auto Track ON

The app pulls new relay events and inserts them into local history.

## 3) Configure userscript (producer)

Open `userscripts/PocketOption-Trade-Logger.user.js` and set:

- `CLOUD_RELAY_URL`
- `CLOUD_RELAY_USER_KEY`
- `CLOUD_RELAY_TOKEN` (if relay token is enabled)

When set, each detected trade is posted to both:

- local desktop receiver (`127.0.0.1:5051`), and
- cloud relay (`/relay/trade-event`)

## Notes

- Keep `user_key` private; it identifies your event stream.
- Relay and mobile do de-duplication by `trade_id`.
- Mobile relay sync works independently of desktop runtime.
- For mobile bot execution: use the in-app **Download bot executor userscript** button and run that userscript in Tampermonkey on the trading browser/device.
