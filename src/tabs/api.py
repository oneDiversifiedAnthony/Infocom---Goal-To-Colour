# Copyright (c) 2026 oneDiversified.
#
#     ..---------.
#   ...         .--.
#  ............   .--            #+ -#.                              -#.  +### ##                +#
# ...........----  .-.           #+                                       #+                     +#
# --     --    --.  ++     -######+ -#  ##   +#  #####+  ####.-####- .# -########  +#####   #######
# --     --    --.  ++    -#-   -#+ -#  .#+ -#- ##---+#+ ##   -##+.  .#.  #+   ## +#+---## ##    ##
# .-     -------.  -+.    .##   +#+ -#   -#+#-  ##.      ##      .## .#   #+   ## -#+      +#-   ##
#  --.   ....     -+-       ######+ -#    ###    +####+  ##   -####+ .#.  #+   ##   #####   -######
#   .--.        -++
#      ------+++-
#
# This software, its source code, and all associated functions, scripts, and
# documentation are the proprietary and confidential property of oneDiversified.
#
# Unauthorized copying, distribution, modification, or disclosure of this software
# is strictly prohibited. This code is provided solely for internal use by authorized
# oneDiversified personnel and may not be shared, published, or distributed externally
# without explicit written permission from oneDiversified.
#
# Use of this software constitutes acceptance of your confidentiality, IP protection,
# and contractual obligations with oneDiversified.

"""API tab -- fetch live sports data from external endpoints with auto-refresh.

Orchestrates the sub-tabs (Raw, Tree, Table, Changes, Call Log) and handles
URL building, HTTP fetching, auto-refresh timing, and rate-limit display.
"""

import datetime
import json
import os
import tkinter as tk
from tkinter import ttk
import threading
import urllib.request
import urllib.error
import webbrowser

from src import scores as _scores_module
from src.tabs.api_raw import build_raw_subtab
from src.tabs.api_tree import build_tree_subtab
from src.tabs.api_table import build_table_subtab
from src.tabs.api_changes import build_changes_subtab
from src.tabs.api_calllog import build_calllog_subtab


DEFAULT_URL = "https://api.sportmonks.com/v3/football/livescores/inplay?api_token={{api_token}}&include=scores;participants;events;periods"
from src.config import CALL_LOG_DIR
CALL_LOG_ROTATE_MINUTES = 60
ENV_FILE = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, ".env")


def _load_env_token():
    """Load SPORTMONKS_API_TOKEN from .env file."""
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("SPORTMONKS_API_TOKEN="):
                    return line.split("=", 1)[1].strip()
    return os.environ.get("SPORTMONKS_API_TOKEN", "")


def _make_dot(colour, size=10):
    """Create a small square PhotoImage of the given colour."""
    img = tk.PhotoImage(width=size, height=size)
    img.put(colour, to=(0, 0, size, size))
    return img


