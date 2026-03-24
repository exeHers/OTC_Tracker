#!/usr/bin/env python3
"""
Pocket Option trade event receiver for the desktop tracker.

Endpoints:
  POST /trade-event     — JSON trade from Tampermonkey (only when collection is ON)
  GET  /tracking-status — { enabled, session_id, session_started_at_utc } for the helper
  POST /tracking-session — { "enabled": true|false } — GUI toggle (starts new session on enable)
  GET  /health          — { "ok": true }
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

from tracker import append_trade_row
from trade_collection_state import load_state, public_status, remember_fingerprint, set_collection_enabled


HOST = "127.0.0.1"
PORT = 5051


def _parse_utc(s: Optional[str]) -> Optional[datetime]:
    if not s or not str(s).strip():
        return None
    t = str(s).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _session_start_dt() -> Optional[datetime]:
    st = load_state().get("session_started_at_utc")
    return _parse_utc(st) if st else None


def _fingerprint(data: Dict[str, Any]) -> str:
    tid = (data.get("trade_id") or "").strip()
    if tid:
        return tid
    raw = "|".join(
        [
            str(data.get("asset") or ""),
            str(data.get("closed_at") or ""),
            str(data.get("amount") or ""),
            str(data.get("result") or ""),
            str(data.get("direction") or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TradeEventHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        # Quieter console; uncomment for debug
        if self.path not in ("/favicon.ico",):
            super().log_message(fmt, *args)

    def _set_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/tracking-status"):
            body = json.dumps(public_status()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._set_cors()
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/health"):
            body = json.dumps({"ok": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._set_cors()
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self._set_cors()
        self.end_headers()

    def do_POST(self) -> None:
        if self.path.startswith("/tracking-session"):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            en = bool(data.get("enabled"))
            state = set_collection_enabled(en, new_session=True if en else False)
            out = json.dumps({"ok": True, "status": public_status()}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self._set_cors()
            self.end_headers()
            self.wfile.write(out)
            print("Tracking session:", "ON" if en else "OFF", "|", state.get("session_id"))
            return

        if self.path != "/trade-event":
            self.send_response(404)
            self._set_cors()
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            data = json.loads(body.decode("utf-8"))
        except Exception as e:
            print("Invalid JSON in trade event:", e)
            self.send_response(400)
            self._set_cors()
            self.end_headers()
            return

        def respond_json(payload: Dict[str, Any], code: int = 200) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self._set_cors()
            self.end_headers()
            self.wfile.write(raw)

        if not load_state().get("enabled"):
            respond_json({"accepted": False, "reason": "collection_off"})
            return

        sess = _session_start_dt()
        if not sess:
            respond_json({"accepted": False, "reason": "session_not_ready"})
            return

        closed_at = _parse_utc(str(data.get("closed_at") or ""))
        if not closed_at:
            ds = str(data.get("date") or "").strip()
            ts = str(data.get("time") or "").strip()
            if len(ds) >= 10 and len(ts) >= 5:
                closed_at = _parse_utc(f"{ds[:10]}T{ts[:8]}")
        if not closed_at:
            respond_json({"accepted": False, "reason": "missing_closed_at"})
            return

        if closed_at < sess - timedelta(seconds=2):
            respond_json({"accepted": False, "reason": "before_session_start"})
            return

        fp = _fingerprint(data)
        if not remember_fingerprint(fp):
            respond_json({"accepted": False, "reason": "duplicate"})
            return

        try:
            ca = str(data.get("closed_at") or "")
            date = ca[:10] if len(ca) >= 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            time_s = ca[11:19] if len(ca) >= 19 else datetime.now(timezone.utc).strftime("%H:%M:%S")

            stake = float(data.get("amount", 0) or 0)
            payout_v = data.get("payout", 0)
            try:
                payout = float(payout_v) if payout_v is not None else 0.0
            except (TypeError, ValueError):
                payout = 0.0

            result = (data.get("result") or "W").upper()[:1]
            asset = (data.get("asset") or "OTC").strip() or "OTC"
            direction = (data.get("direction") or "").strip()
            dur = data.get("duration_sec")
            if dur is not None and dur != "":
                try:
                    duration_sec = str(int(float(dur)))
                except (TypeError, ValueError):
                    duration_sec = ""
            else:
                duration_sec = ""
            trade_id = (data.get("trade_id") or fp)[:200]

            row = {
                "date": date,
                "time": time_s,
                "amount": str(abs(stake)),
                "asset": asset,
                "result": result,
                "payout": str(payout),
                "direction": direction,
                "duration_sec": duration_sec,
                "source": "browser",
                "trade_id": trade_id,
            }

            append_trade_row(row)
            print("Received trade event:", row)
            respond_json({"accepted": True, "trade_id": trade_id})
        except Exception as e:
            print("Error handling trade event:", e)
            respond_json({"accepted": False, "reason": str(e)}, 500)


def run_server() -> None:
    server = HTTPServer((HOST, PORT), TradeEventHandler)
    print(f"PocketOption receiver: http://{HOST}:{PORT}/trade-event  (status: /tracking-session GET /tracking-status)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
