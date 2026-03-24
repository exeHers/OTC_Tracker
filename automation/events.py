"""
Trade event structure for automatic tracking.
Maps to app trade format (date, time, amount, asset, result) when saving to journal.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TradeEvent:
    """Detected trade from a TradeDetectionProvider."""
    asset: str
    direction: str          # e.g. "call" / "put" or "up" / "down"
    amount: float
    entry_price: Optional[float] = None
    expiry: Optional[float] = None   # seconds or timestamp
    result: Optional[str] = None     # "win" / "loss" or "W" / "L"
    payout: Optional[float] = None   # profit/loss amount
    timestamp: Optional[datetime] = None
    raw: Optional[dict] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.result is not None:
            self.result = str(self.result).upper()[:1] if str(self.result).upper() in ("W", "L") else ("W" if str(self.result).lower() == "win" else "L")

    def to_journal_row(self) -> dict:
        """Convert to app journal format: date, time, amount, asset, result."""
        t = self.timestamp or datetime.now()
        amt = abs(self.payout) if self.payout is not None else self.amount
        res = (self.result or "W") if (self.payout or 0) >= 0 else "L"
        if self.result in ("W", "L"):
            res = self.result
        return {
            "date": t.strftime("%Y-%m-%d"),
            "time": t.strftime("%H:%M:%S"),
            "amount": str(amt),
            "asset": (self.asset or "OTC").strip() or "OTC",
            "result": res,
        }
