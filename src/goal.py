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
Goal celebration flash controller.

Alternates between full team colours and a dimmed/black "off" frame at 400 ms
intervals for 30 seconds to create a visible goal-flash effect on the sACN-
controlled lighting rig.

Events handled:
    - trigger(colours, country_name, duration) -- starts or restarts the flash cycle.
    - stop() -- cancels any active flash.

Design decisions:
    - White/near-white channels (all components >= 200) flash to full black rather
      than dimming, because dimming white only produces grey which lacks visual
      contrast under stage lighting.
    - Non-white colours dim to 15 % brightness instead of going to black so the
      audience can still perceive the team colour identity during the "off" beat.
    - Wall-clock time (time.time()) is used for duration tracking instead of
      counting frames, so the flash length stays accurate even if tkinter's
      after() timer drifts under heavy UI load.
"""

import time

from src.constants import FLASH_INTERVAL_MS, DEFAULT_GOAL_DURATION_SEC

# why: 200 chosen empirically -- above this, dimming produces muddy grey; full black is more dramatic
WHITE_THRESHOLD = 200


def _dim_colour(rgb, factor=0.0):
    """Dim an RGB colour towards black by factor (0.0 = black, 1.0 = original)."""
    return [int(v * factor) for v in rgb]


def _flash_off_colours(colours):
    """Generate the 'off' frame for a goal flash.

    - White/near-white channels flash to black.
    - Other colours dim towards black (to ~30% brightness).
    """
    result = []
    for rgb in colours:
        if all(v >= WHITE_THRESHOLD for v in rgb):
            # White-ish -> flash to black
            result.append([0, 0, 0])
        else:
            # Dim towards black
            result.append(_dim_colour(rgb, 0.15))  # why: 15 % keeps colour recognisable while still creating a visible flash
    return result


class GoalController:
    """Manages goal flash timing. Call from the main app."""

    def __init__(self, root, draw_swatches_cb, set_label_cb):
        self.root = root
        self.draw_swatches = draw_swatches_cb
        self.set_label = set_label_cb
        self.timer_id = None
        self.end_time = 0
        self.team_name = ""
        self.colours = None

    def trigger(self, colours, country_name, duration=DEFAULT_GOAL_DURATION_SEC):
        """Start a goal flash for `duration` seconds."""
        self.colours = colours
        self.team_name = country_name
        self.set_label(f"GOAL! {country_name}")
        self.draw_swatches(colours)

        if self.timer_id:
            self.root.after_cancel(self.timer_id)

        self.end_time = time.time() + duration  # why: wall-clock time avoids drift if after() is delayed by UI work
        self._flash(True)

    def stop(self):
        """Stop any active goal flash."""
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

    @property
    def is_active(self):
        return self.timer_id is not None

    def _flash(self, show_on):
        if time.time() >= self.end_time:
            # Finished — show team colours one last time
            self.set_label(self.team_name or "Random")
            self.draw_swatches(self.colours)
            self.timer_id = None
            return

        if show_on:
            self.draw_swatches(self.colours)
        else:
            self.draw_swatches(_flash_off_colours(self.colours))

        self.timer_id = self.root.after(FLASH_INTERVAL_MS, lambda: self._flash(not show_on))  # why: 400 ms gives a visible strobe without being seizure-inducing
