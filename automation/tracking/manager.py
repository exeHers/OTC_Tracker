"""
Background trade tracking: start/stop, use provider, emit events, save to journal.
"""
import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set

from automation.events import TradeEvent
from .provider import TradeDetectionProvider
from .placeholder_provider import PlaceholderDetectionProvider


class TradeTrackingManager:
    """Core tracking engine: start/stop, monitor activity, detect trades, save to journal."""

    STATUS_STOPPED = "Stopped"
    STATUS_MONITORING = "Monitoring"
    STATUS_ERROR = "Error"

    def __init__(
        self,
        on_status: Optional[Callable[[str], None]] = None,
        on_activity: Optional[Callable[[str], None]] = None,
        on_trade_detected: Optional[Callable[[TradeEvent], None]] = None,
        save_trade_to_journal: Optional[Callable[[dict], None]] = None,
        settings: Optional[Dict] = None,
    ):
        self._on_status = on_status or (lambda s: None)
        self._on_activity = on_activity or (lambda s: None)
        self._on_trade_detected = on_trade_detected or (lambda e: None)
        self._save_trade_to_journal = save_trade_to_journal
        self._settings = settings or {}
        self._provider: Optional[TradeDetectionProvider] = None
        self._running = False
        self._lock = threading.Lock()
        self._trades_today: List[TradeEvent] = []
        self._last_trade: Optional[TradeEvent] = None
        self._activity_log: List[str] = []
        self._seen_signatures: Set[str] = set()
        self._max_activity_lines = 100
        self._error_message: Optional[str] = None

    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        with self._lock:
            self._activity_log.append(line)
            if len(self._activity_log) > self._max_activity_lines:
                self._activity_log.pop(0)
        self._on_activity(line)

    def get_activity_log(self) -> List[str]:
        with self._lock:
            return list(self._activity_log)

    def get_trades_detected_today(self) -> int:
        with self._lock:
            return len(self._trades_today)

    def get_last_trade(self) -> Optional[TradeEvent]:
        with self._lock:
            return self._last_trade

    def get_detection_method(self) -> str:
        if self._provider is None:
            return "None"
        return self._provider.name

    def _trade_signature(self, e: TradeEvent) -> str:
        """For duplicate protection."""
        t = e.timestamp or datetime.now()
        return f"{t.isoformat()}|{e.asset}|{e.amount}|{e.result}"

    def _handle_trade(self, event: TradeEvent) -> None:
        with self._lock:
            self._trades_today.append(event)
            self._last_trade = event
        self._on_trade_detected(event)
        self._log("Trade detected: %s %s %s" % (event.asset, event.result or "?", event.amount))

        duplicate_protection = self._settings.get("duplicate_trade_protection", True)
        if duplicate_protection:
            sig = self._trade_signature(event)
            with self._lock:
                if sig in self._seen_signatures:
                    self._log("Duplicate trade skipped")
                    return
                self._seen_signatures.add(sig)

        auto_save = self._settings.get("automatically_save_detected_trades", True)
        sync_journal = self._settings.get("sync_with_trade_journal", True)
        if auto_save and sync_journal and self._save_trade_to_journal:
            try:
                row = event.to_journal_row()
                self._save_trade_to_journal(row)
                self._log("Trade saved to journal")
            except Exception as ex:
                self._log("Error saving to journal: %s" % ex)
                self._error_message = str(ex)
                self._on_status(self.STATUS_ERROR)

    def start_tracking(self, provider: Optional[TradeDetectionProvider] = None) -> None:
        if self._running:
            self._log("Already monitoring")
            return
        self._error_message = None
        self._provider = provider or PlaceholderDetectionProvider(
            polling_interval_sec=float(self._settings.get("polling_interval_sec", 5.0))
        )
        self._running = True
        self._on_status(self.STATUS_MONITORING)
        self._log("Tracking started — %s" % self._provider.name)
        self._provider.start(on_trade=self._handle_trade, on_activity=self._log)

    def stop_tracking(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._provider:
            try:
                self._provider.stop()
            except Exception as e:
                self._log("Error stopping provider: %s" % e)
            self._provider = None
        self._on_status(self.STATUS_STOPPED)
        self._log("Tracking stopped")

    def is_running(self) -> bool:
        return self._running and (self._provider is None or self._provider.is_connected())

    def get_status(self) -> str:
        if not self._running:
            return self.STATUS_STOPPED
        if self._error_message:
            return self.STATUS_ERROR
        if self._provider and self._provider.is_connected():
            return self.STATUS_MONITORING
        return self.STATUS_ERROR

    def clear_error(self) -> None:
        self._error_message = None
        if self._running:
            self._on_status(self.STATUS_MONITORING)
