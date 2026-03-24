"""
Shared state for browser→desktop trade collection (Pocket Option helper).

- Persists across app restarts until the user turns collection OFF.
- New session_id only when toggling OFF → ON (not on every app launch).
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE = Path(__file__).resolve().parent
STATE_FILE = BASE / "trade_collection_state.json"

_lock = threading.Lock()

_DEFAULT: Dict[str, Any] = {
    "enabled": False,
    "session_id": None,
    "session_started_at_utc": None,
    "seen_fingerprints": [],  # last N fingerprints for dedupe
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _load_state_unlocked() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return dict(_DEFAULT)
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT)
    out = dict(_DEFAULT)
    out.update(data)
    if not isinstance(out.get("seen_fingerprints"), list):
        out["seen_fingerprints"] = []
    # Repair legacy: enabled but missing session anchor
    if out.get("enabled") and not out.get("session_started_at_utc"):
        out["session_id"] = out.get("session_id") or str(uuid.uuid4())
        out["session_started_at_utc"] = _utc_now_iso()
        _save_state_unlocked(out)
    return out


def load_state() -> Dict[str, Any]:
    with _lock:
        return _load_state_unlocked()


def _save_state_unlocked(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # cap fingerprints
    fp = state.get("seen_fingerprints") or []
    if isinstance(fp, list) and len(fp) > 3000:
        state["seen_fingerprints"] = fp[-3000:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def save_state(state: Dict[str, Any]) -> None:
    with _lock:
        _save_state_unlocked(state)


def set_collection_enabled(enabled: bool, new_session: bool = True) -> Dict[str, Any]:
    """
    When enabling: optionally start a new session (new session_id + baseline time).
    When disabling: only flips enabled; session_id kept for debugging/display.
    """
    with _lock:
        state = _load_state_unlocked()
        if enabled:
            state["enabled"] = True
            if new_session:
                state["session_id"] = str(uuid.uuid4())
                state["session_started_at_utc"] = _utc_now_iso()
                state["seen_fingerprints"] = []
        else:
            state["enabled"] = False
        _save_state_unlocked(state)
        return dict(state)


def remember_fingerprint(fp: str) -> bool:
    """Return True if newly added, False if duplicate."""
    if not fp:
        return False
    with _lock:
        state = _load_state_unlocked()
        seen: List[str] = list(state.get("seen_fingerprints") or [])
        if fp in seen:
            return False
        seen.append(fp)
        state["seen_fingerprints"] = seen
        _save_state_unlocked(state)
        return True


def reset_state() -> None:
    """Wipe collection state (e.g. full data reset)."""
    with _lock:
        _save_state_unlocked(dict(_DEFAULT))


def public_status() -> Dict[str, Any]:
    """JSON-safe dict for GET /tracking-status."""
    with _lock:
        s = _load_state_unlocked()
    return {
        "enabled": bool(s.get("enabled")),
        "session_id": s.get("session_id"),
        "session_started_at_utc": s.get("session_started_at_utc"),
    }
