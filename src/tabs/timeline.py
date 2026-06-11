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

"""Timeline tab -- chronological view of all World Cup fixtures from Schedule data.

Reads the cached Schedule/*.json files (fetched from SportMonks API), filters
to World Cup fixtures (league_id 732), deduplicates, and displays them in
chronological order with date headers, colour swatches, and Send / GOAL buttons.
"""

import json
import os
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.constants import DEFAULT_TEAM_COLOURS
from src import scores

SCHEDULE_DIR = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir, "assets", "Schedule"
)
VENUES_FILE = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir, "assets", "venues.json"
)
WORLD_CUP_LEAGUE_ID = 732


def _load_venues():
    """Load venue id → name/city mapping from assets/venues.json."""
    if not os.path.isfile(VENUES_FILE):
        return {}
    try:
        with open(VENUES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        venues = {}
        for vid_str, info in data.items():
            name = info.get("name", "")
            city = info.get("city_name", "")
            label = f"{name}, {city}" if city else name
            venues[int(vid_str)] = label
        return venues
    except Exception:
        return {}


def _load_fixtures_from_schedule(db):
    """Load all World Cup fixtures from assets/Schedule/*.json files.

    Returns a sorted list of fixture dicts with keys:
        id, starting_at, home, away, home_local, away_local,
        stage, round, group_id, venue_id
    """
    # Build sportmonks_id → countries.json team name mapping
    sm_id_to_name = {}
    for team_name, team_info in db.get("teams", {}).items():
        sm_id = team_info.get("sportmonks_id")
        if sm_id:
            sm_id_to_name[sm_id] = team_name

    fixtures = {}
    if not os.path.isdir(SCHEDULE_DIR):
        return []

    for fname in os.listdir(SCHEDULE_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(SCHEDULE_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        for stage in data.get("data", []):
            if not isinstance(stage, dict):
                continue
            if stage.get("league_id") != WORLD_CUP_LEAGUE_ID:
                continue
            stage_name = stage.get("name", "")
            for rnd in stage.get("rounds", []):
                round_name = rnd.get("name", "")
                for fix in rnd.get("fixtures", []):
                    fid = fix.get("id")
                    if not fid or fid in fixtures:
                        continue

                    participants = fix.get("participants", [])
                    home_api = away_api = ""
                    home_local = away_local = ""
                    for p in participants:
                        meta = p.get("meta", {})
                        loc = meta.get("location", "")
                        api_name = p.get("name", "")
                        local_name = sm_id_to_name.get(p.get("id"), "")
                        if loc == "home":
                            home_api = api_name
                            home_local = local_name or api_name
                        elif loc == "away":
                            away_api = api_name
                            away_local = local_name or api_name

                    # Extract score from CURRENT entries
                    home_score = 0
                    away_score = 0
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
                            home_score = int(g)
                        elif sc_data.get("participant") == "away":
                            away_score = int(g)

                    fixtures[fid] = {
                        "id": fid,
                        "starting_at": fix.get("starting_at", ""),
                        "home": home_local,
                        "away": away_local,
                        "home_score": home_score if has_score else None,
                        "away_score": away_score if has_score else None,
                        "stage": stage_name,
                        "round": round_name,
                        "group_id": fix.get("group_id"),
                        "venue_id": fix.get("venue_id"),
                    }

    # Sort by UTC time (which preserves chronological order regardless of timezone)
    return sorted(fixtures.values(), key=lambda f: f["starting_at"])


def _build_group_map(fixtures):
    """Assign group letters A-L based on sorted unique group_ids."""
    group_ids = sorted({f["group_id"] for f in fixtures if f.get("group_id")})
    return {gid: chr(ord("A") + i) for i, gid in enumerate(group_ids)}


def build_timeline_tab(notebook, db, set_team_colours_cb, goal_pressed_cb):
    """Build the Timeline tab with all fixtures in chronological order."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Time Line")

    all_games = _load_fixtures_from_schedule(db)
    group_map = _build_group_map(all_games)
    venues = _load_venues()

    lv_tz = ZoneInfo("America/Los_Angeles")
    to_tz = ZoneInfo("America/Toronto")

    # Scrollable container
    container = tk.Frame(tab)
    container.pack(fill="both", expand=True)

    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas)

    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    # Clock panel on the right
    clock_frame = tk.Frame(container, padx=27, pady=20)
    clock_frame.pack(side="right", fill="y")

    # ── Next game countdown ──────────────────────────────────────────
    countdown_title = tk.Label(clock_frame, text="", font=("Segoe UI", 14, "bold"),
                               fg="#ffcc00")
    countdown_title.pack(anchor="n")
    countdown_label = tk.Label(clock_frame, text="", font=("Consolas", 26, "bold"),
                                fg="#ffcc00")
    countdown_label.pack(anchor="n", pady=(4, 0))
    countdown_match = tk.Label(clock_frame, text="", font=("Segoe UI", 12),
                                fg="#888888")
    countdown_match.pack(anchor="n", pady=(2, 0))
    countdown_sep = ttk.Separator(clock_frame, orient="horizontal")
    countdown_sep.pack(fill="x", pady=(14, 14))

    # Las Vegas clock
    tk.Label(clock_frame, text="Las Vegas", font=("Segoe UI", 17, "bold"),
             fg="#cc6600").pack(anchor="n")
    lv_time_label = tk.Label(clock_frame, text="", font=("Consolas", 30, "bold"),
                             fg="#cc6600")
    lv_time_label.pack(anchor="n", pady=(7, 0))
    lv_date_label = tk.Label(clock_frame, text="", font=("Consolas", 19),
                             fg="#888888")
    lv_date_label.pack(anchor="n", pady=(3, 0))

    # Toronto clock
    ttk.Separator(clock_frame, orient="horizontal").pack(fill="x", pady=(20, 14))
    tk.Label(clock_frame, text="Toronto", font=("Segoe UI", 17, "bold"),
             fg="#cc0066").pack(anchor="n")
    to_time_label = tk.Label(clock_frame, text="", font=("Consolas", 30, "bold"),
                              fg="#cc0066")
    to_time_label.pack(anchor="n", pady=(7, 0))
    to_date_label = tk.Label(clock_frame, text="", font=("Consolas", 19),
                              fg="#888888")
    to_date_label.pack(anchor="n", pady=(3, 0))

    # UTC clock
    ttk.Separator(clock_frame, orient="horizontal").pack(fill="x", pady=(20, 14))
    tk.Label(clock_frame, text="UTC", font=("Segoe UI", 17, "bold"),
             fg="#0066cc").pack(anchor="n")
    utc_time_label = tk.Label(clock_frame, text="", font=("Consolas", 30, "bold"),
                              fg="#0066cc")
    utc_time_label.pack(anchor="n", pady=(7, 0))
    utc_date_label = tk.Label(clock_frame, text="", font=("Consolas", 19),
                              fg="#888888")
    utc_date_label.pack(anchor="n", pady=(3, 0))

    def _find_next_game_today(now_utc):
        """Find the next upcoming game today (UTC date)."""
        today_str = now_utc.strftime("%Y-%m-%d")
        for g in all_games:
            sa = g["starting_at"]
            if not sa.startswith(today_str):
                continue
            try:
                kick = datetime.strptime(sa, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if kick > now_utc:
                return g, kick
        return None, None

    def _update_clock():
        now_utc = datetime.now(timezone.utc)
        utc_time_label.config(text=now_utc.strftime("%H:%M:%S"))
        utc_date_label.config(text=now_utc.strftime("%a %d %b %Y"))
        now_lv = now_utc.astimezone(lv_tz)
        lv_time_label.config(text=now_lv.strftime("%H:%M:%S"))
        lv_date_label.config(text=now_lv.strftime("%a %d %b %Y"))
        now_to = now_utc.astimezone(to_tz)
        to_time_label.config(text=now_to.strftime("%H:%M:%S"))
        to_date_label.config(text=now_to.strftime("%a %d %b %Y"))

        # Countdown to next game today
        game, kick = _find_next_game_today(now_utc)
        if game and kick:
            diff = int((kick - now_utc).total_seconds())
            h, rem = divmod(diff, 3600)
            m, s = divmod(rem, 60)
            countdown_title.config(text="TIME UNTIL NEXT GAME")
            countdown_label.config(text=f"{h:02d}:{m:02d}:{s:02d}")
            countdown_match.config(text=f"{game['home']} vs {game['away']}")
            countdown_sep.pack(fill="x", pady=(14, 14))
        else:
            countdown_title.config(text="")
            countdown_label.config(text="")
            countdown_match.config(text="")

        tab.after(1000, _update_clock)
    _update_clock()

    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    # Register fixtures for score tracking
    scores.register_fixtures(all_games)

    # Status label
    count_label = tk.Label(scroll_frame, text=f"{len(all_games)} fixtures loaded from Schedule data",
                           font=("Segoe UI", 8), fg="#888888")
    count_label.pack(anchor="w", padx=20, pady=(7, 0))

    # Track widgets that need live updates (dot, time label, score label)
    live_widgets = []  # list of (fixture_id, dot_canvas, time_label, score_label)

    current_date = None
    for game in all_games:
        starting_at = game.get("starting_at", "")
        if not starting_at:
            continue

        # Parse datetime
        try:
            utc_dt = datetime.strptime(starting_at, "%Y-%m-%d %H:%M:%S")
            utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        lv_dt = utc_dt.astimezone(lv_tz)
        date_str = lv_dt.strftime("%a %d %b %Y")
        time_lv = lv_dt.strftime("%H:%M")
        time_utc = utc_dt.strftime("%H:%M")

        # Date header (grouped by Las Vegas date)
        if date_str != current_date:
            current_date = date_str
            tk.Frame(scroll_frame, height=10).pack(fill="x")
            date_bar = tk.Frame(scroll_frame, bg="#0066cc", padx=14, pady=7)
            date_bar.pack(fill="x", padx=14, pady=(14, 0))
            tk.Label(date_bar, text=date_str, font=("Segoe UI", 20, "bold"),
                     fg="white", bg="#0066cc").pack(side="left")
            tk.Label(date_bar, text="  (Las Vegas)", font=("Segoe UI", 12),
                     fg="#aaccff", bg="#0066cc").pack(side="left")

        fixture_id = game.get("id", "")

        # Match row
        row = tk.Frame(scroll_frame, padx=20, pady=5)
        row.pack(fill="x")

        # Timeline dot (changes to green when live)
        dot_canvas = tk.Canvas(row, width=20, height=20, highlightthickness=0)
        dot_canvas.create_oval(3, 3, 17, 17, fill="#0066cc", outline="#0066cc")
        dot_canvas.pack(side="left", padx=(7, 7))

        # Game ID
        tk.Label(row, text=str(fixture_id),
                 font=("Consolas", 9), fg="#555555", width=10,
                 anchor="w").pack(side="left", padx=(0, 7))

        # Las Vegas time (primary) + UTC (changes to green when live)
        time_display = f"{time_lv} LV / {time_utc} UTC"
        time_label = tk.Label(row, text=time_display,
                 font=("Consolas", 15, "bold"), fg="#0066cc", width=22,
                 anchor="w")
        time_label.pack(side="left", padx=(0, 7))

        # Group label
        group_letter = group_map.get(game.get("group_id"), "")
        tk.Label(row, text=group_letter, font=("Consolas", 15), width=3,
                 fg="#888888", anchor="w").pack(side="left")

        # Home label + team with swatches
        home = game["home"]
        home_colours = db.get("teams", {}).get(home, {}).get("colours", DEFAULT_TEAM_COLOURS)
        tk.Label(row, text="H", font=("Consolas", 10, "bold"), fg="#666666",
                 width=2).pack(side="left")
        tk.Label(row, text=home, font=("Segoe UI", 17), width=14, anchor="w").pack(side="left")
        for rgb in home_colours:
            hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            sw = tk.Canvas(row, width=24, height=24, highlightthickness=1, highlightbackground="#666")
            sw.create_rectangle(0, 0, 24, 24, fill=hex_col, outline="")
            sw.pack(side="left", padx=2)

        # Score display (updated live)
        score_label = tk.Label(row, text="", font=("Consolas", 17, "bold"),
                               fg="#ffcc00", width=7, anchor="center")
        score_label.pack(side="left", padx=4)

        # Away label + team with swatches
        away = game["away"]
        away_colours = db.get("teams", {}).get(away, {}).get("colours", DEFAULT_TEAM_COLOURS)
        tk.Label(row, text="A", font=("Consolas", 10, "bold"), fg="#666666",
                 width=2).pack(side="left")
        tk.Label(row, text=away, font=("Segoe UI", 17), width=14, anchor="w").pack(side="left")
        for rgb in away_colours:
            hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            sw = tk.Canvas(row, width=24, height=24, highlightthickness=1, highlightbackground="#666")
            sw.create_rectangle(0, 0, 24, 24, fill=hex_col, outline="")
            sw.pack(side="left", padx=2)


        # Venue
        venue_id = game.get("venue_id")
        venue_name = venues.get(venue_id, "")
        if venue_name:
            tk.Label(row, text=f"  {venue_name}", font=("Segoe UI", 14),
                     fg="#888888", anchor="w").pack(side="left", padx=(14, 0))

        # Match clock (updated live, shown to the right of venue)
        clock_label = tk.Label(row, text="", font=("Consolas", 14, "bold"),
                               fg="#28a745", anchor="w")
        clock_label.pack(side="left", padx=(10, 0))

        live_widgets.append((fixture_id, dot_canvas, time_label, score_label, clock_label))

    def _refresh_live():
        """Update live indicators, scores, and match clock every 10 seconds."""
        scores.update_live_flags()
        for fid, dot, time_lbl, score_lbl, clock_lbl in live_widgets:
            live = scores.is_live(fid)
            colour = "#28a745" if live else "#0066cc"
            dot.delete("all")
            dot.create_oval(3, 3, 17, 17, fill=colour, outline=colour)
            time_lbl.config(fg=colour)
            score_text = scores.get_score_display(fid)
            if score_text:
                score_lbl.config(text=score_text,
                                 fg="#28a745" if live else "#ffcc00")
            else:
                score_lbl.config(text="", fg="#ffcc00")
            clock_text = scores.get_match_clock(fid)
            clock_lbl.config(text=clock_text)
        tab.after(10000, _refresh_live)
    _refresh_live()
