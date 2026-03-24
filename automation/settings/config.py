"""
Persistence for tracking and bot settings. Single JSON file in project root.
"""
import json
from pathlib import Path
from typing import Any, Dict

_BASE = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _BASE / "automation_config.json"

_DEFAULT_TRACKING = {
    "detection_method": "placeholder",
    "polling_interval_sec": 5.0,
    "auto_reconnect": True,
    "session_timeout_sec": 3600,
    "automatically_save_detected_trades": True,
    "sync_with_trade_journal": True,
    "duplicate_trade_protection": True,
    "trade_detection_delay_sec": 0.0,
    "max_detection_retries": 3,
    "error_recovery_enabled": True,
}

_DEFAULT_POCKET_OPTION = {
    "ssid": "",
    "is_demo": True,
}

_DEFAULT_BOT = {
    "paper_trading": True,
    "max_trades_per_session": 0,
    "max_trades_per_minute": 0,
    "max_risk_per_trade": 0.0,
    "max_daily_loss": 0.0,
    "max_consecutive_losses": 0,
    "stop_after_profit_target": 0.0,
    "min_time_between_trades_sec": 0.0,
    "execution_delay_sec": 0.0,
    "randomized_delay": False,
    "strategy_asset": "OTC",
    "strategy_otc_symbols": [
        "EURUSD_otc",
        "GBPUSD_otc",
        "USDJPY_otc",
        "AUDUSD_otc",
        "USDCAD_otc",
        "EURGBP_otc",
        "BTCUSD_otc",
        "ETHUSD_otc",
    ],
    "strategy_amount": 1.0,
    "strategy_duration_sec": 30,
    "strategy_interval_sec": 35.0,
    "strategy_direction_mode": "alternate",
    "strategy_jitter_sec": 0.0,
    "paper_win_rate_min": 0.68,
    "paper_win_rate_max": 0.80,
    "paper_payout_ratio": 0.82,
    "live_enabled": False,
    "pocket_account_mode": "demo",
    "broker": "relay_queue",
    "broker_relay_url": "",
    "broker_relay_user_key": "",
    "broker_relay_token": "",
    "broker_asset_symbol": "EURUSD_otc",
    "fail_safe_stop_on_broker_error": True,
    "bot_advanced_custom": True,
}


def _load_raw() -> Dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_raw(data: Dict[str, Any]) -> None:
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_tracking_settings() -> Dict[str, Any]:
    raw = _load_raw()
    out = _DEFAULT_TRACKING.copy()
    out.update(raw.get("tracking", {}))
    return out


def save_tracking_settings(settings: Dict[str, Any]) -> None:
    data = _load_raw()
    data["tracking"] = {**load_tracking_settings(), **settings}
    _save_raw(data)


def load_bot_settings() -> Dict[str, Any]:
    raw = _load_raw()
    out = _DEFAULT_BOT.copy()
    out.update(raw.get("bot", {}))
    return out


def save_bot_settings(settings: Dict[str, Any]) -> None:
    data = _load_raw()
    data["bot"] = {**load_bot_settings(), **settings}
    _save_raw(data)


def load_pocket_option_settings() -> Dict[str, Any]:
    raw = _load_raw()
    out = _DEFAULT_POCKET_OPTION.copy()
    out.update(raw.get("pocket_option", {}))
    return out


def save_pocket_option_settings(settings: Dict[str, Any]) -> None:
    data = _load_raw()
    data["pocket_option"] = {**load_pocket_option_settings(), **settings}
    _save_raw(data)
