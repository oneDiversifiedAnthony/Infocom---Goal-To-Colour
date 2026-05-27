import tkinter as tk
from tkinter import ttk

COLS = 7
ROWS = 7
FONT_SMALL = ("Segoe UI", 10, "bold")
FONT_BIG = ("Segoe UI", 20, "bold")
BG = "#1e1e1e"
BG_BTN = "#2d2d2d"
FG = "#e0e0e0"


def build_flags_tab(notebook, db, set_team_colours_cb):
    """Build the Flags tab as a grid of buttons filling the entire space."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Flags")

    for c in range(COLS):
        tab.columnconfigure(c, weight=1, uniform="col")
    for r in range(ROWS):
        tab.rowconfigure(r, weight=1, uniform="row")

    _add_grid_button(tab, 0, 0, "BLACKOUT",
                     [[0, 0, 0], [0, 0, 0], [0, 0, 0]], set_team_colours_cb)

    teams_sorted = sorted(db["teams"].keys())
    for idx, country in enumerate(teams_sorted):
        team_data = db["teams"][country]
        colours = team_data.get("colours", [[128, 128, 128]] * 3)
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

    def bind_recursive(widget):
        widget.bind("<Button-1>", on_click)
        for child in widget.winfo_children():
            bind_recursive(child)

    bind_recursive(btn)
