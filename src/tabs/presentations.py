# Copyright (c) 2026 oneDiversified.
#
# This software is proprietary and confidential.

"""Presentations Schedule tab -- displays Diversified InfoComm presentations
loaded from assets/DiversifiedPresentations.json with live NOW indicators."""

import json
import os
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from zoneinfo import ZoneInfo

PRESENTATIONS_FILE = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir, "assets", "DiversifiedPresentations.json"
)

_lv_tz = ZoneInfo("America/Los_Angeles")


def _load_presentations():
    """Load presentations from JSON file."""
    try:
        with open(PRESENTATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("presentations", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def build_presentations_tab(notebook):
    """Build the Presentations Schedule tab inside a settings notebook."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Presentations")

    # Header
    tk.Label(tab, text="Diversified InfoComm Presentations",
             font=("Segoe UI", 16, "bold"), fg="#cc6600").pack(pady=(16, 4))
    tk.Label(tab, text="All times are Las Vegas local time",
             font=("Segoe UI", 10), fg="#888888").pack(pady=(0, 8))

    file_label = tk.Label(tab, text=f"Source: {PRESENTATIONS_FILE}",
                          font=("Consolas", 8), fg="#555555")
    file_label.pack(pady=(0, 10))

    # Scrollable area
    container = tk.Frame(tab)
    container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas)

    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    canvas.bind_all("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    presentations = _load_presentations()

    count_label = tk.Label(scroll_frame,
                           text=f"{len(presentations)} presentations loaded",
                           font=("Segoe UI", 9), fg="#888888")
    count_label.pack(anchor="w", padx=14, pady=(4, 6))

    now_labels = []  # track labels to update NOW badges
    current_date = None

    for p in presentations:
        date_str = p.get("date", "")
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            display_date = d.strftime("%A, %B %d, %Y")
        except ValueError:
            display_date = date_str

        # Date header
        if display_date != current_date:
            current_date = display_date
            tk.Frame(scroll_frame, height=6).pack(fill="x")
            bar = tk.Frame(scroll_frame, bg="#cc6600", padx=12, pady=6)
            bar.pack(fill="x", padx=12, pady=(8, 0))
            tk.Label(bar, text=display_date, font=("Segoe UI", 16, "bold"),
                     fg="white", bg="#cc6600").pack(side="left")

        # Presentation card
        card = tk.Frame(scroll_frame, padx=16, pady=6, relief="groove", bd=1)
        card.pack(fill="x", padx=14, pady=3)

        # Top row: time + title
        top = tk.Frame(card)
        top.pack(fill="x")

        start = p.get("start_time", "")
        end = p.get("end_time", "")
        time_label = tk.Label(top, text=f"{start} - {end}",
                              font=("Consolas", 14, "bold"), fg="#cc6600", width=14, anchor="w")
        time_label.pack(side="left")

        # NOW badge placeholder
        now_lbl = tk.Label(top, text="", font=("Segoe UI", 10, "bold"),
                           fg="white", bg="#cc6600", padx=6, pady=1)
        now_lbl.pack(side="left", padx=(4, 8))
        now_labels.append((now_lbl, p))

        tk.Label(top, text=p.get("title", ""), font=("Segoe UI", 13, "bold"),
                 fg="#e0e0e0", anchor="w", wraplength=700).pack(side="left", fill="x", expand=True)

        # Location
        location = p.get("location", "")
        if location:
            tk.Label(card, text=location, font=("Segoe UI", 11),
                     fg="#888888", anchor="w").pack(anchor="w", padx=(0, 0))

        # Presenters
        presenters = p.get("presenters", [])
        if presenters:
            pres_frame = tk.Frame(card)
            pres_frame.pack(anchor="w", pady=(4, 0))
            tk.Label(pres_frame, text="Presenters:", font=("Segoe UI", 10, "bold"),
                     fg="#999999").pack(side="left")
            for pr in presenters:
                name = pr.get("name", "")
                role = pr.get("role", "")
                company = pr.get("company", "")
                parts = [name]
                if role:
                    parts.append(role)
                if company:
                    parts.append(company)
                text = ", ".join(parts)
                tk.Label(pres_frame, text=f"  {text}", font=("Segoe UI", 9),
                         fg="#aaaaaa", wraplength=700, anchor="w").pack(anchor="w")

    def _update_now_badges():
        """Refresh NOW badges every 30 seconds."""
        now_lv = datetime.now(_lv_tz)
        for lbl, p in now_labels:
            try:
                start_dt = datetime.strptime(f"{p['date']} {p['start_time']}", "%Y-%m-%d %H:%M")
                start_dt = start_dt.replace(tzinfo=_lv_tz)
                end_dt = datetime.strptime(f"{p['date']} {p['end_time']}", "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=_lv_tz)
                if start_dt <= now_lv <= end_dt:
                    lbl.config(text=" NOW ", bg="#cc6600")
                else:
                    lbl.config(text="", bg=card.cget("bg"))
            except (ValueError, KeyError):
                lbl.config(text="", bg=card.cget("bg"))
        try:
            tab.after(30000, _update_now_badges)
        except RuntimeError:
            pass

    _update_now_badges()

    return tab
