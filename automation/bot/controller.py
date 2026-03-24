"""
Bot controller: high-level start/stop/pause and settings application.
"""
from typing import Any, Dict, Optional

from .engine import BotEngine
from .execution import ExecutionEngine
from .queue import TradeQueue
from .risk import RiskManager
from .strategy import StrategyModule


class BotController:
    """Single entry point for the bot: config, start/stop/pause, recovery."""

    def __init__(
        self,
        on_status: Optional[Any] = None,
        on_activity: Optional[Any] = None,
        on_metrics: Optional[Any] = None,
    ):
        self._risk = RiskManager()
        self._queue = TradeQueue()
        self._execution = ExecutionEngine(paper_trading=True)
        self._engine = BotEngine(
            risk_manager=self._risk,
            trade_queue=self._queue,
            execution_engine=self._execution,
            on_status=on_status or (lambda s: None),
            on_activity=on_activity or (lambda s: None),
            on_metrics=on_metrics or (lambda d: None),
        )
        self._strategy: Optional[StrategyModule] = None

    @property
    def engine(self) -> BotEngine:
        return self._engine

    @property
    def risk(self) -> RiskManager:
        return self._risk

    @property
    def queue(self) -> TradeQueue:
        return self._queue

    @property
    def execution(self) -> ExecutionEngine:
        return self._execution

    def set_strategy(self, strategy: Optional[StrategyModule]) -> None:
        self._strategy = strategy
        self._engine.set_strategy(strategy)

    def apply_settings(self, settings: Dict[str, Any]) -> None:
        """Apply bot settings (general, risk, execution)."""
        self._execution.paper_trading = settings.get("paper_trading", True)
        self._execution.execution_delay_sec = max(0.0, float(settings.get("execution_delay_sec", 0)))
        self._execution.randomized_delay = bool(settings.get("randomized_delay", False))
        self._queue._min_seconds_between_trades = max(0.0, float(settings.get("min_time_between_trades_sec", 0)))
        self._queue._max_per_minute = max(0, int(settings.get("max_trades_per_minute", 0)))
        self._queue._max_per_session = max(0, int(settings.get("max_trades_per_session", 0)))
        self._risk.max_risk_per_trade = max(0.0, float(settings.get("max_risk_per_trade", 0)))
        self._risk.max_daily_loss = max(0.0, float(settings.get("max_daily_loss", 0)))
        self._risk.max_consecutive_losses = max(0, int(settings.get("max_consecutive_losses", 0)))
        self._risk.stop_after_profit_target = max(0.0, float(settings.get("stop_after_profit_target", 0)))
        pmin = max(0.0, min(1.0, float(settings.get("paper_win_rate_min", 0.68))))
        pmax = max(0.0, min(1.0, float(settings.get("paper_win_rate_max", 0.80))))
        if pmax < pmin:
            pmax = pmin
        self._execution.paper_win_rate_min = pmin
        self._execution.paper_win_rate_max = pmax
        self._execution.paper_payout_ratio = max(0.0, float(settings.get("paper_payout_ratio", 0.82)))
        mode = str(settings.get("pocket_account_mode") or "demo").strip().lower()
        self._execution.pocket_account_mode = mode if mode in ("demo", "live") else "demo"

    def start(self) -> None:
        self._engine.start()

    def stop(self) -> None:
        self._engine.stop()

    def pause(self) -> None:
        self._engine.pause()

    def resume(self) -> None:
        self._engine.resume()

    def reset_session(self) -> None:
        self._risk.reset_session()
        self._queue.reset_session()
