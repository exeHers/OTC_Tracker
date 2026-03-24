#!/usr/bin/env python3
"""
OTC 5-Second Trading Tracker — GUI Edition (Underground Cyberpunk)
Native window. Same data as CLI (trades.csv, config.json).
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import json
import urllib.parse
import urllib.request
import urllib.error
import webbrowser

# Reuse data layer from CLI tracker
from tracker import (
    ensure_files,
    load_trades,
    append_trade,
    append_trade_row,
    overwrite_trades,
    clear_trades_journal,
    delete_trades_for_date,
    get_daily_goal,
    set_daily_goal,
    get_currency,
    set_currency,
    get_theme,
    set_theme,
    get_update_check_url,
    set_update_check_url,
    get_sync_file_path,
    set_sync_file_path,
    export_to_sync_file,
    import_from_sync_file,
    version_newer,
    APP_VERSION,
    session_stats,
    mindset_status,
    feedback_message,
)
from trade_collection_state import load_state, set_collection_enabled
from automation.bot import BotController
from automation.bot.session_strategy import SessionPulseStrategy
from automation.settings import (
    load_bot_settings,
    save_bot_settings,
)
from automation.settings.config import _DEFAULT_BOT
from automation.brokers.relay_queue import RelayQueueBroker
from currencies import CURRENCIES, format_amount

from po_event_receiver import run_server as _run_trade_event_server

# ─── Themes ─────────────────────────────────────────────────────────────────
THEMES = {
    "dark": {
        "BG": "#0a0a0a",
        "BG_FRAME": "#141414",
        "FG_DIM": "#888888",
        "FG_WHITE": "#e0e0e0",
        "ACCENT": "#ffffff",
        "PROFIT": "#00ffbf",
        "LOSS": "#dc143c",
        "BORDER": "#333333",
    },
    "light": {
        "BG": "#f0f0f0",
        "BG_FRAME": "#ffffff",
        "FG_DIM": "#666666",
        "FG_WHITE": "#1a1a1a",
        "ACCENT": "#1a1a1a",
        "PROFIT": "#00875a",
        "LOSS": "#c53030",
        "BORDER": "#cccccc",
    },
}


def make_frame(parent, title, hint="", colors=None, **kwargs):
    """Panel-style frame with title and optional one-line hint."""
    c = colors or THEMES["dark"]
    f = tk.Frame(parent, bg=c["BG_FRAME"], highlightbackground=c["BORDER"], highlightthickness=1, **kwargs)
    lbl = tk.Label(f, text=title, fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9))
    lbl.pack(anchor="w", padx=10, pady=(8, 0))
    if hint:
        h = tk.Label(f, text=hint, fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 8))
        h.pack(anchor="w", padx=10, pady=(0, 4))
    return f


class TradingTrackerApp:
    def __init__(self):
        ensure_files()
        self.theme = get_theme()
        if self.theme not in THEMES:
            self.theme = "dark"
        self.colors = THEMES[self.theme].copy()
        self.root = tk.Tk()
        self.root.title("OTC Trading Tracker")
        self.root.configure(bg=self.colors["BG"])
        self.root.minsize(420, 520)
        self.root.geometry("460x580")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start embedded PocketOption trade-event receiver in background
        self._receiver_thread = threading.Thread(target=_run_trade_event_server, daemon=True)
        self._receiver_thread.start()

        self._build_styles()
        self._build_ui()
        self.refresh_dashboard()
        self._refresh_browser_tracking_dashboard()
        self._update_status_bar()
        self._schedule_auto_refresh()

    def _schedule_auto_refresh(self):
        """Periodically refresh dashboard and history so new browser-tracked trades appear without manual refresh."""
        try:
            self.refresh_dashboard()
            self._refresh_history()
            self._refresh_browser_tracking_dashboard()
        except Exception:
            pass
        # every 10 seconds
        self.root.after(10000, self._schedule_auto_refresh)

    def _build_styles(self):
        c = self.colors
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure(
            "Cyber.Horizontal.TProgressbar",
            troughcolor=c["BG_FRAME"],
            background=c["PROFIT"],
            darkcolor=c["PROFIT"],
            lightcolor=c["PROFIT"],
            bordercolor=c["BORDER"],
        )
        self.style.configure("TEntry", fieldbackground=c["BG_FRAME"], foreground=c["FG_WHITE"])
        self.style.configure("TButton", background=c["BG_FRAME"], foreground=c["ACCENT"])
        self.style.configure("TNotebook", background=c["BG"])
        self.style.configure("TNotebook.Tab", background=c["BG_FRAME"], foreground=c["FG_WHITE"], padding=(10, 4))
        self.style.map("TNotebook.Tab", background=[("selected", c["BORDER"])])
        self.style.configure("Treeview", background=c["BG_FRAME"], foreground=c["FG_WHITE"], fieldbackground=c["BG_FRAME"], rowheight=22)
        self.style.configure("Treeview.Heading", background=c["BORDER"], foreground=c["ACCENT"])
        self.style.map("Treeview", background=[("selected", c["BORDER"])])

    def _make_tab_scroll_area(self, parent, bg=None):
        """Vertical scroll for a notebook page: pack outer into parent; put all tab widgets inside inner."""
        c = self.colors
        bg = bg or c["BG"]
        outer = tk.Frame(parent, bg=bg)
        outer.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(outer, bg=bg, highlightthickness=0)
        vsb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=bg)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _sync_scroll(_event=None):
            canvas.update_idletasks()
            br = canvas.bbox("all")
            if br:
                canvas.configure(scrollregion=br)

        def _on_canvas_resize(event):
            canvas.itemconfig(win_id, width=max(event.width, 1))

        inner.bind("<Configure>", _sync_scroll)
        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def _mw(event):
            br = canvas.bbox("all")
            if br and br[3] > 1:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _mw_linux_up(_event):
            br = canvas.bbox("all")
            if br and br[3] > 1:
                canvas.yview_scroll(-1, "units")

        def _mw_linux_dn(_event):
            br = canvas.bbox("all")
            if br and br[3] > 1:
                canvas.yview_scroll(1, "units")

        canvas.bind("<MouseWheel>", _mw)
        inner.bind("<MouseWheel>", _mw)
        canvas.bind("<Button-4>", _mw_linux_up)
        canvas.bind("<Button-5>", _mw_linux_dn)
        inner.bind("<Button-4>", _mw_linux_up)
        inner.bind("<Button-5>", _mw_linux_dn)
        self._tab_scroll_canvas_regions.append((canvas, inner))
        return outer, inner

    def _build_ui(self):
        c = self.colors
        self._tab_scroll_canvas_regions = []
        # Header + theme toggle
        top = tk.Frame(self.root, bg=c["BG"])
        top.pack(fill="x", padx=12, pady=(12, 0))
        header = tk.Label(top, text="OTC 5-SEC TRADING TRACKER", fg=c["ACCENT"], bg=c["BG"], font=("Consolas", 14, "bold"))
        header.pack(side="left")
        self.theme_btn = tk.Button(top, text="Light" if self.theme == "dark" else "Dark", fg=c["FG_DIM"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._toggle_theme, relief="flat", cursor="hand2")
        self.theme_btn.pack(side="right", padx=4)
        sub = tk.Label(self.root, text="", fg=c["FG_DIM"], bg=c["BG"], font=("Consolas", 9))
        sub.pack(pady=(0, 2))

        self.root_ref = self.root
        self.header_ref = header
        self.sub_ref = sub

        # Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        tab_dash = tk.Frame(self.notebook, bg=c["BG"])
        self.notebook.add(tab_dash, text="  Dashboard  ")
        _, dash_inner = self._make_tab_scroll_area(tab_dash, c["BG"])
        self.tab_dash_ref = tab_dash

        tab_history = tk.Frame(self.notebook, bg=c["BG"])
        self.notebook.add(tab_history, text="  History  ")
        _, hist_inner = self._make_tab_scroll_area(tab_history, c["BG"])
        self.tab_history_ref = tab_history

        # ─── Tab 1: Dashboard ───────────────────────────────────────────────
        dash = make_frame(dash_inner, "SESSION DASHBOARD", hint="Today's P&L, win rate, and trade count. Mindset updates from your run.", colors=c)
        dash.pack(fill="x", padx=16, pady=6)
        self.dash_ref = dash

        self.lbl_mali = tk.Label(dash, text="Session Mali: —", fg=c["FG_WHITE"], bg=c["BG_FRAME"], font=("Consolas", 11))
        self.lbl_mali.pack(anchor="w", padx=12, pady=2)
        self.lbl_winrate = tk.Label(dash, text="Win Rate: —%", fg=c["FG_WHITE"], bg=c["BG_FRAME"], font=("Consolas", 11))
        self.lbl_winrate.pack(anchor="w", padx=12, pady=2)
        self.lbl_trades = tk.Label(dash, text="Total Trades (Today): 0", fg=c["FG_WHITE"], bg=c["BG_FRAME"], font=("Consolas", 11))
        self.lbl_trades.pack(anchor="w", padx=12, pady=2)

        mind_f = tk.Frame(dash, bg=c["BG_FRAME"])
        mind_f.pack(fill="x", padx=12, pady=(8, 10))
        tk.Label(mind_f, text="Mindset:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(side="left")
        self.lbl_mindset = tk.Label(mind_f, text="READY", fg=c["PROFIT"], bg=c["BG_FRAME"], font=("Consolas", 11, "bold"))
        self.lbl_mindset.pack(side="left", padx=(6, 0))
        self.mind_f_ref = mind_f

        # ─── Daily goal ────────────────────────────────────────────────────
        goal_f = make_frame(dash_inner, "DAILY GOAL", hint="Set a target (R). Bar fills as session profit reaches it.", colors=c)
        goal_f.pack(fill="x", padx=16, pady=6)
        self.goal_f_ref = goal_f

        goal_row = tk.Frame(goal_f, bg=c["BG_FRAME"])
        goal_row.pack(fill="x", padx=12, pady=4)
        self.lbl_goal_currency = tk.Label(goal_row, text="Target:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 10))
        self.lbl_goal_currency.pack(side="left", padx=(0, 8))
        self.ent_goal = tk.Entry(goal_row, width=12, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_goal.pack(side="left", padx=(0, 8))
        self.ent_goal.insert(0, str(int(get_daily_goal())))
        btn_goal = tk.Button(goal_row, text="Set goal", fg=c["ACCENT"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["ACCENT"], font=("Consolas", 9), command=self._on_set_goal, relief="flat", cursor="hand2")
        btn_goal.pack(side="left")
        self.goal_row_ref = goal_row

        self.lbl_goal_status = tk.Label(goal_f, text="Set a daily goal to track progress.", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9))
        self.lbl_goal_status.pack(anchor="w", padx=12, pady=(0, 4))
        self.progress = ttk.Progressbar(goal_f, style="Cyber.Horizontal.TProgressbar", length=380, mode="determinate")
        self.progress.pack(padx=12, pady=(0, 10))

        # ─── Log trade ──────────────────────────────────────────────────────
        log_f = make_frame(dash_inner, "LOG TRADE", hint="Enter amount and asset, pick Win/Loss, then Log. Saves to trades.csv.", colors=c)
        log_f.pack(fill="x", padx=16, pady=6)
        self.log_f_ref = log_f

        self.lbl_amount_currency = tk.Label(log_f, text="Amount:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9))
        self.lbl_amount_currency.pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_amount = tk.Entry(log_f, width=16, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_amount.pack(anchor="w", padx=12, pady=(0, 6))

        tk.Label(log_f, text="Asset:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_asset = tk.Entry(log_f, width=16, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_asset.insert(0, "OTC")
        self.ent_asset.pack(anchor="w", padx=12, pady=(0, 6))

        tk.Label(log_f, text="Result:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        btn_row = tk.Frame(log_f, bg=c["BG_FRAME"])
        btn_row.pack(anchor="w", padx=12, pady=(0, 4))
        self.result_var = tk.StringVar(value="W")
        self.r_w = tk.Radiobutton(btn_row, text="Win", variable=self.result_var, value="W", fg=c["PROFIT"], bg=c["BG_FRAME"], selectcolor=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["PROFIT"], font=("Consolas", 10), cursor="hand2")
        self.r_w.pack(side="left", padx=(0, 16))
        self.r_l = tk.Radiobutton(btn_row, text="Loss", variable=self.result_var, value="L", fg=c["LOSS"], bg=c["BG_FRAME"], selectcolor=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["LOSS"], font=("Consolas", 10), cursor="hand2")
        self.r_l.pack(side="left")
        self.log_btn_row_ref = btn_row

        tk.Button(log_f, text="Log trade", fg=c["ACCENT"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["ACCENT"], font=("Consolas", 10, "bold"), command=self._on_log_trade, relief="flat", cursor="hand2").pack(pady=(8, 6))

        self.lbl_feedback = tk.Label(log_f, text="", fg=c["FG_WHITE"], bg=c["BG_FRAME"], font=("Consolas", 10))
        self.lbl_feedback.pack(pady=(0, 10))

        # Dashboard buttons + tips
        btn_row = tk.Frame(dash_inner, bg=c["BG"])
        btn_row.pack(pady=(4, 2))
        tk.Button(btn_row, text="Refresh", fg=c["FG_DIM"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self.refresh_dashboard, relief="flat", cursor="hand2").pack(side="left", padx=2)
        tk.Button(btn_row, text="What's what?", fg=c["FG_DIM"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._show_tips, relief="flat", cursor="hand2").pack(side="left", padx=2)

        tips_frame = make_frame(dash_inner, "QUICK REFERENCE", hint="Session Mali = today's profit/loss. Mindset = READY / STAY COLD / DISCIPLINED / LOCKED IN from your stats.", colors=c)
        tips_frame.pack(fill="x", padx=16, pady=(0, 12))
        self.tips_ref = tips_frame
        self.tips_label_ref = tk.Label(tips_frame, text="Daily goal bar = progress to target. Log trade = record each 5-sec OTC trade to CSV. History tab = full trade list.", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 8), wraplength=400, justify="left")
        self.tips_label_ref.pack(anchor="w", padx=12, pady=(0, 8))

        # ─── Tab 2: History ───────────────────────────────────────────────
        hist_hint = make_frame(hist_inner, "TRADE HISTORY", hint="All trades from CSV. Toggle Today only or All. Use Refresh to reload.", colors=c)
        hist_hint.pack(fill="x", padx=16, pady=(6, 2))
        self.hist_hint_ref = hist_hint

        hist_controls = tk.Frame(hist_inner, bg=c["BG"])
        hist_controls.pack(fill="x", padx=16, pady=4)
        self.hist_controls_ref = hist_controls
        self.history_filter = tk.StringVar(value="all")
        tk.Radiobutton(hist_controls, text="All", variable=self.history_filter, value="all", fg=c["FG_DIM"], bg=c["BG"], selectcolor=c["BG_FRAME"], activebackground=c["BG"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._refresh_history).pack(side="left", padx=(0, 12))
        tk.Radiobutton(hist_controls, text="Today only", variable=self.history_filter, value="today", fg=c["FG_DIM"], bg=c["BG"], selectcolor=c["BG_FRAME"], activebackground=c["BG"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._refresh_history).pack(side="left")
        tk.Button(hist_controls, text="Refresh", fg=c["FG_DIM"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._refresh_history, relief="flat", cursor="hand2").pack(side="right")
        tk.Button(hist_controls, text="Delete today", fg=c["FG_DIM"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._delete_today_trades, relief="flat", cursor="hand2").pack(side="right", padx=(0, 8))
        tk.Button(hist_controls, text="Clear selected", fg=c["FG_DIM"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._clear_selected_trades, relief="flat", cursor="hand2").pack(side="right", padx=(0, 8))
        tk.Button(hist_controls, text="Clear journal", fg=c["LOSS"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["LOSS"], font=("Consolas", 9), command=self._wipe_trades_journal, relief="flat", cursor="hand2").pack(side="right")

        hist_container = tk.Frame(hist_inner, bg=c["BG"])
        hist_container.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.hist_container_ref = hist_container
        scroll = ttk.Scrollbar(hist_container)
        scroll.pack(side="right", fill="y")
        self.history_tree = ttk.Treeview(
            hist_container,
            columns=("date", "time", "amount", "asset", "result", "src"),
            show="headings",
            height=14,
            yscrollcommand=scroll.set,
        )
        headings = {"date": "Date", "time": "Time", "amount": "Amt", "asset": "Asset", "result": "R", "src": "Src"}
        widths = {"date": 88, "time": 62, "amount": 56, "asset": 120, "result": 36, "src": 52}
        for col in ("date", "time", "amount", "asset", "result", "src"):
            self.history_tree.heading(col, text=headings[col])
            self.history_tree.column(col, width=widths[col])
        self.history_tree.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.history_tree.yview)
        self._refresh_history()

        # ─── Tab 3: Extras (Currency) ───────────────────────────────────────
        tab_extras = tk.Frame(self.notebook, bg=c["BG"])
        self.notebook.add(tab_extras, text="  Extras  ")
        _, extras_inner = self._make_tab_scroll_area(tab_extras, c["BG"])
        self.tab_extras_ref = tab_extras
        curr_f = make_frame(extras_inner, "CURRENCY", hint="Search and select your currency. Used for amounts and goals.", colors=c)
        curr_f.pack(fill="x", padx=16, pady=6)
        self.curr_f_ref = curr_f
        curr_row = tk.Frame(curr_f, bg=c["BG_FRAME"])
        curr_row.pack(fill="x", padx=12, pady=4)
        self.curr_row_currency_ref = curr_row
        tk.Label(curr_row, text="Current:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 10)).pack(side="left", padx=(0, 8))
        self.lbl_current_currency = tk.Label(curr_row, text=get_currency(), fg=c["ACCENT"], bg=c["BG_FRAME"], font=("Consolas", 10, "bold"))
        self.lbl_current_currency.pack(side="left")
        tk.Label(curr_f, text="Search:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(6, 0))
        self.currency_search_var = tk.StringVar()
        self.currency_search_var.trace("w", lambda *a: self._filter_currency_list())
        self.ent_currency_search = tk.Entry(curr_f, textvariable=self.currency_search_var, width=30, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_currency_search.pack(anchor="w", padx=12, pady=(0, 4))
        curr_list_frame = tk.Frame(curr_f, bg=c["BG_FRAME"])
        curr_list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        scroll_curr = tk.Scrollbar(curr_list_frame)
        scroll_curr.pack(side="right", fill="y")
        self.currency_listbox = tk.Listbox(curr_list_frame, height=12, bg=c["BG_FRAME"], fg=c["FG_WHITE"], selectbackground=c["BORDER"], font=("Consolas", 9), yscrollcommand=scroll_curr.set)
        self.currency_listbox.pack(side="left", fill="both", expand=True)
        scroll_curr.config(command=self.currency_listbox.yview)
        self._currency_display_list = ["{} – {}".format(code, name) for code, name in CURRENCIES]
        self._currency_codes = [code for code, name in CURRENCIES]
        self._refresh_currency_listbox()
        self.currency_listbox.bind("<<ListboxSelect>>", self._on_currency_select)
        self._update_currency_labels()

        # ─── Check for update (Extras) ─────────────────────────────────────
        update_f = make_frame(extras_inner, "CHECK FOR UPDATE", hint="Set the URL to a version.json (see version.json in this folder). Then click Check.", colors=c)
        update_f.pack(fill="x", padx=16, pady=6)
        self.update_f_ref = update_f
        up_row = tk.Frame(update_f, bg=c["BG_FRAME"])
        up_row.pack(fill="x", padx=12, pady=4)
        self.update_up_row_ref = up_row
        tk.Label(up_row, text="Version:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(side="left", padx=(0, 8))
        self.lbl_update_ver_ref = tk.Label(up_row, text=APP_VERSION, fg=c["ACCENT"], bg=c["BG_FRAME"], font=("Consolas", 9))
        self.lbl_update_ver_ref.pack(side="left")
        tk.Label(update_f, text="Update URL (version.json):", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_update_url = tk.Entry(update_f, width=50, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_update_url.pack(fill="x", padx=12, pady=(0, 4))
        self.ent_update_url.insert(0, get_update_check_url())
        btn_row_up = tk.Frame(update_f, bg=c["BG_FRAME"])
        btn_row_up.pack(fill="x", padx=12, pady=(4, 10))
        self.btn_save_url_ref = tk.Button(btn_row_up, text="Save URL", fg=c["FG_DIM"], bg=c["BG"], font=("Consolas", 9), command=self._save_update_url, relief="flat", cursor="hand2")
        self.btn_save_url_ref.pack(side="left", padx=(0, 8))
        self.btn_check_update_ref = tk.Button(btn_row_up, text="Check for update", fg=c["ACCENT"], bg=c["BG"], font=("Consolas", 9), command=self._check_for_update, relief="flat", cursor="hand2")
        self.btn_check_update_ref.pack(side="left")

        # ─── Cloud sync Drive/OneDrive (Extras) ──────────────────────────────
        sync_f = make_frame(extras_inner, "CLOUD SYNC (DRIVE / ONEDRIVE)", hint="", colors=c)
        self.sync_inst_ref = tk.Label(sync_f, text="1. Browse → pick a file in your Drive or OneDrive folder (e.g. otc_tracker_sync.json).\n2. Save path.\n3. Upload = write data to file (syncs to cloud). Download = load data from file.\nPhone: Export sync file → save to Drive. Then Import sync file and pick that file.", justify="left", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9))
        self.sync_inst_ref.pack(anchor="w", padx=12, pady=(0, 8))
        sync_f.pack(fill="x", padx=16, pady=6)
        self.sync_f_ref = sync_f
        tk.Label(sync_f, text="Sync file path:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        sync_row = tk.Frame(sync_f, bg=c["BG_FRAME"])
        sync_row.pack(fill="x", padx=12, pady=(0, 4))
        self.sync_row_ref = sync_row
        self.ent_sync_path = tk.Entry(sync_row, width=45, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_sync_path.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.ent_sync_path.insert(0, get_sync_file_path())
        self.btn_browse_sync_ref = tk.Button(sync_row, text="Browse…", fg=c["FG_DIM"], bg=c["BG"], font=("Consolas", 9), command=self._browse_sync_file, relief="flat", cursor="hand2")
        self.btn_browse_sync_ref.pack(side="left", padx=(0, 8))
        self.btn_save_sync_path_ref = tk.Button(sync_row, text="Save path", fg=c["FG_DIM"], bg=c["BG"], font=("Consolas", 9), command=self._save_sync_path, relief="flat", cursor="hand2")
        self.btn_save_sync_path_ref.pack(side="left")
        sync_btn_row = tk.Frame(sync_f, bg=c["BG_FRAME"])
        sync_btn_row.pack(fill="x", padx=12, pady=(4, 10))
        self.sync_btn_row_ref = sync_btn_row
        self.btn_upload_sync_ref = tk.Button(sync_btn_row, text="Upload to sync file", fg=c["PROFIT"], bg=c["BG"], font=("Consolas", 9), command=self._upload_sync, relief="flat", cursor="hand2")
        self.btn_upload_sync_ref.pack(side="left", padx=(0, 8))
        self.btn_download_sync_ref = tk.Button(sync_btn_row, text="Download from sync file", fg=c["ACCENT"], bg=c["BG"], font=("Consolas", 9), command=self._download_sync, relief="flat", cursor="hand2")
        self.btn_download_sync_ref.pack(side="left")

        # (Pocket Option SSID section removed; desktop now uses browser helper only)

        # ─── Tab: Automatic Trade Tracking ───────────────────────────────────
        tab_auto_tracking = tk.Frame(self.notebook, bg=c["BG"])
        self.notebook.add(tab_auto_tracking, text="  Auto Track  ")
        self.tab_auto_tracking_ref = tab_auto_tracking
        self._build_auto_tracking_tab(tab_auto_tracking)

        # ─── Tab: Automatic Trading Bot ─────────────────────────────────────
        tab_auto_bot = tk.Frame(self.notebook, bg=c["BG"])
        self.notebook.add(tab_auto_bot, text="  Auto Bot  ")
        self.tab_auto_bot_ref = tab_auto_bot
        self._build_auto_bot_tab(tab_auto_bot)

        # ─── System status bar ───────────────────────────────────────────────
        self.status_bar = tk.Frame(self.root, bg=c["BORDER"], height=24)
        self.status_bar.pack(fill="x", padx=12, pady=(0, 8))
        self.status_bar.pack_propagate(False)
        self.lbl_tracking_status = tk.Label(self.status_bar, text="Collection: —", fg=c["FG_DIM"], bg=c["BORDER"], font=("Consolas", 8))
        self.lbl_tracking_status.pack(side="left", padx=8, pady=2)
        self.lbl_bot_status = tk.Label(self.status_bar, text="Bot: —", fg=c["FG_DIM"], bg=c["BORDER"], font=("Consolas", 8))
        self.lbl_bot_status.pack(side="left", padx=8, pady=2)
        self.lbl_connection_status = tk.Label(self.status_bar, text="Connection: —", fg=c["FG_DIM"], bg=c["BORDER"], font=("Consolas", 8))
        self.lbl_connection_status.pack(side="left", padx=8, pady=2)

    def _build_auto_tracking_tab(self, parent):
        _, content = self._make_tab_scroll_area(parent)
        c = self.colors
        top_f = make_frame(
            content,
            "BROWSER TRADE COLLECTION",
            hint="Receiver runs with this app. Turn Collection ON to save only trades that close while it is ON — nothing from past Pocket Option history.",
            colors=c,
        )
        top_f.pack(fill="x", padx=16, pady=6)
        row1 = tk.Frame(top_f, bg=c["BG_FRAME"])
        row1.pack(fill="x", padx=12, pady=4)
        self.lbl_receiver_status = tk.Label(row1, text="Receiver: running on port 5051", fg=c["PROFIT"], bg=c["BG_FRAME"], font=("Consolas", 10))
        self.lbl_receiver_status.pack(anchor="w", pady=(0, 4))

        row2 = tk.Frame(top_f, bg=c["BG_FRAME"])
        row2.pack(fill="x", padx=12, pady=4)
        self.collection_var = tk.BooleanVar(value=False)
        self.collection_toggle_btn = tk.Checkbutton(
            row2,
            text="Collection ON — save new trades from Pocket Option",
            variable=self.collection_var,
            fg=c["FG_WHITE"],
            bg=c["BG_FRAME"],
            selectcolor=c["BG"],
            activebackground=c["BG_FRAME"],
            activeforeground=c["FG_WHITE"],
            font=("Consolas", 10, "bold"),
            command=self._on_collection_toggle,
            cursor="hand2",
        )
        self.collection_toggle_btn.pack(side="left", padx=(0, 12))
        self.lbl_collection_status_val = tk.Label(row2, text="OFF", fg=c["LOSS"], bg=c["BG_FRAME"], font=("Consolas", 10, "bold"))
        self.lbl_collection_status_val.pack(side="left")

        hint = tk.Label(
            top_f,
            text="Stays ON/OFF until you change it (saved). Each time you switch OFF→ON starts a new session so old list rows are not imported.",
            fg=c["FG_DIM"],
            bg=c["BG_FRAME"],
            font=("Consolas", 8),
            wraplength=420,
            justify="left",
        )
        hint.pack(anchor="w", padx=12, pady=(0, 8))

        dash_f = make_frame(content, "SESSION (BROWSER)", hint="Counts trades saved from the helper with Collection ON.", colors=c)
        dash_f.pack(fill="x", padx=16, pady=6)
        self.lbl_trades_today_val = tk.Label(dash_f, text="Browser trades today: 0", fg=c["FG_WHITE"], bg=c["BG_FRAME"], font=("Consolas", 10))
        self.lbl_trades_today_val.pack(anchor="w", padx=12, pady=2)
        self.lbl_last_trade_val = tk.Label(dash_f, text="Last browser trade: —", fg=c["FG_WHITE"], bg=c["BG_FRAME"], font=("Consolas", 10))
        self.lbl_last_trade_val.pack(anchor="w", padx=12, pady=2)
        self.lbl_session_anchor = tk.Label(dash_f, text="Session started (UTC): —", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9))
        self.lbl_session_anchor.pack(anchor="w", padx=12, pady=(2, 8))

        act_f = make_frame(content, "ACTIVITY", hint="", colors=c)
        act_f.pack(fill="x", padx=16, pady=6)
        act_container = tk.Frame(act_f, bg=c["BG_FRAME"])
        act_container.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        scroll_act = tk.Scrollbar(act_container)
        scroll_act.pack(side="right", fill="y")
        self.tracking_activity_text = tk.Text(act_container, height=5, wrap="word", bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], font=("Consolas", 8), yscrollcommand=scroll_act.set)
        self.tracking_activity_text.pack(side="left", fill="both", expand=True)
        scroll_act.config(command=self.tracking_activity_text.yview)

        self._load_collection_state_ui()
        self._append_tracking_activity(
            "Firefox helper → POST http://127.0.0.1:5051/trade-event — enable Collection above to record trades."
        )
        tut_wrap = make_frame(content, "AUTO TRACK TUTORIAL TAB", hint="Use this tab for in-depth instructions.", colors=c)
        tut_wrap.pack(fill="x", padx=16, pady=6)
        tut_nb = ttk.Notebook(tut_wrap)
        tut_nb.pack(fill="x", padx=12, pady=(4, 8))
        tut_tab = tk.Frame(tut_nb, bg=c["BG_FRAME"])
        tut_nb.add(tut_tab, text=" Tutorial ")
        self.tracking_tutorial_text = tk.Text(tut_tab, height=8, wrap="word", bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], font=("Consolas", 8))
        self.tracking_tutorial_text.pack(fill="both", expand=True, padx=8, pady=8)
        self.tracking_tutorial_text.insert(
            tk.END,
            "1) Start app. Receiver runs on http://127.0.0.1:5051\n"
            "2) Install trade logger userscript in Tampermonkey.\n"
            "3) Open Pocket Option in Firefox/Chrome, keep deals list visible.\n"
            "4) Turn Collection ON in this tab.\n"
            "5) Close a new trade and verify it appears in Activity/History.\n\n"
            "Troubleshooting:\n"
            "- If no trades appear: confirm script is enabled and page URL matches @match.\n"
            "- If old trades appear: toggle OFF then ON to start a fresh session anchor.\n"
            "- If mobile: configure relay in More tab and sync relay events.\n"
        )
        self.tracking_tutorial_text.config(state=tk.DISABLED)

    def _load_collection_state_ui(self):
        st = load_state()
        self.collection_var.set(bool(st.get("enabled")))
        self._update_collection_labels(st)

    def _update_collection_labels(self, st=None):
        st = st or load_state()
        c = self.colors
        on = bool(st.get("enabled"))
        self.lbl_collection_status_val.config(text="ON" if on else "OFF", fg=c["PROFIT"] if on else c["LOSS"])
        anchor = st.get("session_started_at_utc") or "—"
        self.lbl_session_anchor.config(text="Session anchor (UTC): %s" % anchor)
        # Status bar is built after Auto Track tab; avoid touching it during early UI init.
        if getattr(self, "lbl_tracking_status", None) is not None:
            self.lbl_tracking_status.config(text="Collection: %s" % ("ON" if on else "OFF"))

    def _on_collection_toggle(self):
        en = self.collection_var.get()
        st = set_collection_enabled(en, new_session=en)
        self._update_collection_labels(st)
        if en:
            self._append_tracking_activity(
                "Collection ON — new session started. Only trades that close from now on are saved (no backfill)."
            )
        else:
            self._append_tracking_activity("Collection OFF — helper events are ignored until you turn it on again.")
        self._refresh_browser_tracking_dashboard()
        self._update_status_bar()

    def _refresh_browser_tracking_dashboard(self):
        trades = load_trades()
        today = datetime.now().strftime("%Y-%m-%d")
        browser_today = [t for t in trades if (t.get("source") or "").lower() == "browser" and t.get("date") == today]
        self.lbl_trades_today_val.config(text="Browser trades today: %d" % len(browser_today))
        last_b = None
        for t in reversed(trades):
            if (t.get("source") or "").lower() == "browser":
                last_b = t
                break
        if last_b:
            self.lbl_last_trade_val.config(
                text="Last browser trade: %s %s %s" % (last_b.get("asset", ""), last_b.get("result", ""), last_b.get("time", ""))
            )
        else:
            self.lbl_last_trade_val.config(text="Last browser trade: —")
        self._update_collection_labels()

    def _append_tracking_activity(self, msg):
        self.tracking_activity_text.insert(tk.END, msg + "\n")
        self.tracking_activity_text.see(tk.END)

    def _build_auto_bot_tab(self, parent):
        _, content = self._make_tab_scroll_area(parent)
        c = self.colors
        top_f = make_frame(
            content,
            "AUTOMATIC TRADING BOT",
            hint="30s OTC basket. Demo/Live matches your PO site toggle (app cannot switch PO account). Live needs relay + executor; select each signaled pair on PO — script only clicks trade controls.",
            colors=c,
        )
        top_f.pack(fill="x", padx=16, pady=6)
        row1 = tk.Frame(top_f, bg=c["BG_FRAME"])
        row1.pack(fill="x", padx=12, pady=4)
        self.bot_toggle_var = tk.BooleanVar(value=False)
        self.bot_toggle_btn = tk.Checkbutton(row1, text="Enable Automatic Trading Bot", variable=self.bot_toggle_var, fg=c["FG_WHITE"], bg=c["BG_FRAME"], selectcolor=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"], font=("Consolas", 10), command=self._on_bot_toggle, cursor="hand2")
        self.bot_toggle_btn.pack(side="left", padx=(0, 12))
        self.lbl_bot_status_val = tk.Label(row1, text="Stopped", fg=c["LOSS"], bg=c["BG_FRAME"], font=("Consolas", 10, "bold"))
        self.lbl_bot_status_val.pack(side="left")
        tk.Label(
            top_f,
            text="Set options below, click Apply bot settings, then enable the bot. Start always uses the last Applied settings (saved file), not unsaved edits.",
            fg=c["FG_DIM"],
            bg=c["BG_FRAME"],
            font=("Consolas", 8),
            wraplength=420,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        dash_f = make_frame(content, "BOT DASHBOARD", hint="", colors=c)
        dash_f.pack(fill="x", padx=16, pady=6)
        self.lbl_bot_trades_today = tk.Label(dash_f, text="Trades executed today: 0", fg=c["FG_WHITE"], bg=c["BG_FRAME"], font=("Consolas", 10))
        self.lbl_bot_trades_today.pack(anchor="w", padx=12, pady=2)
        self.lbl_bot_session_pnl = tk.Label(dash_f, text="Session P/L: 0", fg=c["FG_WHITE"], bg=c["BG_FRAME"], font=("Consolas", 10))
        self.lbl_bot_session_pnl.pack(anchor="w", padx=12, pady=2)
        self.lbl_bot_last_trade = tk.Label(dash_f, text="Last executed trade: —", fg=c["FG_WHITE"], bg=c["BG_FRAME"], font=("Consolas", 10))
        self.lbl_bot_last_trade.pack(anchor="w", padx=12, pady=(2, 8))

        act_f = make_frame(content, "BOT ACTIVITY LOG", hint="", colors=c)
        act_f.pack(fill="x", padx=16, pady=6)
        act_container = tk.Frame(act_f, bg=c["BG_FRAME"])
        act_container.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        scroll_bot = tk.Scrollbar(act_container)
        scroll_bot.pack(side="right", fill="y")
        self.bot_activity_text = tk.Text(act_container, height=5, wrap="word", bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], font=("Consolas", 8), yscrollcommand=scroll_bot.set)
        self.bot_activity_text.pack(side="left", fill="both", expand=True)
        scroll_bot.config(command=self.bot_activity_text.yview)

        set_f = make_frame(
            content,
            "BOT SETTINGS",
            hint="Easy: core bot + relay. Advanced: optional risk/timing/paper sim — scroll inside Advanced, or turn off custom advanced to use built-in defaults.",
            colors=c,
        )
        set_f.pack(fill="both", expand=True, padx=16, pady=6)
        self.bot_paper_var = tk.BooleanVar(value=True)
        self.bot_live_enabled_var = tk.BooleanVar(value=False)
        self.bot_random_delay_var = tk.BooleanVar(value=False)
        self.bot_fail_safe_var = tk.BooleanVar(value=True)
        self.bot_advanced_custom_var = tk.BooleanVar(value=True)
        settings_tabs = ttk.Notebook(set_f)
        settings_tabs.pack(fill="both", expand=True, padx=12, pady=(4, 8))
        easy_tab = tk.Frame(settings_tabs, bg=c["BG_FRAME"])
        adv_tab = tk.Frame(settings_tabs, bg=c["BG_FRAME"])
        settings_tabs.add(easy_tab, text=" Easy ")
        settings_tabs.add(adv_tab, text=" Advanced ")

        tk.Checkbutton(easy_tab, text="Paper trading mode", variable=self.bot_paper_var, fg=c["FG_DIM"], bg=c["BG_FRAME"], selectcolor=c["BG"], activebackground=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=2)
        tk.Checkbutton(easy_tab, text="Enable live execution (relay + executor userscript)", variable=self.bot_live_enabled_var, fg=c["FG_DIM"], bg=c["BG_FRAME"], selectcolor=c["BG"], activebackground=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=2)
        tk.Label(
            easy_tab,
            text="Pocket Option account (label only — switch Demo/Live on pocketoption.com to match):",
            fg=c["FG_DIM"],
            bg=c["BG_FRAME"],
            font=("Consolas", 9),
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(4, 0))
        self.bot_pocket_account_var = tk.StringVar(value="demo")
        acc_row = tk.Frame(easy_tab, bg=c["BG_FRAME"])
        acc_row.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Radiobutton(acc_row, text="Demo (practice)", variable=self.bot_pocket_account_var, value="demo", fg=c["FG_DIM"], bg=c["BG_FRAME"], selectcolor=c["BG"], activebackground=c["BG_FRAME"], font=("Consolas", 9)).pack(side=tk.LEFT, padx=(0, 16))
        tk.Radiobutton(acc_row, text="Live (real funds)", variable=self.bot_pocket_account_var, value="live", fg=c["LOSS"], bg=c["BG_FRAME"], selectcolor=c["BG"], activebackground=c["BG_FRAME"], font=("Consolas", 9)).pack(side=tk.LEFT)
        tk.Label(
            easy_tab,
            text="OTC basket (paper: leans toward better simulated scores; live: round-robin). On PO, open the pair that matches each queued order before Buy.",
            fg=c["FG_DIM"],
            bg=c["BG_FRAME"],
            font=("Consolas", 8),
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(2, 4))
        tk.Label(easy_tab, text="Symbols (comma-separated, Pocket Option OTC names):", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_otc_symbols = tk.Entry(easy_tab, width=64, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_otc_symbols.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(easy_tab, text="Strategy amount:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_strategy_amount = tk.Entry(easy_tab, width=8, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_strategy_amount.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(
            easy_tab,
            text="Signal interval (sec) — use ≥35 so 30s trades don’t overlap:",
            fg=c["FG_DIM"],
            bg=c["BG_FRAME"],
            font=("Consolas", 9),
        ).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_strategy_interval = tk.Entry(easy_tab, width=8, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_strategy_interval.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(easy_tab, text="Max trades per session:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_max_session = tk.Entry(easy_tab, width=8, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_max_session.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(easy_tab, text="Relay URL (for bot queue):", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_relay_url = tk.Entry(easy_tab, width=48, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_relay_url.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(easy_tab, text="Relay user key:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_relay_user_key = tk.Entry(easy_tab, width=24, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_relay_user_key.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(easy_tab, text="Relay token (optional):", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_relay_token = tk.Entry(easy_tab, width=24, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_relay_token.pack(anchor="w", padx=12, pady=(0, 8))

        adv_hdr = tk.Frame(adv_tab, bg=c["BG_FRAME"])
        adv_hdr.pack(fill="x", padx=8, pady=(4, 2))
        tk.Checkbutton(
            adv_hdr,
            text="Use custom advanced (risk, timing, paper win-band, fail-safe)",
            variable=self.bot_advanced_custom_var,
            fg=c["FG_WHITE"],
            bg=c["BG_FRAME"],
            selectcolor=c["BG"],
            activebackground=c["BG_FRAME"],
            font=("Consolas", 9),
            command=self._on_bot_advanced_custom_toggle,
            cursor="hand2",
        ).pack(anchor="w")
        tk.Label(
            adv_tab,
            text="Off = built-in defaults for the fields below (Easy tab still controls relay & core strategy).",
            fg=c["FG_DIM"],
            bg=c["BG_FRAME"],
            font=("Consolas", 8),
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 4))

        adv_scroll_outer = tk.Frame(adv_tab, bg=c["BG_FRAME"])
        adv_scroll_outer.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self._adv_bot_canvas = tk.Canvas(adv_scroll_outer, bg=c["BG_FRAME"], highlightthickness=0, height=300)
        adv_scroll = tk.Scrollbar(adv_scroll_outer, orient="vertical", command=self._adv_bot_canvas.yview)
        self._adv_bot_scrollable = tk.Frame(self._adv_bot_canvas, bg=c["BG_FRAME"])
        self._adv_bot_canvas_win = self._adv_bot_canvas.create_window((0, 0), window=self._adv_bot_scrollable, anchor="nw")

        def _adv_inner_configure(_event=None):
            self._adv_bot_canvas.configure(scrollregion=self._adv_bot_canvas.bbox("all"))

        def _adv_canvas_configure(event):
            self._adv_bot_canvas.itemconfig(self._adv_bot_canvas_win, width=event.width)

        self._adv_bot_scrollable.bind("<Configure>", _adv_inner_configure)
        self._adv_bot_canvas.bind("<Configure>", _adv_canvas_configure)
        self._adv_bot_canvas.configure(yscrollcommand=adv_scroll.set)
        self._adv_bot_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        adv_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def _adv_mousewheel(event):
            br = self._adv_bot_canvas.bbox("all")
            if br and br[3] > 1:
                self._adv_bot_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self._adv_bot_canvas.bind("<MouseWheel>", _adv_mousewheel)
        self._adv_bot_scrollable.bind("<MouseWheel>", _adv_mousewheel)

        sc = self._adv_bot_scrollable
        tk.Label(sc, text="Max trades per minute:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_max_minute = tk.Entry(sc, width=8, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_max_minute.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(sc, text="Max risk per trade:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_max_risk = tk.Entry(sc, width=8, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_max_risk.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(sc, text="Max daily loss:", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_max_daily_loss = tk.Entry(sc, width=8, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_max_daily_loss.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(sc, text="Min time between trades (sec):", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_min_time = tk.Entry(sc, width=8, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_min_time.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(sc, text="Execution delay (sec):", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_exec_delay = tk.Entry(sc, width=8, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_exec_delay.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(sc, text="Signal jitter (sec):", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_jitter = tk.Entry(sc, width=8, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_jitter.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Checkbutton(sc, text="Randomized delay", variable=self.bot_random_delay_var, fg=c["FG_DIM"], bg=c["BG_FRAME"], selectcolor=c["BG"], activebackground=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=2)
        tk.Checkbutton(sc, text="Stop bot on broker error (fail-safe)", variable=self.bot_fail_safe_var, fg=c["FG_DIM"], bg=c["BG_FRAME"], selectcolor=c["BG"], activebackground=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=2)
        tk.Label(sc, text="Paper win rate min (0–1):", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_paper_win_min = tk.Entry(sc, width=8, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_paper_win_min.pack(anchor="w", padx=12, pady=(0, 4))
        tk.Label(sc, text="Paper win rate max (0–1):", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(4, 0))
        self.ent_bot_paper_win_max = tk.Entry(sc, width=8, bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], relief="solid", bd=1)
        self.ent_bot_paper_win_max.pack(anchor="w", padx=12, pady=(0, 8))

        tk.Button(set_f, text="Apply bot settings", fg=c["ACCENT"], bg=c["BG"], font=("Consolas", 9, "bold"), command=self._apply_bot_settings_ui, relief="flat", cursor="hand2").pack(anchor="w", padx=12, pady=(0, 8))
        wiz_row = tk.Frame(set_f, bg=c["BG_FRAME"])
        wiz_row.pack(fill="x", padx=12, pady=(0, 8))
        tk.Button(wiz_row, text="Wizard: Test relay", fg=c["FG_DIM"], bg=c["BG"], font=("Consolas", 9), command=self._wizard_test_bot_relay, relief="flat", cursor="hand2").pack(side="left", padx=(0, 8))
        tk.Button(wiz_row, text="Wizard: Queue test order", fg=c["FG_DIM"], bg=c["BG"], font=("Consolas", 9), command=self._wizard_queue_test_order, relief="flat", cursor="hand2").pack(side="left")

        tut_wrap = make_frame(content, "AUTO BOT TUTORIAL TAB", hint="Use this tab for in-depth instructions.", colors=c)
        tut_wrap.pack(fill="x", padx=16, pady=6)
        tut_nb = ttk.Notebook(tut_wrap)
        tut_nb.pack(fill="x", padx=12, pady=(4, 8))
        tut_tab = tk.Frame(tut_nb, bg=c["BG_FRAME"])
        tut_nb.add(tut_tab, text=" Tutorial ")
        self.bot_tutorial_text = tk.Text(tut_tab, height=9, wrap="word", bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"], font=("Consolas", 8))
        self.bot_tutorial_text.pack(fill="both", expand=True, padx=8, pady=8)
        self.bot_tutorial_text.insert(
            tk.END,
            "1) Set Demo/Live to match the account mode on pocketoption.com (the app cannot switch PO accounts).\n"
            "2) Configure relay URL + user key (+ token) on the Easy tab; run cloud_relay_server; Apply settings.\n"
            "3) Install Bot Executor userscript; keep PO open. For each queued asset, select that OTC pair on site (executor only clicks amount/direction/buy).\n"
            "4) Turn off paper trading and enable live execution: orders go to relay; executor userscript polls /relay/bot-orders.\n"
            "5) OTC basket rotates pairs; paper mode biases toward better simulated scores — not live profitability.\n"
            "6) History from the trade logger: desktop only accepts POSTs when Collection is ON (Auto Track).\n\n"
            "Safety:\n"
            "- Test paper bot + relay wizard first.\n"
            "- Live uses whichever PO account is open — verify demo vs live on the site.\n"
            "- Use max trades/session and daily loss limits.\n"
            "- Keep fail-safe ON to stop on relay errors.\n"
        )
        self.bot_tutorial_text.config(state=tk.DISABLED)

        self._bot_controller = None
        self._bot_broker = None
        self._load_bot_settings_ui()

    def _load_bot_settings_ui(self):
        s = load_bot_settings()
        self.bot_paper_var.set(s.get("paper_trading", True))
        self.bot_live_enabled_var.set(s.get("live_enabled", False))
        self.ent_bot_max_session.delete(0, tk.END)
        self.ent_bot_max_session.insert(0, str(s.get("max_trades_per_session", 0)))
        self.ent_bot_max_minute.delete(0, tk.END)
        self.ent_bot_max_minute.insert(0, str(s.get("max_trades_per_minute", 0)))
        self.ent_bot_max_risk.delete(0, tk.END)
        self.ent_bot_max_risk.insert(0, str(s.get("max_risk_per_trade", 0)))
        self.ent_bot_max_daily_loss.delete(0, tk.END)
        self.ent_bot_max_daily_loss.insert(0, str(s.get("max_daily_loss", 0)))
        self.ent_bot_min_time.delete(0, tk.END)
        self.ent_bot_min_time.insert(0, str(s.get("min_time_between_trades_sec", 0)))
        self.ent_bot_exec_delay.delete(0, tk.END)
        self.ent_bot_exec_delay.insert(0, str(s.get("execution_delay_sec", 0)))
        self.ent_bot_strategy_amount.delete(0, tk.END)
        self.ent_bot_strategy_amount.insert(0, str(s.get("strategy_amount", 1.0)))
        self.ent_bot_strategy_interval.delete(0, tk.END)
        self.ent_bot_strategy_interval.insert(0, str(s.get("strategy_interval_sec", 35.0)))
        self.ent_bot_jitter.delete(0, tk.END)
        self.ent_bot_jitter.insert(0, str(s.get("strategy_jitter_sec", 0.0)))
        self.ent_bot_paper_win_min.delete(0, tk.END)
        self.ent_bot_paper_win_min.insert(0, str(s.get("paper_win_rate_min", 0.68)))
        self.ent_bot_paper_win_max.delete(0, tk.END)
        self.ent_bot_paper_win_max.insert(0, str(s.get("paper_win_rate_max", 0.80)))
        self.ent_bot_relay_url.delete(0, tk.END)
        self.ent_bot_relay_url.insert(0, str(s.get("broker_relay_url", "")))
        self.ent_bot_relay_user_key.delete(0, tk.END)
        self.ent_bot_relay_user_key.insert(0, str(s.get("broker_relay_user_key", "")))
        self.ent_bot_relay_token.delete(0, tk.END)
        self.ent_bot_relay_token.insert(0, str(s.get("broker_relay_token", "")))
        pam = str(s.get("pocket_account_mode") or "demo").lower()
        self.bot_pocket_account_var.set(pam if pam in ("demo", "live") else "demo")
        syms = s.get("strategy_otc_symbols")
        if not isinstance(syms, list) or not syms:
            syms = list(_DEFAULT_BOT.get("strategy_otc_symbols", []))
        self.ent_bot_otc_symbols.delete(0, tk.END)
        self.ent_bot_otc_symbols.insert(0, ", ".join(str(x).strip() for x in syms if str(x).strip()))
        self.bot_random_delay_var.set(s.get("randomized_delay", False))
        self.bot_fail_safe_var.set(s.get("fail_safe_stop_on_broker_error", True))
        self.bot_advanced_custom_var.set(s.get("bot_advanced_custom", True))
        self._on_bot_advanced_custom_toggle()

    def _iter_adv_bot_tunable_widgets(self):
        for w in self._adv_bot_scrollable.winfo_children():
            stack = [w]
            while stack:
                cur = stack.pop()
                if isinstance(cur, (tk.Entry, tk.Checkbutton)):
                    yield cur
                stack.extend(cur.winfo_children())

    def _on_bot_advanced_custom_toggle(self):
        if not getattr(self, "_adv_bot_scrollable", None):
            return
        st = tk.NORMAL if self.bot_advanced_custom_var.get() else tk.DISABLED
        for w in self._iter_adv_bot_tunable_widgets():
            try:
                w.configure(state=st)
            except tk.TclError:
                pass
        if getattr(self, "_adv_bot_canvas", None):
            br = self._adv_bot_canvas.bbox("all")
            if br:
                self._adv_bot_canvas.configure(scrollregion=br)

    def _apply_bot_settings_ui(self):
        try:
            data = self._collect_bot_settings_from_ui()
        except ValueError as e:
            messagebox.showerror("Settings", "Invalid value: %s" % e)
            return
        save_bot_settings(data)
        if self._bot_controller and self.bot_toggle_var.get():
            ok = self._configure_bot_from_saved_settings(show_errors=True)
            if not ok:
                self._stop_bot()
                self.bot_toggle_var.set(False)
                return
        messagebox.showinfo("Settings", "Bot settings applied and saved. Start uses this saved profile.")

    def _collect_bot_settings_from_ui(self):
        custom_adv = self.bot_advanced_custom_var.get()
        d = dict(_DEFAULT_BOT)
        d["paper_trading"] = self.bot_paper_var.get()
        d["live_enabled"] = self.bot_live_enabled_var.get()
        d["max_trades_per_session"] = int(self.ent_bot_max_session.get() or 0)
        raw_syms = (self.ent_bot_otc_symbols.get() or "").strip()
        parts = [p.strip() for p in raw_syms.replace("\n", ",").split(",") if p.strip()]
        d["strategy_otc_symbols"] = parts if parts else list(_DEFAULT_BOT.get("strategy_otc_symbols", ["EURUSD_otc"]))
        d["strategy_amount"] = float(self.ent_bot_strategy_amount.get() or 1.0)
        d["strategy_interval_sec"] = float(self.ent_bot_strategy_interval.get() or 35.0)
        d["broker_relay_url"] = (self.ent_bot_relay_url.get() or "").strip()
        d["broker_relay_user_key"] = (self.ent_bot_relay_user_key.get() or "").strip()
        d["broker_relay_token"] = (self.ent_bot_relay_token.get() or "").strip()
        pam = str(self.bot_pocket_account_var.get() or "demo").strip().lower()
        d["pocket_account_mode"] = pam if pam in ("demo", "live") else "demo"
        d["bot_advanced_custom"] = custom_adv
        if custom_adv:
            d["max_trades_per_minute"] = int(self.ent_bot_max_minute.get() or 0)
            d["max_risk_per_trade"] = float(self.ent_bot_max_risk.get() or 0)
            d["max_daily_loss"] = float(self.ent_bot_max_daily_loss.get() or 0)
            d["min_time_between_trades_sec"] = float(self.ent_bot_min_time.get() or 0)
            d["execution_delay_sec"] = float(self.ent_bot_exec_delay.get() or 0)
            d["randomized_delay"] = self.bot_random_delay_var.get()
            d["strategy_jitter_sec"] = float(self.ent_bot_jitter.get() or 0.0)
            d["paper_win_rate_min"] = float(self.ent_bot_paper_win_min.get() or 0.68)
            d["paper_win_rate_max"] = float(self.ent_bot_paper_win_max.get() or 0.80)
            d["fail_safe_stop_on_broker_error"] = self.bot_fail_safe_var.get()
        return d

    def _ensure_bot_controller(self):
        if self._bot_controller is None:

            def on_status(s):
                self.root.after(0, lambda: self._update_bot_status(s))

            def on_activity(msg):
                self.root.after(0, lambda: self._append_bot_activity(msg))

            def on_metrics(d):
                self.root.after(0, lambda: self._update_bot_metrics(d))

            self._bot_controller = BotController(on_status=on_status, on_activity=on_activity, on_metrics=on_metrics)

    def _configure_bot_from_saved_settings(self, show_errors: bool) -> bool:
        """Apply strategy, engine, and relay broker from load_bot_settings(). Controller must exist."""
        self._ensure_bot_controller()
        settings = load_bot_settings()
        strategy = SessionPulseStrategy()
        syms = settings.get("strategy_otc_symbols")
        if not syms:
            syms = _DEFAULT_BOT.get("strategy_otc_symbols", ["EURUSD_otc"])
        strategy.set_config({
            "strategy_otc_symbols": syms,
            "amount": float(settings.get("strategy_amount", 1.0)),
            "interval_sec": float(settings.get("strategy_interval_sec", 35.0)),
            "jitter_sec": float(settings.get("strategy_jitter_sec", 0.0)),
            "direction_mode": settings.get("strategy_direction_mode", "alternate"),
        })
        self._bot_controller.set_strategy(strategy)
        self._bot_controller.apply_settings(settings)
        if self._bot_broker:
            try:
                self._bot_broker.disconnect()
            except Exception:
                pass
            self._bot_broker = None
        self._bot_controller.execution.set_broker(None)
        live_enabled = bool(settings.get("live_enabled", False))
        paper_mode = bool(settings.get("paper_trading", True))
        if live_enabled and not paper_mode:
            relay_url = str(settings.get("broker_relay_url", "") or "").strip()
            relay_user_key = str(settings.get("broker_relay_user_key", "") or "").strip()
            relay_token = str(settings.get("broker_relay_token", "") or "").strip()
            if not relay_url or not relay_user_key:
                if show_errors:
                    messagebox.showwarning(
                        "Bot",
                        "Live execution needs relay URL + user key in Advanced. Apply after filling both.",
                    )
                return False
            try:
                self._bot_broker = RelayQueueBroker(relay_url=relay_url, user_key=relay_user_key, relay_token=relay_token)
                ok = self._bot_broker.connect()
                if not ok:
                    raise RuntimeError("Relay connection failed")
                self._bot_controller.execution.set_broker(self._bot_broker)
                pam = str(settings.get("pocket_account_mode") or "demo")
                self._append_bot_activity(
                    "Relay connected (PO account label: %s). On PO, open the chart for each asset the bot signals; executor only clicks deal controls."
                    % pam
                )
            except Exception as e:
                self._bot_broker = None
                self._bot_controller.execution.set_broker(None)
                if settings.get("fail_safe_stop_on_broker_error", True):
                    if show_errors:
                        messagebox.showerror("Bot", "Could not connect broker for live execution: %s" % e)
                    return False
                self._append_bot_activity("Broker error, continuing paper mode: %s" % e)
        return True

    def _on_bot_toggle(self):
        if self.bot_toggle_var.get():
            self._start_bot()
        else:
            self._stop_bot()

    def _start_bot(self):
        self._ensure_bot_controller()
        ok = self._configure_bot_from_saved_settings(show_errors=True)
        if not ok:
            self.bot_toggle_var.set(False)
            return
        self._bot_controller.start()
        self._update_status_bar()

    def _stop_bot(self):
        if self._bot_controller:
            self._bot_controller.stop()
        if self._bot_broker:
            try:
                self._bot_broker.disconnect()
            except Exception:
                pass
            self._bot_broker = None
        self._update_bot_status("Stopped")
        self._update_status_bar()

    def _update_bot_status(self, status):
        self.lbl_bot_status_val.config(text=status)
        self.lbl_bot_status_val.config(fg=self.colors["PROFIT"] if status == "Running" else (self.colors["LOSS"] if status == "Error" else self.colors["FG_DIM"]))
        self.lbl_bot_status.config(text="Bot: %s" % status)

    def _append_bot_activity(self, msg):
        self.bot_activity_text.insert(tk.END, msg + "\n")
        self.bot_activity_text.see(tk.END)

    def _wizard_test_bot_relay(self):
        try:
            s = self._collect_bot_settings_from_ui()
            url = (s.get("broker_relay_url") or "").rstrip("/")
            if not url:
                messagebox.showwarning("Bot Wizard", "Enter relay URL first.")
                return
            req = urllib.request.Request(url + "/relay/health", headers={"Accept": "application/json"}, method="GET")
            token = (s.get("broker_relay_token") or "").strip()
            if token:
                req.add_header("X-Relay-Token", token)
            with urllib.request.urlopen(req, timeout=8) as resp:
                ok = resp.getcode() == 200
            if ok:
                self._append_bot_activity("Wizard: relay health check OK.")
                messagebox.showinfo("Bot Wizard", "Relay is reachable.")
            else:
                messagebox.showerror("Bot Wizard", "Relay health check failed.")
        except Exception as e:
            messagebox.showerror("Bot Wizard", "Relay test failed: %s" % e)

    def _wizard_queue_test_order(self):
        try:
            s = self._collect_bot_settings_from_ui()
            relay = RelayQueueBroker(
                relay_url=s.get("broker_relay_url", ""),
                user_key=s.get("broker_relay_user_key", ""),
                relay_token=s.get("broker_relay_token", ""),
            )
            if not relay.connect():
                raise RuntimeError("Relay connect failed")
            syms = s.get("strategy_otc_symbols") or _DEFAULT_BOT.get("strategy_otc_symbols", ["EURUSD_otc"])
            asset0 = syms[0] if isinstance(syms, list) and syms else "EURUSD_otc"
            r = relay.place_order(
                asset=asset0,
                amount=max(0.1, float(s.get("strategy_amount", 1.0))),
                direction="call",
                duration_sec=SessionPulseStrategy.DURATION_SEC,
                pocket_account_mode=str(s.get("pocket_account_mode") or "demo"),
            )
            if not r or not r.order_id:
                raise RuntimeError("Order queue failed")
            self._append_bot_activity("Wizard: queued test order %s" % r.order_id)
            messagebox.showinfo("Bot Wizard", "Test order queued.\nOrder ID: %s" % r.order_id)
        except Exception as e:
            messagebox.showerror("Bot Wizard", "Could not queue test order: %s" % e)

    def _update_bot_metrics(self, d):
        self.lbl_bot_trades_today.config(text="Trades executed today: %d" % d.get("trades_today", 0))
        self.lbl_bot_session_pnl.config(text="Session P/L: %.2f" % d.get("session_pnl", 0))
        last = d.get("last_trade")
        self.lbl_bot_last_trade.config(text="Last executed trade: %s" % (("%s %s" % (last.asset, last.amount) if last else "—")))
        self._update_status_bar()

    def _update_status_bar(self):
        st = load_state()
        self.lbl_tracking_status.config(text="Collection: %s" % ("ON" if st.get("enabled") else "OFF"))
        if self._bot_controller:
            self.lbl_bot_status.config(text="Bot: %s" % self._bot_controller.engine.get_status())
        else:
            self.lbl_bot_status.config(text="Bot: —")
        self.lbl_connection_status.config(text="Receiver: OK (5051)")

    # (Pocket Option SSID connect/test helpers removed from tracking tab)

    def _browse_sync_file(self):
        path = filedialog.asksaveasfilename(
            title="Choose sync file (e.g. in Drive or OneDrive folder)",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            initialfile="otc_tracker_sync.json",
        )
        if path:
            self.ent_sync_path.delete(0, tk.END)
            self.ent_sync_path.insert(0, path)

    def _save_sync_path(self):
        set_sync_file_path(self.ent_sync_path.get().strip())
        messagebox.showinfo("Sync path", "Path saved.")

    def _upload_sync(self):
        path = (self.ent_sync_path.get() or get_sync_file_path()).strip()
        if not path:
            messagebox.showwarning("Upload", "Set the sync file path first (e.g. a file in your Google Drive or OneDrive folder), then click Save path.")
            return
        try:
            export_to_sync_file(path)
            messagebox.showinfo("Upload", "Data written to sync file.\nIf the file is in a Drive/OneDrive folder, it will sync to the cloud.")
        except Exception as e:
            messagebox.showerror("Upload", str(e))

    def _download_sync(self):
        path = (self.ent_sync_path.get() or get_sync_file_path()).strip()
        if not path:
            messagebox.showwarning("Download", "Set the sync file path first, then click Save path.")
            return
        try:
            updated = import_from_sync_file(path)
            self.refresh_dashboard()
            self._refresh_history()
            self._apply_theme()
            msg = "Data loaded from sync file."
            if updated:
                msg += "\nLast updated: " + updated
            messagebox.showinfo("Download", msg)
        except FileNotFoundError:
            messagebox.showwarning("Download", "Sync file not found. Upload from another device first or check the path.")
        except Exception as e:
            messagebox.showerror("Download", str(e))

    def _save_update_url(self):
        set_update_check_url(self.ent_update_url.get().strip())
        messagebox.showinfo("Update URL", "URL saved.")

    def _check_for_update(self):
        url = (self.ent_update_url.get() or get_update_check_url()).strip()
        if not url:
            messagebox.showinfo("Check for update", "Enter the URL to your version.json (e.g. from GitHub raw or a web server), then click Check for update.")
            return
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OTC-Tracker-Desktop/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            remote_version = (data.get("version") or "").strip()
            download_url = (data.get("url") or "").strip()
            notes = (data.get("notes") or "").strip()
            if not remote_version:
                messagebox.showwarning("Check for update", "version.json did not contain a 'version' field.")
                return
            if version_newer(remote_version, APP_VERSION):
                msg = "Update available: v{}\n\n{}".format(remote_version, notes) if notes else "Update available: v{}".format(remote_version)
                if download_url:
                    msg += "\n\nOpen download link?"
                result = messagebox.askyesno("Update available", msg) if download_url else messagebox.showinfo("Update available", msg)
                if result and download_url:
                    import webbrowser
                    webbrowser.open(download_url)
            else:
                messagebox.showinfo("Check for update", "You're on the latest version (v{}).".format(APP_VERSION))
        except urllib.error.URLError as e:
            messagebox.showerror("Check for update", "Could not reach the update URL.\n\n{}".format(str(e)))
        except json.JSONDecodeError as e:
            messagebox.showerror("Check for update", "Invalid JSON from update URL.\n\n{}".format(str(e)))
        except Exception as e:
            messagebox.showerror("Check for update", str(e))

    def _filter_currency_list(self):
        q = self.currency_search_var.get().strip().upper()
        if not q:
            self._refresh_currency_listbox()
            return
        filtered = [(code, name) for code, name in CURRENCIES if q in code.upper() or q in name.upper()]
        self.currency_listbox.delete(0, tk.END)
        for code, name in filtered:
            self.currency_listbox.insert(tk.END, "{} – {}".format(code, name))

    def _refresh_currency_listbox(self):
        self.currency_listbox.delete(0, tk.END)
        for s in self._currency_display_list:
            self.currency_listbox.insert(tk.END, s)

    def _on_currency_select(self, event):
        sel = self.currency_listbox.curselection()
        if not sel:
            return
        line = (self.currency_listbox.get(sel[0]) or "").strip()
        idx = line.split()[0].upper() if line else ""
        if idx in self._currency_codes:
            set_currency(idx)
            self.lbl_current_currency.config(text=idx)
            self._update_currency_labels()
            self.refresh_dashboard()

    def _update_currency_labels(self):
        code = get_currency()
        self.lbl_goal_currency.config(text="Target ({}):".format(code))
        self.lbl_amount_currency.config(text="Amount ({}):".format(code))

    def _refresh_history(self):
        """Reload and display trade history (all or today only), with daily dividers."""
        for i in self.history_tree.get_children():
            self.history_tree.delete(i)
        self._all_trades = load_trades()
        today = datetime.now().strftime("%Y-%m-%d")
        if self.history_filter.get() == "today":
            pairs = [(i, t) for i, t in enumerate(self._all_trades) if t.get("date") == today]
        else:
            pairs = list(enumerate(self._all_trades))
        pairs.sort(key=lambda x: (x[1].get("date") or "", x[1].get("time") or ""))

        last_date = None
        for i, t in pairs:
            d = t.get("date") or ""
            if d != last_date:
                last_date = d
                self.history_tree.insert(
                    "",
                    "end",
                    iid="div_%s" % d.replace("-", "_"),
                    values=("── %s ──" % d, "", "", "", "", ""),
                    tags=("divider",),
                )
            result = t.get("result", "")
            tag = "win" if result.upper() == "W" else "loss"
            src = (t.get("source") or "").strip().lower()
            if src == "browser":
                sl = "B"
            elif src == "manual":
                sl = "M"
            else:
                sl = (src[:3] or "?").upper()
            self.history_tree.insert(
                "",
                "end",
                iid="t_%d" % i,
                values=(
                    t.get("date", ""),
                    t.get("time", ""),
                    t.get("amount", ""),
                    t.get("asset", ""),
                    result,
                    sl,
                ),
                tags=(tag,),
            )
        self.history_tree.tag_configure("win", foreground=self.colors["PROFIT"])
        self.history_tree.tag_configure("loss", foreground=self.colors["LOSS"])
        self.history_tree.tag_configure("divider", foreground=self.colors["FG_DIM"])

    def _clear_selected_trades(self):
        """Remove selected trade rows from the CSV (skips daily divider rows)."""
        sel = self.history_tree.selection()
        if not sel:
            messagebox.showinfo("Clear selected", "Select one or more trade rows (not the date dividers), then click Clear selected.")
            return
        indices = []
        for iid in sel:
            if str(iid).startswith("div_"):
                continue
            if str(iid).startswith("t_"):
                try:
                    indices.append(int(str(iid).split("_", 1)[1]))
                except ValueError:
                    continue
        if not indices:
            messagebox.showinfo("Clear selected", "Select trade rows only (not the ── date ── lines).")
            return
        if not messagebox.askyesno("Clear selected", "Remove %d selected trade(s) from the journal? This cannot be undone." % len(indices)):
            return
        self._all_trades = load_trades()
        for idx in sorted(set(indices), reverse=True):
            if 0 <= idx < len(self._all_trades):
                self._all_trades.pop(idx)
        overwrite_trades(self._all_trades)
        self._refresh_history()
        self.refresh_dashboard()
        self._refresh_browser_tracking_dashboard()

    def _delete_today_trades(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if not messagebox.askyesno("Delete today", "Remove ALL trades dated %s from the journal?" % today):
            return
        n = delete_trades_for_date(today)
        self._refresh_history()
        self.refresh_dashboard()
        self._refresh_browser_tracking_dashboard()
        messagebox.showinfo("Delete today", "Removed %d trade(s)." % n)

    def _wipe_trades_journal(self):
        """Clear trades CSV and browser collection state only — keeps theme, currency, daily goal, relay/bot config, sync paths."""
        if not messagebox.askyesno(
            "Clear journal",
            "Remove every trade from the history CSV and reset browser Collection state?\n\n"
            "Keeps: theme, currency, daily goal, sync file path, update URL, automation/bot settings (automation_config.json).\n\n"
            "This cannot be undone.",
        ):
            return
        clear_trades_journal()
        self.collection_var.set(False)
        self._update_collection_labels()
        self._refresh_history()
        self.refresh_dashboard()
        self._refresh_browser_tracking_dashboard()
        self._update_status_bar()
        messagebox.showinfo("Clear journal", "Trades cleared. Collection reset to OFF. Your settings were not changed.")

    def _toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        set_theme(self.theme)
        self.colors = THEMES[self.theme].copy()
        self._apply_theme()
        self.theme_btn.config(text="Light" if self.theme == "dark" else "Dark")
        self.refresh_dashboard()

    def _apply_theme(self):
        c = self.colors
        self.root_ref.configure(bg=c["BG"])
        self.header_ref.configure(fg=c["ACCENT"], bg=c["BG"])
        self.sub_ref.configure(fg=c["FG_DIM"], bg=c["BG"])
        self.theme_btn.configure(fg=c["FG_DIM"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"])
        self.tab_dash_ref.configure(bg=c["BG"])
        self.tab_history_ref.configure(bg=c["BG"])
        self.tab_extras_ref.configure(bg=c["BG"])
        self.tab_auto_tracking_ref.configure(bg=c["BG"])
        self.tab_auto_bot_ref.configure(bg=c["BG"])
        for canvas, inner in getattr(self, "_tab_scroll_canvas_regions", []):
            canvas.configure(bg=c["BG"])
            inner.configure(bg=c["BG"])
        if hasattr(self, "status_bar"):
            self.status_bar.configure(bg=c["BORDER"])
            self.lbl_tracking_status.configure(fg=c["FG_DIM"], bg=c["BORDER"])
            self.lbl_bot_status.configure(fg=c["FG_DIM"], bg=c["BORDER"])
            self.lbl_connection_status.configure(fg=c["FG_DIM"], bg=c["BORDER"])
        for frame in (self.dash_ref, self.goal_f_ref, self.log_f_ref, self.tips_ref, self.hist_hint_ref, self.curr_f_ref, self.update_f_ref, self.sync_f_ref):
            frame.configure(bg=c["BG_FRAME"], highlightbackground=c["BORDER"])
        for frame in (self.goal_row_ref, self.mind_f_ref, self.log_btn_row_ref, self.curr_row_currency_ref, self.update_up_row_ref, self.sync_row_ref, self.sync_btn_row_ref):
            frame.configure(bg=c["BG_FRAME"])
        for w in (self.lbl_mali, self.lbl_winrate, self.lbl_trades, self.lbl_mindset, self.lbl_feedback):
            w.configure(fg=c["FG_WHITE"], bg=c["BG_FRAME"])
        self.lbl_goal_status.configure(fg=c["FG_DIM"], bg=c["BG_FRAME"])
        self.tips_label_ref.configure(fg=c["FG_DIM"], bg=c["BG_FRAME"])
        self.lbl_goal_currency.configure(fg=c["FG_DIM"], bg=c["BG_FRAME"])
        self.lbl_amount_currency.configure(fg=c["FG_DIM"], bg=c["BG_FRAME"])
        self.lbl_current_currency.configure(fg=c["ACCENT"], bg=c["BG_FRAME"])
        self.ent_goal.configure(bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"])
        self.ent_currency_search.configure(bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"])
        self.currency_listbox.configure(bg=c["BG_FRAME"], fg=c["FG_WHITE"], selectbackground=c["BORDER"])
        self.ent_amount.configure(bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"])
        self.ent_asset.configure(bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"])
        self.ent_update_url.configure(bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"])
        self.lbl_update_ver_ref.configure(fg=c["ACCENT"], bg=c["BG_FRAME"])
        self.btn_save_url_ref.configure(fg=c["FG_DIM"], bg=c["BG"])
        self.btn_check_update_ref.configure(fg=c["ACCENT"], bg=c["BG"])
        self.ent_sync_path.configure(bg=c["BG_FRAME"], fg=c["FG_WHITE"], insertbackground=c["FG_WHITE"])
        self.btn_browse_sync_ref.configure(fg=c["FG_DIM"], bg=c["BG"])
        self.btn_save_sync_path_ref.configure(fg=c["FG_DIM"], bg=c["BG"])
        self.btn_upload_sync_ref.configure(fg=c["PROFIT"], bg=c["BG"])
        self.btn_download_sync_ref.configure(fg=c["ACCENT"], bg=c["BG"])
        self.sync_inst_ref.configure(fg=c["FG_DIM"], bg=c["BG_FRAME"])
        self.r_w.configure(fg=c["PROFIT"], bg=c["BG_FRAME"], activebackground=c["BG_FRAME"], activeforeground=c["PROFIT"])
        self.r_l.configure(fg=c["LOSS"], bg=c["BG_FRAME"], activebackground=c["BG_FRAME"], activeforeground=c["LOSS"])
        self.hist_controls_ref.configure(bg=c["BG"])
        self.hist_container_ref.configure(bg=c["BG"])
        self.style.configure("Cyber.Horizontal.TProgressbar", troughcolor=c["BG_FRAME"], background=c["PROFIT"], bordercolor=c["BORDER"])
        self.style.configure("TEntry", fieldbackground=c["BG_FRAME"], foreground=c["FG_WHITE"])
        self.style.configure("TNotebook", background=c["BG"])
        self.style.configure("TNotebook.Tab", background=c["BG_FRAME"], foreground=c["FG_WHITE"])
        self.style.map("TNotebook.Tab", background=[("selected", c["BORDER"])])
        self.style.configure("Treeview", background=c["BG_FRAME"], foreground=c["FG_WHITE"], fieldbackground=c["BG_FRAME"])
        self.style.configure("Treeview.Heading", background=c["BORDER"], foreground=c["ACCENT"])
        self.style.map("Treeview", background=[("selected", c["BORDER"])])
        self._refresh_history()

    def refresh_dashboard(self):
        trades = load_trades()
        stats = session_stats(trades)
        goal = get_daily_goal()
        curr = get_currency()

        mali = stats["session_mali"]
        mali_fmt = format_amount(abs(mali), curr)
        mali_text = ("+ " + mali_fmt) if mali >= 0 else ("- " + mali_fmt)
        self.lbl_mali["text"] = "Session Mali: " + mali_text
        self.lbl_mali["fg"] = self.colors["PROFIT"] if mali >= 0 else self.colors["LOSS"]

        self.lbl_winrate["text"] = f"Win Rate: {stats['win_rate']:.1f}%"
        self.lbl_trades["text"] = f"Total Trades (Today): {stats['total_trades']}"

        mindset = mindset_status(stats, goal)
        self.lbl_mindset["text"] = mindset
        self.lbl_mindset["fg"] = self.colors["PROFIT"] if mindset in ("LOCKED IN", "DISCIPLINED", "GRINDING", "READY") else self.colors["LOSS"] if mindset in ("RESET MODE", "STAY COLD") else self.colors["FG_WHITE"]

        if goal > 0:
            pct = min(1.0, max(0.0, mali / goal)) * 100
            self.progress["value"] = pct
            self.lbl_goal_status["text"] = "Daily goal: {} / {} ({:.0f}%)".format(format_amount(mali, curr), format_amount(goal, curr), pct)
            if pct >= 100:
                self.style.configure("Cyber.Horizontal.TProgressbar", background="#00ff88" if self.theme == "dark" else "#00875a")
            else:
                self.style.configure("Cyber.Horizontal.TProgressbar", background=self.colors["PROFIT"])
        else:
            self.progress["value"] = 0
            self.lbl_goal_status["text"] = "Set a daily goal to track progress."
        self._update_currency_labels()

    def _on_set_goal(self):
        try:
            val = float(self.ent_goal.get().strip() or 0)
            if val < 0:
                val = 0
            set_daily_goal(val)
            self.refresh_dashboard()
        except ValueError:
            messagebox.showwarning("Invalid goal", "Enter a number for daily goal.")

    def _on_log_trade(self):
        try:
            amount = float(self.ent_amount.get().strip().replace(",", ".") or 0)
        except ValueError:
            messagebox.showwarning("Invalid amount", "Enter a number for trade amount.")
            return
        asset = self.ent_asset.get().strip() or "OTC"
        result = self.result_var.get().upper()[:1]

        append_trade(amount, asset, result)
        msg = feedback_message(result == "W")
        self.lbl_feedback["text"] = msg
        self.lbl_feedback["fg"] = self.colors["PROFIT"] if result == "W" else self.colors["LOSS"]
        self.ent_amount.delete(0, tk.END)
        self.refresh_dashboard()

    def _show_tips(self):
        """Show concise in-app guide and recommended future features."""
        msg = """WHAT'S WHAT
