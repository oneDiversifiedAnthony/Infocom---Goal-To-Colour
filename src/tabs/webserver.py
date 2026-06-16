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

"""Web Server tab -- hosts a live status page showing current colours,
sound playback state, and the game schedule.

Runs a lightweight HTTP server in a background thread on a configurable port.
Dynamic sections refresh every 2 seconds via fetch(); clocks tick every second
client-side to avoid flicker.
"""

import tkinter as tk
from tkinter import ttk
import threading
import socket
import json
import webbrowser
import base64
import os
from urllib.parse import unquote_plus
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from src import scores
from src.config import get_webserver_bool, set_webserver_bool, get_config, set_config


# Load logo as base64 for embedding in HTML
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "Diversified_logo.png")
try:
    with open(_LOGO_PATH, "rb") as _f:
        _LOGO_B64 = base64.b64encode(_f.read()).decode("ascii")
except FileNotFoundError:
    _LOGO_B64 = ""

# Load flag SVG data
_FLAGS_PATH = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "assets", "Flags.json")
try:
    with open(_FLAGS_PATH, "r", encoding="utf-8") as _f:
        _FLAGS_DATA = json.load(_f).get("flags", {})
except (FileNotFoundError, json.JSONDecodeError):
    _FLAGS_DATA = {}

# Load Diversified presentations
_PRESENTATIONS_PATH = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "assets", "DiversifiedPresentations.json")
try:
    with open(_PRESENTATIONS_PATH, "r", encoding="utf-8") as _f:
        _PRESENTATIONS = json.load(_f).get("presentations", [])
except (FileNotFoundError, json.JSONDecodeError):
    _PRESENTATIONS = []


def _flag_svg(name, width=48, height=32):
    """Return an inline flag SVG element for a country, or empty string."""
    entry = _FLAGS_DATA.get(name)
    if not entry:
        return ""
    svg = entry.get("svg", "")
    if not svg:
        return ""
    # Wrap in a sized container div
    return (
        f'<div style="display:inline-block;width:{width}px;height:{height}px;'
        f'border:1px solid #555;border-radius:2px;overflow:hidden;vertical-align:middle;'
        f'margin-right:4px;">{svg}</div>'
    )

