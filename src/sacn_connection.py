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
sACN (E1.31 streaming DMX) network sender.

Manages DMX universe connections and per-colour RGB channel mapping.  Supports
both unicast (specific IP) and multicast transport modes.

Events handled:
    - connect() / reconfigure() -- (re)establishes the sACN sender session.
    - send_rgb(colours) -- pushes a list of RGB triplets to the mapped DMX channels.
    - send_trigger(universe, channel, value) -- sets a single DMX channel, used for
      goal-trigger signals on dedicated universes.
    - stop() -- tears down the sender (also registered with atexit for crash safety).

Design decisions:
    - A UUID-based CID is generated once per instance so that sACN receivers can
      uniquely identify this source across reconnections within the same process.
    - The channel_map is structured per-colour (one dict per colour with r/g/b/universe
      keys) rather than per-channel, because the application always thinks in terms of
      three colours -- this keeps the mapping API simpler and avoids off-by-one errors.
    - extra_universes allows trigger channels to live on separate DMX universes from
      the colour data without requiring the caller to know activation details.
    - atexit.register(self.stop) ensures DMX outputs are zeroed even on unhandled
      exceptions or interpreter shutdown.
"""

import sacn
import atexit
import uuid

from src.constants import DMX_CHANNEL_COUNT, DMX_MAX_VALUE


class SacnConnection:
    """Configurable sACN sender. Supports unicast (IP) or multicast."""

    def __init__(self, destination_ip=None, source_name="ColourMockDevice"):
        # Per-colour channel mapping: [{r, g, b, universe}, ...]
        self.channel_map = [
            {"r": 1, "g": 2, "b": 3, "universe": 1},
            {"r": 4, "g": 5, "b": 6, "universe": 1},
            {"r": 7, "g": 8, "b": 9, "universe": 1},
        ]
        self.destination_ip = destination_ip
        self.sender = None
        self.source_name = source_name
        self._cid_uuid = uuid.uuid4()  # why: UUID CID lets sACN receivers uniquely identify this source
        self.cid = str(self._cid_uuid)
        self._active_universes = set()
        self.extra_universes = set()  # why: separate universe set for trigger channels so they are auto-activated on connect
        atexit.register(self.stop)  # why: ensures DMX outputs are zeroed even on crash or unhandled exception

    def connect(self):
        self.stop()
        self.sender = sacn.sACNsender(cid=tuple(self._cid_uuid.bytes), source_name=self.source_name)
        self.sender.start()
        self._active_universes = set()
        # Collect all universes to activate (channel map + extras like triggers)
        all_universes = set(m["universe"] for m in self.channel_map)
        all_universes.update(self.extra_universes)
        for uni in sorted(all_universes):
            if uni not in self._active_universes:
                self.sender.activate_output(uni)
                self.sender[uni].source_name = self.source_name
                if self.destination_ip:
                    self.sender[uni].multicast = False
                    self.sender[uni].destination = self.destination_ip
                else:
                    self.sender[uni].multicast = True
                self._active_universes.add(uni)

    def send_rgb(self, colours):
        """Send RGB colours using per-colour channel/universe mapping."""
        if not self.sender:
            return
        # Build per-universe channel data
        uni_data = {}
        for i, rgb in enumerate(colours):
            if i >= len(self.channel_map):
                break
            m = self.channel_map[i]
            uni = m["universe"]
            if uni not in uni_data:
                uni_data[uni] = [0] * DMX_CHANNEL_COUNT
            data = uni_data[uni]
            for ch, val in [(m["r"], rgb[0]), (m["g"], rgb[1]), (m["b"], rgb[2])]:
                if 1 <= ch <= DMX_CHANNEL_COUNT:
                    data[ch - 1] = val
        # Send to each universe
        for uni, data in uni_data.items():
            try:
                output = self.sender[uni]
                if output is None:
                    continue
            except (KeyError, TypeError):
                continue
            output.dmx_data = tuple(data)

    def send_trigger(self, universe, channel, value=DMX_MAX_VALUE):
        """Set a single channel on a universe to a value."""
        if not self.sender:
            return
        # Activate universe if not already active
        if universe not in self._active_universes:
            self.sender.activate_output(universe)
            self.sender[universe].source_name = self.source_name
            if self.destination_ip:
                self.sender[universe].multicast = False
                self.sender[universe].destination = self.destination_ip
            else:
                self.sender[universe].multicast = True
            self._active_universes.add(universe)
        try:
            output = self.sender[universe]
            if output is None:
                return
        except (KeyError, TypeError):
            return
        data = list(output.dmx_data) if output.dmx_data else [0] * DMX_CHANNEL_COUNT
        if 1 <= channel <= DMX_CHANNEL_COUNT:
            data[channel - 1] = value
        output.dmx_data = tuple(data)

    def reconfigure(self, channel_map=None, destination_ip=None):
        if channel_map is not None:
            self.channel_map = channel_map
        if destination_ip is not None:
            self.destination_ip = destination_ip if destination_ip != "" else None
        self.connect()

    def stop(self):
        if self.sender:
            try:
                self.sender.stop()
            except Exception:
                pass
            self.sender = None
