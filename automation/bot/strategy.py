"""
Strategy module interface. Plug-in strategies later; no signal generation here.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class StrategyModule(ABC):
    """Placeholder interface for pluggable strategies. Bot only executes when a strategy is present."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy display name."""
        pass

    @property
    def enabled(self) -> bool:
        """Whether the strategy is active."""
        return True

    def get_config(self) -> Dict[str, Any]:
        """Current strategy config (for persistence)."""
        return {}

    def set_config(self, config: Dict[str, Any]) -> None:
        """Apply config (called when settings load)."""
        pass

    def should_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Return True if the strategy wants to allow execution (e.g. after evaluating market state).
        No actual signals; just a gate. Default: True when enabled.
        """
        return self.enabled

    def next_trade_request(self, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Optional signal producer for framework-driven bots.
        Return dict with keys: asset, direction, amount, duration_sec (optional).
        Default: no signal.
        """
        return None
