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
Main application window (App class) for the World Cup Colour sACN controller.

Orchestrates all UI tabs (sACN, Generator, Groups, Schedule, Flags, Chases,
Country Editor, API, ReadMe), manages the sACN network connection, team colour
state, and goal-flash triggers with a 5-second timeout and progress bar.

Events handled:
    - set_team_colours / _goal_pressed -- user selects a team or fires a goal.
    - _fire_trigger / _clear_all_triggers -- sends and clears DMX trigger pulses.
    - _draw_swatches -- pushes new colours to both UI swatches and sACN output.
    - _on_close -- graceful shutdown of sACN sender.

Design decisions:
    - The status bar is packed bottom-first (before the Notebook) so that tkinter's
      packer keeps it anchored at the bottom edge during window resizes.
    - The trigger system uses root.after() timers for non-blocking 5-second pulses
      instead of threads, keeping all DMX I/O on the main thread and avoiding
      race conditions.
    - countries_db is merged into db ("teams" key) so that every lookup
      (groups, schedule, flags) can share a single unified team dictionary.
    - Version is bumped on every launch (timestamp-based) to make it trivial to
      identify which build a user is running.
"""

import tkinter as tk
from tkinter import ttk
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.theme import apply_dark_theme, FG_DIM
from src.statusbar import StatusBar
from src.sacn_connection import SacnConnection
from src.goal import GoalController
from src import scores
from src.constants import (
    TRIGGER_UNIVERSE, TRIGGER_PULSE_DURATION_MS, TRIGGER_PROGRESS_TICK_MS,
    DMX_MAX_VALUE, SWATCH_CANVAS_SIZE,
)
from src.tabs import (
    build_sacn_tab,
    build_sacn_manual_tab,
    build_generator_tab,
    build_timeline_tab,
    build_flags_tab,
    build_chases_tab,
    build_country_editor_tab,
    build_readme_tab,
    build_api_tab,
    build_api_schedule_tab,
    build_sounds_tab,
    build_webserver_tab,
    build_presentations_tab,
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


def _normalize_team_colours(teams):
    """Strip colour entries down to [r, g, b] triples in place.

    countries.json stores each colour as [r, g, b, "Colour Name"]. The rest of
    the app treats colours as plain RGB triples (iterating per channel for sACN
    output and goal flashing), so the trailing name must be dropped here at the
    single load point. The name remains in the file on disk for the editor and
    Excel export.
    """
    for team in teams.values():
        cols = team.get("colours")
        if not isinstance(cols, list):
            continue
        team["colours"] = [
            [int(c[0]), int(c[1]), int(c[2])]
            for c in cols
            if isinstance(c, (list, tuple)) and len(c) >= 3
        ]


class App:
    def __init__(self):
        self.root = tk.Tk()
        version = _bump_version()
        self.root.title(f"World Cup Colour sACN  v{version}")
        self.root.state("zoomed")
        self.root.resizable(True, True)

        apply_dark_theme(self.root)

        self.sacn = SacnConnection(source_name="DIVERSIFIED WORLD CUP")
        self.sacn.extra_universes.add(TRIGGER_UNIVERSE)  # why: trigger channels live on a separate universe from colour data

        self.team_colours = None
        self.team_name = None

        with open(DB_FILE, "r") as f:
            self.db = json.load(f)
        with open(COUNTRIES_FILE, "r") as f:
            self.countries_db = json.load(f)
        _normalize_team_colours(self.countries_db.get("teams", {}))  # why: drop the [r,g,b,name] colour name so consumers see plain RGB triples
        self.db["teams"] = self.countries_db["teams"]  # why: merge into one dict so all tabs share a single unified team lookup

        self._active_triggers = {}  # {country_name: (uni, ch, timer_id)}
        self._trigger_progress_timer = None

        # Walk-the-triggers test state (steps universe 2, channels 1-50)
        self._walk_active = False
        self._walk_timer = None
        self._walk_channel = 1

        # why: status bar packed bottom-first so it stays anchored during window resize
        self.status_bar = StatusBar(self.root)

        # ── Game header (countdown / live scores) ───────────────────────
        self._header_container = tk.Frame(self.root, bg="#1a1a1a")
        self._header_container.pack(fill="x", padx=8, pady=(8, 0))
        self._header_live_rows = []  # dynamic rows for live games
        # Bottom row: next upcoming game (always visible when applicable)
        self._header_next_frame = tk.Frame(self._header_container, bg="#1a1a1a")
        self._header_next_frame.pack(fill="x", side="bottom")
        self._header_next_title = tk.Label(self._header_next_frame, text="",
                                            font=("Segoe UI", 11, "bold"),
                                            fg="#ffcc00", bg="#1a1a1a")
        self._header_next_title.pack(side="left", padx=(12, 8))
        self._header_next_detail = tk.Label(self._header_next_frame, text="",
                                             font=("Consolas", 16, "bold"),
                                             fg="#ffcc00", bg="#1a1a1a")
        self._header_next_detail.pack(side="left", padx=(0, 8))
        self._header_next_match = tk.Label(self._header_next_frame, text="",
                                            font=("Segoe UI", 10),
                                            fg="#888888", bg="#1a1a1a")
        self._header_next_match.pack(side="left", padx=(0, 12))

        # Main notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        # ── Top-level tabs ─────────────────────────────────────────────
        build_timeline_tab(self.notebook, self.db, self.set_team_colours, self._goal_pressed)
        self._highlight_flag = build_flags_tab(self.notebook, self.db, self._goal_pressed)
        self._flags_tab_index = self.notebook.index("end") - 1

        self._start_api_auto, set_fetch_schedule, set_on_score_change, api_token_var = \
            build_api_tab(self.notebook, self.status_bar)
        self._api_live_tab_index = self.notebook.index("end") - 1
        _, fetch_schedule = build_api_schedule_tab(self.notebook, api_token_var, self.root)
        set_fetch_schedule(fetch_schedule)
        set_on_score_change(self._on_live_score_change)

        # ── Settings tab (sub-notebook) ───────────────────────────────
        settings_tab = tk.Frame(self.notebook)
        self.notebook.add(settings_tab, text="Settings")
        settings_nb = ttk.Notebook(settings_tab)
        settings_nb.pack(fill="both", expand=True)

        # sACN (first in settings)
        self._sacn_connect = build_sacn_tab(
            settings_nb, self.sacn,
            on_connect=self._switch_to_api_live)
        # sACN Manual -- live DMX fader banks on their own tab
        self._update_sacn_country = build_sacn_manual_tab(
            settings_nb, self.sacn, self.countries_db)

        # Web Server (second in settings)
        from src.tabs.timeline import _load_fixtures_from_schedule, _load_venues
        self._load_schedule_fixtures = _load_fixtures_from_schedule
        self._load_schedule_venues = _load_venues

        def _build_web_games():
            """Build game list from schedule files for the web server."""
            fixtures = self._load_schedule_fixtures(self.db)
            venues = self._load_schedule_venues()
            games = []
            for fix in fixtures:
                sa = fix.get("starting_at", "")
                try:
                    dt = datetime.strptime(sa, "%Y-%m-%d %H:%M:%S")
                    date_str = dt.strftime("%b %d").replace(" 0", " ")
                    time_str = dt.strftime("%H:%M")
                except ValueError:
                    date_str = "TBD"
                    time_str = ""
                vid = fix.get("venue_id")
                venue = venues.get(vid, "") if vid else ""
                games.append({
                    "home": fix.get("home", ""),
                    "away": fix.get("away", ""),
                    "date": date_str,
                    "time_utc": time_str,
                    "venue": venue,
                    "group": "",
                })
            # Also push updated scores into the scores module
            scores.register_fixtures(fixtures)
            return games

        self._update_web_state = build_webserver_tab(
            settings_nb,
            goal_pressed_cb=self._goal_pressed,
            set_colours_cb=self.set_team_colours)
        self._update_web_state(games=_build_web_games(), teams=self.db.get("teams", {}))

        # Periodically refresh web game list from schedule files (every 60s)
        def _refresh_web_games():
            self._update_web_state(games=_build_web_games())
            self.root.after(60000, _refresh_web_games)
        self.root.after(60000, _refresh_web_games)

        # Generator
        self.gen_team_label, self.swatches, self.swatch_labels, start_random = \
            build_generator_tab(
                settings_nb, self._draw_swatches,
                lambda: (self.team_colours, self.team_name),
                self._set_raw_state,
                toggle_walk_triggers=self._toggle_walk_triggers,
            )

        # Chases
        self.chase = build_chases_tab(settings_nb, self.root, self._draw_swatches,
                                      lambda: self.team_colours)

        # Country Editor
        self._stop_editor_preview = build_country_editor_tab(settings_nb, self.set_team_colours)

        # Sounds (top-level tab)
        self._fire_sound_event, self._play_sound_by_name, self._stop_sound_by_name, \
            self._list_sounds = build_sounds_tab(
                self.notebook, self.countries_db,
                stop_editor_preview=self._stop_editor_preview)
        # Expose play/stop/list to the web server's /sounds page
        from src.tabs import webserver as _webserver
        _webserver.set_sound_callbacks(
            list_fn=self._list_sounds,
            play_fn=self._play_sound_by_name,
            stop_fn=self._stop_sound_by_name)

        # Presentations Schedule
        build_presentations_tab(settings_nb)

        # ReadMe (in settings)
        build_readme_tab(settings_nb)

        self.goal = GoalController(self.root, self._draw_swatches,
                                   lambda t: self.gen_team_label.config(text=t),
                                   clear_team_cb=self._clear_team)

        # Auto-start sACN connection and API auto-get
        self._sacn_connect()
        self._start_api_auto()

        # Poll sACN connection status for footer indicator
        def _poll_sacn_status():
            connected = self.sacn.sender is not None
            self.status_bar.update_sacn_status(connected)
            self._update_web_state(sacn_connected=connected)
            self.root.after(2000, _poll_sacn_status)
        _poll_sacn_status()

        # ── Game header update loop ──────────────────────────────────
        _pregame_fired_for = [None]  # fixture id we already triggered PreGame for

        def _ensure_live_rows(count):
            """Create or remove header rows so there are exactly `count` live game rows."""
            while len(self._header_live_rows) < count:
                row = tk.Frame(self._header_container, bg="#1a1a1a")
                title = tk.Label(row, text="", font=("Segoe UI", 14, "bold"),
                                 fg="#28a745", bg="#1a1a1a")
                title.pack(side="left", padx=(12, 8))
                detail = tk.Label(row, text="", font=("Consolas", 20, "bold"),
                                  fg="#28a745", bg="#1a1a1a")
                detail.pack(side="left", padx=(0, 8))
                match = tk.Label(row, text="", font=("Segoe UI", 12),
                                 fg="#28a745", bg="#1a1a1a")
                match.pack(side="left", padx=(0, 12))
                row.pack(fill="x", before=self._header_next_frame)
                self._header_live_rows.append((row, title, detail, match))
            while len(self._header_live_rows) > count:
                row, _, _, _ = self._header_live_rows.pop()
                row.destroy()

        def _update_game_header():
            live = scores.get_live_games()
            _ensure_live_rows(len(live))
            for i, (fid, info) in enumerate(live):
                row, title_lbl, detail_lbl, match_lbl = self._header_live_rows[i]
                home = info.get("home", "")
                away = info.get("away", "")
                hs = info.get("home_score", 0)
                aws = info.get("away_score", 0)
                clock = scores.get_match_clock(fid)
                remaining = scores.get_time_remaining(fid)
                clock_display = clock
                if remaining:
                    clock_display = f"{clock}  ({remaining} remaining)"
                title_lbl.config(text="LIVE", fg="#28a745")
                detail_lbl.config(
                    text=f"{home}  {hs} - {aws}  {away}",
                    fg="#28a745")
                match_lbl.config(text=clock_display, fg="#28a745")

            # Next upcoming game (shown on its own row, even during live games)
            nxt = scores.get_next_game_today()
            if nxt:
                fid, home, away, kick = nxt
                now_utc = datetime.now(timezone.utc)
                diff = int((kick - now_utc).total_seconds())
                if diff > 0:
                    h, rem = divmod(diff, 3600)
                    m, s = divmod(rem, 60)
                    self._header_next_title.config(
                        text="NEXT GAME", fg="#ffcc00")
                    self._header_next_detail.config(
                        text=f"{h:02d}:{m:02d}:{s:02d}", fg="#ffcc00")
                    self._header_next_match.config(
                        text=f"{home} vs {away}")

                    # Trigger PreGame.mp3 at 2 minutes before kickoff
                    if diff <= 120 and _pregame_fired_for[0] != fid:
                        _pregame_fired_for[0] = fid
                        self._play_sound_by_name("PreGame")
                else:
                    self._header_next_title.config(text="")
                    self._header_next_detail.config(text="")
                    self._header_next_match.config(text="")
            else:
                self._header_next_title.config(text="")
                self._header_next_detail.config(text="")
                self._header_next_match.config(text="")
            self.root.after(1000, _update_game_header)
        _update_game_header()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # Start in blackout — no colours sent
        self.set_team_colours([[0, 0, 0], [0, 0, 0], [0, 0, 0]], "")
        self.root.mainloop()

    def _on_live_score_change(self, scoring_team, home, away,
                                home_score, away_score,
                                prev_home_score, prev_away_score):
        """Called when the livescores API detects a score change."""
        # Map SportMonks team name to local countries.json name
        local_name = self._resolve_local_name(scoring_team)
        if not local_name:
            return

        # Update scores module
        for fid, s in scores.get_all_scores().items():
            if s["home"] == home or s["away"] == away:
                from src.scores import _scores
                _scores[fid]["home_score"] = home_score
                _scores[fid]["away_score"] = away_score
                _scores[fid]["has_score"] = True
                break

        # Look up colours and fire the goal
        team_info = self.countries_db.get("teams", {}).get(local_name, {})
        colours = team_info.get("colours", [[255, 255, 255], [0, 0, 0], [128, 128, 128]])
        is_home = (scoring_team == home)
        self._goal_pressed(colours, local_name, is_home=is_home)

    def _resolve_local_name(self, api_name):
        """Map a SportMonks API team name to a countries.json team name."""
        teams = self.countries_db.get("teams", {})
        # Direct match
        if api_name in teams:
            return api_name
        # Try matching by sportmonks name stored in countries.json
        for local_name, info in teams.items():
            if info.get("sportmonks_name", "") == api_name:
                return local_name
        # Fuzzy: check if one contains the other
        api_lower = api_name.lower()
        for local_name in teams:
            if api_lower == local_name.lower():
                return local_name
        return ""

    def _switch_to_flags(self):
        self.notebook.select(self._api_live_tab_index)

    def _switch_to_api_live(self):
        self.notebook.select(self._api_live_tab_index)

    def _set_raw_state(self, colours, name):
        self.team_colours = colours
        self.team_name = name

    def _draw_swatches(self, colours):
        for i, rgb in enumerate(colours):
            hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            self.swatches[i].delete("all")
            self.swatches[i].create_rectangle(0, 0, SWATCH_CANVAS_SIZE, SWATCH_CANVAS_SIZE, fill=hex_col, outline="")
            self.swatch_labels[i].config(text=f"{rgb[0]}, {rgb[1]}, {rgb[2]}")
        self.sacn.send_rgb(colours)
        self.status_bar.update(colours, self.team_name, self.team_colours, self.countries_db)
        if hasattr(self, '_update_web_state'):
            self._update_web_state(colours=colours, team_name=self.team_name or "",
                                   goal_active=self.goal.is_active)

    def _clear_team(self):
        """Clear team name and colours after goal ends."""
        self.team_name = ""
        self.team_colours = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        self._highlight_flag("")
        if hasattr(self, '_update_web_state'):
            self._update_web_state(team_name="", goal_active=False,
                                   colours=[[0, 0, 0], [0, 0, 0], [0, 0, 0]])

    def set_team_colours(self, colours, country_name=""):
        self.team_colours = colours
        self.team_name = country_name
        self.gen_team_label.config(text=country_name)
        self._draw_swatches(colours)
        self._update_sacn_country(country_name)
        self._highlight_flag(country_name)
        if country_name:
            self._fire_trigger(country_name)

    def _goal_pressed(self, colours, country_name, is_home=None):
        self.team_colours = colours
        self.team_name = country_name
        self.gen_team_label.config(text=country_name)
        self._draw_swatches(colours)
        self._update_sacn_country(country_name)
        self._highlight_flag(country_name)
        self.goal.trigger(colours, country_name)
        self._fire_trigger(country_name)
        # Fire the most specific event type available
        if is_home is True:
            self._fire_sound_event("Goal Home", country_name)
        elif is_home is False:
            self._fire_sound_event("Goal Away", country_name)
        else:
            self._fire_sound_event("Goal by Team", country_name)

    def _fire_trigger(self, country_name):
        team = self.countries_db.get("teams", {}).get(country_name, {})
        trigger = team.get("trigger")
        if not trigger:
            return
        uni = trigger["universe"]
        ch = trigger["channel"]

        # Cancel existing trigger for this country if re-triggered
        existing = self._active_triggers.get(country_name)
        if existing:
            _, _, old_timer = existing
            if old_timer:
                self.root.after_cancel(old_timer)
            self.sacn.send_trigger(existing[0], existing[1], 0)

        self.sacn.send_trigger(uni, ch, DMX_MAX_VALUE)

        # Show all active trigger names in status bar
        active_names = [n for n in self._active_triggers if n != country_name]
        active_names.append(country_name)
        self.status_bar.trigger_label.config(
            text=f"{' + '.join(active_names)} triggered", fg="#ff9800")

        if self._trigger_progress_timer:
            self.root.after_cancel(self._trigger_progress_timer)
        self._trigger_duration = TRIGGER_PULSE_DURATION_MS
        self._trigger_elapsed = 0
        self.status_bar.trigger_progress["value"] = 100
        self._tick_trigger_progress()

        def _clear_one(name=country_name):
            entry = self._active_triggers.pop(name, None)
            if entry:
                self.sacn.send_trigger(entry[0], entry[1], 0)
            if not self._active_triggers:
                # All triggers done — full cleanup
                self._clear_all_triggers()
            else:
                # Update status bar to show remaining triggers
                remaining = list(self._active_triggers.keys())
                self.status_bar.trigger_label.config(
                    text=f"{' + '.join(remaining)} triggered", fg="#ff9800")

        timer_id = self.root.after(TRIGGER_PULSE_DURATION_MS, _clear_one)
        self._active_triggers[country_name] = (uni, ch, timer_id)

    def _tick_trigger_progress(self):
        self._trigger_elapsed += TRIGGER_PROGRESS_TICK_MS
        remaining = max(0, self._trigger_duration - self._trigger_elapsed)
        pct = (remaining / self._trigger_duration) * 100
        self.status_bar.trigger_progress["value"] = pct
        if remaining > 0:
            self._trigger_progress_timer = self.root.after(TRIGGER_PROGRESS_TICK_MS, self._tick_trigger_progress)
        else:
            self._trigger_progress_timer = None

    def _clear_all_triggers(self):
        for name, entry in list(self._active_triggers.items()):
            uni, ch, timer_id = entry
            if timer_id:
                self.root.after_cancel(timer_id)
            self.sacn.send_trigger(uni, ch, 0)
        self._active_triggers.clear()
        # Also zero any trigger channels not tracked (belt-and-suspenders)
        for team_data in self.countries_db.get("teams", {}).values():
            t = team_data.get("trigger")
            if t:
                self.sacn.send_trigger(t["universe"], t["channel"], 0)
        self.goal.stop()
        self._highlight_flag("")  # clear flag highlight
        self.status_bar.trigger_label.config(text="", fg=FG_DIM)
        self.status_bar.trigger_progress["value"] = 0
        if self._trigger_progress_timer:
            self.root.after_cancel(self._trigger_progress_timer)
            self._trigger_progress_timer = None
        # Blackout colour output
        black = [[0, 0, 0]] * 3
        self._draw_swatches(black)

    # ── Walk the triggers ────────────────────────────────────────────────
    WALK_CHANNEL_COUNT = 50   # why: step channels 1-50 of the trigger universe
    WALK_STEP_MS = 1000       # why: hold each channel high for 1 second

    def _walk_step(self):
        """Light one trigger channel at a time, advancing every second."""
        if not self._walk_active:
            return
        # Zero the previously lit channel so only one is high at a time
        prev = self._walk_channel - 1 if self._walk_channel > 1 else self.WALK_CHANNEL_COUNT
        self.sacn.send_trigger(TRIGGER_UNIVERSE, prev, 0)
        # Drive the current channel high
        self.sacn.send_trigger(TRIGGER_UNIVERSE, self._walk_channel, DMX_MAX_VALUE)
        self.status_bar.trigger_label.config(
            text=f"Walking triggers — U{TRIGGER_UNIVERSE} ch {self._walk_channel}/{self.WALK_CHANNEL_COUNT}",
            fg="#ff9800")
        # Advance, wrapping back to 1 to loop forever
        self._walk_channel += 1
        if self._walk_channel > self.WALK_CHANNEL_COUNT:
            self._walk_channel = 1
        self._walk_timer = self.root.after(self.WALK_STEP_MS, self._walk_step)

    def _stop_walk_triggers(self):
        """Stop the walk and zero every channel it may have lit."""
        self._walk_active = False
        if self._walk_timer:
            self.root.after_cancel(self._walk_timer)
            self._walk_timer = None
        for ch in range(1, self.WALK_CHANNEL_COUNT + 1):
            self.sacn.send_trigger(TRIGGER_UNIVERSE, ch, 0)
        self.status_bar.trigger_label.config(text="", fg=FG_DIM)

    def _toggle_walk_triggers(self):
        """Start or stop the trigger walk. Returns True if now running."""
        if self._walk_active:
            self._stop_walk_triggers()
            return False
        self._walk_active = True
        self._walk_channel = 1
        self._walk_step()
        return True

    def _on_close(self):
        # Tear down every background output/thread so the process exits cleanly.
        # CRITICAL: some cleanup calls (sounddevice/PortAudio stream close, the
        # non-daemon sACN sender thread join) can BLOCK. If they hang, the window
        # never closes and the process never exits -- which, with the always-relaunch
        # watchdog, traps the operator. So we arm a hard force-exit timer first:
        # whichever finishes first (graceful cleanup or the timer) terminates the
        # process. os._exit bypasses any wedged thread and the OS reclaims sockets,
        # audio streams, etc.
        import os
        import threading
        watchdog = threading.Timer(2.5, lambda: os._exit(0))
        watchdog.daemon = True
        watchdog.start()

        try:
            self._stop_walk_triggers()
        except Exception:
            pass
        try:
            self.sacn.stop()
        except Exception:
            pass
        try:
            from src import audio_engine
            audio_engine.shutdown()  # close all sounddevice streams + the decoder mixer
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)  # guarantee termination so the watchdog regains control
