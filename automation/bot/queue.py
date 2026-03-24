"""
Trade queue: throttle and order execution requests.
"""
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Optional


@dataclass
class QueuedTrade:
    """Single trade request in the queue."""
    asset: str
    direction: str
    amount: float
    duration_sec: int = 5
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.created_at == 0:
            self.created_at = time.time()
        if self.duration_sec < 5:
            self.duration_sec = 5


class TradeQueue:
    """Thread-safe queue with min delay between trades and optional max size."""

    def __init__(
        self,
        min_seconds_between_trades: float = 0.0,
        max_trades_per_minute: int = 0,
        max_trades_per_session: int = 0,
    ):
        self._min_seconds = max(0.0, min_seconds_between_trades)
        self._max_per_minute = max(0, max_trades_per_minute)
        self._max_per_session = max(0, max_trades_per_session)
        self._queue: Deque[QueuedTrade] = deque()
        self._lock = threading.Lock()
        self._last_execution_time: float = 0.0
        self._execution_timestamps: Deque[float] = deque(maxlen=120)  # last 2 min
        self._session_count: int = 0

    def reset_session(self) -> None:
        with self._lock:
            self._session_count = 0
            self._execution_timestamps.clear()

    def enqueue(self, trade: QueuedTrade) -> bool:
        """Add trade to queue. Returns True if accepted."""
        with self._lock:
            if self._max_per_session > 0 and self._session_count >= self._max_per_session:
                return False
            self._queue.append(trade)
            return True

    def can_execute_now(self) -> tuple[bool, str]:
        """Returns (allowed, reason)."""
        with self._lock:
            now = time.time()
            if self._min_seconds > 0 and (now - self._last_execution_time) < self._min_seconds:
                return False, "Minimum time between trades not met"
            if self._max_per_minute > 0:
                cutoff = now - 60.0
                recent = sum(1 for t in self._execution_timestamps if t > cutoff)
                if recent >= self._max_per_minute:
                    return False, "Max trades per minute reached"
            if self._max_per_session > 0 and self._session_count >= self._max_per_session:
                return False, "Max trades per session reached"
            return True, ""

    def record_execution(self) -> None:
        with self._lock:
            self._last_execution_time = time.time()
            self._execution_timestamps.append(self._last_execution_time)
            self._session_count += 1

    def pop_next(self) -> Optional[QueuedTrade]:
        with self._lock:
            if not self._queue:
                return None
            return self._queue.popleft()

    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
