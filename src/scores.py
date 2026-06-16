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

"""Shared score tracking for World Cup fixtures.

Stores game scores by fixture ID. Updated by GOAL button presses and
optionally from the livescores API. Read by Timeline and Web Server.
"""

from datetime import datetime, timezone

# {fixture_id: {"home": str, "away": str, "home_score": int, "away_score": int, "live": bool}}
_scores = {}

# {fixture_id: "starting_at" datetime string} for live detection
_fixture_times = {}

# {fixture_id: [list of event dicts]} from livescores API
_events = {}

# {fixture_id: state_id} from livescores API
_state_ids = {}

# {fixture_id: [list of period dicts]} from livescores API
_periods = {}

# SportMonks state_id mapping
STATE_NAMES = {
    1: "NS",       # Not Started
    2: "1H",       # 1st Half (INPLAY_1ST_HALF)
    3: "HT",       # Half Time
    4: "BRK",      # Break
    5: "FT",       # Full Time
    6: "ET",       # Extra Time (INPLAY_ET)
    7: "AET",      # After Extra Time
    8: "FTP",      # After Penalties (FT_PEN)
    9: "PEN",      # Penalties (INPLAY_PENALTIES)
    10: "POST",    # Postponed
    11: "SUSP",    # Suspended
    12: "CANC",    # Cancelled
    13: "TBA",     # To Be Announced
    14: "WO",      # Walk Over
    15: "ABAN",    # Abandoned
    16: "DELA",    # Delayed
    17: "AWAR",    # Awarded
    18: "INT",     # Interrupted
    19: "AU",      # Awaiting Updates
    20: "DEL",     # Deleted
    21: "ETB",     # Extra Time - Break
    22: "2H",      # 2nd Half (INPLAY_2ND_HALF)
    23: "2ET",     # ET - 2nd Half (INPLAY_ET_2ND_HALF)
    25: "PENB",    # Penalties - Break
    26: "PEND",    # Pending
}

MATCH_DURATION_MINUTES = 150  # wall-clock fallback only; API state_id is preferred


def register_fixtures(fixtures):
    """Register fixture start times for live detection.

    fixtures: list of dicts with "id", "starting_at", "home", "away",
              and optionally "home_score", "away_score" from cached schedule data.
    """
    for f in fixtures:
        fid = f.get("id")
        if not fid:
            continue
        _fixture_times[fid] = f.get("starting_at", "")
        has_score = f.get("home_score") is not None
        if fid not in _scores:
            _scores[fid] = {
                "home": f.get("home", ""),
                "away": f.get("away", ""),
                "home_score": f.get("home_score") or 0,
                "away_score": f.get("away_score") or 0,
                "has_score": has_score,
                "live": False,
            }
        elif has_score:
            # Schedule is ground truth for finished games — always update
            # For live games, the livescores API takes priority via update_from_live
            if not _scores[fid].get("live"):
                _scores[fid]["home_score"] = f.get("home_score") or 0
                _scores[fid]["away_score"] = f.get("away_score") or 0
                _scores[fid]["has_score"] = True


def goal_scored(team_name):
    """Increment score for team_name in whatever fixture they're playing."""
    for fid, s in _scores.items():
        if s["home"] == team_name:
            s["home_score"] += 1
            s["has_score"] = True
            return fid
        if s["away"] == team_name:
            s["away_score"] += 1
            s["has_score"] = True
            return fid
    return None


def get_score(fixture_id):
    """Return (home_score, away_score) or None."""
    s = _scores.get(fixture_id)
    if s:
        return s["home_score"], s["away_score"]
    return None


def get_score_display(fixture_id):
    """Return score string like '1 - 0' or empty string."""
    s = _scores.get(fixture_id)
    if not s:
        return ""
    if not s.get("has_score") and s["home_score"] == 0 and s["away_score"] == 0:
        return ""
    return f"{s['home_score']} - {s['away_score']}"


# State IDs that mean the match is actively in progress
_LIVE_STATE_IDS = {
    2,   # 1st Half
    3,   # Half Time
    4,   # Break
    6,   # Extra Time (1st half)
    9,   # Penalties
    18,  # Interrupted
    21,  # Extra Time Break
    22,  # 2nd Half
    23,  # Extra Time (2nd half)
    25,  # Penalties Break
}


