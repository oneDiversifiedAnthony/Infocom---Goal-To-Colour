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
Bottom status bar widget for the main application window.

Displays live colour swatches with RGB values, a trigger-status label with a
countdown progress bar, and a source-info readout (team name and trigger channel).

Events handled:
    - update(colours, team_name, team_colours, countries_db) -- refreshes all
      status indicators whenever the active colour output changes.

Design decisions:
    - The bar is packed with side="bottom" BEFORE the main Notebook widget so that
      tkinter's packer guarantees it stays anchored at the bottom even when the
      window is resized (widgets packed first get layout priority).
    - The trigger progress bar uses orange (#ff9800) for high visibility against
      the dark theme background; orange was chosen because it is not used by any
      team colour and therefore cannot be confused with output.
"""

import tkinter as tk
from tkinter import ttk
from src.theme import BG_LIGHT, FG_DIM, ACCENT


class StatusBar:
    def __init__(self, root):
        self.root = root
        bar = tk.Frame(root, relief="sunken", bd=1, bg=BG_LIGHT)
        bar.pack(fill="x", side="bottom", padx=4, pady=(0, 4))  # why: packed bottom-first so it stays anchored during window resize

        # sACN connection indicator
        self.sacn_indicator = tk.Canvas(bar, width=20, height=20, highlightthickness=0, bg=BG_LIGHT)
        self.sacn_indicator.pack(side="left", padx=(16, 0))
        self.sacn_indicator.create_oval(2, 2, 18, 18, fill="red", outline="#555", tags="dot")
        self.sacn_label = tk.Label(bar, text="sACN", font=("Segoe UI", 14),
                                    fg=FG_DIM, bg=BG_LIGHT)
        self.sacn_label.pack(side="left", padx=(4, 12))

        tk.Label(bar, text="OUTPUT:", font=("Segoe UI", 18, "bold"),
                 fg=ACCENT, bg=BG_LIGHT).pack(side="left", padx=(0, 12))

        self.swatches = []
        for _ in range(3):
            swatch = tk.Canvas(bar, width=120, height=40, highlightthickness=2,
                               highlightbackground="#555555", bg=BG_LIGHT)
            swatch.pack(side="left", padx=4, pady=6)
            self.swatches.append(swatch)

        self.trigger_label = tk.Label(bar, text="", font=("Segoe UI", 18, "bold"),
                                      fg=FG_DIM, bg=BG_LIGHT, anchor="center")
        self.trigger_label.pack(side="left", padx=(20, 0), fill="x", expand=True)

        style = ttk.Style()
        style.configure("Trigger.Horizontal.TProgressbar",
                        troughcolor=BG_LIGHT, background="#ff9800", thickness=36)  # why: orange for high visibility against dark theme; not a team colour so no confusion
        self.trigger_progress = ttk.Progressbar(
            bar, orient="horizontal", length=160, mode="determinate",
            style="Trigger.Horizontal.TProgressbar", maximum=100)
        self.trigger_progress.pack(side="left", padx=(16, 0), pady=8)
        self.trigger_progress["value"] = 0

        # ── Rate Limit (right side) ───────────────────────────────────
        self.rate_label = tk.Label(bar, text="", font=("Segoe UI", 18, "bold"),
                                   fg="#cc0000", bg=BG_LIGHT)
        self.rate_label.pack(side="right", padx=(8, 16))

        style.configure("FooterRate.Horizontal.TProgressbar",
                        troughcolor=BG_LIGHT, background="#28a745", thickness=36)
        self.rate_progress = ttk.Progressbar(
            bar, orient="horizontal", length=320, mode="determinate",
            style="FooterRate.Horizontal.TProgressbar", maximum=100)
        self.rate_progress.pack(side="right", padx=(8, 0), pady=8)
        self.rate_progress["value"] = 0

        self.rate_reset_label = tk.Label(bar, text="", font=("Segoe UI", 16),
                                         fg=FG_DIM, bg=BG_LIGHT)
        self.rate_reset_label.pack(side="right", padx=(8, 0))


    def update(self, colours, team_name, team_colours, countries_db):
        for i, rgb in enumerate(colours):
            hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            self.swatches[i].delete("all")
            self.swatches[i].create_rectangle(0, 0, 120, 40, fill=hex_col, outline="")
            text = f"{rgb[0]:>3},{rgb[1]:>3},{rgb[2]:>3}"
            self.swatches[i].create_text(60, 20, text=text,
                                          fill="#ffffff", font=("Consolas", 12, "bold"),
                                          anchor="center")

    def update_rate_limit(self, remaining, total, resets_in, api_ok=True):
        self.rate_label.config(text=f"API: {remaining}",
                               fg="#28a745" if api_ok else "#ff0000")
        minutes = resets_in // 60
        seconds = resets_in % 60
        self.rate_reset_label.config(text=f"{minutes}m{seconds}s")

        if total > 0:
            pct = (remaining / total) * 100
            self.rate_progress["value"] = pct
            style = ttk.Style()
            if pct < 10:
                style.configure("FooterRate.Horizontal.TProgressbar", background="#ff0000")
            elif pct < 25:
                style.configure("FooterRate.Horizontal.TProgressbar", background="#ff0000")
            elif pct < 50:
                style.configure("FooterRate.Horizontal.TProgressbar", background="#ff6600")
            else:
                style.configure("FooterRate.Horizontal.TProgressbar", background="#28a745")

    def update_sacn_status(self, connected):
        """Update the sACN connection indicator."""
        colour = "#28a745" if connected else "red"
        self.sacn_indicator.delete("dot")
        self.sacn_indicator.create_oval(2, 2, 18, 18, fill=colour, outline="#555", tags="dot")
        self.sacn_label.config(fg=colour)
