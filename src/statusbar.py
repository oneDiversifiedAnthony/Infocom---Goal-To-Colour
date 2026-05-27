import tkinter as tk
from tkinter import ttk
from src.theme import BG_LIGHT, FG_DIM, ACCENT


class StatusBar:
    def __init__(self, root):
        self.root = root
        bar = tk.Frame(root, relief="sunken", bd=1, bg=BG_LIGHT)
        bar.pack(fill="x", side="bottom", padx=4, pady=(0, 4))

        tk.Label(bar, text="OUTPUT:", font=("Segoe UI", 9, "bold"),
                 fg=ACCENT, bg=BG_LIGHT).pack(side="left", padx=(8, 6))

        self.swatches = []
        self.labels = []
        for _ in range(3):
            swatch = tk.Canvas(bar, width=20, height=20, highlightthickness=1,
                               highlightbackground="#555555", bg=BG_LIGHT)
            swatch.pack(side="left", padx=2, pady=3)
            self.swatches.append(swatch)

            lbl = tk.Label(bar, text="0,0,0", font=("Consolas", 8), fg=FG_DIM, bg=BG_LIGHT)
            lbl.pack(side="left", padx=(0, 10))
            self.labels.append(lbl)

        self.trigger_label = tk.Label(bar, text="", font=("Segoe UI", 9, "bold"),
                                      fg=FG_DIM, bg=BG_LIGHT)
        self.trigger_label.pack(side="left", padx=(10, 0))

        style = ttk.Style()
        style.configure("Trigger.Horizontal.TProgressbar",
                        troughcolor=BG_LIGHT, background="#ff9800", thickness=10)
        self.trigger_progress = ttk.Progressbar(
            bar, orient="horizontal", length=80, mode="determinate",
            style="Trigger.Horizontal.TProgressbar", maximum=100)
        self.trigger_progress.pack(side="left", padx=(8, 0), pady=4)
        self.trigger_progress["value"] = 0

        self.source_label = tk.Label(bar, text="", font=("Segoe UI", 8),
                                     fg=FG_DIM, bg=BG_LIGHT)
        self.source_label.pack(side="right", padx=(0, 8))

    def update(self, colours, team_name, team_colours, countries_db):
        for i, rgb in enumerate(colours):
            hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            self.swatches[i].delete("all")
            self.swatches[i].create_rectangle(0, 0, 20, 20, fill=hex_col, outline="")
            self.labels[i].config(text=f"{rgb[0]},{rgb[1]},{rgb[2]}")

        source = team_name if team_colours else "Random"
        if team_name:
            team = countries_db.get("teams", {}).get(team_name, {})
            trigger = team.get("trigger")
            if trigger:
                source += f"  |  Univ {trigger['universe']}  Ch {trigger['channel']}"
        self.source_label.config(text=source)
