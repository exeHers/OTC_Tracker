"""
Broker adapters for live execution and (optionally) trade detection.
"""
from .base import BrokerAdapter
from .relay_queue import RelayQueueBroker

__all__ = ["BrokerAdapter", "RelayQueueBroker"]

try:
    from .pocket_option import PocketOptionBroker
    __all__.append("PocketOptionBroker")
except ImportError:
    PocketOptionBroker = None  # optional dependency
