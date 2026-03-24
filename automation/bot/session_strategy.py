"""
Session pulse strategy: 30s OTC signals, rotating across a basket of OTC symbols.

Paper mode: prefers symbols with better *simulated* session ledger (not live market alpha).
Live mode: round-robin across the basket (executor must have the pair available / selected).
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from .strategy import StrategyModule


class SessionPulseStrategy(StrategyModule):
    """Emits timed signals; contract length is fixed at 30s for Pocket Option."""

    DURATION_SEC = 30

    def __init__(self) -> None:
        self._enabled = True
        self._symbols: List[str] = [
            "EURUSD_otc",
            "GBPUSD_otc",
            "USDJPY_otc",
            "AUDUSD_otc",
        ]
        self._amount = 1.0
        self._duration_sec = self.DURATION_SEC
        self._interval_sec = 30.0
        self._jitter_sec = 0.0
        self._direction_mode = "alternate"
        self._last_signal_ts = 0.0
        self._next_call = True
        self._rr = 0
        self._paper_ledger: Dict[str, float] = {}

    @property
    def name(self) -> str:
        return "30s OTC basket (paper leader / live round-robin)"

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_config(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "symbols": list(self._symbols),
            "amount": self._amount,
            "duration_sec": self._duration_sec,
            "interval_sec": self._interval_sec,
            "jitter_sec": self._jitter_sec,
            "direction_mode": self._direction_mode,
            "paper_ledger": dict(self._paper_ledger),
        }

    def set_config(self, config: Dict[str, Any]) -> None:
        self._enabled = bool(config.get("enabled", self._enabled))
        raw = config.get("strategy_otc_symbols")
        if raw is None:
            raw = config.get("symbols")
        if isinstance(raw, str):
            parts = [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]
            syms = parts if parts else list(self._symbols)
        elif isinstance(raw, list):
            syms = [str(s).strip() for s in raw if str(s).strip()]
        else:
            syms = list(self._symbols)
        if not syms:
            syms = ["EURUSD_otc"]
        self._symbols = syms
        self._paper_ledger = {s: float(self._paper_ledger.get(s, 0.0)) for s in self._symbols}
        self._amount = max(0.0, float(config.get("amount", self._amount)))
        self._duration_sec = self.DURATION_SEC
        self._interval_sec = max(5.0, float(config.get("interval_sec", self._interval_sec)))
        self._jitter_sec = max(0.0, float(config.get("jitter_sec", self._jitter_sec)))
        mode = str(config.get("direction_mode", self._direction_mode) or "alternate").lower()
        self._direction_mode = mode if mode in ("alternate", "call", "put", "random") else "alternate"

    def note_paper_pnl(self, symbol: str, pnl: float) -> None:
        for s in self._symbols:
            self._paper_ledger.setdefault(s, 0.0)
        sym = str(symbol or "").strip()
        if sym in self._paper_ledger:
            self._paper_ledger[sym] += float(pnl)

    def should_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return self._enabled

    def _pick_direction(self) -> str:
        if self._direction_mode == "call":
            return "call"
        if self._direction_mode == "put":
            return "put"
        if self._direction_mode == "random":
            return "call" if random.random() > 0.5 else "put"
        d = "call" if self._next_call else "put"
        self._next_call = not self._next_call
        return d

    def _pick_symbol(self, paper_trading: bool) -> str:
        if len(self._symbols) == 1:
            return self._symbols[0]
        if paper_trading:
            for s in self._symbols:
                self._paper_ledger.setdefault(s, 0.0)
            best = max(self._paper_ledger[s] for s in self._symbols)
            leaders = [s for s in self._symbols if self._paper_ledger[s] >= best - 1e-9]
            if len(leaders) == len(self._symbols):
                pick = self._symbols[self._rr % len(self._symbols)]
                self._rr += 1
                return pick
            return random.choice(leaders)
        pick = self._symbols[self._rr % len(self._symbols)]
        self._rr += 1
        return pick

    def next_trade_request(self, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not self._enabled:
            return None
        now = time.time()
        interval = self._interval_sec
        if self._jitter_sec > 0:
            interval = max(5.0, interval + random.uniform(-self._jitter_sec, self._jitter_sec))
        if (now - self._last_signal_ts) < interval:
            return None
        self._last_signal_ts = now
        ctx = context or {}
        paper = bool(ctx.get("paper_trading", True))
        asset = self._pick_symbol(paper_trading=paper)
        return {
            "asset": asset,
            "direction": self._pick_direction(),
            "amount": self._amount,
            "duration_sec": self._duration_sec,
        }