def is_live(fixture_id):
    """Check if a fixture is currently live using API state_id, with time-based fallback."""
    # Use API state_id if available (most reliable)
    state_id = _state_ids.get(fixture_id)
    if state_id is not None:
        return state_id in _LIVE_STATE_IDS

    # Fallback: estimate from kickoff time
    starting = _fixture_times.get(fixture_id, "")
    if not starting:
        return False
    try:
        utc_dt = datetime.strptime(starting, "%Y-%m-%d %H:%M:%S")
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    diff_minutes = (now - utc_dt).total_seconds() / 60
    return 0 <= diff_minutes <= MATCH_DURATION_MINUTES


def update_live_flags():
    """Refresh all live flags based on current time."""
    for fid in _scores:
        _scores[fid]["live"] = is_live(fid)


def get_match_minute(fixture_id):
    """Return the current match minute as int, or None if not live."""
    starting = _fixture_times.get(fixture_id, "")
    if not starting:
        return None
    try:
        utc_dt = datetime.strptime(starting, "%Y-%m-%d %H:%M:%S")
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    diff = int((now - utc_dt).total_seconds() / 60)
    if diff < 0 or diff > MATCH_DURATION_MINUTES:
        return None
    if diff > 90:
        return 90  # extra time shown as 90+
    return diff


def get_match_minute_display(fixture_id):
    """Return match minute string like \"45'\" or \"90+\" or empty."""
    m = get_match_minute(fixture_id)
    if m is None:
        return ""
    if m >= 90:
        return "90+"
    return f"{m}'"


def update_state(fixture_id, state_id):
    """Store the current state_id for a fixture."""
    _state_ids[fixture_id] = state_id


# Map SportMonks state_id -> loop window name
_WINDOW_BY_STATE = {
    2: "first_half",    # 1st Half
    6: "first_half",    # Extra Time (1st)
    3: "half_time",     # Half Time
    21: "half_time",    # ET Break
    22: "second_half",  # 2nd Half
    23: "second_half",  # ET 2nd Half
}


def get_game_window():
    """Return the current game window for looping ('first_half', 'half_time',
    'second_half') from any live game, or None if no game is in those states."""
    update_live_flags()
    for fid, s in _scores.items():
        if not s.get("live"):
            continue
        window = _WINDOW_BY_STATE.get(_state_ids.get(fid))
        if window:
            return window
    return None


def update_periods(fixture_id, periods):
    """Store period data from the API for a fixture."""
    _periods[fixture_id] = periods


def get_current_period(fixture_id):
    """Return the currently ticking period dict, or None."""
    for p in _periods.get(fixture_id, []):
        if p.get("ticking"):
            return p
    return None


def get_match_clock(fixture_id):
    """Return a match clock string using period data from the API.

    Uses the ``minutes`` and ``seconds`` fields from the active period
    when available, with injury-time formatting (e.g. "45+2:30").
    Falls back to state_id label when no period is ticking.
    """
    # Try period data first (most accurate)
    period = get_current_period(fixture_id)
    if period and period.get("minutes") is not None:
        minutes = period["minutes"]
        seconds = period.get("seconds", 0) or 0
        period_length = period.get("period_length", 45)
        counts_from = period.get("counts_from", 0)
        time_added = period.get("time_added")
        regular_end = counts_from + period_length

        # Injury time display: "45+2:30" instead of "47:30"
        if minutes >= regular_end and time_added:
            injury_min = minutes - regular_end
            return f"{regular_end}+{injury_min}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    # Fall back to state_id labels
    state_id = _state_ids.get(fixture_id)
    if state_id is None:
        return ""
    state_name = STATE_NAMES.get(state_id, "")

    if state_id == 1:   # Not Started
        return ""
    if state_id == 3:   # Half Time
        return "HT"
    if state_id == 5:   # Full Time
        return "FT"
    if state_id == 7:   # After Extra Time
        return "AET"
    if state_id == 8:   # After Penalties
        return "FTP"
    if state_id == 4:   # Break
        return "BRK"
    if state_id == 21:  # Extra Time Break
        return "ETB"
    if state_id == 25:  # Penalties Break
        return "PENB"
    if state_id == 9:   # Penalties in play
        return "PEN"

    return state_name


