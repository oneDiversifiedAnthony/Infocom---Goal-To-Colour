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

MATCH_DURATION_MINUTES = 120


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
        if fid not in _scores:
            _scores[fid] = {
                "home": f.get("home", ""),
                "away": f.get("away", ""),
                "home_score": f.get("home_score") or 0,
                "away_score": f.get("away_score") or 0,
                "live": False,
            }


def goal_scored(team_name):
    """Increment score for team_name in whatever fixture they're playing."""
    for fid, s in _scores.items():
        if s["home"] == team_name:
            s["home_score"] += 1
            return fid
        if s["away"] == team_name:
            s["away_score"] += 1
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
    if s["home_score"] == 0 and s["away_score"] == 0:
        return ""
    return f"{s['home_score']} - {s['away_score']}"


def is_live(fixture_id):
    """Check if a fixture is currently live based on start time."""
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


def get_all_scores():
    """Return the full scores dict (read-only snapshot)."""
    return dict(_scores)
