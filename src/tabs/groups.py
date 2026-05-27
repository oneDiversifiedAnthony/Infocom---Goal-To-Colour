import tkinter as tk
from tkinter import ttk


def build_groups_tab(notebook, db, set_team_colours_cb):
    """Build the Groups tab with sub-tabs A-L."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Groups")

    group_notebook = ttk.Notebook(tab)
    group_notebook.pack(fill="both", expand=True, padx=4, pady=4)

    for group_key in sorted(db["groups"].keys()):
        group = db["groups"][group_key]
        group_tab = tk.Frame(group_notebook)
        group_notebook.add(group_tab, text=f"  {group_key}  ")
        _populate_group_tab(group_tab, group, db, set_team_colours_cb)


def _populate_group_tab(tab, group, db, set_team_colours_cb):
    tk.Label(tab, text="Teams", font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(8, 4))

    for country in group["teams"]:
        team_data = db["teams"].get(country, {})
        colours = team_data.get("colours", [[128, 128, 128]] * 3)
        _add_team_row(tab, country, colours, set_team_colours_cb)

    ttk.Separator(tab, orient="horizontal").pack(fill="x", padx=12, pady=(8, 4))
    tk.Label(tab, text="Fixtures", font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(2, 4))

    for game in group["games"]:
        date_str = game.get("date", "")
        venue_str = game.get("venue", "")
        match_text = f"{game['home']}  vs  {game['away']}"
        if date_str:
            match_text += f"    {date_str}"
        if venue_str:
            match_text += f"  -  {venue_str}"
        tk.Label(tab, text=match_text, font=("Consolas", 9), fg="#555555", anchor="w").pack(anchor="w", padx=20)


def _add_team_row(parent, country, colours, set_team_colours_cb):
    row = tk.Frame(parent, padx=12, pady=3)
    row.pack(fill="x")

    tk.Label(row, text=country, font=("Segoe UI", 11), width=18, anchor="w").pack(side="left")

    for rgb in colours:
        hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        swatch = tk.Canvas(row, width=22, height=22, highlightthickness=1, highlightbackground="#999999")
        swatch.create_rectangle(0, 0, 22, 22, fill=hex_col, outline="")
        swatch.pack(side="left", padx=2)

    rgb_text = "  ".join(f"({r},{g},{b})" for r, g, b in colours)
    tk.Label(row, text=rgb_text, font=("Consolas", 8), fg="#666666").pack(side="left", padx=(8, 0))

    tk.Button(
        row, text="Send", font=("Segoe UI", 8),
        command=lambda c=colours, n=country: set_team_colours_cb(c, n)
    ).pack(side="right")