def build_api_tab(notebook, status_bar=None):
    tab = tk.Frame(notebook)
    notebook.add(tab, text="API Livescore")

    # Holder for schedule fetch callback, set later by gui.py
    _fetch_schedule_cb = [None]
    # Holder for score-change callback: fn(team_name, home, away, home_score, away_score, prev_home, prev_away)
    _on_score_change_cb = [None]

    def set_fetch_schedule(cb):
        _fetch_schedule_cb[0] = cb

    def set_on_score_change(cb):
        _on_score_change_cb[0] = cb

    # Previous livescore snapshot for delta detection
    _prev_live_scores = [{}]

    os.makedirs(CALL_LOG_DIR, exist_ok=True)

    # ── URL ────────────────────────────────────────────────────────────
    url_frame = tk.Frame(tab)
    url_frame.pack(fill="x", padx=12, pady=(12, 4))
    tk.Label(url_frame, text="URL:", font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))
    url_var = tk.StringVar(value=DEFAULT_URL)
    tk.Entry(url_frame, textvariable=url_var, font=("Consolas", 9), width=70).pack(side="left", fill="x", expand=True)
    tk.Button(url_frame, text="SportMonks Dashboard", font=("Segoe UI", 9, "bold"),
              bg="#0066cc", fg="white", padx=8,
              command=lambda: webbrowser.open("https://my.sportmonks.com/login?redirect=dashboard")
              ).pack(side="right", padx=(8, 0))

    # ── API Token ──────────────────────────────────────────────────────
    token_frame = tk.Frame(tab)
    token_frame.pack(fill="x", padx=12, pady=4)
    tk.Label(token_frame, text="API Token:", font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))
    token_var = tk.StringVar(value=_load_env_token())
    tk.Entry(token_frame, textvariable=token_var, font=("Consolas", 9), width=50).pack(side="left", fill="x", expand=True)

    # ── Controls ───────────────────────────────────────────────────────
    ctrl_frame = tk.Frame(tab)
    ctrl_frame.pack(fill="x", padx=12, pady=(8, 4))

    status_label = tk.Label(ctrl_frame, text="", font=("Segoe UI", 9), fg="#888888")

    # why: mutable lists used because closures can't rebind nonlocal ints in nested tkinter callbacks
    auto_timer_id = [None]
    auto_progress_id = [None]
    auto_running = [False]
    auto_elapsed = [0]
    auto_interval = [0]

    def _build_url():
        url = url_var.get().strip()
        token = token_var.get().strip()
        return url.replace("{{api_token}}", token)

    # ── Rate limit state ──────────────────────────────────────────────
    RATE_LIMIT_TOTAL = 2500
    rate_flash_id = [None]
    rate_flash_visible = [True]
    # Call log file rotation: new file every 60 minutes, date/time stamped
    current_log_file = [None]
    current_log_hour = [None]

    def _get_call_log_file():
        """Return the current log file path, rotating every 60 minutes."""
        now = datetime.datetime.now()
        hour_key = now.strftime("%Y%m%d_%H")
        if hour_key != current_log_hour[0]:
            current_log_hour[0] = hour_key
            filename = f"callcounter_{now.strftime('%Y-%m-%d_%H%M')}.log"
            current_log_file[0] = os.path.join(CALL_LOG_DIR, filename)
        return current_log_file[0]

    def _append_call_log(remaining):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = _get_call_log_file()
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp}, tokens_remaining: {remaining}\n")
        except PermissionError:
            pass

    def _stop_rate_flash():
        if rate_flash_id[0]:
            tab.after_cancel(rate_flash_id[0])
            rate_flash_id[0] = None
        rate_flash_visible[0] = True

    def _rate_flash_tick():
        rate_flash_visible[0] = not rate_flash_visible[0]
        if rate_flash_visible[0]:
            rate_style.configure("Rate.Horizontal.TProgressbar", background="#ff0000")
        else:
            rate_style.configure("Rate.Horizontal.TProgressbar", background="#333333")
        rate_flash_id[0] = tab.after(500, _rate_flash_tick)

    def _update_rate_limit(data):
        if not isinstance(data, dict):
            return
        rl = data.get("rate_limit")
        if not isinstance(rl, dict):
            return

        remaining = rl.get("remaining", 0)
        resets_in = rl.get("resets_in_seconds", 0)

        _append_call_log(remaining)

        pct = (remaining / RATE_LIMIT_TOTAL) * 100

        rate_label.config(text=f"Rate Limit: {remaining}/{RATE_LIMIT_TOTAL}  ({pct:.1f}%)")
        minutes = resets_in // 60
        seconds = resets_in % 60
        rate_reset_label.config(text=f"Resets in {minutes}m {seconds}s")

        if resets_in > 0 and remaining > 0:
            max_interval = resets_in / remaining
            rate_max_speed_label.config(text=f"Max speed: 1 call every {max_interval:.1f}s")
        else:
            rate_max_speed_label.config(text="")

        rate_progress["value"] = pct
        _stop_rate_flash()
        if pct < 10:
            rate_style.configure("Rate.Horizontal.TProgressbar", background="#ff0000")
            _rate_flash_tick()
        elif pct < 25:
            rate_style.configure("Rate.Horizontal.TProgressbar", background="#ff0000")
        elif pct < 50:
            rate_style.configure("Rate.Horizontal.TProgressbar", background="#ff6600")
        else:
            rate_style.configure("Rate.Horizontal.TProgressbar", background="#28a745")

        if status_bar:
            status_bar.update_rate_limit(remaining, RATE_LIMIT_TOTAL, resets_in, api_ok=True)

        try:
            from src.tabs.webserver import update_state as _ws_update
            _ws_update(api_remaining=f"{remaining} / {RATE_LIMIT_TOTAL}")
        except ImportError:
            pass

    # ── Fetch logic ───────────────────────────────────────────────────
    # Coloured dot images for tab status (keep references to prevent GC)
    _dot_blue = _make_dot("#0066cc")
    _dot_green = _make_dot("#28a745")
    _dot_red = _make_dot("#ff0000")
    _dot_grey = _make_dot("#555555")

    def _set_tab_status(status):
        """Update the API Livescore tab dot colour."""
        dot = {"fetching": _dot_blue, "ok": _dot_green,
               "error": _dot_red}.get(status, _dot_grey)
        try:
            notebook.tab(tab, image=dot, text="API Livescore", compound="left")
        except Exception:
            pass

    def _fetch():
        final_url = _build_url()
        status_label.config(text="Fetching...", fg="#0066cc")
        _set_tab_status("fetching")
        raw_clear()

        def _do_request():
            try:
                req = urllib.request.Request(final_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                tab.after(0, lambda: _show_result(body))
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                msg = f"HTTP Error {e.code}: {e.reason}\n\n{body}"
                code = e.code
                tab.after(0, lambda: _show_error(msg, code))
            except Exception as e:
                msg = str(e)
                tab.after(0, lambda: _show_error(msg))

        threading.Thread(target=_do_request, daemon=True).start()

    def _parse_live_scores(data):
        """Extract per-fixture scores from livescores API response.

        Returns {fixture_id: {"home": str, "away": str, "home_score": int, "away_score": int}}
        """
        result = {}
        if not isinstance(data, dict):
            return result
        for fix in data.get("data", []):
            if not isinstance(fix, dict):
                continue
            fid = fix.get("id")
            if not fid:
                continue
            participants = fix.get("participants", [])
            home = away = ""
            if isinstance(participants, list):
                for p in participants:
                    if not isinstance(p, dict):
                        continue
                    meta = p.get("meta", {})
                    if isinstance(meta, dict):
                        if meta.get("location") == "home":
                            home = p.get("name", "")
                        elif meta.get("location") == "away":
                            away = p.get("name", "")
            home_goals = 0
            away_goals = 0
            has_score = False
            for sc in fix.get("scores", []):
                if not isinstance(sc, dict):
                    continue
                if sc.get("description") != "CURRENT":
                    continue
                sc_data = sc.get("score", {})
                if not isinstance(sc_data, dict):
                    continue
                g = sc_data.get("goals")
                if g is None or g == "":
                    continue
                has_score = True
                if sc_data.get("participant") == "home":
                    home_goals = int(g)
                elif sc_data.get("participant") == "away":
                    away_goals = int(g)
            if has_score:
                result[fid] = {
                    "home": home, "away": away,
                    "home_score": home_goals, "away_score": away_goals,
                }
        return result

    def _detect_score_changes(parsed):
        """Compare current livescores with previous snapshot, log and fire callbacks on changes."""
        current = _parse_live_scores(parsed)
        prev = _prev_live_scores[0]
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Empty data means no games in play — clear all live state
        if not current:
            _scores_module.clear_live_state()
            _prev_live_scores[0] = {}
            return

        # Always push latest live scores and events into the scores module
        for fid, cur in current.items():
            _scores_module.update_from_live(
                fid, cur["home"], cur["away"],
                cur["home_score"], cur["away_score"],
            )
        # Store events, state, and periods from each live fixture
        if isinstance(parsed, dict):
            for fix in parsed.get("data", []):
                if isinstance(fix, dict) and fix.get("id"):
                    fid = fix["id"]
                    events = fix.get("events", [])
                    if isinstance(events, list):
                        _scores_module.update_events(fid, events)
                    state_id = fix.get("state_id")
                    if state_id is not None:
                        _scores_module.update_state(fid, state_id)
                    periods = fix.get("periods", [])
                    if isinstance(periods, list):
                        _scores_module.update_periods(fid, periods)

        # Detect deltas
        for fid, cur in current.items():
            old = prev.get(fid)
            if old is None:
                continue  # first time seeing this fixture, no delta
            if cur["home_score"] != old["home_score"] or cur["away_score"] != old["away_score"]:
                # Score changed!
                entry = (
                    f"[{timestamp}] SCORE CHANGE: {cur['home']} vs {cur['away']}  "
                    f"{old['home_score']}-{old['away_score']} → "
                    f"{cur['home_score']}-{cur['away_score']}\n"
                )
                # Log to changes file
                changes_file = os.path.join(CALL_LOG_DIR, "changes.log")
                try:
                    with open(changes_file, "a", encoding="utf-8") as f:
                        f.write(entry)
                except PermissionError:
                    pass

                # Determine which team scored
                scoring_team = ""
                if cur["home_score"] > old["home_score"]:
                    scoring_team = cur["home"]
                elif cur["away_score"] > old["away_score"]:
                    scoring_team = cur["away"]

                if _on_score_change_cb[0] and scoring_team:
                    _on_score_change_cb[0](
                        scoring_team, cur["home"], cur["away"],
                        cur["home_score"], cur["away_score"],
                        old["home_score"], old["away_score"],
                    )

        _prev_live_scores[0] = current

    def _show_result(text):
        parsed = None
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass

        raw_update(parsed, text)
        tree_update(parsed, text)
        table_update(parsed)

        if parsed is not None:
            _update_rate_limit(parsed)
            changes_check(parsed)
            _detect_score_changes(parsed)

        status_label.config(text="OK", fg="#28a745")
        auto_style.configure("Auto.Horizontal.TProgressbar", background="#28a745")
        _set_tab_status("ok")

    def _show_error(msg, http_code=None):
        raw_error(msg)
        tree_error(msg)
        auto_style.configure("Auto.Horizontal.TProgressbar", background="#ff0000")
        if http_code == 429:
            status_label.config(text="Rate limited – retrying", fg="#ff6600")
        else:
            status_label.config(text="Error – retrying", fg="red")
        _set_tab_status("error")
        if status_bar:
            status_bar.rate_label.config(fg="#ff0000")

    # ── Get / Auto controls ───────────────────────────────────────────
    tk.Button(ctrl_frame, text="Get", font=("Segoe UI", 10, "bold"),
              bg="#0066cc", fg="white", padx=16, pady=2,
              command=_fetch).pack(side="left", padx=(0, 12))

    ttk.Separator(ctrl_frame, orient="vertical").pack(side="left", fill="y", padx=8)
    tk.Label(ctrl_frame, text="Auto every", font=("Segoe UI", 10)).pack(side="left", padx=(4, 4))
    interval_var = tk.IntVar(value=1500)
    tk.Spinbox(ctrl_frame, from_=100, to=60000, increment=100, textvariable=interval_var,
               font=("Consolas", 10), width=6, justify="center").pack(side="left")
    tk.Label(ctrl_frame, text="ms", font=("Segoe UI", 10)).pack(side="left", padx=(2, 8))

    def _start_auto():
        if auto_running[0]:
            return
        auto_running[0] = True
        auto_btn.config(text="Stop Auto", bg="#cc0000", command=_stop_auto)
        _auto_cycle()

    def _stop_auto():
        auto_running[0] = False
        if auto_timer_id[0]:
            tab.after_cancel(auto_timer_id[0])
            auto_timer_id[0] = None
        if auto_progress_id[0]:
            tab.after_cancel(auto_progress_id[0])
            auto_progress_id[0] = None
        progress["value"] = 0
        auto_btn.config(text="Auto Get", bg="#28a745", command=_start_auto)

    def _auto_cycle():
        if not auto_running[0]:
            return
        _fetch()
        interval_ms = max(100, interval_var.get())
        auto_interval[0] = interval_ms
        auto_elapsed[0] = 0
        progress["value"] = 0
        _tick_progress()
        auto_timer_id[0] = tab.after(interval_ms, _auto_cycle)

    def _tick_progress():
        if not auto_running[0]:
            return
        auto_elapsed[0] += 100
        pct = min(100, (auto_elapsed[0] / auto_interval[0]) * 100)
        progress["value"] = pct
        if auto_elapsed[0] < auto_interval[0]:
            auto_progress_id[0] = tab.after(100, _tick_progress)

    auto_btn = tk.Button(ctrl_frame, text="Auto Get", font=("Segoe UI", 10, "bold"),
                         bg="#28a745", fg="white", padx=12, pady=2,
                         command=_start_auto)
    auto_btn.pack(side="left", padx=4)

    status_label.pack(side="right", padx=8)

    # ── Auto countdown progress bar ──────────────────────────────────
    auto_style = ttk.Style()
    auto_style.configure("Auto.Horizontal.TProgressbar", troughcolor="#333333",
                         background="#0066cc")
    progress = ttk.Progressbar(tab, length=200, mode="determinate", maximum=100,
                               style="Auto.Horizontal.TProgressbar")
    progress.pack(fill="x", padx=12, pady=(4, 2))

    # ── Rate Limit ────────────────────────────────────────────────────
    rate_frame = tk.Frame(tab)
    rate_frame.pack(fill="x", padx=12, pady=(2, 2))
    rate_label = tk.Label(rate_frame, text="Rate Limit: --", font=("Segoe UI", 10, "bold"),
                          fg="#cc0000")
    rate_label.pack(side="left")
    rate_max_speed_label = tk.Label(rate_frame, text="", font=("Segoe UI", 9, "bold"), fg="#0066cc")
    rate_max_speed_label.pack(side="right", padx=(8, 0))
    rate_reset_label = tk.Label(rate_frame, text="", font=("Segoe UI", 9), fg="#888888")
    rate_reset_label.pack(side="right")

    rate_style = ttk.Style()
    rate_style.configure("Rate.Horizontal.TProgressbar", troughcolor="#333333",
                         background="#28a745")
    rate_progress = ttk.Progressbar(tab, length=200, mode="determinate", maximum=100,
                                    style="Rate.Horizontal.TProgressbar")
    rate_progress.pack(fill="x", padx=12, pady=(0, 6))

    # ── Results (sub-tabbed) ─────────────────────────────────────────
    result_notebook = ttk.Notebook(tab)
    result_notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # Build sub-tabs
    _, raw_update, raw_error, raw_clear = build_raw_subtab(result_notebook)
    _, tree_update, tree_error = build_tree_subtab(result_notebook)
    _, table_update = build_table_subtab(result_notebook)
    _, changes_check = build_changes_subtab(result_notebook, CALL_LOG_DIR)
    build_calllog_subtab(result_notebook, CALL_LOG_DIR, tab)

    # ── Auto-pull schedule every 15 minutes (at :00, :15, :30, :45) ──
    _last_schedule_quarter = [None]

    def _check_schedule_timer():
        now = datetime.datetime.now()
        quarter = now.minute // 15
        key = (now.hour, quarter)
        if key != _last_schedule_quarter[0]:
            _last_schedule_quarter[0] = key
            if _fetch_schedule_cb[0]:
                _fetch_schedule_cb[0]()
        tab.after(30_000, _check_schedule_timer)

    tab.after(5_000, _check_schedule_timer)

    return _start_auto, set_fetch_schedule, set_on_score_change, token_var
