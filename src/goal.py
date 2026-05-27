import time

# Threshold: if a channel is above this, it counts as "white-ish"
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
            result.append(_dim_colour(rgb, 0.15))
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

    def trigger(self, colours, country_name, duration=30):
        """Start a goal flash for `duration` seconds."""
        self.colours = colours
        self.team_name = country_name
        self.set_label(f"GOAL! {country_name}")
        self.draw_swatches(colours)

        if self.timer_id:
            self.root.after_cancel(self.timer_id)

        self.end_time = time.time() + duration
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

        self.timer_id = self.root.after(400, lambda: self._flash(not show_on))
