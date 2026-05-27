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

"""Shared constants used across multiple modules.

Centralises magic numbers so every module references the same named value
rather than duplicating raw literals.
"""

# ── DMX / sACN ────────────────────────────────────────────────────────
DMX_CHANNEL_COUNT = 512         # why: E1.31 / DMX512 standard defines 512 channels per universe
DMX_MAX_VALUE = 255             # why: DMX channel values are 8-bit unsigned (0-255)
TRIGGER_UNIVERSE = 2            # why: trigger channels live on a separate universe from colour data

# ── Default colours ───────────────────────────────────────────────────
DEFAULT_TEAM_COLOURS = [[128, 128, 128]] * 3  # why: neutral grey placeholder when a team has no colours defined

# ── Timing (milliseconds unless noted) ────────────────────────────────
RANDOM_CYCLE_INTERVAL_MS = 3000         # why: fast enough to confirm sACN output, slow enough to read RGB values
TRIGGER_PULSE_DURATION_MS = 5000        # why: 5-second trigger pulse matches typical sports-broadcast cue length
TRIGGER_PROGRESS_TICK_MS = 50           # why: 50ms tick gives smooth progress-bar animation (20 fps)
FLASH_INTERVAL_MS = 400                 # why: 400ms on/off cycle is visible but not seizure-inducing
DEFAULT_GOAL_DURATION_SEC = 30          # why: 30-second goal celebration matches typical broadcast replay window

# ── UI sizing ─────────────────────────────────────────────────────────
SWATCH_CANVAS_SIZE = 100                # why: main generator swatches -- large enough to be clearly visible
