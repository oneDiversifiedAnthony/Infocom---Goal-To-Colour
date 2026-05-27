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

"""Colour Generator tab -- RGB sliders for custom colour, random mode, and blackout.

Handles events:
    - Slider changes update the live colour preview.
    - PUSH sends the custom colour to all three sACN channels.
    - Random Mode resets to cycling random colours every 3 seconds.
    - BLACKOUT sends black (0,0,0) to all channels.

Returns widget references (gen_team_label, swatches, swatch_labels, _update_colour)
so the App class can update them when a team is selected from other tabs.
"""

import tkinter as tk
import random

from src.constants import SWATCH_CANVAS_SIZE, RANDOM_CYCLE_INTERVAL_MS, DMX_MAX_VALUE


def build_generator_tab(notebook, draw_swatches, get_state, set_state):
    """Build the Colour Generator tab.

    get_state() -> (team_colours, team_name)
    set_state(team_colours, team_name)
    """
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Colour Generator")

    gen_team_label = tk.Label(tab, text="Random", font=("Segoe UI", 14, "bold"))
    gen_team_label.pack(pady=(15, 0))

    swatch_frame = tk.Frame(tab)
    swatch_frame.pack(padx=20, pady=(12, 0))
    swatches = []
    swatch_labels = []
    for _ in range(3):  # why: three swatches match the three sACN colour channels
        col_frame = tk.Frame(swatch_frame)
        col_frame.pack(side="left", padx=8)
        canvas = tk.Canvas(col_frame, width=SWATCH_CANVAS_SIZE, height=SWATCH_CANVAS_SIZE,
                           highlightthickness=1, highlightbackground="#999999")
        canvas.pack()
        lbl = tk.Label(col_frame, text="", font=("Consolas", 10))
        lbl.pack(pady=(4, 0))
        swatches.append(canvas)
        swatch_labels.append(lbl)

    def _reset_to_random():
        set_state(None, None)
        gen_team_label.config(text="Random")

    tk.Button(tab, text="Random Mode", font=("Segoe UI", 10),
              command=_reset_to_random).pack(pady=(15, 5))

    # Colour picker
    picker_frame = tk.LabelFrame(tab, text="Create", font=("Segoe UI", 10), padx=10, pady=6)
    picker_frame.pack(padx=20, pady=(5, 5), fill="x")

    slider_row = tk.Frame(picker_frame)
    slider_row.pack(fill="x")

    r_slider = tk.Scale(slider_row, from_=0, to=DMX_MAX_VALUE, orient="horizontal",
                        label="R", fg="red", length=150, font=("Consolas", 8))
    r_slider.pack(side="left", expand=True, fill="x", padx=2)
    g_slider = tk.Scale(slider_row, from_=0, to=DMX_MAX_VALUE, orient="horizontal",
                        label="G", fg="green", length=150, font=("Consolas", 8))
    g_slider.pack(side="left", expand=True, fill="x", padx=2)
    b_slider = tk.Scale(slider_row, from_=0, to=DMX_MAX_VALUE, orient="horizontal",
                        label="B", fg="blue", length=150, font=("Consolas", 8))
    b_slider.pack(side="left", expand=True, fill="x", padx=2)

    # Preview
    preview_row = tk.Frame(picker_frame)
    preview_row.pack(pady=(6, 2))

    colour_preview = tk.Canvas(preview_row, width=50, height=30,
                               highlightthickness=1, highlightbackground="#999999")
    colour_preview.create_rectangle(0, 0, 50, 30, fill="#000000", outline="")
    colour_preview.pack(side="left", padx=(0, 10))

    preview_label = tk.Label(preview_row, text="0, 0, 0", font=("Consolas", 9))
    preview_label.pack(side="left", padx=(0, 10))

    def _update_preview(*_):
        r, g, b = r_slider.get(), g_slider.get(), b_slider.get()
        hex_col = f"#{r:02x}{g:02x}{b:02x}"
        colour_preview.delete("all")
        colour_preview.create_rectangle(0, 0, 50, 30, fill=hex_col, outline="")
        preview_label.config(text=f"{r}, {g}, {b}")

    r_slider.config(command=_update_preview)
    g_slider.config(command=_update_preview)
    b_slider.config(command=_update_preview)

    def _push_custom():
        r, g, b = r_slider.get(), g_slider.get(), b_slider.get()
        colours = [[r, g, b]] * 3  # why: same colour to all 3 channels for uniform single-colour output
        set_state(colours, "Custom")
        gen_team_label.config(text="Custom")
        draw_swatches(colours)

    tk.Button(preview_row, text="PUSH", font=("Segoe UI", 10, "bold"),
              bg="#0066cc", fg="white", padx=20, pady=2,
              command=_push_custom).pack(side="left")

    def _blackout():
        colours = [[0, 0, 0]] * 3
        set_state(colours, "Blackout")
        gen_team_label.config(text="Blackout")
        draw_swatches(colours)

    tk.Button(tab, text="BLACKOUT", font=("Segoe UI", 12, "bold"),
              bg="#000000", fg="white", padx=30, pady=8,
              command=_blackout).pack(pady=(8, 10))

    def _update_colour():
        team_colours, _ = get_state()
        if not team_colours:
            colours = [
                [random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)]
                for _ in range(3)
            ]
            draw_swatches(colours)
        tab.after(RANDOM_CYCLE_INTERVAL_MS, _update_colour)  # why: 3-second cycle keeps the display lively when no team is selected

    # why: returning widget refs lets the App class update them when a team is selected from other tabs
    return gen_team_label, swatches, swatch_labels, _update_colour
