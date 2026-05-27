import tkinter as tk
from tkinter import ttk
import json
import os


class CountriesWindow:
    """Browse World Cup teams by group tab, view flag colours, and send a
    selected team's colours to the Colour Generator display."""

    SWATCH_SIZE = 24
    DB_FILE = os.path.join(os.path.dirname(__file__), os.pardir, "assets", "worldcup_teams.json")

    def __init__(self, root=None, colour_callback=None):
        self.colour_callback = colour_callback
        self.standalone = root is None

        if self.standalone:
            self.root = tk.Tk()
        else:
            self.root = tk.Toplevel(root)

        self.root.title("World Cup 2026 - Teams & Colours")
        self.root.resizable(True, True)
        self.root.geometry("620x500")

        with open(self.DB_FILE, "r") as f:
            self.db = json.load(f)

        self._build_ui()

        if self.standalone:
            self.root.mainloop()

    def _build_ui(self):
        # Header
        tk.Label(
            self.root, text="FIFA World Cup 2026",
            font=("Segoe UI", 16, "bold")
        ).pack(pady=(10, 0))
        tk.Label(
            self.root, text="Teams & Flag Colours",
            font=("Segoe UI", 10)
        ).pack()

        # Notebook with one tab per group
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        for group_key in sorted(self.db["groups"].keys()):
            group = self.db["groups"][group_key]
            tab = tk.Frame(self.notebook)
            self.notebook.add(tab, text=f"Group {group_key}")
            self._populate_group_tab(tab, group)

    def _populate_group_tab(self, tab, group):
        # Teams section
        teams_header = tk.Label(tab, text="Teams", font=("Segoe UI", 12, "bold"), anchor="w")
        teams_header.pack(fill="x", padx=12, pady=(10, 4))

        for country in group["teams"]:
            team_data = self.db["teams"].get(country, {})
            colours = team_data.get("colours", [[128, 128, 128]] * 3)
            self._add_team_row(tab, country, colours)

        # Separator
        ttk.Separator(tab, orient="horizontal").pack(fill="x", padx=12, pady=(10, 6))

        # Games section
        games_header = tk.Label(tab, text="Fixtures", font=("Segoe UI", 12, "bold"), anchor="w")
        games_header.pack(fill="x", padx=12, pady=(4, 4))

        for game in group["games"]:
            date_str = game.get("date", "")
            venue_str = game.get("venue", "")
            match_text = f"{game['home']}  vs  {game['away']}"
            if date_str:
                match_text += f"    {date_str}"
            if venue_str:
                match_text += f"  -  {venue_str}"
            tk.Label(
                tab, text=match_text,
                font=("Consolas", 9), fg="#555555", anchor="w"
            ).pack(anchor="w", padx=20)

    def _add_team_row(self, parent, country, colours):
        row = tk.Frame(parent, padx=12, pady=3)
        row.pack(fill="x")

        # Country name
        tk.Label(
            row, text=country, font=("Segoe UI", 11), width=20, anchor="w"
        ).pack(side="left")

        # Three colour swatches
        for rgb in colours:
            hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            swatch = tk.Canvas(
                row, width=self.SWATCH_SIZE, height=self.SWATCH_SIZE,
                highlightthickness=1, highlightbackground="#999999"
            )
            swatch.create_rectangle(
                0, 0, self.SWATCH_SIZE, self.SWATCH_SIZE,
                fill=hex_col, outline=""
            )
            swatch.pack(side="left", padx=2)

        # RGB text
        rgb_text = "  ".join(f"({r},{g},{b})" for r, g, b in colours)
        tk.Label(
            row, text=rgb_text, font=("Consolas", 8), fg="#666666"
        ).pack(side="left", padx=(8, 0))

        # Send button
        if self.colour_callback:
            btn = tk.Button(
                row, text="Send", font=("Segoe UI", 8),
                command=lambda c=colours, n=country: self._send_colours(c, n)
            )
            btn.pack(side="right")

    def _send_colours(self, colours, country_name):
        if self.colour_callback:
            self.colour_callback(colours, country_name)


if __name__ == "__main__":
    CountriesWindow()
