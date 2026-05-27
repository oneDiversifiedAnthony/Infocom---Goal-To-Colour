import tkinter as tk
from tkinter import ttk


def build_schedule_tab(notebook, db, set_team_colours_cb, goal_pressed_cb):
    """Build the Schedule tab with all fixtures sorted by date."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Schedule")

    # Collect all games, sort by date
    all_games = []
    for group_key, group in db["groups"].items():
        for game in group["games"]:
            all_games.append({**game, "group": group_key})

    date_order = {f"Jun {d}": d for d in range(11, 28)}
    all_games.sort(key=lambda g: date_order.get(g.get("date", ""), 99))

    # Scrollable list
    container = tk.Frame(tab)
    container.pack(fill="both", expand=True)

    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas)

    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    # Header
    hdr = tk.Frame(scroll_frame, padx=8, pady=4)
    hdr.pack(fill="x")
    tk.Label(hdr, text="Date", font=("Segoe UI", 10, "bold"), width=8, anchor="w").pack(side="left")
    tk.Label(hdr, text="Grp", font=("Segoe UI", 10, "bold"), width=4, anchor="w").pack(side="left")
    tk.Label(hdr, text="Match", font=("Segoe UI", 10, "bold"), anchor="w").pack(side="left")
    ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", padx=4)

    current_date = None
    for game in all_games:
        date_str = game.get("date", "TBD")
        if date_str != current_date:
            current_date = date_str
            date_hdr = tk.Frame(scroll_frame, padx=8)
            date_hdr.pack(fill="x", pady=(8, 2))
            tk.Label(date_hdr, text=date_str, font=("Segoe UI", 10, "bold"),
                     fg="#0066cc").pack(side="left")
            ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", padx=8)

        row = tk.Frame(scroll_frame, padx=8, pady=2)
        row.pack(fill="x")

        tk.Label(row, text=game["group"], font=("Consolas", 9), width=3,
                 fg="#888888", anchor="w").pack(side="left")

        # Home team
        home = game["home"]
        home_colours = db["teams"].get(home, {}).get("colours", [[128, 128, 128]] * 3)
        tk.Label(row, text=home, font=("Segoe UI", 10), width=14, anchor="w").pack(side="left")
        tk.Button(row, text="Send", font=("Segoe UI", 7), padx=3,
                  command=lambda c=home_colours, n=home: set_team_colours_cb(c, n)
                  ).pack(side="left", padx=1)
        tk.Button(row, text="GOAL!", font=("Segoe UI", 7, "bold"),
                  bg="#ff4444", fg="white", padx=3,
                  command=lambda c=home_colours, n=home: goal_pressed_cb(c, n)
                  ).pack(side="left", padx=(1, 6))

        tk.Label(row, text="vs", font=("Segoe UI", 9), fg="#999999").pack(side="left", padx=4)

        # Away team
        away = game["away"]
        away_colours = db["teams"].get(away, {}).get("colours", [[128, 128, 128]] * 3)
        tk.Label(row, text=away, font=("Segoe UI", 10), width=14, anchor="w").pack(side="left")
        tk.Button(row, text="Send", font=("Segoe UI", 7), padx=3,
                  command=lambda c=away_colours, n=away: set_team_colours_cb(c, n)
                  ).pack(side="left", padx=1)
        tk.Button(row, text="GOAL!", font=("Segoe UI", 7, "bold"),
                  bg="#ff4444", fg="white", padx=3,
                  command=lambda c=away_colours, n=away: goal_pressed_cb(c, n)
                  ).pack(side="left", padx=1)
