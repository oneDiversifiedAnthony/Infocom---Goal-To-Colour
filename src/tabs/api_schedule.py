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

"""Schedule sub-tab -- fetch team schedules from SportMonks and display in a table.

Fetches the schedule for every team that has a sportmonks_id in countries.json,
saves each response to assets/Schedule/{team_name}.json, fetches venue details,
and displays all fixtures in a sortable, filterable table.
"""

import datetime
import json
import os
import threading
import tkinter as tk
from tkinter import ttk
import urllib.request
import urllib.error

from src.theme import BG, BG_LIGHT, FG, FG_DIM

COUNTRIES_FILE = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir, "assets", "countries.json"
)
SCHEDULE_DIR = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir, "assets", "Schedule"
)
VENUES_FILE = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir, "assets", "venues.json"
)
SCHEDULE_URL = "https://api.sportmonks.com/v3/football/schedules/teams/{team_id}?api_token={token}"
VENUE_URL = "https://api.sportmonks.com/v3/football/venues/{venue_id}?api_token={token}"
WORLD_CUP_LEAGUE_ID = 732


def _load_venues():
    """Load venue_id -> name mapping from venues.json."""
    if not os.path.isfile(VENUES_FILE):
        return {}
    try:
        with open(VENUES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        venues = {}
        for vid_str, info in data.items():
            name = info.get("name", "")
            city = info.get("city_name", "")
            venues[int(vid_str)] = f"{name}, {city}" if city else name
        return venues
    except Exception:
        return {}


def _fetch_venues(token):
    """Collect unique venue_ids from saved schedules and fetch each venue."""
    venue_ids = set()
    if not os.path.isdir(SCHEDULE_DIR):
        return
    for fname in os.listdir(SCHEDULE_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(SCHEDULE_DIR, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            for stage in data.get("data", []):
                if not isinstance(stage, dict) or stage.get("league_id") != WORLD_CUP_LEAGUE_ID:
                    continue
                for rnd in stage.get("rounds", []):
                    for fix in rnd.get("fixtures", []):
                        vid = fix.get("venue_id")
                        if vid:
                            venue_ids.add(vid)
        except Exception:
            pass

    existing = {}
    if os.path.isfile(VENUES_FILE):
        try:
            with open(VENUES_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    needed = {vid for vid in venue_ids if str(vid) not in existing}
    if not needed:
        return

    for vid in sorted(needed):
        url = VENUE_URL.format(venue_id=vid, token=token)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            v = json.loads(body).get("data", {})
            existing[str(vid)] = {
                "id": v.get("id"),
                "name": v.get("name", ""),
                "city_name": v.get("city_name", ""),
                "address": v.get("address", ""),
                "capacity": v.get("capacity"),
                "surface": v.get("surface", ""),
                "image_path": v.get("image_path", ""),
                "country_id": v.get("country_id"),
            }
        except Exception:
            pass

    with open(VENUES_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def build_schedule_subtab(result_notebook, token_var, tab_root):
    """Build the Schedule sub-tab. Returns the frame."""
    frame = tk.Frame(result_notebook, bg=BG)
    result_notebook.add(frame, text="API Schedule")

    os.makedirs(SCHEDULE_DIR, exist_ok=True)

    # Venue lookup
    venue_map = [_load_venues()]

    # Store all loaded fixtures for filtering
    all_loaded_fixtures = []
    # Teams fetched in the most recent pull (for green highlighting)
    last_pulled_teams = set()

    # ── Controls ─────────────────────────────────────────────────────
    ctrl = tk.Frame(frame, bg=BG)
    ctrl.pack(fill="x", padx=8, pady=(8, 4))

    status_label = tk.Label(ctrl, text="", font=("Segoe UI", 9), fg=FG_DIM, bg=BG)
    progress_label = tk.Label(ctrl, text="", font=("Consolas", 9), fg=FG_DIM, bg=BG)

    fetching = [False]

    def _find_teams_today_tomorrow():
        """Find teams playing today or tomorrow from cached schedule files."""
        today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        tomorrow = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        target_dates = {today, tomorrow}
        teams_needed = set()

        if not os.path.isdir(SCHEDULE_DIR):
            return teams_needed

        for fname in os.listdir(SCHEDULE_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(SCHEDULE_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for stage in data.get("data", []):
                    if not isinstance(stage, dict):
                        continue
                    if stage.get("league_id") != WORLD_CUP_LEAGUE_ID:
                        continue
                    for rnd in stage.get("rounds", []):
                        if not isinstance(rnd, dict):
                            continue
                        for fix in rnd.get("fixtures", []):
                            sa = fix.get("starting_at", "")
                            if sa[:10] in target_dates:
                                for p in fix.get("participants", []):
                                    if isinstance(p, dict) and p.get("name"):
                                        teams_needed.add(p["name"])
            except Exception:
                pass
        return teams_needed

    def _get_schedules():
        if fetching[0]:
            return
        fetching[0] = True
        fetch_btn.config(state="disabled", bg="#888888")
        status_label.config(text="Finding today/tomorrow teams...", fg="#0066cc")

        def _worker():
            try:
                with open(COUNTRIES_FILE, "r", encoding="utf-8") as f:
                    countries = json.load(f)
            except Exception as e:
                tab_root.after(0, lambda: _done(f"Error loading countries: {e}"))
                return

            # Find which teams play today/tomorrow
            api_teams_needed = _find_teams_today_tomorrow()

            # Build mapping: local name → sportmonks_id, filtering to today/tomorrow teams
            all_teams = {}
            for name, info in countries.get("teams", {}).items():
                sm_id = info.get("sportmonks_id")
                if sm_id:
                    all_teams[name] = sm_id

            # Match needed API team names to local names
            teams = []
            if api_teams_needed:
                # Build reverse lookup: sportmonks name → local name
                for local_name, sm_id in all_teams.items():
                    # Check if this team's API name matches any needed team
                    if local_name in api_teams_needed:
                        teams.append((local_name, sm_id))
                        continue
                    # Also check cached schedule for participant names matching this sm_id
                    for api_name in api_teams_needed:
                        if api_name.lower() == local_name.lower():
                            teams.append((local_name, sm_id))
                            break
                # If no matches found via name, fetch all (fallback)
                if not teams:
                    teams = list(all_teams.items())
            else:
                # No cached data yet, fetch all teams
                teams = list(all_teams.items())

            if not teams:
                tab_root.after(0, lambda: _done("No teams to fetch"))
                return

            total = len(teams)
            token = token_var.get().strip()
            raw_fixtures = []
            fetched_teams = set()

            tab_root.after(0, lambda t=total:
                status_label.config(
                    text=f"Fetching {t} team{'s' if t != 1 else ''} (today/tomorrow)...",
                    fg="#0066cc"))

            for idx, (name, sm_id) in enumerate(teams, 1):
                tab_root.after(0, lambda n=name, i=idx, t=total:
                    _update_progress(n, i, t))

                url = SCHEDULE_URL.format(team_id=sm_id, token=token)
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        body = resp.read().decode("utf-8", errors="replace")

                    data = json.loads(body)

                    safe_name = name.replace(" ", "_")
                    save_path = os.path.join(SCHEDULE_DIR, f"{safe_name}.json")
                    with open(save_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)

                    fetched_teams.add(name)

                except urllib.error.HTTPError as e:
                    tab_root.after(0, lambda n=name, c=e.code:
                        status_label.config(
                            text=f"HTTP {c} for {n} – continuing...",
                            fg="#ff6600"))
                except Exception as e:
                    tab_root.after(0, lambda n=name, err=str(e):
                        status_label.config(
                            text=f"Error for {n}: {err} – continuing...",
                            fg="#ff6600"))

            # Fetch venues
            tab_root.after(0, lambda:
                status_label.config(text="Fetching venues...", fg="#0066cc"))
            _fetch_venues(token)
            venue_map[0] = _load_venues()

            # Reload ALL cached fixtures (not just the ones we just fetched)
            tab_root.after(0, lambda ft=fetched_teams: _finish_fetch(ft))
            tab_root.after(0, lambda t=total:
                _done(f"Done – {t} teams fetched (today/tomorrow)"))

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_fetch(fetched_teams):
        """After fetching, reload all cached data and track which teams were refreshed."""
        last_pulled_teams.clear()
        last_pulled_teams.update(fetched_teams)
        _load_cached()

    def _update_progress(name, current, total):
        progress_label.config(text=f"{current}/{total}")
        status_label.config(text=f"Fetching {name}...", fg="#0066cc")

    def _done(msg):
        fetching[0] = False
        fetch_btn.config(state="normal", bg="#0066cc")
        status_label.config(text=msg, fg="#28a745" if "Done" in msg else "#ff0000")
        progress_label.config(text="")
        if "Done" in msg:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            last_pulled_label.config(text=f"Last schedule pulled: {now}")

    def _load_cached():
        """Load previously saved schedule files and populate the table."""
        raw_fixtures = []
        if not os.path.isdir(SCHEDULE_DIR):
            return
        for fname in os.listdir(SCHEDULE_DIR):
            if not fname.endswith(".json"):
                continue
            team_name = fname.replace(".json", "").replace("_", " ")
            fpath = os.path.join(SCHEDULE_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                fixtures = _extract_fixtures(data, team_name)
                raw_fixtures.extend(fixtures)
            except Exception:
                pass
        if raw_fixtures:
            venue_map[0] = _load_venues()
            raw_fixtures.sort(key=lambda f: f.get("starting_at", ""))
            _on_fixtures_loaded(raw_fixtures)
            status_label.config(
                text=f"Loaded {len(raw_fixtures)} cached fixtures",
                fg="#888888")

    def _on_fixtures_loaded(fixtures):
        """Store fixtures and populate table with current filter."""
        all_loaded_fixtures.clear()
        all_loaded_fixtures.extend(fixtures)
        _apply_filter()

    def _apply_filter(*_args):
        """Filter fixtures by start/end date and repopulate table."""
        start = start_var.get().strip()
        end = end_var.get().strip()
        filtered = []
        for fix in all_loaded_fixtures:
            dt = fix.get("starting_at", "")[:10]
            if start and dt < start:
                continue
            if end and dt > end:
                continue
            filtered.append(fix)
        _populate_table(filtered)

    last_pulled_label = tk.Label(ctrl, text="", font=("Segoe UI", 9), fg="#888888", bg=BG)

    fetch_btn = tk.Button(ctrl, text="Get Schedule", font=("Segoe UI", 10, "bold"),
                          bg="#0066cc", fg="white", padx=16, pady=2,
                          command=_get_schedules)
    fetch_btn.pack(side="left", padx=(0, 8))

    load_btn = tk.Button(ctrl, text="Load Cached", font=("Segoe UI", 9),
                         padx=8, pady=2, command=_load_cached)
    load_btn.pack(side="left", padx=(0, 8))

    progress_label.pack(side="left", padx=(0, 8))
    status_label.pack(side="left", fill="x", expand=True)
    last_pulled_label.pack(side="right", padx=(8, 0))

    # ── Filter controls ────────────────────────────────────────────
    filter_frame = tk.Frame(frame, bg=BG)
    filter_frame.pack(fill="x", padx=8, pady=(2, 4))

    tk.Label(filter_frame, text="From:", font=("Segoe UI", 9),
             fg=FG_DIM, bg=BG).pack(side="left", padx=(0, 4))
    start_var = tk.StringVar(value="2026-06-11")
    start_entry = tk.Entry(filter_frame, textvariable=start_var,
                           font=("Consolas", 9), width=12, bg=BG_LIGHT, fg=FG,
                           insertbackground=FG)
    start_entry.pack(side="left", padx=(0, 12))

    tk.Label(filter_frame, text="To:", font=("Segoe UI", 9),
             fg=FG_DIM, bg=BG).pack(side="left", padx=(0, 4))
    end_var = tk.StringVar(value="2026-07-19")
    end_entry = tk.Entry(filter_frame, textvariable=end_var,
                         font=("Consolas", 9), width=12, bg=BG_LIGHT, fg=FG,
                         insertbackground=FG)
    end_entry.pack(side="left", padx=(0, 12))

    tk.Button(filter_frame, text="Filter", font=("Segoe UI", 9, "bold"),
              bg="#0066cc", fg="white", padx=12, pady=1,
              command=_apply_filter).pack(side="left", padx=(0, 8))

    tk.Button(filter_frame, text="Clear", font=("Segoe UI", 9),
              padx=8, pady=1,
              command=lambda: (start_var.set(""), end_var.set(""),
                               _apply_filter())).pack(side="left")

    # ── Table ────────────────────────────────────────────────────────
    sched_style = ttk.Style()
    sched_style.configure("Schedule.Treeview",
                          background=BG, foreground=FG,
                          fieldbackground=BG, borderwidth=0)
    sched_style.configure("Schedule.Treeview.Heading",
                          background=BG_LIGHT, foreground=FG)
    sched_style.map("Schedule.Treeview",
                     background=[("selected", "#3d3d3d")],
                     foreground=[("selected", FG)])

    columns = ("game_id", "date", "time", "home", "home_goals", "score",
               "away_goals", "away", "result", "venue", "status")
    table = ttk.Treeview(frame, columns=columns, show="headings", height=25,
                         style="Schedule.Treeview")

    col_config = {
        "game_id":    ("Game ID",  90),
        "date":       ("Date",     90),
        "time":       ("Time",     60),
        "home":       ("Home",    140),
        "home_goals": ("H Goals",  60),
        "score":      ("Score",    70),
        "away_goals": ("A Goals",  60),
        "away":       ("Away",    140),
        "result":     ("Result",  220),
        "venue":      ("Venue",   200),
        "status":     ("Status",   80),
    }
    sort_reverse = {}

    def _sort_by_column(col):
        reverse = sort_reverse.get(col, False)
        rows = [(table.set(iid, col), iid) for iid in table.get_children()]
        rows.sort(key=lambda r: r[0], reverse=reverse)
        for idx, (_, iid) in enumerate(rows):
            table.move(iid, "", idx)
        sort_reverse[col] = not reverse

    for col_id in columns:
        heading, width = col_config[col_id]
        table.heading(col_id, text=heading, anchor="w",
                      command=lambda c=col_id: _sort_by_column(c))
        table.column(col_id, width=width, anchor="w")

    xscroll = tk.Scrollbar(frame, orient="horizontal", command=table.xview)
    yscroll = tk.Scrollbar(frame, orient="vertical", command=table.yview)
    table.config(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
    yscroll.pack(side="right", fill="y")
    xscroll.pack(side="bottom", fill="x")
    table.pack(fill="both", expand=True)

    def _populate_table(fixtures):
        for item in table.get_children():
            table.delete(item)

        # Tag for green rows (recently pulled teams)
        table.tag_configure("recent", background="#0a3a0a", foreground="#66ff66")

        venues = venue_map[0]
        seen = set()
        for fix in fixtures:
            key = (fix.get("starting_at", ""), fix.get("home", ""), fix.get("away", ""))
            if key in seen:
                continue
            seen.add(key)

            starting = fix.get("starting_at", "")
            date_str = ""
            time_str = ""
            if starting:
                try:
                    dt = datetime.datetime.fromisoformat(starting.replace("Z", "+00:00"))
                    date_str = dt.strftime("%Y-%m-%d")
                    time_str = dt.strftime("%H:%M")
                except (ValueError, AttributeError):
                    date_str = starting[:10] if len(starting) >= 10 else starting

            # Resolve venue from venues.json
            venue_display = fix.get("venue", "")
            venue_id = fix.get("venue_id")
            if venue_id and venues.get(venue_id):
                venue_display = venues[venue_id]

            # Green highlight if home or away was in the most recent pull
            home = fix.get("home", "")
            away = fix.get("away", "")
            tags = ("recent",) if (home in last_pulled_teams or away in last_pulled_teams) else ()

            table.insert("", "end", values=(
                fix.get("game_id", ""),
                date_str,
                time_str,
                home,
                fix.get("home_goals", ""),
                fix.get("score", ""),
                fix.get("away_goals", ""),
                away,
                fix.get("result", ""),
                venue_display,
                fix.get("status", ""),
            ), tags=tags)

    # Auto-load cached data on startup
    tab_root.after(500, _load_cached)

    return frame, _get_schedules


def _extract_fixtures(data, team_name):
    """Extract fixture rows from a SportMonks schedule response."""
    fixtures = []

    if not isinstance(data, dict):
        return fixtures

    raw_items = data.get("data", [])
    if isinstance(raw_items, dict):
        raw_items = [raw_items]

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        # Schedule response has stages with rounds containing fixtures
        rounds = item.get("rounds", [])
        if isinstance(rounds, list) and rounds:
            for rnd in rounds:
                if not isinstance(rnd, dict):
                    continue
                for fix in rnd.get("fixtures", []):
                    row = _parse_fixture(fix, team_name)
                    if row:
                        fixtures.append(row)
        else:
            # Try nested fixtures/schedules
            nested = item.get("fixtures", item.get("schedules", []))
            if isinstance(nested, list) and nested:
                for fix in nested:
                    row = _parse_fixture(fix, team_name)
                    if row:
                        fixtures.append(row)
            else:
                row = _parse_fixture(item, team_name)
                if row:
                    fixtures.append(row)

    if not fixtures and isinstance(data.get("data"), list):
        for item in data["data"]:
            if isinstance(item, dict):
                row = _parse_fixture(item, team_name)
                if row:
                    fixtures.append(row)

    return fixtures


def _parse_fixture(fix, team_name):
    """Parse a single fixture dict into a table row."""
    if not isinstance(fix, dict):
        return None

    starting = fix.get("starting_at", fix.get("starting_at_timestamp", ""))
    if not starting:
        return None

    game_id = fix.get("id", "")

    # Participant names
    participants = fix.get("participants", [])
    home = ""
    away = ""
    if isinstance(participants, list):
        for p in participants:
            if isinstance(p, dict):
                meta = p.get("meta", {})
                if isinstance(meta, dict) and meta.get("location") == "home":
                    home = p.get("name", "")
                elif isinstance(meta, dict) and meta.get("location") == "away":
                    away = p.get("name", "")

    if not home and not away:
        home = team_name

    # Score — parse goals by participant (home/away) from the CURRENT score entries
    score_str = ""
    home_goals = 0
    away_goals = 0
    has_scores = False
    s1 = fix.get("scores", [])
    if isinstance(s1, list) and s1:
        try:
            for sc in s1:
                if not isinstance(sc, dict):
                    continue
                sc_data = sc.get("score", {})
                if not isinstance(sc_data, dict):
                    continue
                desc = sc.get("description", "")
                participant = sc_data.get("participant", "")
                g = sc_data.get("goals")
                if g is None or g == "":
                    continue
                g = int(g)
                if desc == "CURRENT":
                    has_scores = True
                    if participant == "home":
                        home_goals = g
                    elif participant == "away":
                        away_goals = g
            if has_scores:
                score_str = f"{home_goals} - {away_goals}"
        except Exception:
            pass
    # Result info (game summary string)
    result_info = fix.get("result_info", "")

    # Venue -- store venue_id so the table can resolve from venues.json
    venue_name = ""
    venue_id = fix.get("venue_id")
    venue = fix.get("venue", {})
    if isinstance(venue, dict):
        venue_name = venue.get("name", "")

    # Status
    state = fix.get("state", {})
    status = ""
    if isinstance(state, dict):
        status = state.get("short_name", state.get("state", ""))
    elif isinstance(state, str):
        status = state
    if not status:
        status = fix.get("state_id", "")

    return {
        "game_id": str(game_id),
        "starting_at": str(starting),
        "home": home,
        "away": away,
        "home_goals": str(home_goals) if has_scores else "",
        "away_goals": str(away_goals) if has_scores else "",
        "score": score_str,
        "result": result_info,
        "venue": venue_name,
        "venue_id": venue_id,
        "status": str(status),
    }
