"""
Pocket Option broker adapter using pocketoptionapi-async.
Install: pip install pocketoptionapi-async
Uses SSID for auth; runs async API in a dedicated thread.
Normalizes SSID so sessionToken works (library expects "session").
"""
import asyncio
import json
import threading
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .base import BalanceResult, BrokerAdapter, OrderResult

try:
    from pocketoptionapi_async import AsyncPocketOptionClient, OrderDirection
    _HAS_API = True
except ImportError:
    AsyncPocketOptionClient = None
    OrderDirection = None
    _HAS_API = False


def normalize_ssid_for_library(ssid: str, is_demo: bool) -> str:
    """
    Normalize SSID so the library accepts it. The library requires a "session" field;
    Pocket Option sometimes sends "sessionToken" instead. We convert and output the
    exact format the library expects: 42["auth",{"session":"...","isDemo":1,"uid":...,"platform":1}]
    """
    raw = (ssid or "").strip()
    if not raw.startswith("42[\"auth\","):
        return raw
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end <= start:
            return raw
        data = json.loads(raw[start:end])
        session = data.get("session") or data.get("sessionToken") or ""
        if isinstance(session, str):
            session = session.strip()
        uid = data.get("uid", 0)
        if isinstance(uid, str) and uid.isdigit():
            uid = int(uid)
        platform = int(data.get("platform", 1))
        normalized = {
            "session": session,
            "isDemo": 1 if is_demo else 0,
            "uid": uid,
            "platform": platform,
        }
        return '42["auth",' + json.dumps(normalized) + "]"
    except Exception:
        return raw