# Shared state dict updated by the main app
_state = {
    "colours": [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
    "team_name": "",
    "goal_active": False,
    "games": [],          # list of game dicts from schedule
    "teams": {},          # {name: {"colours": [[r,g,b], ...]}}
    "api_remaining": "",  # e.g. "2950 / 3000"
    "sacn_connected": False,
}

# Section definitions: key -> display label
_SECTION_LABELS = {
    "show_clock_utc":      "Clock — UTC",
    "show_clock_lasvegas": "Clock — Las Vegas",
    "show_clock_toronto":  "Clock — Toronto",
    "show_live_status":    "Live Status / Now Playing",
    "show_goal_banner":    "Goal Banner",
    "show_colours":        "Current Colours",
    "show_todays_games":   "Today's Games",
    "show_schedule":       "Whole Schedule",
    "show_schedule_times": "Schedule Times (LV / TO / UTC)",
}

_DEFAULT_ORDER = list(_SECTION_LABELS.keys())

# Web page section visibility (loaded from config.ini)
_WEB_SECTIONS = {k: get_webserver_bool(k, True) for k in _SECTION_LABELS}

# Section display order (loaded from config.ini)
def _load_section_order():
    raw = get_config("webserver", "section_order", fallback="")
    if not raw:
        return list(_DEFAULT_ORDER)
    keys = [k.strip() for k in raw.split(",") if k.strip() in _SECTION_LABELS]
    # Append any missing keys at end
    for k in _DEFAULT_ORDER:
        if k not in keys:
            keys.append(k)
    return keys

_WEB_SECTION_ORDER = _load_section_order()


def _save_section_order():
    set_config("webserver", "section_order", ",".join(_WEB_SECTION_ORDER))

_lv_tz = ZoneInfo("America/Los_Angeles")
_to_tz = ZoneInfo("America/Toronto")

# Callbacks set by the main app (called from HTTP thread via root.after)
_callbacks = {
    "goal_pressed": None,   # fn(colours, country_name)
    "set_colours": None,    # fn(colours, country_name)
    "root": None,           # tkinter root for after() scheduling
}

# Sound callbacks for the /sounds page (set by the main app after the Sounds tab builds)
_sound_callbacks = {
    "list": None,   # fn() -> [{"name": str, "playing": bool}]
    "play": None,   # fn(name) -> bool
    "stop": None,   # fn(name) -> bool
}


def set_sound_callbacks(list_fn=None, play_fn=None, stop_fn=None):
    """Register the Sounds tab's list/play/stop functions for the /sounds page."""
    if list_fn is not None:
        _sound_callbacks["list"] = list_fn
    if play_fn is not None:
        _sound_callbacks["play"] = play_fn
    if stop_fn is not None:
        _sound_callbacks["stop"] = stop_fn


def update_state(*, colours=None, team_name=None, goal_active=None,
                 games=None, teams=None, api_remaining=None,
                 sacn_connected=None):
    """Update shared state from the main app. Thread-safe for reads."""
    if colours is not None:
        _state["colours"] = colours
    if team_name is not None:
        _state["team_name"] = team_name
    if goal_active is not None:
        _state["goal_active"] = goal_active
    if games is not None:
        _state["games"] = games
    if teams is not None:
        _state["teams"] = teams
    if api_remaining is not None:
        _state["api_remaining"] = api_remaining
    if sacn_connected is not None:
        _state["sacn_connected"] = sacn_connected


def _build_html():
    """Generate the status HTML page."""
    colours = _state["colours"]
    team = _state["team_name"] or "None"
    goal = _state["goal_active"]
    games = _state["games"]
    teams = _state["teams"]

    now_utc = datetime.now(timezone.utc)
    now_lv = now_utc.astimezone(_lv_tz)
    now_to = now_utc.astimezone(_to_tz)

    # Colour swatches HTML
    swatch_html = ""
    for i, rgb in enumerate(colours):
        hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        swatch_html += (
            f'<div style="display:inline-block;width:120px;height:120px;'
            f'background:{hex_col};border:2px solid #555;margin:8px;'
            f'border-radius:8px;vertical-align:top;text-align:center;'
            f'line-height:120px;">'
            f'<span style="color:#fff;text-shadow:1px 1px 2px #000;'
            f'font-size:14px;">{rgb[0]},{rgb[1]},{rgb[2]}</span></div>'
        )

    # Goal banner
    goal_html = ""
    if goal and _WEB_SECTIONS["show_goal_banner"]:
        goal_html = (
            '<div style="background:#ff4444;color:white;padding:16px;'
            'text-align:center;font-size:28px;font-weight:bold;'
            'border-radius:8px;margin:12px 0;animation:blink 0.5s infinite alternate;">'
            f'GOAL! {_flag_svg(team, width=48, height=32)} {team}</div>'
        )

    # Now playing / next game countdown
    countdown_html = ""
    scores.update_live_flags()
    live_games = scores.get_live_games()
    if live_games and _WEB_SECTIONS["show_live_status"]:
        # Show NOW PLAYING with big team names and scores
        fid, info = live_games[0]
        lh = info.get("home", "")
        la = info.get("away", "")
        lhs = info.get("home_score", 0)
        las = info.get("away_score", 0)
        match_clock = scores.get_match_clock(fid)
        # Build events list
        events = scores.get_events(fid)
        events_html = ""
        if events:
            sorted_events = sorted(events, key=lambda e: (e.get("minute", 0), e.get("extra_minute") or 0))
            event_rows = ""
            for ev in sorted_events:
                minute = ev.get("minute", "")
                extra = ev.get("extra_minute")
                min_str = f"{minute}'" if minute else ""
                if extra:
                    min_str = f"{minute}+{extra}'"
                type_id = ev.get("type_id")
                player = ev.get("player_name", "")
                info = ev.get("info", "")
                addition = ev.get("addition", "")
                result = ev.get("result", "")
                # Determine which team
                pid = ev.get("participant_id")
                # Icon and colour based on event type
                if type_id == 14:  # Goal
                    icon = "⚽"
                    colour = "#28a745"
                    detail = f"{player}"
                    if result:
                        detail += f" ({result})"
                elif type_id == 19:  # Yellow card
                    icon = "🟨"
                    colour = "#ffcc00"
                    detail = f"{player}"
                    if info:
                        detail += f" — {info}"
                elif type_id == 20:  # Red card
                    icon = "🟥"
                    colour = "#ff0000"
                    detail = f"{player}"
                elif type_id == 18:  # Substitution
                    icon = "🔄"
                    colour = "#0088ff"
                    related = ev.get("related_player_name", "")
                    detail = f"{player} ↔ {related}" if related else player
                else:
                    icon = "📋"
                    colour = "#888"
                    detail = f"{player} — {info}" if info else player
                    if addition:
                        detail += f" ({addition})"

                event_rows += (
                    f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;'
                    f'border-bottom:1px solid #333;">'
                    f'<span style="font-family:Consolas;font-weight:bold;color:#888;'
                    f'min-width:40px;text-align:right;">{min_str}</span>'
                    f'<span style="font-size:18px;">{icon}</span>'
                    f'<span style="color:{colour};font-weight:bold;">{detail}</span>'
                    f'</div>'
                )
            events_html = (
                f'<div style="background:#1a1a1a;border-radius:0 0 8px 8px;'
                f'padding:12px 24px;margin:-16px 0 16px 0;'
                f'border:1px solid #333;border-top:none;">'
                f'{event_rows}</div>'
            )

        clock_html = ('  —  <span style="font-family:Consolas;font-size:28px;">'
                      + match_clock + '</span>') if match_clock else ''
        countdown_html = (
            f'<div style="background:#222;border:3px solid #28a745;border-radius:8px;'
            f'padding:20px 32px;margin:0 0 0 0;text-align:center;">'
            f'<div style="font-size:24px;font-weight:bold;color:#28a745;margin-bottom:8px;">'
            f'NOW PLAYING'
            f'{clock_html}'
            f'</div>'
            f'<div style="display:flex;align-items:center;justify-content:center;gap:16px;">'
            f'<div style="font-size:60px;font-family:Consolas,monospace;font-weight:bold;color:#ffcc00;">{lhs}</div>'
            f'{_flag_svg(lh, width=80, height=53)}'
            f'<div style="font-size:32px;font-weight:bold;color:#e0e0e0;">{lh}</div>'
            f'<div style="font-size:28px;color:#888;font-weight:bold;">vs</div>'
            f'<div style="font-size:32px;font-weight:bold;color:#e0e0e0;">{la}</div>'
            f'{_flag_svg(la, width=80, height=53)}'
            f'<div style="font-size:60px;font-family:Consolas,monospace;font-weight:bold;color:#ffcc00;">{las}</div>'
            f'</div></div>'
            f'{events_html}'
        )
    elif _WEB_SECTIONS["show_live_status"]:
        today_utc = now_utc.strftime("%b %d").replace(" 0", " ")
        next_game = None
        next_kick = None
        for g in sorted(games, key=lambda g: g.get("time_utc", "99:99")):
            if g.get("date", "") != today_utc:
                continue
            t = g.get("time_utc", "")
            if not t:
                continue
            try:
                utc_dt = datetime.strptime(f"2026 {today_utc} {t}", "%Y %b %d %H:%M")
                utc_dt = utc_dt.replace(tzinfo=timezone.utc)
                if utc_dt > now_utc:
                    next_game = g
                    next_kick = utc_dt
                    break
            except ValueError:
                continue
        if next_game and next_kick:
            diff = int((next_kick - now_utc).total_seconds())
            ch, rem = divmod(diff, 3600)
            cm, cs = divmod(rem, 60)
            countdown_html = (
                f'<div style="background:#222;border:2px solid #ffcc00;border-radius:8px;'
                f'padding:16px 32px;margin:0 0 16px 0;text-align:center;">'
                f'<div style="font-size:22px;font-weight:bold;color:#ffcc00;">TIME UNTIL NEXT GAME</div>'
                f'<div style="font-size:52px;font-family:Consolas,monospace;font-weight:bold;'
                f'color:#ffcc00;">{ch:02d}:{cm:02d}:{cs:02d}</div>'
                f'<div style="font-size:18px;color:#888;">'
                f'{next_game.get("home","")} vs {next_game.get("away","")}</div>'
                f'</div>'
            )

    def _team_flag(name):
        """Generate an inline flag for a team in the schedule."""
        return _flag_svg(name, width=30, height=20)

    # ── Build unified timeline: games + presentations sorted by LV time ──
    scores.update_live_flags()
    schedule_rows = ""

    # Build list of (lv_datetime, type, data) for unified sorting
    timeline_items = []

    # Add games
    for g in games:
        d = g.get("date", "")
        t = g.get("time_utc", "")
        if d and t:
            try:
                utc_dt = datetime.strptime(f"2026 {d} {t}", "%Y %b %d %H:%M")
                utc_dt = utc_dt.replace(tzinfo=timezone.utc)
                lv_dt = utc_dt.astimezone(_lv_tz)
                timeline_items.append((lv_dt, "game", g, utc_dt))
            except ValueError:
                timeline_items.append((datetime(2099, 1, 1, tzinfo=timezone.utc), "game", g, None))
        else:
            timeline_items.append((datetime(2099, 1, 1, tzinfo=timezone.utc), "game", g, None))

    # Add presentations (times are already LV local)
    for p in _PRESENTATIONS:
        try:
            lv_naive = datetime.strptime(f"{p['date']} {p['start_time']}", "%Y-%m-%d %H:%M")
            lv_dt = lv_naive.replace(tzinfo=_lv_tz)
            timeline_items.append((lv_dt, "presentation", p, None))
        except (ValueError, KeyError):
            pass

    timeline_items.sort(key=lambda x: x[0])

    current_date = None
    all_scores = scores.get_all_scores()
    for lv_dt, item_type, data, utc_dt in timeline_items:
        lv_date_str = lv_dt.strftime("%b %d").replace(" 0", " ") if lv_dt.year < 2099 else "TBD"

        if lv_date_str != current_date:
            current_date = lv_date_str
            schedule_rows += (
                f'<tr><td colspan="6" style="background:#0066cc;color:white;'
                f'padding:6px 12px;font-weight:bold;font-size:16px;">{lv_date_str} (LV)</td></tr>'
            )

        if item_type == "presentation":
            # Presentation row
            p = data
            start = p.get("start_time", "")
            end = p.get("end_time", "")
            title = p.get("title", "")
            location = p.get("location", "")
            presenters = p.get("presenters", [])
            presenter_names = ", ".join(
                pr["name"] + (f' <span style="color:#666;">({pr["company"]})</span>' if pr.get("company") else "")
                for pr in presenters
            )
            # Check if currently happening
            is_now = False
            try:
                end_naive = datetime.strptime(f"{p['date']} {p['end_time']}", "%Y-%m-%d %H:%M")
                end_dt = end_naive.replace(tzinfo=_lv_tz)
                is_now = lv_dt <= now_utc.astimezone(_lv_tz) <= end_dt
            except (ValueError, KeyError):
                pass
            now_badge = (' <span style="background:#cc6600;color:#fff;padding:2px 8px;'
                         'border-radius:4px;font-size:11px;font-weight:bold;">NOW</span>') if is_now else ''
            border_col = "#cc6600" if is_now else "#333"
            schedule_rows += (
                f'<tr style="border-bottom:1px solid {border_col};border-left:3px solid #cc6600;">'
                f'<td style="padding:6px;width:16px;">'
                f'<span style="display:inline-block;width:12px;height:12px;border-radius:2px;'
                f'background:#cc6600;"></span></td>'
                f'<td style="padding:6px;color:#cc6600;font-family:monospace;">'
                f'{start} - {end} LV{now_badge}</td>'
                f'<td colspan="3" style="padding:6px;">'
                f'<div style="font-weight:bold;color:#e0e0e0;font-size:13px;">'
                f'<span style="color:#cc6600;">PRESENTATION</span> &mdash; {title}</div>'
                f'<div style="color:#999;font-size:11px;margin-top:2px;">{presenter_names}</div>'
                f'</td>'
                f'<td style="padding:6px;color:#888;font-size:12px;">{location}</td></tr>'
            )
        else:
            # Game row
            g = data
            time_lv = lv_dt.strftime("%H:%M") if lv_dt.year < 2099 else ""
            time_to = ""
            time_utc_str = g.get("time_utc", "")
            is_live = False
            if utc_dt:
                to_dt = utc_dt.astimezone(_to_tz)
                time_to = to_dt.strftime("%H:%M")
                diff_min = (now_utc - utc_dt).total_seconds() / 60
                is_live = 0 <= diff_min <= 120

            time_colour = "#28a745" if is_live else "#0088ff"
            dot_colour = "#28a745" if is_live else "#0066cc"
            if _WEB_SECTIONS["show_schedule_times"]:
                time_display = f"{time_lv} LV" if time_lv else ""
                if time_to:
                    time_display += f" / {time_to} TO"
                if time_utc_str:
                    time_display += f" / {time_utc_str} UTC"
            else:
                time_display = ""
            venue = g.get("venue", "")
            home = g.get("home", "")
            away = g.get("away", "")
            # Score and match minute from score tracker
            score_display = ""
            minute_display = ""
            for fid, sc in all_scores.items():
                if sc["home"] == home and sc["away"] == away:
                    sd = scores.get_score_display(fid)
                    if sd:
                        score_display = sd
                    minute_display = scores.get_match_clock(fid)
                    break
            home_score_parts = score_display.split(" - ") if score_display else []
            if len(home_score_parts) == 2:
                home_score_html = f'<span style="color:#ffcc00;font-weight:bold;font-size:24px;font-family:Consolas,monospace;padding:0 6px;">{home_score_parts[0]}</span>'
                away_score_html = f'<span style="color:#ffcc00;font-weight:bold;font-size:24px;font-family:Consolas,monospace;padding:0 6px;">{home_score_parts[1]}</span>'
            else:
                home_score_html = ''
                away_score_html = ''
            vs_html = '<span style="color:#555;padding:0 4px;">vs</span>' if not score_display else '<span style="color:#555;padding:0 4px;">-</span>'
            live_badge = f' <span style="background:#28a745;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;">LIVE {minute_display}</span>' if is_live else ''
            schedule_rows += (
                f'<tr style="border-bottom:1px solid #333;">'
                f'<td style="padding:6px;width:16px;"><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{dot_colour};"></span></td>'
                f'<td style="padding:6px;color:{time_colour};font-family:monospace;">{time_display}{live_badge}</td>'
                f'<td style="padding:6px;font-weight:bold;text-align:right;white-space:nowrap;">'
                f'{home_score_html}{_team_flag(home)} <span style="color:#aaa;font-size:10px;">H</span> {home}</td>'
                f'<td style="padding:6px;text-align:center;">{vs_html}</td>'
                f'<td style="padding:6px;font-weight:bold;white-space:nowrap;">'
                f'{away} <span style="color:#aaa;font-size:10px;">A</span> {_team_flag(away)}{away_score_html}</td>'
                f'<td style="padding:6px;color:#888;font-size:13px;">{venue}</td></tr>'
            )

    # Build conditional HTML blocks
    # Build individual clock divs
    clock_divs = ""
    clocks_js_parts = []
    if _WEB_SECTIONS["show_clock_utc"]:
        clock_divs += (
            f'<div class="clock">'
            f'<div class="clock-label" style="color:#0066cc;">UTC</div>'
            f'<div class="clock-time" id="clock-utc" style="color:#0066cc;">{now_utc.strftime("%H:%M:%S")}</div>'
            f'<div class="clock-date" id="clock-utc-date">{now_utc.strftime("%a %d %b %Y")}</div>'
            f'</div>'
        )
        clocks_js_parts.append(
            "var utc = new Date(now.toLocaleString('en-US', {timeZone:'UTC'}));\n"
            "document.getElementById('clock-utc').textContent = fmt(utc);\n"
            "document.getElementById('clock-utc-date').textContent = fmtDate(utc);"
        )
    if _WEB_SECTIONS["show_clock_lasvegas"]:
        clock_divs += (
            f'<div class="clock">'
            f'<div class="clock-label" style="color:#cc6600;">Las Vegas</div>'
            f'<div class="clock-time" id="clock-lv" style="color:#cc6600;">{now_lv.strftime("%H:%M:%S")}</div>'
            f'<div class="clock-date" id="clock-lv-date">{now_lv.strftime("%a %d %b %Y")}</div>'
            f'</div>'
        )
        clocks_js_parts.append(
            "var lv = new Date(now.toLocaleString('en-US', {timeZone:'America/Los_Angeles'}));\n"
            "document.getElementById('clock-lv').textContent = fmt(lv);\n"
            "document.getElementById('clock-lv-date').textContent = fmtDate(lv);"
        )
    if _WEB_SECTIONS["show_clock_toronto"]:
        clock_divs += (
            f'<div class="clock">'
            f'<div class="clock-label" style="color:#cc0066;">Toronto</div>'
            f'<div class="clock-time" id="clock-to" style="color:#cc0066;">{now_to.strftime("%H:%M:%S")}</div>'
            f'<div class="clock-date" id="clock-to-date">{now_to.strftime("%a %d %b %Y")}</div>'
            f'</div>'
        )
        clocks_js_parts.append(
            "var to = new Date(now.toLocaleString('en-US', {timeZone:'America/Toronto'}));\n"
            "document.getElementById('clock-to').textContent = fmt(to);\n"
            "document.getElementById('clock-to-date').textContent = fmtDate(to);"
        )

    clocks_html = ""
    clocks_js = ""
    if clock_divs:
        clocks_html = f'<div class="clocks">{clock_divs}</div>'
        clocks_js = (
            "function updateClocks() {\n"
            "  var now = new Date();\n"
            "  function pad(n) { return n < 10 ? '0' + n : n; }\n"
            "  function fmt(d) { return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()); }\n"
            "  function fmtDate(d) {\n"
            "    var days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];\n"
            "    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];\n"
            "    return days[d.getDay()] + ' ' + pad(d.getDate()) + ' ' + months[d.getMonth()] + ' ' + d.getFullYear();\n"
            "  }\n"
            "  " + "\n  ".join(clocks_js_parts) + "\n"
            "}\n"
            "setInterval(updateClocks, 1000);\n"
            "updateClocks();\n"
        )

    colours_html = ""
    if _WEB_SECTIONS["show_colours"]:
        colours_html = (
            f'<div id="colours-area">'
            f'<h2>Current Colours &mdash; {team}</h2>'
            f'<div style="display:flex;align-items:center;gap:24px;">'
            f'<div>{swatch_html}</div>'
            f'{_flag_svg(team, width=200, height=133)}'
            f'</div></div>'
        )

    # Today's Games (LV time) — filtered from timeline
    todays_games_html = ""
    if _WEB_SECTIONS["show_todays_games"]:
        today_lv_str = now_utc.astimezone(_lv_tz).strftime("%Y-%m-%d")
        today_rows = ""
        for lv_dt, item_type, data, utc_dt in timeline_items:
            if item_type != "game":
                continue
            if lv_dt.year >= 2099:
                continue
            if lv_dt.strftime("%Y-%m-%d") != today_lv_str:
                continue
            g = data
            time_lv = lv_dt.strftime("%H:%M")
            time_to = ""
            time_utc_str = g.get("time_utc", "")
            is_live = False
            if utc_dt:
                to_dt = utc_dt.astimezone(_to_tz)
                time_to = to_dt.strftime("%H:%M")
                diff_min = (now_utc - utc_dt).total_seconds() / 60
                is_live = 0 <= diff_min <= 120
            time_colour = "#28a745" if is_live else "#0088ff"
            dot_colour = "#28a745" if is_live else "#0066cc"
            if _WEB_SECTIONS["show_schedule_times"]:
                time_display = f"{time_lv} LV"
                if time_to:
                    time_display += f" / {time_to} TO"
                if time_utc_str:
                    time_display += f" / {time_utc_str} UTC"
            else:
                time_display = ""
            home = g.get("home", "")
            away = g.get("away", "")
            venue = g.get("venue", "")
            score_display = ""
            minute_display = ""
            for fid, sc in all_scores.items():
                if sc["home"] == home and sc["away"] == away:
                    sd = scores.get_score_display(fid)
                    if sd:
                        score_display = sd
                    minute_display = scores.get_match_clock(fid)
                    break
            home_score_parts = score_display.split(" - ") if score_display else []
            if len(home_score_parts) == 2:
                home_score_html = f'<span style="color:#ffcc00;font-weight:bold;font-size:24px;font-family:Consolas,monospace;padding:0 6px;">{home_score_parts[0]}</span>'
                away_score_html = f'<span style="color:#ffcc00;font-weight:bold;font-size:24px;font-family:Consolas,monospace;padding:0 6px;">{home_score_parts[1]}</span>'
            else:
                home_score_html = ''
                away_score_html = ''
            vs_html = '<span style="color:#555;padding:0 4px;">vs</span>' if not score_display else '<span style="color:#555;padding:0 4px;">-</span>'
            live_badge = f' <span style="background:#28a745;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;">LIVE {minute_display}</span>' if is_live else ''
            today_rows += (
                f'<tr style="border-bottom:1px solid #333;">'
                f'<td style="padding:6px;width:16px;"><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{dot_colour};"></span></td>'
                f'<td style="padding:6px;color:{time_colour};font-family:monospace;">{time_display}{live_badge}</td>'
                f'<td style="padding:6px;font-weight:bold;text-align:right;white-space:nowrap;">'
                f'{home_score_html}{_flag_svg(home, width=30, height=20)} <span style="color:#aaa;font-size:10px;">H</span> {home}</td>'
                f'<td style="padding:6px;text-align:center;">{vs_html}</td>'
                f'<td style="padding:6px;font-weight:bold;white-space:nowrap;">'
                f'{away} <span style="color:#aaa;font-size:10px;">A</span> {_flag_svg(away, width=30, height=20)}{away_score_html}</td>'
                f'<td style="padding:6px;color:#888;font-size:13px;">{venue}</td></tr>'
            )
        if today_rows:
            today_lv_display = now_utc.astimezone(_lv_tz).strftime("%A, %b %d").replace(" 0", " ")
            todays_games_html = (
                f'<div id="todays-games-area">'
                f'<h2>Today\'s Games — {today_lv_display} (LV)</h2>'
                f'<table>{today_rows}</table>'
                f'</div>'
            )

    schedule_html = ""
    if _WEB_SECTIONS["show_schedule"]:
        # Group schedule rows by date for day-at-a-time rotation
        # Parse the rows to split by date header
        schedule_days = {}  # {date_str: rows_html}
        _current_day_key = None
        _day_order = []  # preserve insertion order
        import re as _re
        # Split schedule_rows by date header rows
        _row_parts = _re.split(r'(<tr><td colspan="6"[^>]*>)', schedule_rows)
        i = 0
        while i < len(_row_parts):
            part = _row_parts[i]
            if part.startswith('<tr><td colspan="6"'):
                # This is a date header — extract date text
                header_html = part + (_row_parts[i + 1] if i + 1 < len(_row_parts) else "")
                date_match = _re.search(r'>([^<]+)</td>', header_html)
                _current_day_key = date_match.group(1).strip() if date_match else f"day_{len(_day_order)}"
                if _current_day_key not in schedule_days:
                    schedule_days[_current_day_key] = ""
                    _day_order.append(_current_day_key)
                schedule_days[_current_day_key] += header_html
                i += 2
            else:
                if _current_day_key and part.strip():
                    schedule_days[_current_day_key] += part
                i += 1

        # Determine which days to show: today (LV), tomorrow (LV), and the last day
        today_lv_str = now_lv.strftime("%b %d").replace(" 0", " ") + " (LV)"
        tomorrow_lv = now_lv + timedelta(days=1)
        tomorrow_lv_str = tomorrow_lv.strftime("%b %d").replace(" 0", " ") + " (LV)"
        last_day_str = _day_order[-1] if _day_order else None

        _show_days = []
        for d in [today_lv_str, tomorrow_lv_str]:
            if d in schedule_days and d not in _show_days:
                _show_days.append(d)
        if last_day_str and last_day_str not in _show_days:
            _show_days.append(last_day_str)

        # If none matched (dates might not align), show all days
        if not _show_days:
            _show_days = _day_order

        # Build day divs
        day_divs = ""
        for idx, day_key in enumerate(_show_days):
            display = "block" if idx == 0 else "none"
            day_divs += (
                f'<div class="schedule-day" style="display:{display};'
                f'opacity:{1 if idx == 0 else 0};transition:opacity 0.8s ease;">'
                f'<table>{schedule_days[day_key]}</table></div>'
            )

        schedule_html = (
            f'<div id="schedule-area">'
            f'<h2>Schedule</h2>'
            f'{day_divs}'
            f'</div>'
        )

    # Assemble body sections in configured order
    _section_html = {
        "show_live_status":    f'<div id="countdown-area">{countdown_html}</div>',
        "show_clock_utc":      "",  # clocks handled as group below
        "show_clock_lasvegas": "",
        "show_clock_toronto":  "",
        "show_goal_banner":    f'<div id="goal-area">{goal_html}</div>',
        "show_colours":        colours_html,
        "show_todays_games":   todays_games_html,
        "show_schedule":       schedule_html,
        "show_schedule_times": "",  # sub-option, not a standalone section
    }
    # Insert clocks HTML after the first clock key in order
    _clock_keys = {"show_clock_utc", "show_clock_lasvegas", "show_clock_toronto"}
    first_clock_done = False
    ordered_parts = []
    for key in _WEB_SECTION_ORDER:
        if key in _clock_keys:
            if not first_clock_done:
                first_clock_done = True
                ordered_parts.append(clocks_html)
            continue
        html_block = _section_html.get(key, "")
        if html_block:
            ordered_parts.append(html_block)
    ordered_body = "\n".join(ordered_parts)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>World Cup Colour - Live Status</title>
<style>
  @keyframes blink {{ 0% {{ opacity:1; }} 100% {{ opacity:0.4; }} }}
  body {{ background:#1a1a1a; color:#e0e0e0; font-family:'Segoe UI',sans-serif;
         margin:0; padding:20px; }}
  .container {{ max-width:1000px; margin:0 auto; }}
  h1 {{ color:#0066cc; margin:0; }}
  h2 {{ color:#0088ff; margin-top:24px; }}
  .header {{ display:flex; align-items:center; justify-content:space-between;
             border-bottom:2px solid #0066cc; padding-bottom:12px; margin-bottom:16px; }}
  .header h1 {{ border:none; margin:0; padding:0; }}
  .header img {{ height:60px; }}
  .clocks {{ display:flex; gap:40px; margin:16px 0; align-items:center; }}
  .clock {{ background:#222; padding:20px 32px; border-radius:8px; text-align:center; }}
  .clock-label {{ font-size:28px; font-weight:bold; }}
  .clock-time {{ font-size:56px; font-family:Consolas,monospace; font-weight:bold; }}
  .clock-date {{ font-size:28px; color:#888; font-family:Consolas,monospace; }}
  table {{ width:100%; border-collapse:collapse; margin-top:8px; }}
  .fade-update {{ transition: opacity 0.15s ease; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>World Cup Colour - Live Status</h1>
  <img src="data:image/png;base64,{_LOGO_B64}" alt="Diversified">
</div>

{ordered_body}

</div>
<script>
{clocks_js}
// Smooth data refresh — fetch page, swap only dynamic sections
var refreshing = false;
function refreshData() {{
  if (refreshing) return;
  refreshing = true;
  fetch(window.location.href, {{cache: 'no-store'}})
    .then(function(r) {{ return r.text(); }})
    .then(function(html) {{
      var parser = new DOMParser();
      var doc = parser.parseFromString(html, 'text/html');
      var ids = ['countdown-area', 'goal-area', 'colours-area', 'todays-games-area'];
      for (var i = 0; i < ids.length; i++) {{
        var newEl = doc.getElementById(ids[i]);
        var curEl = document.getElementById(ids[i]);
        if (newEl && curEl && newEl.innerHTML !== curEl.innerHTML) {{
          curEl.innerHTML = newEl.innerHTML;
        }}
      }}
      // Update schedule day contents without resetting rotation state
      var curArea = document.getElementById('schedule-area');
      var newArea = doc.getElementById('schedule-area');
      if (curArea && newArea) {{
        var curDays = curArea.querySelectorAll('.schedule-day');
        var newDays = newArea.querySelectorAll('.schedule-day');
        for (var d = 0; d < curDays.length && d < newDays.length; d++) {{
          var curTable = curDays[d].querySelector('table');
          var newTable = newDays[d].querySelector('table');
          if (curTable && newTable && curTable.innerHTML !== newTable.innerHTML) {{
            curTable.innerHTML = newTable.innerHTML;
          }}
        }}
      }}
    }})
    .catch(function() {{}})
    .finally(function() {{ refreshing = false; }});
}}
setInterval(refreshData, 1000);

// Schedule day rotation with fade
(function() {{
  var currentDay = 0;
  var ROTATE_INTERVAL = 8000;  // 8 seconds per day
  var FADE_DURATION = 800;     // matches CSS transition

  function rotateDays() {{
    var area = document.getElementById('schedule-area');
    if (!area) return;
    var days = area.querySelectorAll('.schedule-day');
    if (days.length <= 1) return;

    var cur = days[currentDay % days.length];
    // Fade out current
    cur.style.opacity = '0';
    setTimeout(function() {{
      cur.style.display = 'none';
      currentDay = (currentDay + 1) % days.length;
      var next = days[currentDay];
      next.style.display = 'block';
      // Force reflow before fade in
      void next.offsetHeight;
      next.style.opacity = '1';
    }}, FADE_DURATION);
  }}

  setInterval(rotateDays, ROTATE_INTERVAL);
}})();
</script>
</body>
</html>"""
    return html


def _build_api_json():
    """Return state as JSON for API consumers."""
    data = {
        "colours": _state["colours"],
        "team_name": _state["team_name"],
        "goal_active": _state["goal_active"],
        "live": False,
        "home": "",
        "away": "",
        "home_score": None,
        "away_score": None,
    }
    try:
        live = scores.get_live_games()
        if live:
            _fid, info = live[0]  # primary live game (matches the "NOW PLAYING" panel)
            data["live"] = True
            data["home"] = info.get("home", "")
            data["away"] = info.get("away", "")
            data["home_score"] = info.get("home_score", 0)
            data["away_score"] = info.get("away_score", 0)
    except Exception:
        pass
    return json.dumps(data, indent=2)


def _build_live_scores_html():
    """Build HTML section showing live game scores."""
    scores.update_live_flags()
    all_scores = scores.get_all_scores()
    active = [(fid, s) for fid, s in all_scores.items()
              if s["live"] or s["home_score"] > 0 or s["away_score"] > 0]
    if not active:
        return ""
    rows = ""
    for fid, s in active:
        minute = scores.get_match_minute_display(fid)
        live_dot = '<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#28a745;"></span>' if s["live"] else '<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#555;"></span>'
        minute_html = f'<span style="color:#28a745;font-weight:bold;font-size:16px;">{minute}</span>' if minute else ''
        home_flag = _flag_svg(s["home"], width=24, height=16)
        away_flag = _flag_svg(s["away"], width=24, height=16)
        rows += (
            f'<tr style="border-bottom:1px solid #333;">'
            f'<td style="padding:6px;">{live_dot}</td>'
            f'<td style="padding:6px;text-align:center;">{minute_html}</td>'
            f'<td style="padding:6px;text-align:right;font-weight:bold;">{home_flag} <span style="color:#aaa;font-size:10px;">H</span> {s["home"]}</td>'
            f'<td style="padding:6px;text-align:center;color:#ffcc00;font-weight:bold;font-size:20px;">{s["home_score"]} - {s["away_score"]}</td>'
            f'<td style="padding:6px;font-weight:bold;">{s["away"]} <span style="color:#aaa;font-size:10px;">A</span> {away_flag}</td>'
            f'</tr>'
        )
    return (
        f'<div class="status" style="margin-top:12px;">'
        f'<div style="font-size:16px;font-weight:bold;color:#ffcc00;margin-bottom:8px;">Live Scores</div>'
        f'<table style="width:100%;border-collapse:collapse;">{rows}</table></div>'
    )


def _build_testing_html():
    """Generate the testing/flags HTML page."""
    teams = _state["teams"]
    sorted_names = sorted(teams.keys())

    buttons_html = ""
    # Blackout button
    buttons_html += (
        '<form method="POST" action="/testing" style="display:inline-block;margin:4px;">'
        '<input type="hidden" name="action" value="send">'
        '<input type="hidden" name="team" value="BLACKOUT">'
        '<button type="submit" style="width:140px;height:100px;background:#1a1a1a;'
        'border:2px solid #555;border-radius:8px;cursor:pointer;padding:4px;'
        'vertical-align:top;">'
        '<div style="color:#fff;font-size:16px;font-weight:bold;">BLACKOUT</div>'
        '<div style="display:flex;gap:2px;margin-top:6px;">'
        '<div style="flex:1;height:24px;background:#000;border:1px solid #333;border-radius:3px;"></div>'
        '<div style="flex:1;height:24px;background:#000;border:1px solid #333;border-radius:3px;"></div>'
        '<div style="flex:1;height:24px;background:#000;border:1px solid #333;border-radius:3px;"></div>'
        '</div></button></form>'
    )

    active_team = _state["team_name"] or ""
    for name in sorted_names:
        team = teams[name]
        colours = team.get("colours", [[0, 0, 0], [0, 0, 0], [0, 0, 0]])
        swatches = ""
        for rgb in colours:
            hex_c = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            swatches += (
                f'<div style="flex:1;height:20px;background:{hex_c};'
                f'border:1px solid #333;border-radius:3px;"></div>'
            )
        # Escape name for HTML
        safe_name = name.replace('"', '&quot;').replace("'", "&#39;")
        first = name[0]
        rest = name[1:]
        trigger = team.get("trigger", {})
        ch = trigger.get("channel", "")
        ch_label = f' <span style="color:#888;font-size:10px;">({ch})</span>' if ch else ""
        is_active = name == active_team
        active_cls = " active-team" if is_active else ""
        flag = _flag_svg(name, width=54, height=36)
        buttons_html += (
            f'<form method="POST" action="/testing" style="display:inline-block;margin:4px;">'
            f'<input type="hidden" name="action" value="goal">'
            f'<input type="hidden" name="team" value="{safe_name}">'
            f'<button type="submit" class="{active_cls}" style="width:160px;height:100px;background:#2a2a2a;'
            f'border:2px solid #555;border-radius:8px;cursor:pointer;padding:4px;'
            f'vertical-align:top;">'
            f'<div style="color:#fff;font-size:11px;font-weight:bold;">'
            f'<span style="font-size:16px;">{first}</span>{rest}{ch_label}</div>'
            f'<div style="display:flex;align-items:center;gap:4px;margin-top:3px;">'
            f'{flag}'
            f'<div style="display:flex;flex:1;gap:2px;">{swatches}</div>'
            f'</div>'
            f'</button></form>'
        )

    # Current colours and status for display below flags
    colours = _state["colours"]
    team_name = _state["team_name"] or "None"
    goal_active = _state["goal_active"]
    api_remaining = _state["api_remaining"]
    sacn_connected = _state["sacn_connected"]

    cur_swatches = ""
    for rgb in colours:
        hex_c = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        cur_swatches += (
            f'<div style="display:inline-block;width:80px;height:80px;'
            f'background:{hex_c};border:2px solid #555;margin:4px;'
            f'border-radius:6px;text-align:center;line-height:80px;">'
            f'<span style="color:#fff;text-shadow:1px 1px 2px #000;'
            f'font-size:12px;">{rgb[0]:>3},{rgb[1]:>3},{rgb[2]:>3}</span></div>'
        )

    goal_banner = ""
    if goal_active:
        goal_banner = (
            f'<div style="background:#ff4444;color:white;padding:10px;'
            f'text-align:center;font-size:22px;font-weight:bold;'
            f'border-radius:6px;margin:8px 0;animation:blink 0.5s infinite alternate;">'
            f'GOAL! {_flag_svg(team_name, width=40, height=27)} {team_name}</div>'
        )

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>World Cup Colour - Testing</title>
<style>
  @keyframes blink {{ 0% {{ opacity:1; }} 100% {{ opacity:0.4; }} }}
  @keyframes glow {{ 0% {{ box-shadow:0 0 8px #ff4444,0 0 16px #ff4444; }} 100% {{ box-shadow:0 0 4px #ff8800,0 0 8px #ff8800; }} }}
  body {{ background:#1a1a1a; color:#e0e0e0; font-family:'Segoe UI',sans-serif;
         margin:0; padding:20px; }}
  .container {{ max-width:1200px; margin:0 auto; }}
  .header {{ display:flex; align-items:center; justify-content:space-between;
             border-bottom:2px solid #0066cc; padding-bottom:12px; margin-bottom:16px; }}
  h1 {{ color:#0066cc; margin:0; }}
  .status {{ background:#222; padding:12px 20px; border-radius:8px; margin-top:16px; }}
  .active-team {{ border:2px solid #ff4444 !important; animation:glow 0.6s infinite alternate; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>Testing - Remote Flags</h1>
  <img src="data:image/png;base64,{_LOGO_B64}" alt="Diversified" style="height:60px;">
</div>
<p style="color:#888;">Click a country to trigger a goal celebration.</p>
<div id="flags-area">{buttons_html}</div>

<div id="status-area">
{goal_banner}

<div class="status">
  <div style="font-size:18px;font-weight:bold;margin-bottom:8px;">Current: {_flag_svg(team_name, width=40, height=27)} {team_name}</div>
  {cur_swatches}
</div>

<div class="status" style="margin-top:8px;display:flex;gap:24px;align-items:center;">
  <div>
    <span style="font-size:14px;color:#0088ff;font-weight:bold;">API Calls Remaining: </span>
    <span style="font-size:14px;font-family:Consolas,monospace;">{api_remaining if api_remaining else '--'}</span>
  </div>
  <div>
    <span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:{'#28a745' if sacn_connected else '#ff0000'};vertical-align:middle;margin-right:6px;"></span>
    <span style="font-size:14px;font-weight:bold;color:{'#28a745' if sacn_connected else '#ff0000'};">sACN {'Connected' if sacn_connected else 'Disconnected'}</span>
  </div>
</div>

{_build_live_scores_html()}
</div>

</div>
<script>
// Smooth data refresh — update status area without full reload (preserves flag buttons)
var refreshing = false;
function refreshData() {{
  if (refreshing) return;
  refreshing = true;
  fetch(window.location.href, {{cache: 'no-store'}})
    .then(function(r) {{ return r.text(); }})
    .then(function(html) {{
      var parser = new DOMParser();
      var doc = parser.parseFromString(html, 'text/html');
      var ids = ['flags-area', 'status-area'];
      for (var i = 0; i < ids.length; i++) {{
        var newEl = doc.getElementById(ids[i]);
        var curEl = document.getElementById(ids[i]);
        if (newEl && curEl && newEl.innerHTML !== curEl.innerHTML) {{
          curEl.innerHTML = newEl.innerHTML;
        }}
      }}
    }})
    .catch(function() {{}})
    .finally(function() {{ refreshing = false; }});
}}
setInterval(refreshData, 1000);
</script>
</body>
</html>"""
    return html


def _build_sounds_html():
    """Generate the /sounds page: Play/Stop buttons for every loaded sound."""
    list_fn = _sound_callbacks.get("list")
    sounds = list_fn() if list_fn else []

    cards = ""
    for s in sounds:
        name = s.get("name", "")
        playing = s.get("playing", False)
        safe = name.replace('"', '&quot;').replace("'", "&#39;")
        border = "#28a745" if playing else "#444444"
        status = ('<span style="color:#28a745;font-weight:bold;">PLAYING</span>'
                  if playing else '<span style="color:#888;">stopped</span>')
        cards += (
            f'<div style="display:flex;align-items:center;gap:12px;background:#222;'
            f'border:2px solid {border};border-radius:8px;padding:10px 16px;margin:6px 0;">'
            f'<div style="flex:1;font-size:16px;font-weight:bold;color:#e0e0e0;">{name}'
            f'<div style="font-size:12px;margin-top:2px;">{status}</div></div>'
            f'<form method="POST" action="/sounds" style="margin:0;">'
            f'<input type="hidden" name="action" value="play">'
            f'<input type="hidden" name="name" value="{safe}">'
            f'<button type="submit" style="background:#28a745;color:#fff;border:none;'
            f'border-radius:6px;padding:10px 24px;font-size:15px;font-weight:bold;cursor:pointer;">'
            f'Play</button></form>'
            f'<form method="POST" action="/sounds" style="margin:0;">'
            f'<input type="hidden" name="action" value="stop">'
            f'<input type="hidden" name="name" value="{safe}">'
            f'<button type="submit" style="background:#cc0000;color:#fff;border:none;'
            f'border-radius:6px;padding:10px 24px;font-size:15px;font-weight:bold;cursor:pointer;">'
            f'Stop</button></form>'
            f'</div>'
        )
    if not cards:
        cards = '<p style="color:#888;">No sounds loaded.</p>'

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>World Cup Colour - Sounds</title>
<style>
  body {{ background:#1a1a1a; color:#e0e0e0; font-family:'Segoe UI',sans-serif; margin:0; padding:20px; }}
  .container {{ max-width:800px; margin:0 auto; }}
  .header {{ display:flex; align-items:center; justify-content:space-between;
             border-bottom:2px solid #0066cc; padding-bottom:12px; margin-bottom:16px; }}
  h1 {{ color:#0066cc; margin:0; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>Sounds</h1>
  <img src="data:image/png;base64,{_LOGO_B64}" alt="Diversified" style="height:60px;">
</div>
<div id="sounds-area">{cards}</div>
</div>
<script>
// Refresh playing state every second without a full reload
var refreshing = false;
function refreshData() {{
  if (refreshing) return;
  refreshing = true;
  fetch(window.location.href, {{cache:'no-store'}})
    .then(function(r) {{ return r.text(); }})
    .then(function(html) {{
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var cur = document.getElementById('sounds-area');
      var nw = doc.getElementById('sounds-area');
      if (cur && nw && cur.innerHTML !== nw.innerHTML) cur.innerHTML = nw.innerHTML;
    }})
    .catch(function() {{}})
    .finally(function() {{ refreshing = false; }});
}}
setInterval(refreshData, 1000);
</script>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def do_GET(self):
        if self.path == "/api/status":
            body = _build_api_json().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/testing":
            if not _testing_enabled[0]:
                body = b"<html><body style='background:#1a1a1a;color:#ff4444;font-family:sans-serif;text-align:center;padding:80px;'><h1>Testing page is disabled</h1></body></html>"
                self.send_response(403)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = _build_testing_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/sounds":
            body = _build_sounds_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = _build_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        if self.path == "/testing":
            if not _testing_enabled[0]:
                self.send_response(403)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            params = {}
            for pair in body.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[k] = unquote_plus(v)
            action = params.get("action", "")
            team_name = params.get("team", "")
            root = _callbacks.get("root")
            print(f"[WebServer] POST /testing action={action} team={team_name} "
                  f"root={'yes' if root else 'no'} "
                  f"goal_cb={'yes' if _callbacks.get('goal_pressed') else 'no'} "
                  f"team_found={'yes' if team_name in _state['teams'] else 'no'}")
            if team_name == "BLACKOUT":
                colours = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
                cb = _callbacks.get("set_colours")
                if cb and root:
                    root.after(0, lambda: cb(colours, "BLACKOUT"))
            elif team_name and team_name in _state["teams"]:
                colours = _state["teams"][team_name].get("colours",
                           [[0, 0, 0], [0, 0, 0], [0, 0, 0]])
                if action == "goal":
                    cb = _callbacks.get("goal_pressed")
                    if cb and root:
                        root.after(0, lambda c=colours, n=team_name: cb(c, n))
                else:
                    cb = _callbacks.get("set_colours")
                    if cb and root:
                        root.after(0, lambda c=colours, n=team_name: cb(c, n))
            # Redirect back to testing page
            self.send_response(303)
            self.send_header("Location", "/testing")
            self.end_headers()
        elif self.path == "/sounds":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            params = {}
            for pair in body.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[k] = unquote_plus(v)
            action = params.get("action", "")
            name = params.get("name", "")
            root = _callbacks.get("root")
            fn = _sound_callbacks.get("stop") if action == "stop" else _sound_callbacks.get("play")
            # Sound play/stop touch Tk + audio, so run them on the main thread
            if fn and root and name:
                root.after(0, lambda f=fn, n=name: f(n))
            self.send_response(303)
            self.send_header("Location", "/sounds")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress console logging


_server_instance = [None]
_server_thread = [None]
_testing_enabled = [True]


def _start_server(port, status_label, bind_ip="0.0.0.0"):
    """Start the HTTP server on the given port and bind address."""
    if _server_instance[0]:
        _stop_server(status_label)
    try:
        server = HTTPServer((bind_ip, port), _Handler)
        _server_instance[0] = server
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        _server_thread[0] = t
        where = "all interfaces" if bind_ip == "0.0.0.0" else bind_ip
        status_label.config(text=f"Running on {where}:{port}", fg="#28a745")
    except OSError as e:
        status_label.config(text=f"Error: {e}", fg="red")


def _stop_server(status_label):
    """Stop the HTTP server."""
    if _server_instance[0]:
        _server_instance[0].shutdown()
        _server_instance[0] = None
        _server_thread[0] = None
    status_label.config(text="Stopped", fg="red")


def _get_local_ips():
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addr = info[4][0]
            if addr not in ips:
                ips.append(addr)
    except socket.gaierror:
        pass
    if not ips:
        ips.append("127.0.0.1")
    return ips


def build_webserver_tab(notebook, port=8080, goal_pressed_cb=None,
                        set_colours_cb=None):
    """Build the Web Server tab. Returns update_state function."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Web Server")

    _callbacks["root"] = notebook.winfo_toplevel()
    if goal_pressed_cb:
        _callbacks["goal_pressed"] = goal_pressed_cb
    if set_colours_cb:
        _callbacks["set_colours"] = set_colours_cb

    tk.Label(tab, text="Web Server",
             font=("Segoe UI", 14, "bold")).pack(pady=(20, 10))

    # Port config
    port_frame = tk.Frame(tab)
    port_frame.pack(pady=6)
    tk.Label(port_frame, text="Port:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 8))
    port_var = tk.IntVar(value=port)
    tk.Entry(port_frame, textvariable=port_var, font=("Consolas", 11),
             width=8, justify="center").pack(side="left")

    # Bind adapter dropdown (only one can be selected)
    _ALL_LABEL = "All interfaces (0.0.0.0)"

    def _bind_options():
        opts = [_ALL_LABEL]
        for ip in _get_local_ips():
            if ip not in opts:
                opts.append(ip)
        return opts

    def _ip_to_label(ip):
        return _ALL_LABEL if ip in ("", "0.0.0.0") else ip

    def _label_to_ip(label):
        return "0.0.0.0" if label == _ALL_LABEL else label

    bind_frame = tk.Frame(tab)
    bind_frame.pack(pady=6)
    tk.Label(bind_frame, text="Bind to adapter:",
             font=("Segoe UI", 11)).pack(side="left", padx=(0, 8))
    saved_bind_ip = get_config("webserver", "bind_ip", fallback="0.0.0.0")
    bind_options = _bind_options()
    saved_label = _ip_to_label(saved_bind_ip)
    if saved_label not in bind_options:
        bind_options.append(saved_label)
    bind_var = tk.StringVar(value=saved_label)
    bind_combo = ttk.Combobox(bind_frame, textvariable=bind_var,
                              values=bind_options, state="readonly",
                              font=("Consolas", 11), width=28)
    bind_combo.pack(side="left")

    def _on_bind_change(*_args):
        new_ip = _label_to_ip(bind_var.get())
        set_config("webserver", "bind_ip", new_ip)
        # Reflect the new binding in the Access URLs list
        _update_urls()
        # Restart immediately if currently running so the change takes effect
        if _server_instance[0]:
            _start_server(port_var.get(), status_label, new_ip)

    bind_combo.bind("<<ComboboxSelected>>", _on_bind_change)

    # Status
    status_label = tk.Label(tab, text="Stopped", font=("Consolas", 10), fg="red")

    # Buttons
    btn_frame = tk.Frame(tab)
    btn_frame.pack(pady=15)

    def _start():
        _start_server(port_var.get(), status_label, _label_to_ip(bind_var.get()))

    def _stop():
        _stop_server(status_label)

    tk.Button(btn_frame, text="Start", font=("Segoe UI", 11, "bold"),
              bg="#28a745", fg="white", padx=20, pady=4,
              command=_start).pack(side="left", padx=8)

    tk.Button(btn_frame, text="Stop", font=("Segoe UI", 11),
              padx=20, pady=4, command=_stop).pack(side="left", padx=8)

    def _best_ip():
        # If bound to a specific adapter, that's the only address it answers on.
        bound = _label_to_ip(bind_var.get())
        if bound not in ("", "0.0.0.0"):
            return bound
        ips = _get_local_ips()
        for ip in ips:
            if ip != "127.0.0.1":
                return ip
        return ips[0] if ips else "localhost"

    def _open_browser():
        webbrowser.open(f"http://{_best_ip()}:{port_var.get()}/")

    tk.Button(btn_frame, text="Open in Web Browser", font=("Segoe UI", 11, "bold"),
              bg="#0066cc", fg="white", padx=20, pady=4,
              command=_open_browser).pack(side="left", padx=8)

    def _open_testing():
        webbrowser.open(f"http://{_best_ip()}:{port_var.get()}/testing")

    tk.Button(btn_frame, text="Open Testing Page", font=("Segoe UI", 11, "bold"),
              bg="#ff4444", fg="white", padx=20, pady=4,
              command=_open_testing).pack(side="left", padx=8)

    def _open_sounds():
        webbrowser.open(f"http://{_best_ip()}:{port_var.get()}/sounds")

    tk.Button(btn_frame, text="Open Sounds Page", font=("Segoe UI", 11, "bold"),
              bg="#6600cc", fg="white", padx=20, pady=4,
              command=_open_sounds).pack(side="left", padx=8)

    status_label.pack(pady=(5, 10))

    # Testing page toggle
    testing_var = tk.BooleanVar(value=True)

    def _on_testing_toggle(*_args):
        _testing_enabled[0] = testing_var.get()

    testing_var.trace_add("write", _on_testing_toggle)
    tk.Checkbutton(tab, text="Enable Testing Page (/testing)",
                   font=("Segoe UI", 11), variable=testing_var,
                   onvalue=True, offvalue=False).pack(pady=(0, 10))

    # ── Live Status Page sections ─────────────────────────────────────
    sections_frame = tk.LabelFrame(tab, text="Live Status Page Sections",
                                    font=("Segoe UI", 10, "bold"),
                                    padx=12, pady=8)
    sections_frame.pack(padx=30, pady=(0, 10), fill="x")

    list_frame = tk.Frame(sections_frame)
    list_frame.pack(fill="both", expand=True)

    section_listbox = tk.Listbox(list_frame, font=("Segoe UI", 10),
                                  height=len(_SECTION_LABELS),
                                  selectmode="browse", activestyle="none",
                                  bg="#2a2a2a", fg="#e0e0e0",
                                  selectbackground="#0066cc",
                                  selectforeground="white")
    section_listbox.pack(side="left", fill="both", expand=True)

    btn_panel = tk.Frame(list_frame)
    btn_panel.pack(side="left", padx=(8, 0), fill="y")

    def _refresh_listbox():
        """Redraw the listbox from _WEB_SECTION_ORDER."""
        section_listbox.delete(0, "end")
        for key in _WEB_SECTION_ORDER:
            label = _SECTION_LABELS.get(key, key)
            enabled = _WEB_SECTIONS.get(key, True)
            marker = "\u2611" if enabled else "\u2610"
            section_listbox.insert("end", f"  {marker}  {label}")
            if not enabled:
                idx = section_listbox.size() - 1
                section_listbox.itemconfig(idx, fg="#666666")

    def _move_up():
        sel = section_listbox.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        _WEB_SECTION_ORDER[i], _WEB_SECTION_ORDER[i - 1] = (
            _WEB_SECTION_ORDER[i - 1], _WEB_SECTION_ORDER[i])
        _save_section_order()
        _refresh_listbox()
        section_listbox.selection_set(i - 1)
        section_listbox.see(i - 1)

    def _move_down():
        sel = section_listbox.curselection()
        if not sel or sel[0] >= len(_WEB_SECTION_ORDER) - 1:
            return
        i = sel[0]
        _WEB_SECTION_ORDER[i], _WEB_SECTION_ORDER[i + 1] = (
            _WEB_SECTION_ORDER[i + 1], _WEB_SECTION_ORDER[i])
        _save_section_order()
        _refresh_listbox()
        section_listbox.selection_set(i + 1)
        section_listbox.see(i + 1)

    def _toggle_enabled():
        sel = section_listbox.curselection()
        if not sel:
            return
        i = sel[0]
        key = _WEB_SECTION_ORDER[i]
        new_val = not _WEB_SECTIONS.get(key, True)
        _WEB_SECTIONS[key] = new_val
        set_webserver_bool(key, new_val)
        _refresh_listbox()
        section_listbox.selection_set(i)

    tk.Button(btn_panel, text="\u25B2 Up", font=("Segoe UI", 9, "bold"),
              width=8, command=_move_up).pack(pady=(0, 4))
    tk.Button(btn_panel, text="\u25BC Down", font=("Segoe UI", 9, "bold"),
              width=8, command=_move_down).pack(pady=(0, 8))
    tk.Button(btn_panel, text="\u2611 Toggle", font=("Segoe UI", 9, "bold"),
              width=8, bg="#0066cc", fg="white",
              command=_toggle_enabled).pack(pady=(0, 4))

    _refresh_listbox()
    section_listbox.selection_set(0)

    # URLs
    url_frame = tk.LabelFrame(tab, text="Access URLs", font=("Segoe UI", 10),
                               padx=12, pady=8)
    url_frame.pack(padx=30, pady=(5, 10), fill="x")

    url_labels = []
    for ip in _get_local_ips():
        lbl = tk.Label(url_frame, text="", font=("Consolas", 10), fg="#0088ff",
                       anchor="w")
        lbl.pack(anchor="w")
        url_labels.append((lbl, ip))

    api_label = tk.Label(url_frame, text="", font=("Consolas", 9), fg="#888888",
                          anchor="w")
    api_label.pack(anchor="w", pady=(8, 0))

    def _update_urls(*_args):
        p = port_var.get()
        bound = _label_to_ip(bind_var.get())
        all_ifaces = bound in ("", "0.0.0.0")
        # Show every adapter when bound to all interfaces, otherwise just the
        # one the server actually answers on.
        any_shown = False
        for lbl, ip in url_labels:
            if all_ifaces or ip == bound:
                lbl.config(text=f"http://{ip}:{p}/")
                lbl.pack(anchor="w", before=api_label)
                any_shown = True
            else:
                lbl.pack_forget()
        # Fallback: if the bound IP has no matching label, show them all
        # rather than an empty list.
        if not any_shown:
            for lbl, ip in url_labels:
                lbl.config(text=f"http://{ip}:{p}/")
                lbl.pack(anchor="w", before=api_label)
        api_label.config(text=f"JSON API: http://localhost:{p}/api/status    |    Testing: http://localhost:{p}/testing    |    Sounds: http://localhost:{p}/sounds")

    port_var.trace_add("write", _update_urls)
    _update_urls()

    # Auto-start
    tab.after(500, _start)

    return update_state
