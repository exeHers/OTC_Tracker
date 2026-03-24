"""
Relay queue broker adapter.

Instead of direct broker API execution, this adapter posts order requests to the
cloud relay bot queue. A browser userscript executor then performs the click-side
execution and reports status back to relay.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Optional

from .base import BrokerAdapter, OrderResult


class RelayQueueBroker(BrokerAdapter):
    def __init__(self, relay_url: str, user_key: str, relay_token: str = "", timeout_sec: float = 8.0):
        self._relay_url = str(relay_url or "").rstrip("/")
        self._user_key = str(user_key or "").strip()
        self._relay_token = str(relay_token or "").strip()
        self._timeout = max(2.0, float(timeout_sec))
        self._connected = False

    @property
    def name(self) -> str:
        return "Relay Queue Bridge"

    def connect(self) -> bool:
        if not self._relay_url or not self._user_key:
            self._connected = False
            return False
        try:
            req = urllib.request.Request(
                self._relay_url + "/relay/health",
                headers=self._headers({"Accept": "application/json"}),
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                self._connected = (resp.getcode() == 200)
            return self._connected
        except Exception:
            self._connected = False
            return False

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def place_order(
        self,
        asset: str,
        amount: float,
        direction: str,
        duration_sec: int = 5,
        pocket_account_mode: str = "",
    ) -> Optional[OrderResult]:
        if not self._connected:
            return None
        payload = {
            "user_key": self._user_key,
            "asset": str(asset or "EURUSD_otc"),
            "amount": float(amount or 0),
            "direction": str(direction or "call").lower(),
            "duration_sec": max(5, min(300, int(duration_sec or 5))),
            "source": "desktop-bot-relay",
            "pocket_account_mode": str(pocket_account_mode or "").strip().lower()[:16],
        }
        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._relay_url + "/relay/bot-order",
            data=raw,
            headers=self._headers({"Content-Type": "application/json", "Accept": "application/json"}),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if not body.get("ok"):
                return None
            oid = str(body.get("order_id") or "")
            if not oid:
                return None
            return OrderResult(
                order_id=oid,
                status="queued",
                asset=payload["asset"],
                amount=payload["amount"],
                direction=payload["direction"],
                duration_sec=payload["duration_sec"],
                raw=body,
            )
        except Exception:
            return None

    def _headers(self, base: dict) -> dict:
        out = dict(base)
        if self._relay_token:
            out["X-Relay-Token"] = self._relay_token
        return out

