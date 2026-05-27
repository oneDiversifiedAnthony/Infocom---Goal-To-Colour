import tkinter as tk
from tkinter import ttk
import json
import os
from datetime import datetime

from src.theme import apply_dark_theme, FG_DIM
from src.statusbar import StatusBar
from src.ScanMockDevice import SacnConnection
from src.goal import GoalController
from src.tabs import (
    build_sacn_tab,
    build_generator_tab,
    build_groups_tab,
    build_schedule_tab,
    build_flags_tab,
    build_chases_tab,
    build_country_editor_tab,
    build_readme_tab,
    build_api_tab,
)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "assets")
DB_FILE = os.path.join(ASSETS_DIR, "worldcup_teams.json")
COUNTRIES_FILE = os.path.join(ASSETS_DIR, "countries.json")
VERSION_FILE = os.path.join(ASSETS_DIR, "Version.json")


def _bump_version():
    now = datetime.now().strftime("%Y%m%d.%H%M")
    with open(VERSION_FILE, "w") as f:
        json.dump({"version": now}, f, indent=4)
    return now


def _load_version():
    try:
        with open(VERSION_FILE, "r") as f:
            return json.load(f)["version"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return _bump_version()


class App:
    def __init__(self):
        self.root = tk.Tk()
        version = _bump_version()
        self.root.title(f"World Cup Colour sACN  v{version}")
        self.root.geometry("720x580")
        self.root.resizable(True, True)

        apply_dark_theme(self.root)

        self.sacn = SacnConnection(source_name="DIVERSIFIED WORLD CUP")
        self.sacn.extra_universes.add(2)

        self.team_colours = None
        self.team_name = None

        with open(DB_FILE, "r") as f:
            self.db = json.load(f)
        with open(COUNTRIES_FILE, "r") as f:
            self.countries_db = json.load(f)
        self.db["teams"] = self.countries_db["teams"]

        self._trigger_timer = None
        self._trigger_progress_timer = None
        self._active_trigger = None

        # Status bar (pack bottom first)
        self.status_bar = StatusBar(self.root)

        # Main notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        # Tabs
        build_sacn_tab(self.notebook, self.sacn, on_connect=self._switch_to_flags)

        self.gen_team_label, self.swatches, self.swatch_labels, start_random = \
            build_generator_tab(
                self.notebook, self._draw_swatches,
                lambda: (self.team_colours, self.team_name),
                self._set_raw_state,
            )

        self.goal = GoalController(self.root, self._draw_swatches,
                                   lambda t: self.gen_team_label.config(text=t))

        build_groups_tab(self.notebook, self.db, self.set_team_colours)
        build_schedule_tab(self.notebook, self.db, self.set_team_colours, self._goal_pressed)
        build_flags_tab(self.notebook, self.db, self.set_team_colours)
        self._flags_tab_index = self.notebook.index("end") - 1
        self.chase = build_chases_tab(self.notebook, self.root, self._draw_swatches,
                                      lambda: self.team_colours)
        build_country_editor_tab(self.notebook, self.set_team_colours)
        build_api_tab(self.notebook)
        build_readme_tab(self.notebook)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        start_random()
        self.root.mainloop()

    def _switch_to_flags(self):
        self.notebook.select(self._flags_tab_index)

    def _set_raw_state(self, colours, name):
        self.team_colours = colours
        self.team_name = name

    def _draw_swatches(self, colours):
        for i, rgb in enumerate(colours):
            hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            self.swatches[i].delete("all")
            self.swatches[i].create_rectangle(0, 0, 100, 100, fill=hex_col, outline="")
            self.swatch_labels[i].config(text=f"{rgb[0]}, {rgb[1]}, {rgb[2]}")
        self.sacn.send_rgb(colours)
        self.status_bar.update(colours, self.team_name, self.team_colours, self.countries_db)

    def set_team_colours(self, colours, country_name=""):
        self.team_colours = colours
        self.team_name = country_name
        self.gen_team_label.config(text=country_name)
        self._draw_swatches(colours)
        if country_name:
            self._fire_trigger(country_name)

    def _goal_pressed(self, colours, country_name):
        self.team_colours = colours
        self.team_name = country_name
        self.goal.trigger(colours, country_name)
        self._fire_trigger(country_name)

    def _fire_trigger(self, country_name):
        team = self.countries_db.get("teams", {}).get(country_name, {})
        trigger = team.get("trigger")
        if not trigger:
            return
        uni = trigger["universe"]
        ch = trigger["channel"]

        if self._active_trigger:
            prev_uni, prev_ch = self._active_trigger
            self.sacn.send_trigger(prev_uni, prev_ch, 0)

        if self._trigger_timer:
            self.root.after_cancel(self._trigger_timer)
        if self._trigger_progress_timer:
            self.root.after_cancel(self._trigger_progress_timer)

        self._active_trigger = (uni, ch)
        self.sacn.send_trigger(uni, ch, 255)
        self.status_bar.trigger_label.config(
            text=f"{country_name} Ch{ch} triggered", fg="#ff9800")

        self._trigger_duration = 5000
        self._trigger_elapsed = 0
        self.status_bar.trigger_progress["value"] = 100
        self._tick_trigger_progress()

        def _clear():
            self._clear_all_triggers()
            self._trigger_timer = None

        self._trigger_timer = self.root.after(5000, _clear)

    def _tick_trigger_progress(self):
        self._trigger_elapsed += 50
        remaining = max(0, self._trigger_duration - self._trigger_elapsed)
        pct = (remaining / self._trigger_duration) * 100
        self.status_bar.trigger_progress["value"] = pct
        if remaining > 0:
            self._trigger_progress_timer = self.root.after(50, self._tick_trigger_progress)
        else:
            self._trigger_progress_timer = None

    def _clear_all_triggers(self):
        for team_data in self.countries_db.get("teams", {}).values():
            t = team_data.get("trigger")
            if t:
                self.sacn.send_trigger(t["universe"], t["channel"], 0)
        self._active_trigger = None
        self.status_bar.trigger_label.config(text="", fg=FG_DIM)
        self.status_bar.trigger_progress["value"] = 0

    def _on_close(self):
        self.sacn.stop()
        self.root.destroy()
