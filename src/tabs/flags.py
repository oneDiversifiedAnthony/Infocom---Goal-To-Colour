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

from src.theme import BG, BG_LIGHT, FG  # why: import from theme instead of duplicating colour values
from src.constants import DEFAULT_TEAM_COLOURS

COLS = 7  # why: 7x7 grid accommodates up to 48 teams (including BLACKOUT) on one screen
ROWS = 7
FONT_SMALL = ("Segoe UI", 10, "bold")
FONT_BIG = ("Segoe UI", 20, "bold")
BG_BTN = BG_LIGHT  # why: button background uses the theme's lighter shade


def build_flags_tab(notebook, db, set_team_colours_cb):
    """Build the Flags tab as a grid of buttons filling the entire space."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Flags")

    for c in range(COLS):
        tab.columnconfigure(c, weight=1, uniform="col")  # why: uniform weight ensures buttons scale equally with window
    for r in range(ROWS):
        tab.rowconfigure(r, weight=1, uniform="row")

    _add_grid_button(tab, 0, 0, "BLACKOUT",
                     [[0, 0, 0], [0, 0, 0], [0, 0, 0]], set_team_colours_cb)

    teams_sorted = sorted(db["teams"].keys())
    for idx, country in enumerate(teams_sorted):
        team_data = db["teams"][country]
        colours = team_data.get("colours", DEFAULT_TEAM_COLOURS)
        trigger = team_data.get("trigger", {})
        channel = trigger.get("channel", "")
        row = (idx + 1) // COLS
        col = (idx + 1) % COLS
        _add_grid_button(tab, row, col, country, colours, set_team_colours_cb, channel)


def _add_grid_button(parent, row, col, name, colours, callback, channel=""):
    """Create a button that fills its grid cell with country name and colour swatches."""
    btn = tk.Frame(parent, relief="raised", bd=1, cursor="hand2", bg=BG_BTN)
    btn.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)

    # Top half: country name with drop-cap
    name_area = tk.Frame(btn, bg=BG_BTN)
    name_area.pack(side="top", expand=True, fill="both")

    text_row = tk.Frame(name_area, bg=BG_BTN)
    text_row.pack(expand=True)

    first = name[0]
    rest = name[1:]
    lbl_big = tk.Label(text_row, text=first, font=FONT_BIG, bg=BG_BTN, fg=FG)
    lbl_big.pack(side="left")
    lbl_rest = tk.Label(text_row, text=rest, font=FONT_SMALL, bg=BG_BTN, fg=FG)
    lbl_rest.pack(side="left", anchor="s", pady=(0, 4))

    if channel != "":
        lbl_ch = tk.Label(name_area, text=f"Ch {channel}", font=("Segoe UI", 10),
                          bg=BG_BTN, fg="#888888")
        lbl_ch.pack()

    # Bottom half: three colour swatches
    swatch_area = tk.Frame(btn, bg=BG_BTN)
    swatch_area.pack(side="bottom", expand=True, fill="both", padx=2, pady=(0, 2))
    for i in range(3):
        swatch_area.columnconfigure(i, weight=1)
    swatch_area.rowconfigure(0, weight=1)

    for i, rgb in enumerate(colours):
        hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        s = tk.Frame(swatch_area, bg=hex_col)
        s.grid(row=0, column=i, sticky="nsew", padx=1, pady=1)

    # Bind click on entire button and all children
    def on_click(event, c=colours, n=name):
        callback(c, n)

    def bind_recursive(widget):  # why: recursive bind ensures clicks on any child widget (label, swatch) trigger the button
        widget.bind("<Button-1>", on_click)
        for child in widget.winfo_children():
            bind_recursive(child)

    bind_recursive(btn)
