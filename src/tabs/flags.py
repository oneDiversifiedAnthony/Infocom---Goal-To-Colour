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

"""Flags tab -- grid of country buttons filling the entire tab space.

Handles events:
    - Clicking any country button (or its child labels/swatches) sends that
      team's colours to the sACN output via set_team_colours_cb.

Key design decisions:
    - 7x7 grid with uniform column/row weights so buttons scale with the window.
    - Drop-cap style (large first letter) makes country names scannable at a glance.
    - Recursive bind ensures clicks on any child widget (label, swatch) bubble up
      to trigger the button callback.
    - BLACKOUT is always first button (position 0,0) for quick emergency access.
"""

import tkinter as tk
from tkinter import ttk
import json
import os

from PIL import ImageTk

from src.theme import BG, BG_LIGHT, FG  # why: import from theme instead of duplicating colour values
from src.constants import DEFAULT_TEAM_COLOURS
from src.svg_renderer import svg_to_image

COLS = 7  # why: fixed column count; row count is computed at build time to fit all teams
ROWS = 7  # minimum row count (grid grows beyond this when there are more teams)
FONT_SMALL = ("Segoe UI", 10, "bold")
FONT_BIG = ("Segoe UI", 20, "bold")
BG_BTN = BG_LIGHT  # why: button background uses the theme's lighter shade
FLAG_W, FLAG_H = 60, 40  # flag image size in pixels

# Load flag SVG data once at import
_FLAGS_FILE = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "assets", "Flags.json")
try:
    with open(_FLAGS_FILE, "r", encoding="utf-8") as _f:
        _FLAGS_DATA = json.load(_f).get("flags", {})
except (FileNotFoundError, json.JSONDecodeError):
    _FLAGS_DATA = {}

# Cache rendered PhotoImages (must persist to prevent garbage collection)
_flag_images = {}


def build_flags_tab(notebook, db, set_team_colours_cb):
    """Build the Flags tab as a grid of buttons filling the entire space.

    Returns a highlight_team(name) callback that blinks the triggered country.
    """
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Flags")

    teams_sorted = sorted(db["teams"].keys())
    total_buttons = len(teams_sorted) + 1  # why: +1 for the always-present BLACKOUT button
    # why: grow rows to fit every button so none spill into unweighted cells (which would
    # collapse to minimum height and clip their colour swatches). Ceiling division.
    rows_needed = max(ROWS, -(-total_buttons // COLS))

    for c in range(COLS):
        tab.columnconfigure(c, weight=1, uniform="col")  # why: uniform weight ensures buttons scale equally with window
    for r in range(rows_needed):
        tab.rowconfigure(r, weight=1, uniform="row")

    button_frames = {}  # country name -> button Frame widget

    button_frames["BLACKOUT"] = _add_grid_button(
        tab, 0, 0, "BLACKOUT",
        [[0, 0, 0], [0, 0, 0], [0, 0, 0]], set_team_colours_cb)

    for idx, country in enumerate(teams_sorted):
        team_data = db["teams"][country]
        colours = team_data.get("colours", DEFAULT_TEAM_COLOURS)
        trigger = team_data.get("trigger", {})
        channel = trigger.get("channel", "")
        row = (idx + 1) // COLS
        col = (idx + 1) % COLS
        button_frames[country] = _add_grid_button(
            tab, row, col, country, colours, set_team_colours_cb, channel)

    # Blink state
    _blink_timer = [None]
    _blink_widget = [None]
    _blink_on = [False]

    HIGHLIGHT_COLOUR = "#ff4444"
    BLINK_INTERVAL_MS = 400

    def _blink_tick():
        widget = _blink_widget[0]
        if widget is None:
            return
        _blink_on[0] = not _blink_on[0]
        colour = HIGHLIGHT_COLOUR if _blink_on[0] else BG_BTN
        widget.config(bg=colour)
        _blink_timer[0] = tab.after(BLINK_INTERVAL_MS, _blink_tick)

    def highlight_team(name):
        # Stop previous blink
        if _blink_timer[0]:
            tab.after_cancel(_blink_timer[0])
            _blink_timer[0] = None
        if _blink_widget[0]:
            _blink_widget[0].config(bg=BG_BTN)
        widget = button_frames.get(name)
        _blink_widget[0] = widget
        if widget:
            _blink_on[0] = False
            _blink_tick()

    return highlight_team


def _get_flag_image(name):
    """Get or render a flag PhotoImage for a country. Returns None if no flag data."""
    if name in _flag_images:
        return _flag_images[name]
    entry = _FLAGS_DATA.get(name)
    if not entry:
        return None
    try:
        pil_img = svg_to_image(entry["svg"], FLAG_W, FLAG_H)
        tk_img = ImageTk.PhotoImage(pil_img)
        _flag_images[name] = tk_img
        return tk_img
    except Exception:
        return None


def _add_grid_button(parent, row, col, name, colours, callback, channel=""):
    """Create a button that fills its grid cell with flag, country name, and colour swatches."""
    btn = tk.Frame(parent, relief="raised", bd=1, cursor="hand2", bg=BG_BTN)
    btn.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)

    # Top: country name with drop-cap
    name_area = tk.Frame(btn, bg=BG_BTN)
    name_area.pack(side="top", fill="x")

    text_row = tk.Frame(name_area, bg=BG_BTN)
    text_row.pack()

    first = name[0]
    rest = name[1:]
    lbl_big = tk.Label(text_row, text=first, font=FONT_BIG, bg=BG_BTN, fg=FG)
    lbl_big.pack(side="left")
    lbl_rest = tk.Label(text_row, text=rest, font=FONT_SMALL, bg=BG_BTN, fg=FG)
    lbl_rest.pack(side="left", anchor="s", pady=(0, 4))

    if channel != "":
        lbl_ch = tk.Label(name_area, text=f"Ch {channel}", font=("Segoe UI", 8),
                          bg=BG_BTN, fg="#888888")
        lbl_ch.pack()

    # Middle: flag image
    flag_img = _get_flag_image(name)
    if flag_img:
        flag_label = tk.Label(btn, image=flag_img, bg=BG_BTN, bd=1, relief="solid")
        flag_label.pack(pady=(0, 1))

    # Bottom: three colour swatches
    swatch_area = tk.Frame(btn, bg=BG_BTN)
    swatch_area.pack(side="bottom", fill="x", padx=2, pady=(0, 2))
    for i in range(3):
        swatch_area.columnconfigure(i, weight=1)

    for i, rgb in enumerate(colours):
        hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        s = tk.Frame(swatch_area, bg=hex_col, height=8)
        s.grid(row=0, column=i, sticky="ew", padx=1)

    # Bind click on entire button and all children
    def on_click(event, c=colours, n=name):
        callback(c, n)

    def bind_recursive(widget):  # why: recursive bind ensures clicks on any child widget (label, swatch) trigger the button
        widget.bind("<Button-1>", on_click)
        for child in widget.winfo_children():
            bind_recursive(child)

    bind_recursive(btn)
    return btn
