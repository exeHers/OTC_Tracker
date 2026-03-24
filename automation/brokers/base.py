"""
Broker adapter interface: connect, place order, optional order status.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class OrderResult:
    """Result of placing or checking an order."""
    order_id: str
    status: str   # e.g. "open", "win", "loss", "pending"
    profit: Optional[float] = None
    asset: Optional[str] = None
    amount: Optional[float] = None
    direction: Optional[str] = None
    duration_sec: Optional[int] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass
class BalanceResult:
    balance: float
    currency: str
    is_demo: bool


class BrokerAdapter(ABC):
    """Implement for each broker (e.g. Pocket Option)."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def connect(self) -> bool:
        """Connect to broker. Return True if successful."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    def get_balance(self) -> Optional[BalanceResult]:
        """Optional: current balance."""
        return None

    @abstractmethod
    def place_order(
        self,
        asset: str,
        amount: float,
        direction: str,
        duration_sec: int = 5,
        pocket_account_mode: str = "",
    ) -> Optional[OrderResult]:
        """Place a single order. Return OrderResult or None on failure."""
        pass

    def get_active_orders(self) -> List[OrderResult]:
        """Optional: list of open orders (for tracking)."""
        return []

    def check_order_result(self, order_id: str) -> Optional[OrderResult]:
        """Optional: get result of an order (win/loss/pending)."""
        return None