def get_time_remaining(fixture_id):
    """Return a string like '22:15' showing time left in the current period, or empty.

    Uses period_length (typically 45) minus elapsed minutes/seconds.
    Returns empty for injury time, breaks, and non-ticking states.
    """
    period = get_current_period(fixture_id)
    if not period or period.get("minutes") is None:
        return ""
    minutes = period["minutes"]
    seconds = period.get("seconds", 0) or 0
    period_length = period.get("period_length", 45)
    counts_from = period.get("counts_from", 0)
    regular_end = counts_from + period_length

    # In injury time — no predictable remaining
    if minutes >= regular_end:
        return ""

    total_elapsed_sec = (minutes - counts_from) * 60 + seconds
    total_period_sec = period_length * 60
    remaining_sec = max(0, total_period_sec - total_elapsed_sec)
    rm = remaining_sec // 60
    rs = remaining_sec % 60
    return f"{rm}:{rs:02d}"


def get_game_seconds_remaining(fixture_id):
    """Estimate total seconds remaining in the match (all periods), or None.

    Only returns a value during 2nd half or later (state_id 22, 6, 23, 9).
    In the 2nd half, estimates based on 90-minute regulation.
    Returns None for 1st half, breaks, or finished matches.
    """
    state_id = _state_ids.get(fixture_id)
    if state_id is None:
        return None

    # Only burn during 2nd half and beyond
    if state_id not in {22, 6, 23, 9}:  # 2H, ET, ET2H, PEN
        return None

    period = get_current_period(fixture_id)
    if not period or period.get("minutes") is None:
        return None

    minutes = period["minutes"]
    seconds = period.get("seconds", 0) or 0

    if state_id == 22:  # 2nd half — game ends around 90'
        end_minute = 90
    elif state_id == 6:   # ET 1st half — ends around 105'
        end_minute = 105
    elif state_id == 23:  # ET 2nd half — ends around 120'
        end_minute = 120
    elif state_id == 9:   # Penalties — could end any moment
        return 300  # rough estimate: 5 minutes
    else:
        return None

    # Add ~5 min for expected injury time
    end_minute += 5
    remaining = max(0, (end_minute * 60) - (minutes * 60 + seconds))
    return remaining


def get_game_phase_is_second_half():
    """Return True if any live game is in the 2nd half or later."""
    for fid, sid in _state_ids.items():
        if sid in {22, 6, 23, 9}:  # 2H, ET, ET2H, PEN
            return True
    return False


def get_min_game_seconds_remaining():
    """Return the minimum seconds remaining across all live games, or None."""
    results = []
    for fid in _state_ids:
        r = get_game_seconds_remaining(fid)
        if r is not None:
            results.append(r)
    return min(results) if results else None


HALFTIME_DURATION_SEC = 15 * 60  # 15 minute halftime break


def get_phase_time_segments():
    """Estimate remaining seconds in each upcoming phase for token budgeting.

    Returns a list of (phase, seconds) tuples representing the time segments
    from now until the match ends. For example, during the 1st half:
        [("playing", 600), ("break", 900), ("playing", 2700)]
    means 10 min left in 1H, 15 min halftime, then 45 min 2H.

    Returns None if no live games or not enough info to estimate.
    """
    for fid, sid in _state_ids.items():
        period = get_current_period(fid)

        if sid == 2:  # 1st Half
            if period and period.get("minutes") is not None:
                minutes = period["minutes"]
                seconds = period.get("seconds", 0) or 0
                period_length = period.get("period_length", 45)
                counts_from = period.get("counts_from", 0)
                regular_end = counts_from + period_length
                elapsed_sec = (minutes - counts_from) * 60 + seconds
                remaining_1h = max(0, period_length * 60 - elapsed_sec)
                # Add ~3 min for expected injury time
                remaining_1h += 3 * 60
            else:
                remaining_1h = 45 * 60  # fallback: full half

            return [
                (PHASE_PLAYING, remaining_1h),
                (PHASE_BREAK, HALFTIME_DURATION_SEC),
                (PHASE_PLAYING, 50 * 60),  # 2H ~45 + 5 min injury
            ]

        elif sid == 3:  # Halftime
            # Estimate time left in halftime — rough guess, ~7.5 min average
            ht_remaining = 7 * 60 + 30
            return [
                (PHASE_BREAK, ht_remaining),
                (PHASE_PLAYING, 50 * 60),
            ]

        elif sid == 22:  # 2nd Half
            r = get_game_seconds_remaining(fid)
            if r is not None:
                return [(PHASE_PLAYING, r)]

    return None


