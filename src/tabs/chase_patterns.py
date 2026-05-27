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

"""Chase pattern constants, colour resolution, and file I/O.

Key design decisions:
    - Colour resolution maps dropdown labels ("Colour 1/2/3") to actual team RGB
      values at runtime, allowing patterns to adapt to any team's colours.
    - Patterns stored as JSON for easy hand-editing and external tooling.
"""

import json
import os

PATTERNS_FILE = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "assets", "patterns.json")

COLOUR_OPTIONS = ["Colour 1", "Colour 2", "Colour 3", "Black", "White"]
COLOUR_MAP = {
    "Black": [0, 0, 0],
    "White": [255, 255, 255],
}


def resolve_colour(choice, team_colours):
    """Resolve a dropdown choice to an RGB list."""
    if choice in COLOUR_MAP:
        return list(COLOUR_MAP[choice])
    if team_colours:
        # why: maps "Colour 1/2/3" labels to team RGB values so patterns adapt to any team
        idx = {"Colour 1": 0, "Colour 2": 1, "Colour 3": 2}.get(choice, 0)
        if idx < len(team_colours):
            return list(team_colours[idx])
    return [0, 0, 0]


def load_patterns():
    if os.path.exists(PATTERNS_FILE):
        with open(PATTERNS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_patterns(patterns):
    with open(PATTERNS_FILE, "w") as f:
        json.dump(patterns, f, indent=2)
