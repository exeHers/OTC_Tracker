"""
Interface for trade detection. Implementations: session monitoring, WebSocket, DOM parsing, etc.
"""
from abc import ABC, abstractmethod
from typing import Callable, List, Optional

# Avoid circular import; use string type hint or import in method
try:
    from automation.events import TradeEvent
except ImportError:
    TradeEvent = None  # type: ignore


class TradeDetectionProvider(ABC):
    """Implement this to add a detection method (WebSocket, DOM, session, etc.)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Display name for this provider (e.g. 'WebSocket', 'DOM parsing')."""
        pass

    @abstractmethod
    def start(self, on_trade: Callable[["TradeEvent"], None], on_activity: Callable[[str], None]) -> None:
        """Start monitoring. Call on_trade when a trade is detected, on_activity for log messages."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop monitoring and clean up."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the provider is connected and monitoring."""
        pass
