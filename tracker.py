#!/usr/bin/env python3
"""
OTC 5-Second Trading Tracker — Underground Cyberpunk Edition
DNVN Digital–grade CLI. Stay cold. Log every move.
"""

import csv
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, FloatPrompt
from rich import box
from rich.theme import Theme
from rich.text import Text

# ─── Paths ─────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent
TRADES_CSV = BASE / "trades.csv"
CONFIG_JSON = BASE / "config.json"

# CSV columns (extended for browser helper accuracy; older files auto-migrate on load)
TRADE_FIELDNAMES = [
    "date",
    "time",
    "amount",
    "asset",
    "result",
    "payout",
    "direction",
    "duration_sec",
    "source",
    "trade_id",
]

# App version (bump this when you release an update)
APP_VERSION = "1.0.2"

# ─── Underground Cyberpunk Theme ───────────────────────────────────────────
CUSTOM_THEME = Theme({
    "bg": "black",
    "profit": "bold cyan1",
    "loss": "bold red3",
    "neutral": "bright_white",
    "accent": "bold bright_white",
    "dim": "dim white",
    "border": "bright_black",
})

BOX_DOUBLE = box.DOUBLE
BOX_HEAVY = box.HEAVY

console = Console(theme=CUSTOM_THEME, force_terminal=True)


def _migrate_trades_csv_if_needed():
    """Upgrade legacy 5-column CSV to extended header without losing rows."""
    if not TRADES_CSV.exists():
        return
    try:
        with open(TRADES_CSV, "r", newline="", encoding="utf-8") as f:
            first = f.readline()
    except OSError:
        return
    if "trade_id" in first and first.count(",") >= 9:
        return
    rows = load_trades()
    overwrite_trades(rows)


