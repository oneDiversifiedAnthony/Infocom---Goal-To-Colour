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

"""Country Editor tab -- edit team colours via colour picker and view trigger channels.

Handles events:
    - Clicking a colour swatch opens the native OS colour picker.
    - Selecting a new colour saves to countries.json immediately.
    - Send button outputs that team's colours to the sACN channels.

Key design decisions:
    - Uses tkinter colorchooser for the native OS colour picker dialog.
    - Saves to countries.json immediately on pick for instant persistence (no save button).
    - Grid layout with column constants (COL_NAME, COL_SW1, etc.) keeps alignment
      consistent and makes column references readable throughout the code.
"""

import tkinter as tk
from tkinter import ttk, colorchooser
import json
import os
import threading

COUNTRIES_FILE = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "assets", "countries.json")
from src.config import ANTHEMS_DIR

SWATCH_SIZE = 28


def _load_countries():
    with open(COUNTRIES_FILE, "r") as f:
        return json.load(f)


def _save_countries(data):
    with open(COUNTRIES_FILE, "w") as f:
        json.dump(data, f, indent=2)  # why: indent=2 keeps JSON human-readable for hand-editing


# why: column constants keep grid alignment consistent and column references readable
COL_NAME = 0
COL_SW1 = 1
COL_RGB1 = 2
COL_SW2 = 3
COL_RGB2 = 4
COL_SW3 = 5
COL_RGB3 = 6
COL_UNIV = 7
COL_CH = 8
COL_SEND = 9
COL_ANTHEM = 10
COL_PLAY = 11
COL_SM_ID = 12
COL_COUNTRY_ID = 13


def build_country_editor_tab(notebook, set_team_colours_cb):
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Country Editor")

    data = _load_countries()

    # Track currently playing anthem for stop
    _playing = [None]  # pygame Sound object

    # ── Fixed header ────────────────────────────────────────────────────
    header_frame = tk.Frame(tab)
    header_frame.pack(fill="x", padx=12, pady=(6, 0))

    header_grid = tk.Frame(header_frame)
    header_grid.pack(fill="x")

    tk.Label(header_grid, text="Country", font=("Segoe UI", 10, "bold"),
             anchor="w", width=16).grid(row=0, column=COL_NAME, sticky="w", padx=(0, 8))
    tk.Label(header_grid, text="Colour 1", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=0, column=COL_SW1, columnspan=2, padx=4)
    tk.Label(header_grid, text="Colour 2", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=0, column=COL_SW2, columnspan=2, padx=4)
    tk.Label(header_grid, text="Colour 3", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=0, column=COL_SW3, columnspan=2, padx=4)
    tk.Label(header_grid, text="Univ", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=0, column=COL_UNIV, padx=4)
    tk.Label(header_grid, text="Ch", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=0, column=COL_CH, padx=4)
    tk.Label(header_grid, text="", width=5).grid(row=0, column=COL_SEND)
    tk.Label(header_grid, text="Anthem", font=("Segoe UI", 10, "bold"),
             anchor="w").grid(row=0, column=COL_ANTHEM, sticky="w", padx=4)
    tk.Label(header_grid, text="", width=3).grid(row=0, column=COL_PLAY)
    tk.Label(header_grid, text="SM ID", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=0, column=COL_SM_ID, padx=4)
    tk.Label(header_grid, text="Country ID", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=0, column=COL_COUNTRY_ID, padx=4)

    ttk.Separator(tab, orient="horizontal").pack(fill="x", padx=12, pady=(2, 0))

    # ── Scrollable area ────────────────────────────────────────────────
    canvas = tk.Canvas(tab, highlightthickness=0)
    scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas)

    scroll_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

    def _on_canvas_configure(e):
        canvas.itemconfig(canvas_window, width=e.width)

    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.bind("<Configure>", _on_canvas_configure)

    # Mouse wheel scrolling
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    # Grid inside scroll_frame
    grid = tk.Frame(scroll_frame)
    grid.pack(fill="x", padx=12, pady=(6, 6))

    # Data rows
    row_idx = 0
    for country in sorted(data["teams"].keys()):
        colours = data["teams"][country]["colours"]
        _add_editor_row(grid, row_idx, country, colours, data,
                        set_team_colours_cb, _playing)
        row_idx += 1

    def stop_preview():
        """Stop any anthem preview playing in the country editor."""
        if _playing[0]:
            _playing[0].stop()
            _playing[0] = None

    return stop_preview


