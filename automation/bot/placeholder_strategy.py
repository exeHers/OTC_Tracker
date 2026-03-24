"""
Placeholder strategy: no signals. Used so ExecutionEngine has a strategy and can run (stub executions).
"""
from typing import Any, Dict, Optional

from .strategy import StrategyModule


class PlaceholderStrategy(StrategyModule):
    """No real logic; allows bot framework to run without a real strategy."""

    @property
    def name(self) -> str:
        return "None (placeholder)"

    @property
    def enabled(self) -> bool:
        return True

    def should_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return True
