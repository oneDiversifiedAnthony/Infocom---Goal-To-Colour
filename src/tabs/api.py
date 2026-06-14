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


SCORES_URL = "https://api.sportmonks.com/v3/football/livescores/inplay?api_token={{api_token}}&include=scores;periods"
EVENTS_URL = "https://api.sportmonks.com/v3/football/livescores/inplay?api_token={{api_token}}&include=scores;participants;events;periods"
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

    # ── URLs ───────────────────────────────────────────────────────────
    url_frame = tk.Frame(tab)
    url_frame.pack(fill="x", padx=12, pady=(12, 2))
    tk.Label(url_frame, text="Scores URL:", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
    scores_url_var = tk.StringVar(value=SCORES_URL)
    tk.Entry(url_frame, textvariable=scores_url_var, font=("Consolas", 8), width=70).pack(side="left", fill="x", expand=True)
    tk.Button(url_frame, text="SportMonks Dashboard", font=("Segoe UI", 9, "bold"),
              bg="#0066cc", fg="white", padx=8,
              command=lambda: webbrowser.open("https://my.sportmonks.com/login?redirect=dashboard")
              ).pack(side="right", padx=(8, 0))

    url_frame2 = tk.Frame(tab)
    url_frame2.pack(fill="x", padx=12, pady=(0, 4))
    tk.Label(url_frame2, text="Events URL:", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
    events_url_var = tk.StringVar(value=EVENTS_URL)
    tk.Entry(url_frame2, textvariable=events_url_var, font=("Consolas", 8), width=70).pack(side="left", fill="x", expand=True)

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

    # Call counter for events URL rotation (events every Nth call)
    _call_counter = [0]

    def _build_scores_url():
        token = token_var.get().strip()
        return scores_url_var.get().strip().replace("{{api_token}}", token)

    def _build_events_url():
        token = token_var.get().strip()
        return events_url_var.get().strip().replace("{{api_token}}", token)

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

    _last_call_type = ["scores"]
    _prev_state_ids = {}  # {fixture_id: state_id} for detecting state changes

    def _append_call_log(remaining):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        call_type = _last_call_type[0]
        phase = _scores_module.get_poll_phase()
        log_file = _get_call_log_file()
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp}, tokens_remaining: {remaining}, call: {call_type}, phase: {phase}\n")
        except PermissionError:
            pass

    def _log_state_change(fixture_id, home, away, old_state_id, new_state_id):
        """Write a state change marker line to the call log."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        old_name = _scores_module.STATE_NAMES.get(old_state_id, str(old_state_id)) if old_state_id else "—"
        new_name = _scores_module.STATE_NAMES.get(new_state_id, str(new_state_id))
        log_file = _get_call_log_file()
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp}, STATE_CHANGE: {home} vs {away} [{old_name} -> {new_name}]\n")
        except PermissionError:
            pass

    def _log_goal(home, away, home_score, away_score, scoring_team):
        """Write a GOAL marker line to the call log."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = _get_call_log_file()
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp}, GOAL: {scoring_team} ({home} {home_score}-{away_score} {away})\n")
        except PermissionError:
            pass

    _seen_event_ids = set()  # track event IDs already logged

    def _log_new_events(fixture_id, home, away):
        """Log any new match events (cards, subs, etc.) to the call log."""
        events = _scores_module.get_events(fixture_id)
        if not events:
            return
        log_file = _get_call_log_file()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_lines = []
        for ev in events:
            eid = ev.get("id")
            if not eid or eid in _seen_event_ids:
                continue
            _seen_event_ids.add(eid)
            type_id = ev.get("type_id")
            minute = ev.get("minute", "")
            extra = ev.get("extra_minute")
            player = ev.get("player_name", "")
            min_str = f"{minute}'" if minute else ""
            if extra:
                min_str = f"{minute}+{extra}'"
            # Map type_id to label
            if type_id == 14:
                label = "GOAL"
            elif type_id == 19:
                label = "YELLOW_CARD"
            elif type_id == 20:
                label = "RED_CARD"
            elif type_id == 18:
                label = "SUBSTITUTION"
            else:
                label = f"EVENT_{type_id}"
            result = ev.get("result", "")
            detail = player
            if result:
                detail += f" ({result})"
            new_lines.append(
                f"{timestamp}, EVENT: {label} {min_str} {detail} [{home} vs {away}]\n"
            )
        if new_lines:
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.writelines(new_lines)
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

    # Minimum interval (ms) derived from rate limit -- enforced as a floor on all polling
    _rate_limit_floor_ms = [0]
    # Auto-tuned game rate: smoothed toward optimal to leave 3 tokens at reset
    _auto_game_rate_ms = [0]  # 0 = not yet calculated
    TOKEN_RESERVE = 3  # tokens to keep in reserve at reset
    RATE_SMOOTHING = 0.3  # blend factor: 0.3 = 30% new value, 70% old (smooth)
    # Burn mode: when game ends before rate limit resets, burn surplus tokens at 700ms
    BURN_INTERVAL_MS = 700
    _burn_mode = [False]
    _burn_tokens_available = [0]  # surplus tokens to burn

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
            max_interval_sec = resets_in / remaining
            floor_ms = int(max_interval_sec * 1000)
            _rate_limit_floor_ms[0] = floor_ms
            rate_max_speed_label.config(
                text=f"Max speed: 1/{max_interval_sec:.1f}s ({floor_ms}ms)")

            # Auto-tune game rate: phase-aware budgeting
            # Account for different polling rates in each upcoming phase
            # (1H playing, halftime break, 2H playing) instead of assuming
            # a single constant rate for the entire reset window.
            usable = remaining - TOKEN_RESERVE
            if usable > 0:
                segments = _scores_module.get_phase_time_segments()
                break_rate_ms = max(100, break_interval_var.get())

                if segments:
                    # Cap segments to the reset window
                    time_budget = resets_in
                    break_calls = 0
                    playing_secs = 0
                    for seg_phase, seg_secs in segments:
                        seg_secs = min(seg_secs, time_budget)
                        if seg_secs <= 0:
                            break
                        if seg_phase == _scores_module.PHASE_BREAK:
                            break_calls += seg_secs / (break_rate_ms / 1000)
                        else:
                            playing_secs += seg_secs
                        time_budget -= seg_secs
                        if time_budget <= 0:
                            break

                    # Tokens available for playing phases
                    playing_tokens = usable - int(break_calls)
                    if playing_tokens > 0 and playing_secs > 0:
                        optimal_ms = int((playing_secs / playing_tokens) * 1000)
                    else:
                        optimal_ms = int((resets_in / usable) * 1000)
                else:
                    # No segment info — fall back to simple calculation
                    optimal_ms = int((resets_in / usable) * 1000)

                optimal_ms = max(100, optimal_ms)  # never below 100ms
                # Smooth toward target to avoid jumpy adjustments
                if _auto_game_rate_ms[0] <= 0:
                    _auto_game_rate_ms[0] = optimal_ms  # first calculation
                else:
                    prev_rate = _auto_game_rate_ms[0]
                    _auto_game_rate_ms[0] = int(
                        prev_rate * (1 - RATE_SMOOTHING) + optimal_ms * RATE_SMOOTHING
                    )
                # Update the spinbox so the UI reflects the auto-tuned rate
                phase = _scores_module.get_poll_phase()
                if phase == _scores_module.PHASE_PLAYING:
                    playing_interval_var.set(_auto_game_rate_ms[0])

                # Prediction display — phase-aware call estimate
                game_rate_ms = _auto_game_rate_ms[0]
                if segments:
                    est_calls = 0
                    t_left = resets_in
                    for seg_phase, seg_secs in segments:
                        seg_secs = min(seg_secs, t_left)
                        if seg_secs <= 0:
                            break
                        if seg_phase == _scores_module.PHASE_BREAK:
                            est_calls += seg_secs / (break_rate_ms / 1000)
                        else:
                            est_calls += seg_secs / (game_rate_ms / 1000)
                        t_left -= seg_secs
                        if t_left <= 0:
                            break
                    calls_until_reset = int(est_calls)
                else:
                    calls_until_reset = int(resets_in / (game_rate_ms / 1000))
                predicted_remaining = remaining - calls_until_reset
                rate_prediction_label.config(
                    text=f"Auto game rate: {game_rate_ms}ms  |  "
                         f"~{predicted_remaining} tokens left at reset  "
                         f"({calls_until_reset} calls in {resets_in // 60}m {resets_in % 60}s)",
                    fg="#28a745" if predicted_remaining >= TOKEN_RESERVE else "#ff6600")
            else:
                _auto_game_rate_ms[0] = 0
                rate_prediction_label.config(
                    text=f"Token reserve ({TOKEN_RESERVE}) reached — throttling",
                    fg="#ff0000")
        else:
            _rate_limit_floor_ms[0] = 0
            _auto_game_rate_ms[0] = 0
            rate_max_speed_label.config(text="")
            rate_prediction_label.config(text="")

        # ── Burn mode detection ──────────────────────────────────────
        # In 2nd half+: if rate limit resets AFTER the game ends,
        # surplus tokens will expire unused. Burn them at 700ms.
        game_secs = _scores_module.get_min_game_seconds_remaining()
        if (game_secs is not None and resets_in > 0 and remaining > TOKEN_RESERVE
                and game_secs < resets_in):
            # Tokens we'd normally use during remaining game time at current rate
            current_rate_sec = max(0.7, (_auto_game_rate_ms[0] or 1000) / 1000)
            tokens_for_game = int(game_secs / current_rate_sec)
            # Surplus = tokens that would expire after game ends
            surplus = remaining - tokens_for_game - TOKEN_RESERVE
            if surplus > 10:  # only burn if meaningful surplus
                _burn_mode[0] = True
                _burn_tokens_available[0] = surplus
                game_m, game_s = divmod(int(game_secs), 60)
                rate_prediction_label.config(
                    text=f"BURN MODE: {surplus} surplus tokens | "
                         f"game ends in ~{game_m}m{game_s:02d}s | "
                         f"reset in {resets_in // 60}m{resets_in % 60:02d}s | "
                         f"burning at {BURN_INTERVAL_MS}ms",
                    fg="#ff4400")
            else:
                _burn_mode[0] = False
                _burn_tokens_available[0] = 0
        else:
            _burn_mode[0] = False
            _burn_tokens_available[0] = 0

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

    def _fetch(url_override=None, call_type="scores"):
        final_url = url_override or _build_scores_url()
        _last_call_type[0] = call_type
        status_label.config(text=f"Fetching ({call_type})...", fg="#0066cc")
        _set_tab_status("fetching")
        raw_clear()

        def _do_request():
            try:
                req = urllib.request.Request(final_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                try:
                    tab.after(0, lambda: _show_result(body))
                except RuntimeError:
                    return
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                msg = f"HTTP Error {e.code}: {e.reason}\n\n{body}"
                code = e.code
                try:
                    tab.after(0, lambda: _show_error(msg, code))
                except RuntimeError:
                    return
            except Exception as e:
                msg = str(e)
                try:
                    tab.after(0, lambda: _show_error(msg))
                except RuntimeError:
                    return

        threading.Thread(target=_do_request, daemon=True).start()

    def _parse_live_scores(data):
        """Extract per-fixture scores from livescores API response.

        Returns {fixture_id: {"home": str, "away": str, "home_score": int, "away_score": int}}
        Participant names come from the API when included, otherwise fall back
        to names already stored in the scores module (from a previous events call).
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
            # Fall back to names from scores module (populated by earlier events calls)
            if not home or not away:
                existing = _scores_module.get_all_scores().get(fid)
                if existing:
                    home = home or existing.get("home", "")
                    away = away or existing.get("away", "")
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
            had_live = bool(_prev_live_scores[0])
            _scores_module.clear_live_state()
            _prev_live_scores[0] = {}
            # Games just ended — trigger schedule fetch to get final scores
            if had_live and _fetch_schedule_cb[0]:
                _fetch_schedule_cb[0]()
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
                    if "events" in fix:
                        events = fix["events"]
                        if isinstance(events, list):
                            _scores_module.update_events(fid, events)
                            cur_info = current.get(fid, {})
                            _log_new_events(fid,
                                            cur_info.get("home", ""),
                                            cur_info.get("away", ""))
                    state_id = fix.get("state_id")
                    if state_id is not None:
                        old_sid = _prev_state_ids.get(fid)
                        if old_sid != state_id:
                            # State changed — log it
                            cur_info = current.get(fid, {})
                            _log_state_change(
                                fid,
                                cur_info.get("home", fix.get("name", "")),
                                cur_info.get("away", ""),
                                old_sid, state_id,
                            )
                            _prev_state_ids[fid] = state_id
                            # Game just finished — fetch schedule for final scores
                            if state_id in (5, 7, 8) and _fetch_schedule_cb[0]:
                                _fetch_schedule_cb[0]()
                        _scores_module.update_state(fid, state_id)
                    periods = fix.get("periods")
                    if isinstance(periods, list) and periods:
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

                if scoring_team:
                    _log_goal(cur["home"], cur["away"],
                              cur["home_score"], cur["away_score"], scoring_team)

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

        call_type = _last_call_type[0]
        status_label.config(text=f"OK ({call_type})", fg="#28a745")
        _set_tab_status("ok")

        # Update phase display (always) and schedule next cycle (if auto-running)
        _update_phase_display()
        if auto_running[0]:
            _schedule_next_cycle()

    def _show_error(msg, http_code=None):
        raw_error(msg)
        tree_error(msg)
        auto_style.configure("Auto.Horizontal.TProgressbar", background="#ff0000")
        if http_code == 429:
            status_label.config(text="Rate limited – retrying", fg="#ff6600")
        else:
            status_label.config(text="Error – retrying", fg="red")
        _set_tab_status("error")

        # Schedule next auto-cycle even on error
        if auto_running[0]:
            _schedule_next_cycle()
        if status_bar:
            status_bar.rate_label.config(fg="#ff0000")

    # ── Get / Auto controls ───────────────────────────────────────────
    tk.Button(ctrl_frame, text="Get Scores", font=("Segoe UI", 9, "bold"),
              bg="#0066cc", fg="white", padx=8, pady=2,
              command=lambda: _fetch(_build_scores_url(), "scores")).pack(side="left", padx=(0, 4))
    tk.Button(ctrl_frame, text="Get Events", font=("Segoe UI", 9, "bold"),
              bg="#6600cc", fg="white", padx=8, pady=2,
              command=lambda: _fetch(_build_events_url(), "events")).pack(side="left", padx=(0, 12))

    ttk.Separator(ctrl_frame, orient="vertical").pack(side="left", fill="y", padx=8)

    # ── Polling frequency settings ────────────────────────────────────
    poll_frame = tk.Frame(tab)
    poll_frame.pack(fill="x", padx=12, pady=(2, 2))

    def _poll_setting(parent, label_text, default_ms, col, step=100):
        lbl = tk.Label(parent, text=label_text, font=("Segoe UI", 8), fg="#888888",
                       padx=3, pady=1)
        lbl.grid(row=0, column=col, padx=(0, 2), sticky="e")
        var = tk.IntVar(value=default_ms)
        spn = tk.Spinbox(parent, from_=5, to=60000, increment=step, textvariable=var,
                         font=("Consolas", 9), width=6, justify="center")
        spn.grid(row=0, column=col+1, padx=(0, 2))
        ms_lbl = tk.Label(parent, text="ms", font=("Segoe UI", 8), fg="#888888")
        ms_lbl.grid(row=0, column=col+2, padx=(0, 12))
        return var, lbl, spn, ms_lbl

    idle_interval_var,     idle_lbl,     idle_spn,     idle_ms     = _poll_setting(poll_frame, "Idle:",      60000,  0)
    pregame_interval_var,  pregame_lbl,  pregame_spn,  pregame_ms  = _poll_setting(poll_frame, "Pregame:",   20000,  3)
    playing_interval_var,  playing_lbl,  playing_spn,  playing_ms  = _poll_setting(poll_frame, "Game Time:", 500,  6, step=5)
    break_interval_var,    break_lbl,    break_spn,    break_ms    = _poll_setting(poll_frame, "Half-Time:", 45000,  9)
    postgame_interval_var, postgame_lbl, postgame_spn, postgame_ms = _poll_setting(poll_frame, "Post-Game:", 10000, 12)

    # Map phase → (label, spinbox, ms_label) for highlighting
    _phase_widgets = {
        _scores_module.PHASE_IDLE:     (idle_lbl,     idle_spn,     idle_ms),
        _scores_module.PHASE_PREGAME:  (pregame_lbl,  pregame_spn,  pregame_ms),
        _scores_module.PHASE_PLAYING:  (playing_lbl,  playing_spn,  playing_ms),
        _scores_module.PHASE_BREAK:    (break_lbl,    break_spn,    break_ms),
        _scores_module.PHASE_POSTGAME: (postgame_lbl, postgame_spn, postgame_ms),
    }

    _default_bg = poll_frame.cget("bg")

    def _highlight_active_phase(phase):
        """Highlight the active polling mode with its phase colour, clear others."""
        for p, (lbl, spn, ms) in _phase_widgets.items():
            if p == phase:
                bg = _PHASE_COLOURS.get(p, "#cc0000")
                # Use black text on yellow for readability
                fg = "#000000" if bg == "#ffcc00" else "white"
                lbl.config(bg=bg, fg=fg)
                ms.config(bg=bg, fg=fg)
            else:
                lbl.config(bg=_default_bg, fg="#888888")
                ms.config(bg=_default_bg, fg="#888888")

    tk.Label(poll_frame, text="Events every", font=("Segoe UI", 8), fg="#888888"
             ).grid(row=0, column=15, padx=(0, 2), sticky="e")
    events_nth_var = tk.IntVar(value=10)
    tk.Spinbox(poll_frame, from_=1, to=100, increment=1, textvariable=events_nth_var,
               font=("Consolas", 9), width=4, justify="center"
               ).grid(row=0, column=16, padx=(0, 2))
    tk.Label(poll_frame, text="calls", font=("Segoe UI", 8), fg="#888888"
             ).grid(row=0, column=17, padx=(0, 0))

    # Phase display label
    phase_label = tk.Label(ctrl_frame, text="", font=("Consolas", 9, "bold"), fg="#888888")
    phase_label.pack(side="left", padx=(8, 4))

    def _get_dynamic_interval():
        """Return the polling interval in ms based on current game phase.

        The interval is clamped to never go below the rate-limit-derived floor
        (resets_in_seconds / remaining_tokens), recalculated after every API call.

        In burn mode (2nd half+, surplus tokens expiring after game ends),
        overrides to BURN_INTERVAL_MS (700ms) to maximize data freshness.
        """
        phase = _scores_module.get_poll_phase()

        # Burn mode overrides during active play
        if _burn_mode[0] and phase == _scores_module.PHASE_PLAYING:
            return BURN_INTERVAL_MS, phase

        if phase == _scores_module.PHASE_PLAYING:
            desired = max(100, playing_interval_var.get())
        elif phase == _scores_module.PHASE_BREAK:
            desired = max(100, break_interval_var.get())
        elif phase == _scores_module.PHASE_POSTGAME:
            desired = max(100, postgame_interval_var.get())
        elif phase == _scores_module.PHASE_PREGAME:
            desired = max(100, pregame_interval_var.get())
        else:
            desired = max(100, idle_interval_var.get())

        # Enforce rate-limit floor on non-playing phases only.
        # During active play, use the configured speed regardless.
        if phase != _scores_module.PHASE_PLAYING:
            floor = _rate_limit_floor_ms[0]
            desired = max(desired, floor)
        return desired, phase

    _PHASE_COLOURS = {
        _scores_module.PHASE_IDLE:     "#888888",
        _scores_module.PHASE_PREGAME:  "#ffcc00",
        _scores_module.PHASE_PLAYING:  "#28a745",
        _scores_module.PHASE_BREAK:    "#ffcc00",
        _scores_module.PHASE_POSTGAME: "#0066cc",
    }

    def _start_auto():
        if auto_running[0]:
            return
        auto_running[0] = True
        _call_counter[0] = 0
        auto_btn.config(text="Stop Auto", bg="#cc0000", command=_stop_auto)
        # First call on startup is always a full events fetch to get complete game state
        _auto_cycle(force_events=True)

    def _stop_auto():
        auto_running[0] = False
        if auto_timer_id[0]:
            tab.after_cancel(auto_timer_id[0])
            auto_timer_id[0] = None
        if auto_progress_id[0]:
            tab.after_cancel(auto_progress_id[0])
            auto_progress_id[0] = None
        progress["value"] = 0
        phase_label.config(text="")
        _highlight_active_phase(None)
        auto_btn.config(text="Auto Get", bg="#28a745", command=_start_auto)

    def _update_phase_display():
        """Refresh the phase label and highlight based on current state_ids."""
        _, phase = _get_dynamic_interval()
        colour = _PHASE_COLOURS.get(phase, "#888888")
        phase_label.config(text=f"{phase.upper()}", fg=colour)
        _highlight_active_phase(phase)

    def _auto_cycle(force_events=False):
        """Fire the next API fetch. Scheduling of the following cycle happens
        in _schedule_next_cycle(), called from _show_result/_show_error after
        the response arrives so the phase is based on fresh state_ids."""
        if not auto_running[0]:
            return

        # Decide which URL to use: events every Nth call
        # force_events=True on first call after startup to get full game state
        _call_counter[0] += 1
        n = max(1, events_nth_var.get())
        if force_events or _call_counter[0] % n == 0:
            _fetch(_build_events_url(), "events")
        else:
            _fetch(_build_scores_url(), "scores")

    def _schedule_next_cycle():
        """Determine phase from fresh state_ids and schedule the next auto-cycle."""
        if not auto_running[0]:
            return
        # Cancel any pending timer (in case of rapid calls)
        if auto_timer_id[0]:
            tab.after_cancel(auto_timer_id[0])
            auto_timer_id[0] = None
        if auto_progress_id[0]:
            tab.after_cancel(auto_progress_id[0])
            auto_progress_id[0] = None

        interval_ms, phase = _get_dynamic_interval()
        auto_interval[0] = interval_ms
        auto_elapsed[0] = 0
        progress["value"] = 0

        # Update phase display and highlight active setting
        if _burn_mode[0] and phase == _scores_module.PHASE_PLAYING:
            colour = "#ff4400"
            phase_label.config(text=f"BURN {interval_ms}ms ({_burn_tokens_available[0]} surplus)",
                               fg=colour)
        else:
            colour = _PHASE_COLOURS.get(phase, "#888888")
            phase_label.config(text=f"{phase.upper()} {interval_ms}ms",
                               fg=colour)
        auto_style.configure("Auto.Horizontal.TProgressbar", background=colour)
        _highlight_active_phase(phase)

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
    rate_progress.pack(fill="x", padx=12, pady=(0, 2))

    rate_prediction_label = tk.Label(tab, text="", font=("Segoe UI", 9), fg="#888888")
    rate_prediction_label.pack(fill="x", padx=12, pady=(0, 6))

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