def _run_async(coro):
    """Run a coroutine from sync code using a dedicated loop in a thread."""
    loop = getattr(_run_async, "_loop", None)
    if loop is None or not loop.is_running():
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class PocketOptionBroker(BrokerAdapter):
    """
    Pocket Option broker. Requires SSID cookie (from browser after login).
    Run connect() before place_order / get_active_orders / check_order_result.
    """

    def __init__(self, ssid: str, is_demo: bool = True, poll_interval_sec: float = 3.0):
        if not _HAS_API:
            raise ImportError("Install Pocket Option API: pip install pocketoptionapi-async")
        self._ssid = (ssid or "").strip()
        self._is_demo = bool(is_demo)
        self._poll_interval = max(1.0, poll_interval_sec)
        self._client: Optional[AsyncPocketOptionClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._lock = threading.Lock()
        self._order_closed_callback: Optional[Callable[[OrderResult], None]] = None
        self._order_closed_callback_ref = None
        self._emitted_deal_ids: set = set()
        self._json_data_patch_ref = None

    @property
    def name(self) -> str:
        return "Pocket Option"

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()
            return self._loop

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro) -> Any:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)

    def _deal_to_order_result(self, deal: dict) -> Optional[OrderResult]:
        """Build OrderResult from a raw deal dict (server may send asset, amount, profit, win)."""
        if not isinstance(deal, dict) or "id" not in deal:
            return None
        deal_id = str(deal["id"])
        profit = float(deal.get("profit", 0) or 0)
        win = deal.get("win", profit > 0)
        status = "win" if (win if isinstance(win, bool) else profit > 0) else "lose"
        asset = str(deal.get("asset", deal.get("asset_name", "OTC")) or "OTC")
        amount = float(deal.get("amount", deal.get("investment", 0)) or 0)
        direction = (deal.get("direction") or deal.get("action") or "call")
        direction = str(getattr(direction, "value", direction)).lower()
        return OrderResult(order_id=deal_id, status=status, profit=profit, asset=asset, amount=amount, direction=direction, raw=deal)

    def _on_json_data_patch(self, data: Any) -> None:
        """Process 'deals' that weren't matched by the library (e.g. browser-opened trades)."""
        try:
            if not isinstance(data, dict) or "deals" not in data or not isinstance(data["deals"], list):
                return
            cb = self._order_closed_callback
            if not cb:
                return
            for deal in data["deals"]:
                if not isinstance(deal, dict) or "id" not in deal:
                    continue
                deal_id = str(deal["id"])
                if deal_id in self._emitted_deal_ids:
                    continue
                self._emitted_deal_ids.add(deal_id)
                result = self._deal_to_order_result(deal)
                if result:
                    cb(result)
        except Exception:
            pass

    def _on_order_closed_from_lib(self, data: Any) -> None:
        """Called from library's event loop when an order closes. Convert to our OrderResult and notify."""
        try:
            order_id = (getattr(data, "order_id", None) if hasattr(data, "order_id") else (data.get("order_id") if isinstance(data, dict) else None))
            if order_id:
                self._emitted_deal_ids.add(str(order_id))
        except Exception:
            pass
        cb = self._order_closed_callback
        if not cb:
            return
        try:
            if hasattr(data, "order_id"):
                r = data
                order_id = getattr(r, "order_id", "") or ""
                asset = getattr(r, "asset", None) or "OTC"
                amount = float(getattr(r, "amount", 0) or 0)
                direction = getattr(r, "direction", None)
                if direction is not None and hasattr(direction, "value"):
                    direction = str(direction.value).lower()
                else:
                    direction = "call"
                status = getattr(r, "status", None)
                if status is not None and hasattr(status, "value"):
                    status = str(status.value).lower()
                else:
                    status = ""
                profit = getattr(r, "profit", None)
                if profit is None:
                    profit = 0.0
                else:
                    profit = float(profit)
                placed_at = getattr(r, "placed_at", None)
            elif isinstance(data, dict):
                order_id = str(data.get("order_id", ""))
                asset = str(data.get("asset", "OTC") or "OTC")
                amount = float(data.get("amount", 0) or 0)
                direction = (data.get("direction") or "call")
                if hasattr(direction, "value"):
                    direction = str(direction.value).lower()
                else:
                    direction = str(direction).lower()
                status = str(data.get("status", "") or "").lower()
                profit = float(data.get("profit", 0) or 0)
                placed_at = data.get("placed_at")
            else:
                return
            result = OrderResult(
                order_id=order_id,
                status=status,
                profit=profit,
                asset=asset,
                amount=amount,
                direction=direction,
                raw={"placed_at": placed_at} if placed_at else None,
            )
            cb(result)
        except Exception:
            pass

    def register_order_closed_callback(self, callback: Optional[Callable[[OrderResult], None]]) -> None:
        """Register a callback for when an order closes (real-time from WebSocket)."""
        self._order_closed_callback = callback

    def connect(self) -> bool:
        if not self._ssid:
            return False
        try:
            self._emitted_deal_ids.clear()
            normalized = normalize_ssid_for_library(self._ssid, self._is_demo)
            self._client = AsyncPocketOptionClient(
                normalized,
                is_demo=self._is_demo,
                enable_logging=False,
            )
            async def our_deals_patch(data):
                self._on_json_data_patch(data)
            self._json_data_patch_ref = our_deals_patch
            if hasattr(self._client, "_websocket") and self._client._websocket is not None:
                self._client._websocket.add_event_handler("json_data", our_deals_patch)
            self._run(self._client.connect())
            self._connected = True
            self._order_closed_callback_ref = self._on_order_closed_from_lib
            self._client.add_event_callback("order_closed", self._order_closed_callback_ref)
            return True
        except Exception:
            self._connected = False
            return False

    def disconnect(self) -> None:
        self._connected = False
        if self._client:
            try:
                if self._order_closed_callback_ref is not None:
                    self._client.remove_event_callback("order_closed", self._order_closed_callback_ref)
            except Exception:
                pass
            self._order_closed_callback_ref = None
            if self._json_data_patch_ref is not None and hasattr(self._client, "_websocket") and self._client._websocket is not None:
                try:
                    self._client._websocket.remove_event_handler("json_data", self._json_data_patch_ref)
                except Exception:
                    pass
                self._json_data_patch_ref = None
            try:
                self._run(self._client.disconnect())
            except Exception:
                pass
            self._client = None

    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    def get_balance(self) -> Optional[BalanceResult]:
        if not self._client or not self._connected:
            return None
        try:
            bal = self._run(self._client.get_balance())
            return BalanceResult(
                balance=getattr(bal, "balance", 0) or 0,
                currency=getattr(bal, "currency", "") or "",
                is_demo=getattr(bal, "is_demo", self._is_demo),
            )
        except Exception:
            return None

    def _dir_to_order_direction(self, direction: str):
        d = (direction or "").strip().upper()
        if d in ("PUT", "DOWN"):
            return OrderDirection.PUT
        return OrderDirection.CALL

    def place_order(
        self,
        asset: str,
        amount: float,
        direction: str,
        duration_sec: int = 5,
        pocket_account_mode: str = "",
    ) -> Optional[OrderResult]:
        if not self._client or not self._connected:
            return None
        duration_sec = max(5, min(300, int(duration_sec)))
        try:
            order = self._run(
                self._client.place_order(
                    asset=asset or "EURUSD_otc",
                    amount=float(amount),
                    direction=self._dir_to_order_direction(direction),
                    duration=duration_sec,
                )
            )
            return OrderResult(
                order_id=str(getattr(order, "order_id", "") or ""),
                status=getattr(order, "status", "open") or "open",
                asset=asset,
                amount=amount,
                direction=direction,
                duration_sec=duration_sec,
                raw=order.__dict__ if hasattr(order, "__dict__") else None,
            )
        except Exception:
            return None

    def _order_to_result(self, o: Any) -> OrderResult:
        """Map library order/result to our OrderResult, including from raw dict."""
        if o is None:
            return OrderResult(order_id="", status="", raw=None)
        order_id = str(getattr(o, "order_id", "") or getattr(o, "id", "") or "")
        status = getattr(o, "status", None)
        if status is not None and hasattr(status, "value"):
            status = str(status.value).lower()
        else:
            status = str(status or "open").lower()
        asset = getattr(o, "asset", None) or getattr(o, "asset_name", None) or getattr(o, "symbol", None) or "OTC"
        amount = getattr(o, "amount", None) or getattr(o, "investment", None)
        amount = float(amount) if amount is not None else 0.0
        direction = getattr(o, "direction", None)
        if direction is not None and hasattr(direction, "value"):
            direction = str(direction.value).lower()
        else:
            direction = str(direction or "call").lower()
        duration = getattr(o, "duration", None) or getattr(o, "time", None)
        duration = int(duration) if duration is not None else None
        profit = getattr(o, "profit", None)
        profit = float(profit) if profit is not None else None
        placed_at = getattr(o, "placed_at", None)
        raw = getattr(o, "__dict__", None) if not isinstance(o, dict) else o
        if isinstance(raw, dict) and placed_at is not None:
            raw = dict(raw)
            raw["placed_at"] = placed_at
        return OrderResult(
            order_id=order_id,
            status=status,
            asset=asset,
            amount=amount,
            direction=direction,
            duration_sec=duration,
            profit=profit,
            raw=raw,
        )

    def get_active_orders(self) -> List[OrderResult]:
        if not self._client or not self._connected:
            return []
        try:
            orders = self._run(self._client.get_active_orders())
            out = []
            for o in orders or []:
                r = self._order_to_result(o)
                if r.order_id:
                    out.append(r)
            return out
        except Exception:
            return []

    def check_order_result(self, order_id: str) -> Optional[OrderResult]:
        if not self._client or not self._connected or not order_id:
            return None
        try:
            r = self._run(self._client.check_order_result(order_id))
            if r is None:
                return None
            return self._order_to_result(r)
        except Exception:
            return None
