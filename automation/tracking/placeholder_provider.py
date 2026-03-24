"""
Placeholder provider: no real detection. Used when no WebSocket/DOM provider is loaded.
"""
import threading
import time
from typing import Callable, Optional

from automation.events import TradeEvent
from .provider import TradeDetectionProvider


class PlaceholderDetectionProvider(TradeDetectionProvider):
    """No-op provider. Replace with WebSocket/DOM provider when available."""

    def __init__(self, polling_interval_sec: float = 5.0):
        self._polling_interval = max(1.0, polling_interval_sec)
        self._on_trade: Callable[[TradeEvent], None] = lambda e: None
        self._on_activity: Callable[[str], None] = lambda s: None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def name(self) -> str:
        return "None (placeholder)"

    def start(self, on_trade: Callable[[TradeEvent], None], on_activity: Callable[[str], None]) -> None:
        self._on_trade = on_trade
        self._on_activity = on_activity
        self._running = True
        self._on_activity("Monitoring started (placeholder — no detection method loaded)")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._polling_interval + 1)
        self._on_activity("Monitoring stopped")

    def is_connected(self) -> bool:
        return self._running

    def _loop(self) -> None:
        while self._running:
            time.sleep(self._polling_interval)
            # No actual detection; just keep-alive for future expansion
