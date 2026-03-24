"""
Risk limits: per-trade, daily loss, consecutive losses, profit target stop.
"""
from typing import Optional


class RiskManager:
    """Enforce risk limits. No trading logic; only checks."""

    def __init__(
        self,
        max_risk_per_trade: float = 0.0,
        max_daily_loss: float = 0.0,
        max_consecutive_losses: int = 0,
        stop_after_profit_target: float = 0.0,
    ):
        self.max_risk_per_trade = max(0.0, max_risk_per_trade)
        self.max_daily_loss = max(0.0, max_daily_loss)
        self.max_consecutive_losses = max(0, max_consecutive_losses)
        self.stop_after_profit_target = max(0.0, stop_after_profit_target)
        self._session_pnl: float = 0.0
        self._consecutive_losses: int = 0
        self._trades_today: int = 0

    def reset_session(self) -> None:
        self._session_pnl = 0.0
        self._consecutive_losses = 0
        self._trades_today = 0

    def record_trade_result(self, pnl: float) -> None:
        self._trades_today += 1
        self._session_pnl += pnl
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def can_open_trade(self, risk_amount: float) -> tuple[bool, str]:
        """
        Returns (allowed, reason). risk_amount is the potential loss for the trade.
        """
        if self.max_risk_per_trade > 0 and risk_amount > self.max_risk_per_trade:
            return False, "Risk per trade exceeds limit"
        if self.max_daily_loss > 0 and self._session_pnl <= -self.max_daily_loss:
            return False, "Daily loss limit reached"
        if self.max_consecutive_losses > 0 and self._consecutive_losses >= self.max_consecutive_losses:
            return False, "Max consecutive losses reached"
        if self.stop_after_profit_target > 0 and self._session_pnl >= self.stop_after_profit_target:
            return False, "Profit target reached"
        return True, ""

    @property
    def session_pnl(self) -> float:
        return self._session_pnl

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses

    @property
    def trades_today(self) -> int:
        return self._trades_today