def _add_editor_row(grid, row_idx, country, colours, data,
                    set_team_colours_cb, playing_ref):
    tk.Label(grid, text=country, font=("Segoe UI", 11), anchor="w",
             width=16).grid(row=row_idx, column=COL_NAME, sticky="w", padx=(0, 8), pady=2)

    swatch_canvases = []
    col_pairs = [(COL_SW1, COL_RGB1), (COL_SW2, COL_RGB2), (COL_SW3, COL_RGB3)]

    for i, rgb in enumerate(colours):
        sw_col, rgb_col = col_pairs[i]
        hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        swatch = tk.Canvas(grid, width=SWATCH_SIZE, height=SWATCH_SIZE,
                           highlightthickness=1, highlightbackground="#999999")
        swatch.create_rectangle(0, 0, SWATCH_SIZE, SWATCH_SIZE, fill=hex_col, outline="")
        swatch.grid(row=row_idx, column=sw_col, padx=(4, 0), pady=2)
        swatch_canvases.append(swatch)

        lbl = tk.Label(grid, text=f"{rgb[0]},{rgb[1]},{rgb[2]}",
                       font=("Consolas", 8), fg="#666666", width=11, anchor="w")
        lbl.grid(row=row_idx, column=rgb_col, padx=(2, 8), pady=2)

        swatch.bind("<Button-1>",
                    lambda e, idx=i, s=swatch, l=lbl, c=country:
                    _pick_colour(e, idx, s, l, c, data, swatch_canvases))
        lbl.bind("<Button-1>",
                 lambda e, idx=i, s=swatch, l=lbl, c=country:
                 _pick_colour(e, idx, s, l, c, data, swatch_canvases))

    # Trigger fields
    trigger = data["teams"][country].get("trigger", {"universe": 2, "channel": 0})
    tk.Label(grid, text=str(trigger["universe"]),
             font=("Consolas", 9), fg="#888888", width=4,
             anchor="center").grid(row=row_idx, column=COL_UNIV, padx=4, pady=2)
    tk.Label(grid, text=str(trigger["channel"]),
             font=("Consolas", 9), fg="#888888", width=4,
             anchor="center").grid(row=row_idx, column=COL_CH, padx=4, pady=2)

    tk.Button(grid, text="Send", font=("Segoe UI", 8),
              command=lambda c=country: set_team_colours_cb(
                  data["teams"][c]["colours"], c)
              ).grid(row=row_idx, column=COL_SEND, padx=(8, 0), pady=2, sticky="w")

    # Anthem path and play button
    anthem = data["teams"][country].get("anthem", "")
    anthem_display = anthem if anthem else "—"
    fg = "#888888" if anthem else "#555555"
    tk.Label(grid, text=anthem_display, font=("Consolas", 7), fg=fg,
             anchor="w", width=30).grid(row=row_idx, column=COL_ANTHEM,
                                         padx=4, pady=2, sticky="w")

    if anthem:
        anthem_path = os.path.join(ANTHEMS_DIR, anthem)

        def _play_anthem(path=anthem_path):
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                if playing_ref[0]:
                    playing_ref[0].stop()
                    playing_ref[0] = None
                snd = pygame.mixer.Sound(path)
                snd.play()
                playing_ref[0] = snd
            except Exception:
                pass

        tk.Button(grid, text="▶", font=("Segoe UI", 8), width=3,
                  command=_play_anthem).grid(row=row_idx, column=COL_PLAY,
                                              padx=2, pady=2)

    # SportMonks ID and Country ID
    sm_id = data["teams"][country].get("sportmonks_id", "")
    country_id = data["teams"][country].get("country_id", "")
    sm_fg = "#888888" if sm_id else "#555555"
    cid_fg = "#888888" if country_id else "#555555"
    tk.Label(grid, text=str(sm_id) if sm_id else "—",
             font=("Consolas", 9), fg=sm_fg, width=8,
             anchor="center").grid(row=row_idx, column=COL_SM_ID, padx=4, pady=2)
    tk.Label(grid, text=str(country_id) if country_id else "—",
             font=("Consolas", 9), fg=cid_fg, width=8,
             anchor="center").grid(row=row_idx, column=COL_COUNTRY_ID, padx=4, pady=2)


def _pick_colour(event, colour_index, swatch, label, country, data, all_swatches):
    current = data["teams"][country]["colours"][colour_index]
    initial = f"#{current[0]:02x}{current[1]:02x}{current[2]:02x}"
    result = colorchooser.askcolor(initialcolor=initial, title=f"{country} - Colour {colour_index + 1}")
    if result and result[0]:
        r, g, b = [int(v) for v in result[0]]
        data["teams"][country]["colours"][colour_index] = [r, g, b]
        hex_col = f"#{r:02x}{g:02x}{b:02x}"
        swatch.delete("all")
        swatch.create_rectangle(0, 0, SWATCH_SIZE, SWATCH_SIZE, fill=hex_col, outline="")
        label.config(text=f"{r},{g},{b}")
        _save_countries(data)  # why: saves immediately on pick for instant persistence -- no separate save button needed
