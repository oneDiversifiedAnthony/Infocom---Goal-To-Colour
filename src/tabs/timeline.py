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

"""Timeline tab -- chronological view of all fixtures with date, venue, teams,
colour swatches, and Send / GOAL! buttons.

Combines the old Groups and Schedule tabs into a single timeline view sorted
by match date, with visual date headers and venue/location info.
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from src.constants import DEFAULT_TEAM_COLOURS


def build_timeline_tab(notebook, db, set_team_colours_cb, goal_pressed_cb):
    """Build the Timeline tab with all fixtures in chronological order."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Time Line")

    # Collect all games from every group, sorted by date
    all_games = []
    for group_key, group in db["groups"].items():
        for game in group["games"]:
            all_games.append({**game, "group": group_key})

    date_order = {f"Jun {d}": d for d in range(11, 28)}
    # Sort by date first, then by UTC time
    def _sort_key(g):
        date_num = date_order.get(g.get("date", ""), 99)
        time_str = g.get("time_utc", "99:99")
        return (date_num, time_str)
    all_games.sort(key=_sort_key)

    # Scrollable container
    container = tk.Frame(tab)
    container.pack(fill="both", expand=True)

    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas)

    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    # UTC clock panel on the right
    clock_frame = tk.Frame(container, padx=32, pady=24)
    clock_frame.pack(side="right", fill="y")
    tk.Label(clock_frame, text="UTC", font=("Segoe UI", 20, "bold"),
             fg="#0066cc").pack(anchor="n")
    utc_time_label = tk.Label(clock_frame, text="", font=("Consolas", 36, "bold"),
                              fg="#0066cc")
    utc_time_label.pack(anchor="n", pady=(8, 0))
    utc_date_label = tk.Label(clock_frame, text="", font=("Consolas", 22),
                              fg="#888888")
    utc_date_label.pack(anchor="n", pady=(4, 0))

    # Las Vegas clock
    ttk.Separator(clock_frame, orient="horizontal").pack(fill="x", pady=(24, 16))
    tk.Label(clock_frame, text="Las Vegas", font=("Segoe UI", 20, "bold"),
             fg="#cc6600").pack(anchor="n")
    lv_time_label = tk.Label(clock_frame, text="", font=("Consolas", 36, "bold"),
                             fg="#cc6600")
    lv_time_label.pack(anchor="n", pady=(8, 0))
    lv_date_label = tk.Label(clock_frame, text="", font=("Consolas", 22),
                             fg="#888888")
    lv_date_label.pack(anchor="n", pady=(4, 0))

    lv_tz = ZoneInfo("America/Los_Angeles")

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

    current_date = None
    for game in all_games:
        date_str = game.get("date", "TBD")
        venue = game.get("venue", "")

        # Date header
        if date_str != current_date:
            current_date = date_str
            if current_date != all_games[0].get("date"):
                # spacer between date groups
                tk.Frame(scroll_frame, height=12).pack(fill="x")
            date_bar = tk.Frame(scroll_frame, bg="#0066cc", padx=16, pady=8)
            date_bar.pack(fill="x", padx=16, pady=(16, 0))
            tk.Label(date_bar, text=date_str, font=("Segoe UI", 24, "bold"),
                     fg="white", bg="#0066cc").pack(side="left")

        # Match row
        row = tk.Frame(scroll_frame, padx=24, pady=6)
        row.pack(fill="x")

        # Timeline dot
        dot_canvas = tk.Canvas(row, width=24, height=24, highlightthickness=0)
        dot_canvas.create_oval(4, 4, 20, 20, fill="#0066cc", outline="#0066cc")
        dot_canvas.pack(side="left", padx=(8, 8))

        # UTC time + Las Vegas time
        time_utc = game.get("time_utc", "")
        if time_utc:
            try:
                utc_dt = datetime.strptime(f"2026 {date_str} {time_utc}", "%Y %b %d %H:%M")
                utc_dt = utc_dt.replace(tzinfo=timezone.utc)
                lv_dt = utc_dt.astimezone(lv_tz)
                time_lv = lv_dt.strftime("%H:%M")
                time_display = f"{time_utc} UTC / {time_lv} LV"
            except ValueError:
                time_display = f"{time_utc} UTC"
        else:
            time_display = ""
        tk.Label(row, text=time_display,
                 font=("Consolas", 18, "bold"), fg="#0066cc", width=22,
                 anchor="w").pack(side="left", padx=(0, 8))

        # Group label
        tk.Label(row, text=game["group"], font=("Consolas", 18), width=3,
                 fg="#888888", anchor="w").pack(side="left")

        # Home team with swatches
        home = game["home"]
        home_colours = db["teams"].get(home, {}).get("colours", DEFAULT_TEAM_COLOURS)
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
        away_colours = db["teams"].get(away, {}).get("colours", DEFAULT_TEAM_COLOURS)
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

        # Venue / location
        if venue:
            tk.Label(row, text=f"  {venue}", font=("Segoe UI", 16),
                     fg="#888888", anchor="w").pack(side="left", padx=(16, 0))
