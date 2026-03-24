"""
Execution engine: executes trades only when a strategy module is present.
Paper trading and execution delay supported. Optional broker for live execution.
"""
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, TYPE_CHECKING

from .queue import QueuedTrade
from .strategy import StrategyModule

if TYPE_CHECKING:
    from automation.brokers.base import BrokerAdapter


@dataclass
class ExecutedTrade:
    """Record of an executed trade (paper or live)."""
    asset: str
    direction: str
    amount: float
    executed_at: float
    paper: bool
    success: bool
    message: str = ""
    order_id: Optional[str] = None


class ExecutionEngine:
    """
    Executes trades from the queue only when a strategy is present.
    Supports paper trading and execution delay. If broker is set and paper_trading is False, executes live.
    """

    def __init__(
        self,
        paper_trading: bool = True,
        execution_delay_sec: float = 0.0,
        randomized_delay: bool = False,
        on_executed: Optional[Callable[[ExecutedTrade], None]] = None,
        on_activity: Optional[Callable[[str], None]] = None,
    ):
        self.paper_trading = paper_trading
        self.execution_delay_sec = max(0.0, execution_delay_sec)
        self.randomized_delay = randomized_delay
        self._on_executed = on_executed or (lambda e: None)
        self._on_activity = on_activity or (lambda s: None)
        self._strategy: Optional[StrategyModule] = None
        self._broker: Optional["BrokerAdapter"] = None
        self._lock = threading.Lock()
        # Paper-mode simulation only (not live win rate).
        self.paper_win_rate_min: float = 0.68
        self.paper_win_rate_max: float = 0.80
        self.paper_payout_ratio: float = 0.82
        self.pocket_account_mode: str = "demo"

    def set_strategy(self, strategy: Optional[StrategyModule]) -> None:
        with self._lock:
            self._strategy = strategy

    def set_broker(self, broker: Optional["BrokerAdapter"]) -> None:
        with self._lock:
            self._broker = broker

    def has_strategy(self) -> bool:
        with self._lock:
            return self._strategy is not None and self._strategy.enabled

    def execute(self, trade: QueuedTrade) -> ExecutedTrade:
        """
        Execute one trade. Only runs if strategy is present and should_execute().
        If paper_trading is False and broker is set, places live order via broker.
        """
        import random
        with self._lock:
            strat = self._strategy
            broker = self._broker
        if strat is None or not strat.enabled:
            return ExecutedTrade(
                asset=trade.asset,
                direction=trade.direction,
                amount=trade.amount,
                executed_at=time.time(),
                paper=True,
                success=False,
                message="No strategy module",
            )
        if not strat.should_execute():
            return ExecutedTrade(
                asset=trade.asset,
                direction=trade.direction,
                amount=trade.amount,
                executed_at=time.time(),
                paper=self.paper_trading,
                success=False,
                message="Strategy declined",
            )
        delay = self.execution_delay_sec
        if self.randomized_delay and delay > 0:
            delay = delay * (0.5 + random.random())
        if delay > 0:
            time.sleep(delay)
        duration = getattr(trade, "duration_sec", 5) or 5
        duration = max(5, min(300, int(duration)))
        # Live execution if broker set and not paper
        if not self.paper_trading and broker is not None and broker.is_connected():
            try:
                result = broker.place_order(
                    asset=trade.asset,
                    amount=trade.amount,
                    direction=trade.direction,
                    duration_sec=duration,
                    pocket_account_mode=str(getattr(self, "pocket_account_mode", "") or ""),
                )
                if result and result.order_id:
                    executed = ExecutedTrade(
                        asset=trade.asset,
                        direction=trade.direction,
                        amount=trade.amount,
                        executed_at=time.time(),
                        paper=False,
                        success=True,
                        message="Executed (live)",
                        order_id=result.order_id,
                    )
                else:
                    executed = ExecutedTrade(
                        asset=trade.asset,
                        direction=trade.direction,
                        amount=trade.amount,
                        executed_at=time.time(),
                        paper=False,
                        success=False,
                        message="Broker returned no order ID",
                    )
            except Exception as e:
                executed = ExecutedTrade(
                    asset=trade.asset,
                    direction=trade.direction,
                    amount=trade.amount,
                    executed_at=time.time(),
                    paper=False,
                    success=False,
                    message="Broker error: %s" % e,
                )
        else:
            executed = ExecutedTrade(
                asset=trade.asset,
                direction=trade.direction,
                amount=trade.amount,
                executed_at=time.time(),
                paper=self.paper_trading,
                success=True,
                message="Executed (paper)" if self.paper_trading else "Executed",
            )
        self._on_executed(executed)
        self._on_activity("Trade executed: %s %s %.2f" % (trade.asset, trade.direction, trade.amount))
        return executed