• Session dashboard — Today's P&L (Mali), win rate %, total trades. Mindset updates from your run (READY → STAY COLD / DISCIPLINED / LOCKED IN).
• Daily goal — Set target in R. Progress bar fills as session profit reaches it.
• Log trade — Amount (R), asset name, Win/Loss. Saves to trades.csv. History tab = full list.

WHERE DATA IS SAVED (this desktop app)
• Trades: saved to trades.csv in this folder (every log is appended; nothing is lost).
• Daily goal & theme: saved to config.json in this folder.
• Everything persists until you delete those files or the folder.

RECOMMENDED ADD-ONS (future)
• Best/worst streak — Consecutive wins or losses in session.
• Notes per trade — One-line note (e.g. setup) stored in CSV.
• Export — Export week/month to CSV or summary PDF.
• Hotkeys — Quick Win/Loss without mouse (e.g. Ctrl+W / Ctrl+L).
• Session timer — How long you've been trading today.
• Per-asset stats — Win rate and P&L broken down by asset.
• Loss limit alert — Warn or lock logging when daily loss hits a cap.
• Weekly/monthly view — Roll-up stats and simple charts.
• Backup/restore — One-click backup of trades.csv to dated file.
• Dark/light theme toggle — Keep cyberpunk or switch to light.
• Sound feedback — Short sound on Win vs Loss (optional).
• Mobile companion — Use tracker_mobile.html on your phone; export CSV to merge."""
        messagebox.showinfo("What's what / Ideas", msg)

    def run(self):
        self.root.mainloop()

    def _on_close(self):
        try:
            self._stop_bot()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    app = TradingTrackerApp()
    app.run()
