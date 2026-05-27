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

"""Chase pattern step runner -- steps through frames using tkinter after() timer.

Handles events:
    - start() begins playback of a step list, scheduling each frame via after().
    - stop() cancels the active timer and halts the chase.

Key design decisions:
    - Separated from the Chases UI so the controller can be reused or tested independently.
    - Minimum 50ms delay prevents UI freeze on very fast patterns.
    - Modulo wrapping on current_step creates an infinite loop through steps.
"""

from .chase_patterns import resolve_colour


class ChaseController:
    """Runs a chase pattern by stepping through frames."""

    def __init__(self, root, draw_swatches_cb, get_team_colours_cb):
        self.root = root
        self.draw_swatches = draw_swatches_cb
        self.get_team_colours = get_team_colours_cb
        self.timer_id = None
        self.steps = []
        self.current_step = 0
        self.running = False

    def start(self, steps):
        """Start running a chase pattern (list of step dicts)."""
        self.stop()
        if not steps:
            return
        self.steps = steps
        self.current_step = 0
        self.running = True
        self._run_step()

    def stop(self):
        self.running = False
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

    @property
    def is_active(self):
        return self.running

    def _run_step(self):
        if not self.running or not self.steps:
            return

        step = self.steps[self.current_step]
        team_colours = self.get_team_colours()

        colours = [
            resolve_colour(step["ch1"], team_colours),
            resolve_colour(step["ch2"], team_colours),
            resolve_colour(step["ch3"], team_colours),
        ]
        self.draw_swatches(colours)

        delay_ms = int(float(step.get("time", 0.5)) * 1000)
        delay_ms = max(50, delay_ms)  # why: minimum 50ms prevents UI freeze on very fast patterns

        self.current_step = (self.current_step + 1) % len(self.steps)  # why: modulo wrapping creates infinite loop through steps
        self.timer_id = self.root.after(delay_ms, self._run_step)
