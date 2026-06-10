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

                    fixtures[fid] = {
                        "id": fid,
                        "starting_at": fix.get("starting_at", ""),
                        "home": home_local,
                        "away": away_local,
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

    # Scrollable container
    container = tk.Frame(tab)
    container.pack(fill="both", expand=True)

    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas)

    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    # Las Vegas clock panel on the right (primary)
    clock_frame = tk.Frame(container, padx=32, pady=24)
    clock_frame.pack(side="right", fill="y")
    tk.Label(clock_frame, text="Las Vegas", font=("Segoe UI", 20, "bold"),
             fg="#cc6600").pack(anchor="n")
    lv_time_label = tk.Label(clock_frame, text="", font=("Consolas", 36, "bold"),
                             fg="#cc6600")
    lv_time_label.pack(anchor="n", pady=(8, 0))
    lv_date_label = tk.Label(clock_frame, text="", font=("Consolas", 22),
                             fg="#888888")
    lv_date_label.pack(anchor="n", pady=(4, 0))

    # UTC clock
    ttk.Separator(clock_frame, orient="horizontal").pack(fill="x", pady=(24, 16))
    tk.Label(clock_frame, text="UTC", font=("Segoe UI", 20, "bold"),
             fg="#0066cc").pack(anchor="n")
    utc_time_label = tk.Label(clock_frame, text="", font=("Consolas", 36, "bold"),
                              fg="#0066cc")
    utc_time_label.pack(anchor="n", pady=(8, 0))
    utc_date_label = tk.Label(clock_frame, text="", font=("Consolas", 22),
                              fg="#888888")
    utc_date_label.pack(anchor="n", pady=(4, 0))

    def _update_clock():
        now_utc = datetime.now(timezone.utc)
        utc_time_label.config(text=now_utc.strftime("%H:%M:%S"))
        utc_date_label.config(text=now_utc.strftime("%a %d %b %Y"))
        now_lv = now_utc.astimezone(lv_tz)
        lv_time_label.config(text=now_lv.strftime("%H:%M:%S"))
        lv_date_label.config(text=now_lv.strftime("%a %d %b %Y"))
        tab.after(1000, _update_clock)
    _update_clock()

    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    # Status label
    count_label = tk.Label(scroll_frame, text=f"{len(all_games)} fixtures loaded from Schedule data",
                           font=("Segoe UI", 9), fg="#888888")
    count_label.pack(anchor="w", padx=24, pady=(8, 0))

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
            tk.Frame(scroll_frame, height=12).pack(fill="x")
            date_bar = tk.Frame(scroll_frame, bg="#0066cc", padx=16, pady=8)
            date_bar.pack(fill="x", padx=16, pady=(16, 0))
            tk.Label(date_bar, text=date_str, font=("Segoe UI", 24, "bold"),
                     fg="white", bg="#0066cc").pack(side="left")
            tk.Label(date_bar, text="  (Las Vegas)", font=("Segoe UI", 14),
                     fg="#aaccff", bg="#0066cc").pack(side="left")

        # Match row
        row = tk.Frame(scroll_frame, padx=24, pady=6)
        row.pack(fill="x")

        # Timeline dot
        dot_canvas = tk.Canvas(row, width=24, height=24, highlightthickness=0)
        dot_canvas.create_oval(4, 4, 20, 20, fill="#0066cc", outline="#0066cc")
        dot_canvas.pack(side="left", padx=(8, 8))

        # Game ID
        game_id = game.get("id", "")
        tk.Label(row, text=str(game_id),
                 font=("Consolas", 11), fg="#555555", width=10,
                 anchor="w").pack(side="left", padx=(0, 8))

        # Las Vegas time (primary) + UTC
        time_display = f"{time_lv} LV / {time_utc} UTC"
        tk.Label(row, text=time_display,
                 font=("Consolas", 18, "bold"), fg="#0066cc", width=22,
                 anchor="w").pack(side="left", padx=(0, 8))

        # Group label
        group_letter = group_map.get(game.get("group_id"), "")
        tk.Label(row, text=group_letter, font=("Consolas", 18), width=3,
                 fg="#888888", anchor="w").pack(side="left")

        # Home team with swatches
        home = game["home"]
        home_colours = db.get("teams", {}).get(home, {}).get("colours", DEFAULT_TEAM_COLOURS)
        tk.Label(row, text=home, font=("Segoe UI", 20), width=14, anchor="w").pack(side="left")
        for rgb in home_colours:
            hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            sw = tk.Canvas(row, width=28, height=28, highlightthickness=1, highlightbackground="#666")
            sw.create_rectangle(0, 0, 28, 28, fill=hex_col, outline="")
            sw.pack(side="left", padx=2)

        tk.Button(row, text="Send", font=("Segoe UI", 14), padx=6,
                  command=lambda c=home_colours, n=home: set_team_colours_cb(c, n)
                  ).pack(side="left", padx=2)
        tk.Button(row, text="GOAL!", font=("Segoe UI", 14, "bold"),
                  bg="#ff4444", fg="white", padx=6,
                  command=lambda c=home_colours, n=home: goal_pressed_cb(c, n)
                  ).pack(side="left", padx=(2, 12))

        tk.Label(row, text="vs", font=("Segoe UI", 18), fg="#999999").pack(side="left", padx=8)

        # Away team with swatches
        away = game["away"]
        away_colours = db.get("teams", {}).get(away, {}).get("colours", DEFAULT_TEAM_COLOURS)
        tk.Label(row, text=away, font=("Segoe UI", 20), width=14, anchor="w").pack(side="left")
        for rgb in away_colours:
            hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            sw = tk.Canvas(row, width=28, height=28, highlightthickness=1, highlightbackground="#666")
            sw.create_rectangle(0, 0, 28, 28, fill=hex_col, outline="")
            sw.pack(side="left", padx=2)

        tk.Button(row, text="Send", font=("Segoe UI", 14), padx=6,
                  command=lambda c=away_colours, n=away: set_team_colours_cb(c, n)
                  ).pack(side="left", padx=2)
        tk.Button(row, text="GOAL!", font=("Segoe UI", 14, "bold"),
                  bg="#ff4444", fg="white", padx=6,
                  command=lambda c=away_colours, n=away: goal_pressed_cb(c, n)
                  ).pack(side="left", padx=2)

        # Venue
        venue_id = game.get("venue_id")
        venue_name = venues.get(venue_id, "")
        if venue_name:
            tk.Label(row, text=f"  {venue_name}", font=("Segoe UI", 16),
                     fg="#888888", anchor="w").pack(side="left", padx=(16, 0))
