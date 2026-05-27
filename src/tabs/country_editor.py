import tkinter as tk
from tkinter import ttk, colorchooser
import json
import os

COUNTRIES_FILE = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "assets", "countries.json")

SWATCH_SIZE = 28


def _load_countries():
    with open(COUNTRIES_FILE, "r") as f:
        return json.load(f)


def _save_countries(data):
    with open(COUNTRIES_FILE, "w") as f:
        json.dump(data, f, indent=2)


# Column indices
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


def build_country_editor_tab(notebook, set_team_colours_cb):
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Country Editor")

    data = _load_countries()

    # Scrollable area
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

    # Header row
    row_idx = 0
    tk.Label(grid, text="Country", font=("Segoe UI", 10, "bold"),
             anchor="w").grid(row=row_idx, column=COL_NAME, sticky="w", padx=(0, 8))
    tk.Label(grid, text="Colour 1", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=row_idx, column=COL_SW1, columnspan=2, padx=4)
    tk.Label(grid, text="Colour 2", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=row_idx, column=COL_SW2, columnspan=2, padx=4)
    tk.Label(grid, text="Colour 3", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=row_idx, column=COL_SW3, columnspan=2, padx=4)
    tk.Label(grid, text="Univ", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=row_idx, column=COL_UNIV, padx=4)
    tk.Label(grid, text="Ch", font=("Segoe UI", 10, "bold"),
             anchor="center").grid(row=row_idx, column=COL_CH, padx=4)
    tk.Label(grid, text="", width=5).grid(row=row_idx, column=COL_SEND)

    row_idx += 1
    ttk.Separator(grid, orient="horizontal").grid(
        row=row_idx, column=0, columnspan=10, sticky="ew", pady=(0, 4))

    # Data rows
    row_idx += 1
    for country in sorted(data["teams"].keys()):
        colours = data["teams"][country]["colours"]
        _add_editor_row(grid, row_idx, country, colours, data, set_team_colours_cb)
        row_idx += 1


def _add_editor_row(grid, row_idx, country, colours, data, set_team_colours_cb):
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
        _save_countries(data)
