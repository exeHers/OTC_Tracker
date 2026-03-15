#!/usr/bin/env python3
"""
OTC 5-Second Trading Tracker — GUI Edition (Underground Cyberpunk)
Native window. Same data as CLI (trades.csv, config.json).
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import json
import urllib.request
import urllib.error

# Reuse data layer from CLI tracker
from tracker import (
    ensure_files,
    load_trades,
    append_trade,
    overwrite_trades,
    clear_all_data,
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
from currencies import CURRENCIES, format_amount

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

        self._build_styles()
        self._build_ui()
        self.refresh_dashboard()

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

    def _build_ui(self):
        c = self.colors
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
        tab_history = tk.Frame(self.notebook, bg=c["BG"])
        self.notebook.add(tab_dash, text="  Dashboard  ")
        self.notebook.add(tab_history, text="  History  ")
        self.tab_dash_ref = tab_dash
        self.tab_history_ref = tab_history

        # ─── Tab 1: Dashboard ───────────────────────────────────────────────
        dash = make_frame(tab_dash, "SESSION DASHBOARD", hint="Today's P&L, win rate, and trade count. Mindset updates from your run.", colors=c)
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
        goal_f = make_frame(tab_dash, "DAILY GOAL", hint="Set a target (R). Bar fills as session profit reaches it.", colors=c)
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
        log_f = make_frame(tab_dash, "LOG TRADE", hint="Enter amount and asset, pick Win/Loss, then Log. Saves to trades.csv.", colors=c)
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
        btn_row = tk.Frame(tab_dash, bg=c["BG"])
        btn_row.pack(pady=(4, 2))
        tk.Button(btn_row, text="Refresh", fg=c["FG_DIM"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self.refresh_dashboard, relief="flat", cursor="hand2").pack(side="left", padx=2)
        tk.Button(btn_row, text="What's what?", fg=c["FG_DIM"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._show_tips, relief="flat", cursor="hand2").pack(side="left", padx=2)

        tips_frame = make_frame(tab_dash, "QUICK REFERENCE", hint="Session Mali = today's profit/loss. Mindset = READY / STAY COLD / DISCIPLINED / LOCKED IN from your stats.", colors=c)
        tips_frame.pack(fill="x", padx=16, pady=(0, 12))
        self.tips_ref = tips_frame
        self.tips_label_ref = tk.Label(tips_frame, text="Daily goal bar = progress to target. Log trade = record each 5-sec OTC trade to CSV. History tab = full trade list.", fg=c["FG_DIM"], bg=c["BG_FRAME"], font=("Consolas", 8), wraplength=400, justify="left")
        self.tips_label_ref.pack(anchor="w", padx=12, pady=(0, 8))

        # ─── Tab 2: History ───────────────────────────────────────────────
        hist_hint = make_frame(tab_history, "TRADE HISTORY", hint="All trades from CSV. Toggle Today only or All. Use Refresh to reload.", colors=c)
        hist_hint.pack(fill="x", padx=16, pady=(6, 2))
        self.hist_hint_ref = hist_hint

        hist_controls = tk.Frame(tab_history, bg=c["BG"])
        hist_controls.pack(fill="x", padx=16, pady=4)
        self.hist_controls_ref = hist_controls
        self.history_filter = tk.StringVar(value="all")
        tk.Radiobutton(hist_controls, text="All", variable=self.history_filter, value="all", fg=c["FG_DIM"], bg=c["BG"], selectcolor=c["BG_FRAME"], activebackground=c["BG"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._refresh_history).pack(side="left", padx=(0, 12))
        tk.Radiobutton(hist_controls, text="Today only", variable=self.history_filter, value="today", fg=c["FG_DIM"], bg=c["BG"], selectcolor=c["BG_FRAME"], activebackground=c["BG"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._refresh_history).pack(side="left")
        tk.Button(hist_controls, text="Refresh", fg=c["FG_DIM"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._refresh_history, relief="flat", cursor="hand2").pack(side="right")
        tk.Button(hist_controls, text="Clear selected", fg=c["FG_DIM"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["FG_WHITE"], font=("Consolas", 9), command=self._clear_selected_trades, relief="flat", cursor="hand2").pack(side="right", padx=(0, 8))
        tk.Button(hist_controls, text="Start fresh", fg=c["LOSS"], bg=c["BG"], activebackground=c["BG_FRAME"], activeforeground=c["LOSS"], font=("Consolas", 9), command=self._start_fresh, relief="flat", cursor="hand2").pack(side="right")

        hist_container = tk.Frame(tab_history, bg=c["BG"])
        hist_container.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.hist_container_ref = hist_container
        scroll = ttk.Scrollbar(hist_container)
        scroll.pack(side="right", fill="y")
        self.history_tree = ttk.Treeview(hist_container, columns=("date", "time", "amount", "asset", "result"), show="headings", height=14, yscrollcommand=scroll.set)
        for col, w in [("date", 90), ("time", 70), ("amount", 70), ("asset", 90), ("result", 50)]:
            self.history_tree.heading(col, text=col.capitalize())
            self.history_tree.column(col, width=w)
        self.history_tree.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.history_tree.yview)
        self._refresh_history()

        # ─── Tab 3: Extras (Currency) ───────────────────────────────────────
        tab_extras = tk.Frame(self.notebook, bg=c["BG"])
        self.notebook.add(tab_extras, text="  Extras  ")
        self.tab_extras_ref = tab_extras
        curr_f = make_frame(tab_extras, "CURRENCY", hint="Search and select your currency. Used for amounts and goals.", colors=c)
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
        update_f = make_frame(tab_extras, "CHECK FOR UPDATE", hint="Set the URL to a version.json (see version.json in this folder). Then click Check.", colors=c)
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
        sync_f = make_frame(tab_extras, "CLOUD SYNC (DRIVE / ONEDRIVE)", hint="", colors=c)
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
        idx = self.currency_listbox.get(sel[0]).split(" – ")[0]
        if len(idx) == 3 and idx in self._currency_codes:
            set_currency(idx)
            self.lbl_current_currency.config(text=idx)
            self._update_currency_labels()
            self.refresh_dashboard()

    def _update_currency_labels(self):
        code = get_currency()
        self.lbl_goal_currency.config(text="Target ({}):".format(code))
        self.lbl_amount_currency.config(text="Amount ({}):".format(code))

    def _refresh_history(self):
        """Reload and display trade history (all or today only)."""
        for i in self.history_tree.get_children():
            self.history_tree.delete(i)
        self._all_trades = load_trades()
        today = datetime.now().strftime("%Y-%m-%d")
        display = [t for t in self._all_trades if t.get("date") == today] if self.history_filter.get() == "today" else self._all_trades
        for t in display:
            result = t.get("result", "")
            tag = "win" if result.upper() == "W" else "loss"
            self.history_tree.insert("", "end", values=(
                t.get("date", ""),
                t.get("time", ""),
                t.get("amount", ""),
                t.get("asset", ""),
                result,
            ), tags=(tag,))
        self.history_tree.tag_configure("win", foreground=self.colors["PROFIT"])
        self.history_tree.tag_configure("loss", foreground=self.colors["LOSS"])

    def _clear_selected_trades(self):
        """Remove selected rows from the trade history (and from CSV)."""
        sel = self.history_tree.selection()
        if not sel:
            messagebox.showinfo("Clear selected", "Select one or more rows in the table, then click Clear selected.")
            return
        if not messagebox.askyesno("Clear selected", "Remove the selected trade(s) from history? This cannot be undone."):
            return
        to_remove = []
        for iid in sel:
            row = self.history_tree.item(iid, "values")
            if len(row) >= 5:
                to_remove.append({"date": row[0], "time": row[1], "amount": row[2], "asset": row[3], "result": row[4]})
        key = lambda t: (t.get("date"), t.get("time"), t.get("amount"), t.get("asset"), t.get("result"))
        remove_set = {key(r) for r in to_remove}
        self._all_trades = [t for t in self._all_trades if key(t) not in remove_set]
        overwrite_trades(self._all_trades)
        self._refresh_history()
        self.refresh_dashboard()

    def _start_fresh(self):
        """Clear all trades and reset config; confirm first."""
        if not messagebox.askyesno("Start fresh", "Clear ALL trades and reset daily goal & theme? This cannot be undone."):
            return
        clear_all_data()
        self.theme = "dark"
        self.colors = THEMES["dark"].copy()
        self._apply_theme()
        self.theme_btn.config(text="Light")
        self.lbl_current_currency.config(text=get_currency())
        self.ent_goal.delete(0, tk.END)
        self.ent_goal.insert(0, "0")
        self._update_currency_labels()
        self._refresh_history()
        self.refresh_dashboard()
        messagebox.showinfo("Start fresh", "All data cleared. App reset to default.")

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


if __name__ == "__main__":
    app = TradingTrackerApp()
    app.run()
