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

"""Sound keybinding -- maps F-keys to sound card play/stop.

F1 = first sound, F2 = second, etc. up to F12.
- Quick press toggles play/stop.
- Press and hold plays; release stops.
"""

import time

HOLD_THRESHOLD_MS = 300
F_KEYS = [f"F{i}" for i in range(1, 13)]


def bind_sound_keys(root, sound_controls):
    """Bind F-keys to sound controls.

    Args:
        root: The tkinter root window.
        sound_controls: List of dicts with 'play', 'stop', and 'is_playing' callables.
    """
    key_press_time = {}
    key_held = {}

    def _on_key_press(event):
        key = event.keysym
        if key not in F_KEYS:
            return
        idx = F_KEYS.index(key)
        if idx >= len(sound_controls):
            return

        ctrl = sound_controls[idx]

        # Ignore auto-repeat (key already held down)
        if key_held.get(key, False):
            return

        key_press_time[key] = time.time()
        key_held[key] = True

        if ctrl["is_playing"]():
            # Already playing -- stop (toggle off)
            ctrl["stop"]()
            key_held[key] = False
            key_press_time.pop(key, None)
        else:
            # Start playing
            ctrl["play"]()

    def _on_key_release(event):
        key = event.keysym
        if key not in F_KEYS:
            return
        idx = F_KEYS.index(key)
        if idx >= len(sound_controls):
            return

        if not key_held.get(key, False):
            return
        key_held[key] = False

        ctrl = sound_controls[idx]
        press_time = key_press_time.pop(key, None)
        if press_time is None:
            return

        elapsed_ms = (time.time() - press_time) * 1000

        if elapsed_ms >= HOLD_THRESHOLD_MS and ctrl["is_playing"]():
            # Was held -- stop on release
            ctrl["stop"]()
        # If quick press, leave it playing (toggle behavior)

    root.bind("<KeyPress>", _on_key_press, add=True)
    root.bind("<KeyRelease>", _on_key_release, add=True)