def get_period_info(fixture_id):
    """Return dict with period details for display, or None.

    Keys: minutes, seconds, description, time_added, ticking, counts_from, period_length
    """
    period = get_current_period(fixture_id)
    if not period:
        # Return last completed period if match is in a break state
        periods = _periods.get(fixture_id, [])
        if periods:
            sorted_p = sorted(periods, key=lambda p: p.get("sort_order", 0))
            return sorted_p[-1] if sorted_p else None
        return None
    return period


def update_events(fixture_id, events):
    """Store live events for a fixture."""
    _events[fixture_id] = events


def get_events(fixture_id):
    """Return events list for a fixture, or empty list."""
    return _events.get(fixture_id, [])


def update_from_live(fixture_id, home, away, home_score, away_score):
    """Update scores from live API data. Creates the entry if it doesn't exist."""
    if fixture_id in _scores:
        _scores[fixture_id]["home_score"] = home_score
        _scores[fixture_id]["away_score"] = away_score
        _scores[fixture_id]["has_score"] = True
        _scores[fixture_id]["live"] = True
    else:
        _scores[fixture_id] = {
            "home": home,
            "away": away,
            "home_score": home_score,
            "away_score": away_score,
            "has_score": True,
            "live": True,
        }


def get_live_games():
    """Return list of (fixture_id, info_dict) for currently live games."""
    update_live_flags()
    return [(fid, s) for fid, s in _scores.items() if s.get("live")]


def get_next_game_today():
    """Return (fixture_id, home, away, kickoff_dt) for the next upcoming game today, or None."""
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    best = None
    for fid, starting in _fixture_times.items():
        if not starting or not starting.startswith(today_str):
            continue
        try:
            utc_dt = datetime.strptime(starting, "%Y-%m-%d %H:%M:%S")
            utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if utc_dt <= now:
            continue
        if best is None or utc_dt < best[3]:
            s = _scores.get(fid, {})
            best = (fid, s.get("home", ""), s.get("away", ""), utc_dt)
    return best


def clear_live_state():
    """Clear all live tracking state (no games in play)."""
    _state_ids.clear()
    _periods.clear()
    _events.clear()
    for fid in _scores:
        _scores[fid]["live"] = False


def get_all_scores():
    """Return the full scores dict (read-only snapshot)."""
    return dict(_scores)


# ── Polling phase detection ──────────────────────────────────────────────
# State IDs grouped by polling phase
_PREGAME_STATE_IDS = {1, 13, 26}             # NS, TBA, PEND -- not started yet
_PLAYING_STATE_IDS = {2, 6, 9, 22, 23}      # 1H, ET, PEN, 2H, ET2H -- active play
_BREAK_STATE_IDS = {3, 4, 18, 21, 25}       # HT, BRK, INT, ETB, PENB -- breaks
_FINISHED_STATE_IDS = {5, 7, 8}             # FT, AET, FTP -- match over

# Phases returned by get_poll_phase()
PHASE_IDLE = "idle"           # no live games, nothing imminent
PHASE_PREGAME = "pregame"     # game coming up soon but not started
PHASE_PLAYING = "playing"     # active play (1H, 2H, ET, PEN)
PHASE_BREAK = "break"         # half-time or other break
PHASE_POSTGAME = "postgame"   # match just ended (cooldown)

# How long after FT/AET/FTP to stay in postgame phase (seconds)
POSTGAME_COOLDOWN_SEC = 300


def get_poll_phase():
    """Determine the current polling phase based on live game states.

    Returns one of: PHASE_IDLE, PHASE_PREGAME, PHASE_PLAYING, PHASE_BREAK, PHASE_POSTGAME
    """
    has_pregame = False
    has_playing = False
    has_break = False
    has_finished = False

    for fid in list(_state_ids.keys()):
        sid = _state_ids[fid]
        if sid in _PLAYING_STATE_IDS:
            has_playing = True
        elif sid in _BREAK_STATE_IDS:
            has_break = True
        elif sid in _FINISHED_STATE_IDS:
            has_finished = True
        elif sid in _PREGAME_STATE_IDS:
            has_pregame = True

    if has_playing:
        return PHASE_PLAYING
    if has_break:
        return PHASE_BREAK
    if has_finished:
        return PHASE_POSTGAME
    if has_pregame:
        return PHASE_PREGAME

    # No active states -- check if a game is coming up soon
    nxt = get_next_game_today()
    if nxt:
        _, _, _, kick = nxt
        now = datetime.now(timezone.utc)
        secs = (kick - now).total_seconds()
        if 0 < secs <= 600:  # within 10 minutes
            return PHASE_PREGAME

    return PHASE_IDLE
