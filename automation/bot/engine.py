"""
Bot engine: main loop, risk checks, queue, execution. No strategy logic.
"""
import threading
import time
import random
from typing import Callable, List, Optional

from .execution import ExecutionEngine, ExecutedTrade
from .queue import TradeQueue, QueuedTrade
from .risk import RiskManager
from .strategy import StrategyModule


class BotEngine:
    """
    Core bot loop: pull from queue, check risk, execute only when strategy present.
    Runs in background thread with error recovery.
    """

    STATUS_STOPPED = "Stopped"
    STATUS_RUNNING = "Running"
    STATUS_PAUSED = "Paused"
    STATUS_ERROR = "Error"

    def __init__(
        self,
        risk_manager: RiskManager,
        trade_queue: TradeQueue,
        execution_engine: ExecutionEngine,
        on_status: Optional[Callable[[str], None]] = None,
        on_activity: Optional[Callable[[str], None]] = None,
        on_metrics: Optional[Callable[[dict], None]] = None,
    ):
        self.risk = risk_manager
        self.queue = trade_queue
        self.execution = execution_engine
        self._on_status = on_status or (lambda s: None)
        self._on_activity = on_activity or (lambda s: None)
        self._on_metrics = on_metrics or (lambda d: None)
        self._strategy: Optional[StrategyModule] = None
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._error_message: Optional[str] = None
        self._trades_executed_today: List[ExecutedTrade] = []
        self._last_executed: Optional[ExecutedTrade] = None
        self._poll_interval_sec = 0.5

    def set_strategy(self, strategy: Optional[StrategyModule]) -> None:
        self.execution.set_strategy(strategy)
        with self._lock:
            self._strategy = strategy

    def start(self) -> None:
        if self._running:
            self._on_activity("Bot already running")
            return
        self._error_message = None
        self._running = True
        self._paused = False
        self._on_status(self.STATUS_RUNNING)
        self._on_activity("Bot started")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._paused = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._on_status(self.STATUS_STOPPED)
        self._on_activity("Bot stopped")

    def pause(self) -> None:
        self._paused = True
        self._on_status(self.STATUS_PAUSED)
        self._on_activity("Bot paused")

    def resume(self) -> None:
        self._paused = False
        self._on_status(self.STATUS_RUNNING)
        self._on_activity("Bot resumed")

    def _loop(self) -> None:
        while self._running:
            try:
                if self._paused:
                    time.sleep(self._poll_interval_sec)
                    continue
                trade = self.queue.pop_next()
                if trade is None:
                    # Strategy can emit trade requests directly into queue.
                    with self._lock:
                        strat = self._strategy
                    if strat and strat.enabled:
                        with self._lock:
                            paper = self.execution.paper_trading
                        ctx = {
                            "status": self.get_status(),
                            "trades_executed": self.get_trades_executed_today(),
                            "session_pnl": self.get_session_pnl(),
                            "now": time.time(),
                            "paper_trading": paper,
                        }
                        try:
                            req = strat.next_trade_request(ctx)
                        except Exception:
                            req = None
                        if req:
                            q = QueuedTrade(
                                asset=str(req.get("asset") or "OTC"),
                                direction=str(req.get("direction") or "call"),
                                amount=float(req.get("amount") or 0.0),
                                duration_sec=int(float(req.get("duration_sec") or 5)),
                            )
                            if self.queue.enqueue(q):
                                self._on_activity("Signal queued: %s %s %.2f" % (q.asset, q.direction, q.amount))
                    time.sleep(self._poll_interval_sec)
                    continue
                ok, reason = self.queue.can_execute_now()
                if not ok:
                    self._on_activity("Skipped: %s" % reason)
                    self.queue.enqueue(trade)  # put back
                    time.sleep(self._poll_interval_sec)
                    continue
                ok, reason = self.risk.can_open_trade(trade.amount)
                if not ok:
                    self._on_activity("Risk block: %s" % reason)
                    time.sleep(self._poll_interval_sec)
                    continue
                executed = self.execution.execute(trade)
                self.queue.record_execution()
                if executed.success:
                    if executed.paper:
                        with self._lock:
                            eng = self.execution
                        pmin = float(getattr(eng, "paper_win_rate_min", 0.68))
                        pmax = float(getattr(eng, "paper_win_rate_max", 0.80))
                        pratio = float(getattr(eng, "paper_payout_ratio", 0.82))
                        eff = random.uniform(pmin, pmax)
                        pnl = (trade.amount * pratio) if (random.random() < eff) else (-trade.amount)
                    else:
                        # Live result is unknown at execution time in this framework.
                        pnl = 0.0
                    self.risk.record_trade_result(pnl)
                    if executed.paper and strat is not None and hasattr(strat, "note_paper_pnl"):
                        try:
                            strat.note_paper_pnl(trade.asset, pnl)
                        except Exception:
                            pass
                    with self._lock:
                        self._trades_executed_today.append(executed)
                        self._last_executed = executed
                self._emit_metrics()
            except Exception as e:
                self._error_message = str(e)
                self._on_status(self.STATUS_ERROR)
                self._on_activity("Error: %s" % e)
                time.sleep(1.0)
        self._emit_metrics()

    def _emit_metrics(self) -> None:
        with self._lock:
            pnl = self.risk.session_pnl
            count = len(self._trades_executed_today)
        self._on_metrics({
            "status": self.get_status(),
            "trades_today": count,
            "session_pnl": pnl,
            "last_trade": self._last_executed,
        })

    def get_status(self) -> str:
        if not self._running:
            return self.STATUS_STOPPED
        if self._error_message:
            return self.STATUS_ERROR
        if self._paused:
            return self.STATUS_PAUSED
        return self.STATUS_RUNNING

    def get_trades_executed_today(self) -> int:
        with self._lock:
            return len(self._trades_executed_today)

    def get_session_pnl(self) -> float:
        return self.risk.session_pnl

    def get_last_executed(self) -> Optional[ExecutedTrade]:
        with self._lock:
            return self._last_executed

    def clear_error(self) -> None:
        self._error_message = None
        if self._running and not self._paused:
            self._on_status(self.STATUS_RUNNING)
