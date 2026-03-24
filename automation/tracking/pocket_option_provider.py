"""
Trade detection via Pocket Option: order_closed events (real-time) + polling fallback.
Emits TradeEvent with market (asset), amount, win/loss, time.
"""
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from automation.events import TradeEvent

from .provider import TradeDetectionProvider

try:
    from automation.brokers.pocket_option import PocketOptionBroker
    _BROKER = PocketOptionBroker
except Exception:
    _BROKER = None


class PocketOptionDetectionProvider(TradeDetectionProvider):
    """
    Listens for order_closed WebSocket events for real-time tracking; also polls active orders as fallback.
    Tracks market (asset), amount, win/loss, and time for every closed trade.
    """

    def __init__(self, broker: "PocketOptionBroker", poll_interval_sec: float = 1.5):
        if _BROKER is None or broker is None:
            raise RuntimeError("Pocket Option broker not available")
        self._broker = broker
        self._poll_interval = max(1.0, poll_interval_sec)
        self._on_trade: Optional[Callable[[TradeEvent], None]] = None
        self._on_activity: Optional[Callable[[str], None]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._seen_open: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._poll_count = 0

    @property
    def name(self) -> str:
        return "Pocket Option (API)"

    def _order_result_to_event(self, r: Any) -> Optional[TradeEvent]:
        """Convert broker OrderResult to TradeEvent (asset, amount, win/loss, time)."""
        if r is None:
            return None
        order_id = getattr(r, "order_id", "") or ""
        asset = (getattr(r, "asset", None) or "OTC").strip() or "OTC"
        amount = float(getattr(r, "amount", 0) or 0)
        direction = (getattr(r, "direction", None) or "call")
        if hasattr(direction, "value"):
            direction = str(direction.value).lower()
        else:
            direction = str(direction).lower()
        status = (getattr(r, "status", None) or "").lower()
        profit = getattr(r, "profit", None)
        profit = float(profit) if profit is not None else 0.0
        win = status in ("win", "w") or profit > 0
        result = "W" if win else "L"
        raw = getattr(r, "raw", None) or {}
        placed_at = raw.get("placed_at") if isinstance(raw, dict) else None
        if placed_at is None and hasattr(r, "placed_at"):
            placed_at = r.placed_at
        if isinstance(placed_at, datetime):
            timestamp = placed_at
        else:
            timestamp = datetime.now()
        return TradeEvent(
            asset=asset,
            direction=direction,
            amount=amount,
            result=result,
            payout=profit,
            timestamp=timestamp,
            raw={"order_id": order_id, "status": status},
        )

    def _on_order_closed(self, order_result: Any) -> None:
        """Called by broker when WebSocket receives order_closed. Runs in broker's thread."""
        event = self._order_result_to_event(order_result)
        if event and self._on_trade:
            self._on_trade(event)
            self._log("Trade: %s %s %.2f %s" % (event.asset, event.result, event.amount, event.timestamp.strftime("%H:%M:%S")))

    def start(
        self,
        on_trade: Callable[[TradeEvent], None],
        on_activity: Callable[[str], None],
    ) -> None:
        self._on_trade = on_trade
        self._on_activity = on_activity
        if not self._broker.is_connected():
            on_activity("Pocket Option not connected. Connect in settings first.")
            return
        self._broker.register_order_closed_callback(self._on_order_closed)
        self._running = True
        self._on_activity("Monitoring Pocket Option (events + poll every %.1fs). Place a trade on the same account to test." % self._poll_interval)
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._broker.register_order_closed_callback(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._poll_interval + 2)
        with self._lock:
            self._seen_open.clear()
        if self._on_activity:
            self._on_activity("Pocket Option monitoring stopped.")

    def is_connected(self) -> bool:
        return self._running and self._broker.is_connected()

    def _log(self, msg: str) -> None:
        if self._on_activity:
            self._on_activity(msg)

    def _poll_loop(self) -> None:
        while self._running:
            try:
                active = self._broker.get_active_orders()
                current_ids = {o.order_id for o in active if o.order_id}
                for o in active:
                    if o.order_id and o.order_id not in self._seen_open:
                        with self._lock:
                            self._seen_open[o.order_id] = {
                                "asset": o.asset or "OTC",
                                "amount": o.amount or 0,
                                "direction": (o.direction or "call").lower() if o.direction else "call",
                            }
                self._poll_count += 1
                if self._poll_count % 20 == 1:
                    bal = self._broker.get_balance()
                    bal_str = "Balance: %s %.2f" % (getattr(bal, "currency", "") or "", getattr(bal, "balance", 0) or 0) if bal else "Balance: —"
                    self._log("Connection alive — %s | Active orders: %d" % (bal_str, len(active)))
                with self._lock:
                    to_check = [oid for oid in self._seen_open if oid not in current_ids]
                for order_id in to_check:
                    with self._lock:
                        info = self._seen_open.pop(order_id, {})
                    result = self._broker.check_order_result(order_id)
                    asset = info.get("asset") or "OTC"
                    amount = float(info.get("amount") or 0)
                    direction = info.get("direction") or "call"
                    if result:
                        event = self._order_result_to_event(result)
                        if event:
                            event = TradeEvent(
                                asset=asset or event.asset,
                                direction=direction or event.direction,
                                amount=amount or event.amount,
                                result=event.result,
                                payout=event.payout,
                                timestamp=event.timestamp,
                                raw=event.raw,
                            )
                            if self._on_trade:
                                self._on_trade(event)
                            self._log("Trade (poll): %s %s %.2f" % (event.asset, event.result, event.amount))
                    else:
                        self._log("Order %s closed (result unknown)" % order_id)
            except Exception as e:
                self._log("Pocket Option poll error: %s" % e)
            time.sleep(self._poll_interval)
