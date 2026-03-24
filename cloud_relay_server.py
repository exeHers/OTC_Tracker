#!/usr/bin/env python3
"""
Simple self-hosted cloud relay for Pocket Option trade events.

Endpoints:
  GET  /relay/health
  POST /relay/trade-event
       body: { user_key, trade_id, asset, amount, result, direction, payout, duration_sec, closed_at }
  GET  /relay/trades?user_key=...&since_id=...
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, urlparse

HOST = "0.0.0.0"
PORT = 8787
BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "relay-data"
EVENTS_FILE = DATA_DIR / "events.jsonl"
META_FILE = DATA_DIR / "relay_meta.json"
BOT_ORDERS_FILE = DATA_DIR / "bot_orders.jsonl"
BOT_RESULTS_FILE = DATA_DIR / "bot_results.jsonl"

_lock = threading.Lock()
_rate_lock = threading.Lock()
_requests_by_ip: Dict[str, List[float]] = {}

API_TOKEN = os.getenv("RELAY_API_TOKEN", "").strip()
MAX_EVENTS = max(1000, int(os.getenv("RELAY_MAX_EVENTS", "50000") or "50000"))
RETENTION_DAYS = max(1, int(os.getenv("RELAY_RETENTION_DAYS", "30") or "30"))
MAX_REQ_PER_MINUTE_PER_IP = max(30, int(os.getenv("RELAY_MAX_REQ_PER_MIN", "180") or "180"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not EVENTS_FILE.exists():
        EVENTS_FILE.write_text("", encoding="utf-8")
    if not BOT_ORDERS_FILE.exists():
        BOT_ORDERS_FILE.write_text("", encoding="utf-8")
    if not BOT_RESULTS_FILE.exists():
        BOT_RESULTS_FILE.write_text("", encoding="utf-8")


def _read_events() -> List[Dict[str, Any]]:
    _ensure_store()
    events: List[Dict[str, Any]] = []
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _append_event(event: Dict[str, Any]) -> None:
    _ensure_store()
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=True) + "\n")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    _ensure_store()
    items: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    items.append(obj)
            except json.JSONDecodeError:
                continue
    return items


def _append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    _ensure_store()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=True) + "\n")


def _parse_utc_iso(v: Any) -> datetime | None:
    s = str(v or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_meta() -> Dict[str, Any]:
    _ensure_store()
    if not META_FILE.exists():
        return {"last_cleanup_utc": ""}
    try:
        with open(META_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"last_cleanup_utc": ""}


def _save_meta(meta: Dict[str, Any]) -> None:
    _ensure_store()
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def _cleanup_events_if_needed() -> Tuple[int, int]:
    meta = _load_meta()
    last_cleanup = _parse_utc_iso(meta.get("last_cleanup_utc"))
    now = datetime.now(timezone.utc)
    if last_cleanup and (now - last_cleanup) < timedelta(minutes=15):
        return 0, 0

    events = _read_events()
    cutoff = now - timedelta(days=RETENTION_DAYS)
    kept = []
    dropped_by_age = 0
    for e in events:
        ts = _parse_utc_iso(e.get("timestamp_utc") or e.get("closed_at"))
        if ts and ts < cutoff:
            dropped_by_age += 1
            continue
        kept.append(e)
    dropped_by_size = 0
    if len(kept) > MAX_EVENTS:
        dropped_by_size = len(kept) - MAX_EVENTS
        kept = kept[-MAX_EVENTS:]

    if dropped_by_age > 0 or dropped_by_size > 0:
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            for e in kept:
                f.write(json.dumps(e, ensure_ascii=True) + "\n")
    meta["last_cleanup_utc"] = _utc_now()
    _save_meta(meta)
    return dropped_by_age, dropped_by_size


def _cleanup_jsonl(path: Path, ts_fields: Tuple[str, ...]) -> None:
    items = _read_jsonl(path)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    kept: List[Dict[str, Any]] = []
    for item in items:
        ts = None
        for field in ts_fields:
            ts = _parse_utc_iso(item.get(field))
            if ts:
                break
        if ts and ts < cutoff:
            continue
        kept.append(item)
    if len(kept) > MAX_EVENTS:
        kept = kept[-MAX_EVENTS:]
    with open(path, "w", encoding="utf-8") as f:
        for item in kept:
            f.write(json.dumps(item, ensure_ascii=True) + "\n")


def _cleanup_bot_store_if_needed() -> None:
    meta = _load_meta()
    last_cleanup = _parse_utc_iso(meta.get("last_cleanup_utc"))
    now = datetime.now(timezone.utc)
    if last_cleanup and (now - last_cleanup) < timedelta(minutes=15):
        return
    _cleanup_jsonl(BOT_ORDERS_FILE, ("created_at_utc",))
    _cleanup_jsonl(BOT_RESULTS_FILE, ("timestamp_utc",))
    meta["last_cleanup_utc"] = _utc_now()
    _save_meta(meta)


def _auth_ok(headers, query: Dict[str, List[str]]) -> bool:
    if not API_TOKEN:
        return True
    header_token = str(headers.get("X-Relay-Token") or "").strip()
    q_token = (query.get("token") or [""])[0].strip()
    return header_token == API_TOKEN or q_token == API_TOKEN


def _rate_limited(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        bucket = _requests_by_ip.get(ip) or []
        cutoff = now - 60.0
        bucket = [t for t in bucket if t >= cutoff]
        if len(bucket) >= MAX_REQ_PER_MINUTE_PER_IP:
            _requests_by_ip[ip] = bucket
            return True
        bucket.append(now)
        _requests_by_ip[ip] = bucket
    return False


def _valid_user_key(v: str) -> bool:
    if not v:
        return False
    if len(v) < 6 or len(v) > 120:
        return False
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    return all(ch in allowed for ch in v)


class RelayHandler(BaseHTTPRequestHandler):
    def _set_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def _reply_json(self, payload: Dict[str, Any], code: int = 200) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self._set_cors()
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if _rate_limited(self.client_address[0]):
            self._reply_json({"ok": False, "error": "rate_limited"}, 429)
            return
        p = urlparse(self.path)
        q = parse_qs(p.query)
        if p.path == "/relay/health":
            self._reply_json({"ok": True, "utc": _utc_now()})
            return
        if p.path == "/relay/trades":
            if not _auth_ok(self.headers, q):
                self._reply_json({"ok": False, "error": "unauthorized"}, 401)
                return
            user_key = (q.get("user_key") or [""])[0].strip()
            since_id = (q.get("since_id") or [""])[0].strip()
            if not _valid_user_key(user_key):
                self._reply_json({"ok": False, "error": "invalid_user_key"}, 400)
                return
            with _lock:
                _cleanup_events_if_needed()
                events = [e for e in _read_events() if (e.get("user_key") or "") == user_key]
            if since_id:
                idx = -1
                for i, e in enumerate(events):
                    if str(e.get("event_id")) == since_id:
                        idx = i
                if idx >= 0:
                    events = events[idx + 1 :]
            # do not leak user_key back
            out = []
            for e in events[-1000:]:
                c = dict(e)
                c.pop("user_key", None)
                out.append(c)
            last_event_id = out[-1]["event_id"] if out else since_id
            self._reply_json({"ok": True, "events": out, "last_event_id": last_event_id})
            return
        if p.path == "/relay/bot-orders":
            if not _auth_ok(self.headers, q):
                self._reply_json({"ok": False, "error": "unauthorized"}, 401)
                return
            user_key = (q.get("user_key") or [""])[0].strip()
            since_id = (q.get("since_id") or [""])[0].strip()
            if not _valid_user_key(user_key):
                self._reply_json({"ok": False, "error": "invalid_user_key"}, 400)
                return
            with _lock:
                _cleanup_bot_store_if_needed()
                items = [o for o in _read_jsonl(BOT_ORDERS_FILE) if str(o.get("user_key") or "") == user_key]
            if since_id:
                idx = -1
                for i, item in enumerate(items):
                    if str(item.get("order_id")) == since_id:
                        idx = i
                if idx >= 0:
                    items = items[idx + 1 :]
            out = []
            for item in items[-1000:]:
                c = dict(item)
                c.pop("user_key", None)
                out.append(c)
            last_order_id = out[-1]["order_id"] if out else since_id
            self._reply_json({"ok": True, "orders": out, "last_order_id": last_order_id})
            return
        if p.path == "/relay/bot-results":
            if not _auth_ok(self.headers, q):
                self._reply_json({"ok": False, "error": "unauthorized"}, 401)
                return
            user_key = (q.get("user_key") or [""])[0].strip()
            if not _valid_user_key(user_key):
                self._reply_json({"ok": False, "error": "invalid_user_key"}, 400)
                return
            with _lock:
                _cleanup_bot_store_if_needed()
                results = [r for r in _read_jsonl(BOT_RESULTS_FILE) if str(r.get("user_key") or "") == user_key]
            out = []
            for r in results[-200:]:
                c = dict(r)
                c.pop("user_key", None)
                out.append(c)
            self._reply_json({"ok": True, "results": out})
            return
        self._reply_json({"ok": False, "error": "not_found"}, 404)

    def do_POST(self) -> None:
        if _rate_limited(self.client_address[0]):
            self._reply_json({"ok": False, "error": "rate_limited"}, 429)
            return
        p = urlparse(self.path)
        if p.path not in ("/relay/trade-event", "/relay/bot-order", "/relay/bot-order-result"):
            self._reply_json({"ok": False, "error": "not_found"}, 404)
            return
        q = parse_qs(p.query)
        if not _auth_ok(self.headers, q):
            self._reply_json({"ok": False, "error": "unauthorized"}, 401)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            self._reply_json({"ok": False, "error": "invalid_json"}, 400)
            return
        user_key = str(data.get("user_key") or "").strip()
        if not _valid_user_key(user_key):
            self._reply_json({"ok": False, "error": "invalid_user_key"}, 400)
            return
        if p.path == "/relay/bot-order":
            amount = float(data.get("amount", 0) or 0)
            duration_sec = int(float(data.get("duration_sec", 5) or 5))
            direction = str(data.get("direction") or "").lower()
            if amount <= 0 or direction not in ("call", "put"):
                self._reply_json({"ok": False, "error": "invalid_order"}, 400)
                return
            pam = str(data.get("pocket_account_mode") or "").strip().lower()[:16]
            order = {
                "order_id": str(uuid.uuid4()),
                "user_key": user_key,
                "asset": str(data.get("asset") or "OTC"),
                "amount": amount,
                "direction": direction,
                "duration_sec": max(5, min(300, duration_sec)),
                "source": str(data.get("source") or "mobile-bot"),
                "pocket_account_mode": pam if pam in ("demo", "live") else "",
                "created_at_utc": _utc_now(),
            }
            with _lock:
                _cleanup_bot_store_if_needed()
                _append_jsonl(BOT_ORDERS_FILE, order)
            self._reply_json({"ok": True, "order_id": order["order_id"]})
            return
        if p.path == "/relay/bot-order-result":
            order_id = str(data.get("order_id") or "").strip()
            status = str(data.get("status") or "").strip().lower()
            if not order_id or status not in ("executed", "failed", "ignored"):
                self._reply_json({"ok": False, "error": "invalid_result"}, 400)
                return
            result = {
                "result_id": str(uuid.uuid4()),
                "user_key": user_key,
                "order_id": order_id,
                "status": status,
                "message": str(data.get("message") or "")[:300],
                "timestamp_utc": _utc_now(),
                "source": str(data.get("source") or "mobile-executor"),
            }
            with _lock:
                _cleanup_bot_store_if_needed()
                _append_jsonl(BOT_RESULTS_FILE, result)
            self._reply_json({"ok": True, "result_id": result["result_id"]})
            return

        trade_id = str(data.get("trade_id") or "").strip()
        if not trade_id:
            asset = str(data.get("asset") or "")
            closed_at = str(data.get("closed_at") or "")
            amount = str(data.get("amount") or "")
            result = str(data.get("result") or "")
            trade_id = f"relay|{asset}|{closed_at}|{amount}|{result}"

        event = {
            "event_id": str(uuid.uuid4()),
            "user_key": user_key,
            "trade_id": trade_id[:200],
            "asset": str(data.get("asset") or "OTC"),
            "amount": float(data.get("amount", 0) or 0),
            "result": str(data.get("result") or "W").upper()[:1],
            "direction": str(data.get("direction") or ""),
            "payout": float(data.get("payout", 0) or 0),
            "duration_sec": data.get("duration_sec"),
            "closed_at": str(data.get("closed_at") or _utc_now()),
            "timestamp_utc": _utc_now(),
            "source": str(data.get("source") or "relay-ingest"),
        }

        with _lock:
            _cleanup_events_if_needed()
            events = _read_events()
            duplicate = any(
                (e.get("user_key") == user_key and e.get("trade_id") == event["trade_id"])
                for e in events[-5000:]
            )
            if duplicate:
                self._reply_json({"ok": True, "duplicate": True})
                return
            _append_event(event)
        self._reply_json({"ok": True, "event_id": event["event_id"]})


def run_server() -> None:
    _ensure_store()
    server = HTTPServer((HOST, PORT), RelayHandler)
    print(f"Cloud relay listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
