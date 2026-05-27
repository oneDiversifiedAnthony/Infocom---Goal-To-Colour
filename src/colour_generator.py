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

"""
Legacy standalone colour generator (pre-tabbed-UI version).

Cycles random RGB colours every 3 seconds and allows team selection via a
Countries popup window.  Kept as a standalone entry point for quick testing
of sACN colour output without launching the full tabbed application.

Events handled:
    - update_colour() -- called every 3 s via after(); generates random colours
      when no team is selected.
    - set_team_colours(colours, country_name) -- locks display to a team's colours.
    - reset_to_random() -- clears team lock and resumes random cycling.
    - open_countries() -- spawns the CountriesWindow as a child Toplevel.

Design decisions:
    - This file is intentionally kept separate from gui.py so it can be run with
      ``python "Colour Generator.py"`` for rapid hardware testing without the
      overhead of tabs, schedules, or chase controllers.
    - The 3-second random interval is a deliberate choice: fast enough to verify
      that sACN output is working, slow enough to read the RGB values on screen.
"""

import tkinter as tk
import random
from src.countries import CountriesWindow


class ColourGenerator:
    def __init__(self, root, sacn_connection=None):
        self.root = root
        self.sacn = sacn_connection
        self.root.title("Colour Generator")
        self.root.resizable(False, False)

        self.team_colours = None
        self.team_name = None

        # Team name label (shown when a team is selected)
        self.team_label = tk.Label(self.root, text="Random", font=("Segoe UI", 14, "bold"))
        self.team_label.pack(pady=(10, 0))

        # Three swatch boxes side by side
        self.swatch_frame = tk.Frame(self.root)
        self.swatch_frame.pack(padx=20, pady=(10, 0))
        self.swatches = []
        self.swatch_labels = []
        for i in range(3):
            col_frame = tk.Frame(self.swatch_frame)
            col_frame.pack(side="left", padx=6)
            canvas = tk.Canvas(col_frame, width=90, height=90, highlightthickness=1,
                               highlightbackground="#999999")
            canvas.pack()
            lbl = tk.Label(col_frame, text="", font=("Consolas", 9))
            lbl.pack(pady=(2, 0))
            self.swatches.append(canvas)
            self.swatch_labels.append(lbl)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=(10, 15))

        tk.Button(
            btn_frame, text="World Cup Teams",
            font=("Segoe UI", 10),
            command=self.open_countries
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame, text="Random Mode",
            font=("Segoe UI", 10),
            command=self.reset_to_random
        ).pack(side="left", padx=5)

        self.update_colour()

    def open_countries(self):
        CountriesWindow(root=self.root, colour_callback=self.set_team_colours)

    def set_team_colours(self, colours, country_name=""):
        self.team_colours = colours
        self.team_name = country_name
        self.team_label.config(text=self.team_name)
        self._draw_swatches(colours)

    def reset_to_random(self):
        self.team_colours = None
        self.team_name = None
        self.team_label.config(text="Random")

    def _draw_swatches(self, colours):
        for i, rgb in enumerate(colours):
            hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            self.swatches[i].delete("all")
            self.swatches[i].create_rectangle(0, 0, 90, 90, fill=hex_col, outline="")
            self.swatch_labels[i].config(text=f"{rgb[0]},{rgb[1]},{rgb[2]}")
        if self.sacn:
            self.sacn.send_rgb(colours)

    def update_colour(self):
        if not self.team_colours:
            colours = [
                [random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)]
                for _ in range(3)
            ]
            self._draw_swatches(colours)

        self.root.after(3000, self.update_colour)  # why: 3 s is fast enough to confirm sACN output, slow enough to read RGB values


if __name__ == "__main__":
    root = tk.Tk()
    ColourGenerator(root)
    root.mainloop()