def ensure_files():
    """Create CSV and config if missing."""
    if not TRADES_CSV.exists():
        with open(TRADES_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(TRADE_FIELDNAMES)
    else:
        _migrate_trades_csv_if_needed()
    if not CONFIG_JSON.exists():
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump({"daily_goal": 0}, f, indent=2)


def load_trades():
    """Load all trades from CSV."""
    rows = []
    if not TRADES_CSV.exists():
        return rows
    with open(TRADES_CSV, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("date") and row.get("result"):
                for k in TRADE_FIELDNAMES:
                    row.setdefault(k, "")
                rows.append(row)
    return rows


def append_trade(amount: float, asset: str, result: str):
    """Append one trade to CSV. result is 'W' or 'L'."""
    now = datetime.now()
    row = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "amount": str(amount),
        "asset": asset.strip() or "OTC",
        "result": result.upper()[:1],
        "payout": "",
        "direction": "",
        "duration_sec": "",
        "source": "manual",
        "trade_id": "",
    }
    with open(TRADES_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_FIELDNAMES)
        w.writerow(row)
    return row


def append_trade_row(row: dict):
    """Append one trade (manual, browser helper, or automation). Missing keys default to empty."""
    out = {k: str(row.get(k, "") or "") for k in TRADE_FIELDNAMES}
    if not out.get("source"):
        out["source"] = "browser" if row.get("trade_id") or row.get("payout") not in (None, "") else "manual"
    with open(TRADES_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_FIELDNAMES)
        w.writerow(out)


def overwrite_trades(trades: list):
    """Replace entire trades CSV with the given list of trade dicts."""
    with open(TRADES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_FIELDNAMES)
        w.writeheader()
        for t in trades:
            w.writerow({k: (t.get(k, "") or "") for k in TRADE_FIELDNAMES})


def clear_trades_journal():
    """Delete all trade rows from CSV. Keeps config.json (theme, currency, goals, sync URL, etc.). Resets browser collection state file."""
    with open(TRADES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_FIELDNAMES)
        w.writeheader()
    try:
        from trade_collection_state import reset_state

        reset_state()
    except Exception:
        pass


def clear_all_data():
    """Full factory reset: trades + config (daily_goal=0, theme=dark, currency=ZAR). Prefer clear_trades_journal() from GUI wipe."""
    clear_trades_journal()
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump({"daily_goal": 0, "theme": "dark", "currency": "ZAR"}, f, indent=2)


def delete_trades_for_date(date_str: str) -> int:
    """Remove all trades where date == date_str. Returns count removed."""
    trades = load_trades()
    kept = [t for t in trades if (t.get("date") or "") != date_str]
    n = len(trades) - len(kept)
    if n:
        overwrite_trades(kept)
    return n


def get_daily_goal():
    """Read daily goal from config."""
    try:
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            return float(json.load(f).get("daily_goal", 0) or 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0.0


def set_daily_goal(value: float):
    """Write daily goal to config."""
    data = {}
    if CONFIG_JSON.exists():
        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    data["daily_goal"] = value
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_theme():
    """Read theme from config ('dark' or 'light')."""
    try:
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            return json.load(f).get("theme", "dark") or "dark"
    except (FileNotFoundError, json.JSONDecodeError):
        return "dark"


def set_theme(value: str):
    """Write theme to config."""
    data = {}
    if CONFIG_JSON.exists():
        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    data["theme"] = value
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_currency():
    """Read currency code from config (default ZAR)."""
    try:
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            return json.load(f).get("currency", "ZAR") or "ZAR"
    except (FileNotFoundError, json.JSONDecodeError):
        return "ZAR"


def set_currency(value: str):
    """Write currency code to config."""
    data = {}
    if CONFIG_JSON.exists():
        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    data["currency"] = value
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_update_check_url():
    """Read update check URL from config (empty = not set)."""
    try:
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            return (json.load(f).get("update_check_url") or "").strip()
    except (FileNotFoundError, json.JSONDecodeError):
        return ""


def set_update_check_url(value: str):
    """Write update check URL to config."""
    data = {}
    if CONFIG_JSON.exists():
        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    data["update_check_url"] = (value or "").strip()
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_sync_file_path():
    """Read sync file path from config (for Drive/OneDrive). Empty = not set."""
    try:
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            return (json.load(f).get("sync_file_path") or "").strip()
    except (FileNotFoundError, json.JSONDecodeError):
        return ""


def set_sync_file_path(value: str):
    """Write sync file path to config."""
    data = {}
    if CONFIG_JSON.exists():
        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    data["sync_file_path"] = (value or "").strip()
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def export_to_sync_file(path: str = None):
    """Write current trades and config to a JSON file (for cloud sync). path defaults to config sync_file_path."""
    path = (path or get_sync_file_path()).strip()
    if not path:
        raise ValueError("Sync file path is not set")
    trades = load_trades()
    data = {
        "trades": trades,
        "daily_goal": get_daily_goal(),
        "theme": get_theme(),
        "currency": get_currency(),
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


def import_from_sync_file(path: str = None):
    """Read sync file and overwrite local trades and config. path defaults to config sync_file_path."""
    path = (path or get_sync_file_path()).strip()
    if not path:
        raise ValueError("Sync file path is not set")
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Sync file not found: {path}")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    trades = data.get("trades") or []
    overwrite_trades(trades)
    if "daily_goal" in data:
        set_daily_goal(float(data["daily_goal"]) if data["daily_goal"] is not None else 0)
    if data.get("theme"):
        set_theme(str(data["theme"]))
    if data.get("currency"):
        set_currency(str(data["currency"]))
    return data.get("updated_at", "")


def version_newer(remote: str, local: str) -> bool:
    """Return True if remote version is newer than local (e.g. 1.0.1 > 1.0.0)."""
    def parse(v):
        parts = []
        for x in (v or "0").strip().split("."):
            try:
                parts.append(int(x))
            except ValueError:
                parts.append(0)
        return parts
    r, l = parse(remote), parse(local)
    while len(r) < len(l):
        r.append(0)
    while len(l) < len(r):
        l.append(0)
    return r > l


def session_stats(trades: list):
    """Compute stats for today's session."""
    today = datetime.now().strftime("%Y-%m-%d")
    session = [t for t in trades if t.get("date") == today]
    total = len(session)
    wins = sum(1 for t in session if t.get("result", "").upper() == "W")
    losses = total - wins

    mali = 0.0
    for t in session:
        try:
            amt = float(t.get("amount", 0))
        except (ValueError, TypeError):
            amt = 0
        if t.get("result", "").upper() == "W":
            mali += amt
        else:
            mali -= amt

    win_rate = (wins / total * 100) if total else 0.0
    return {
        "session_mali": mali,
        "win_rate": win_rate,
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "session_trades": session,
    }


def mindset_status(stats: dict, daily_goal: float) -> str:
    """Return mindset label from session state."""
    mali = stats["session_mali"]
    total = stats["total_trades"]
    win_rate = stats["win_rate"]

    if total == 0:
        return "READY"
    if daily_goal > 0 and mali >= daily_goal:
        return "LOCKED IN"
    if stats["losses"] >= 3 and win_rate < 40:
        return "STAY COLD"
    if win_rate >= 60 and mali > 0:
        return "DISCIPLINED"
    if mali < 0:
        return "RESET MODE"
    return "GRINDING"


def feedback_message(is_win: bool) -> str:
    """South African–flavor feedback."""
    if is_win:
        return "Nxa, keep grinding."
    return "Don't be a chop, reset."


def render_dashboard(stats: dict, daily_goal: float):
    """Draw main dashboard with tables and panels."""
    mali = stats["session_mali"]
    win_rate = stats["win_rate"]
    total = stats["total_trades"]
    mindset = mindset_status(stats, daily_goal)

    # Stats table
    table = Table(show_header=True, header_style="bold bright_white", box=BOX_DOUBLE, border_style="bright_black")
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    mali_style = "profit" if mali >= 0 else "loss"
    mali_text = f"+{mali:.2f}" if mali >= 0 else f"{mali:.2f}"
    table.add_row("Current Session Mali", f"[{mali_style}]{mali_text}[/]")
    table.add_row("Win Rate %", f"[neutral]{win_rate:.1f}%[/]")
    table.add_row("Total Trades (Today)", f"[neutral]{total}[/]")

    console.print()
    console.print(Panel(table, title="[accent] SESSION DASHBOARD [/]", border_style="bright_black", box=BOX_DOUBLE, padding=(0, 1)))
    console.print()

    # Mindset panel
    mindset_style = "profit" if mindset in ("LOCKED IN", "DISCIPLINED", "GRINDING", "READY") else "loss" if mindset in ("RESET MODE", "STAY COLD") else "neutral"
    console.print(Panel(f"[{mindset_style}]{mindset}[/]", title="[dim] MINDSET STATUS [/]", border_style="bright_black", box=BOX_HEAVY, padding=(0, 2)))
    console.print()

    # Daily goal progress
    if daily_goal > 0:
        progress_pct = min(1.0, max(0.0, mali / daily_goal)) if daily_goal else 0.0
        width = 36
        filled = int(width * progress_pct)
        bar_fill = "█" * filled
        bar_empty = "░" * (width - filled)
        bar_color = "cyan1" if progress_pct < 1.0 else "green1"
        bar_text = Text()
        bar_text.append(f"Daily Goal: R {mali:.0f} / R {daily_goal:.0f}  ", style="bold")
        bar_text.append(bar_fill, style=bar_color)
        bar_text.append(bar_empty, style="bright_black")
        bar_text.append(f"  {progress_pct * 100:.0f}%", style="bold")
        console.print(Panel(bar_text, title="[dim] DAILY GOAL [/]", border_style="bright_black", box=BOX_DOUBLE, padding=(0, 1)))
        console.print()
    else:
        console.print(Panel("[dim]Set a daily goal from the menu to track progress.[/]", title="[dim] DAILY GOAL [/]", border_style="bright_black", box=BOX_DOUBLE, padding=(0, 1)))
        console.print()


def log_trade_flow():
    """Interactive flow to log one trade."""
    console.print(Panel("[accent] LOG TRADE [/]", border_style="bright_black", box=BOX_HEAVY, padding=(0, 2)))
    console.print()

    amount = FloatPrompt.ask("[dim]Trade amount (R)[/]", default=0.0)
    asset = Prompt.ask("[dim]Asset[/]", default="OTC")
    result = Prompt.ask("[dim]Result (W/L)[/]", choices=["w", "l", "W", "L"], default="w").upper()[:1]

    append_trade(amount, asset, result)
    is_win = result == "W"
    msg = feedback_message(is_win)
    style = "profit" if is_win else "loss"
    console.print(Panel(f"[{style}]{msg}[/]", border_style="bright_black", box=BOX_DOUBLE, padding=(0, 2)))
    console.print()


def set_goal_flow():
    """Set daily goal."""
    console.print(Panel("[accent] SET DAILY GOAL [/]", border_style="bright_black", box=BOX_HEAVY, padding=(0, 2)))
    current = get_daily_goal()
    console.print(f"[dim]Current goal: {current:.0f}[/]")
    value = FloatPrompt.ask("[dim]New daily goal (R)[/]", default=current)
    if value < 0:
        value = 0
    set_daily_goal(value)
    console.print(Panel(f"[profit]Daily goal set to R {value:.0f}[/]", border_style="bright_black", box=BOX_DOUBLE))
    console.print()


def main():
    ensure_files()
    console.print(Panel("[accent] OTC 5-SEC TRADING TRACKER [/] [dim]— Underground Cyberpunk[/]", border_style="bright_black", box=BOX_DOUBLE, padding=(0, 2)))
    console.print("[dim]Data: " + str(TRADES_CSV) + "[/]")
    console.print()

    while True:
        trades = load_trades()
        stats = session_stats(trades)
        daily_goal = get_daily_goal()
        render_dashboard(stats, daily_goal)

        console.print("[dim]1[/] Log trade  [dim]2[/] Set daily goal  [dim]3[/] Refresh  [dim]4[/] Exit")
        choice = Prompt.ask("[accent]Choice[/]", choices=["1", "2", "3", "4"], default="1")

        if choice == "1":
            log_trade_flow()
        elif choice == "2":
            set_goal_flow()
        elif choice == "3":
            continue
        else:
            console.print("[dim]Stay cold. Exit.[/]")
            break


if __name__ == "__main__":
    main()
