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
import socket
import uuid

from src.constants import DMX_CHANNEL_COUNT, DMX_MAX_VALUE


# Work around a bug in the `sacn` library: when sACNsender construction fails
# (e.g. an unbindable bind_address), __init__ raises before setting
# `_sender_handler`, and the half-built object's __del__ -> stop() then raises
# "AttributeError: 'sACNsender' object has no attribute '_sender_handler'".
# Guard stop() so such an object is garbage-collected silently.
_orig_sender_stop = sacn.sACNsender.stop


def _safe_sender_stop(self):
    if getattr(self, "_sender_handler", None) is None:
        return
    _orig_sender_stop(self)


sacn.sACNsender.stop = _safe_sender_stop


class SacnConnection:
    """Configurable sACN sender. Supports unicast (IP) or multicast."""

    def __init__(self, destination_ip=None, source_name="ColourMockDevice", bind_address="0.0.0.0"):
        # Per-colour channel mapping: [{r, g, b, universe}, ...]
        self.channel_map = [
            {"r": 1, "g": 2, "b": 3, "universe": 1},
            {"r": 4, "g": 5, "b": 6, "universe": 1},
            {"r": 7, "g": 8, "b": 9, "universe": 1},
        ]
        self.destination_ip = destination_ip
        # why: binding the sender socket to a specific NIC's IP forces multicast (and
        # unicast) egress out that interface -- essential on multi-NIC machines where the
        # OS would otherwise pick the default-route NIC. "0.0.0.0" = let the OS choose.
        self.bind_address = bind_address or "0.0.0.0"
        self.sender = None
        self.source_name = source_name
        self._cid_uuid = uuid.uuid4()  # why: UUID CID lets sACN receivers uniquely identify this source
        self.cid = str(self._cid_uuid)
        self._active_universes = set()
        self.extra_universes = set()  # why: separate universe set for trigger channels so they are auto-activated on connect
        atexit.register(self.stop)  # why: ensures DMX outputs are zeroed even on crash or unhandled exception

    def connect(self):
        """Start sACN sender. Raises if bind_address is unavailable.

        Always leaves the object cleanly disconnected on any failure (so a failed
        re-connect -- e.g. pressing Connect again while already connected -- can't
        leave a half-built sender behind).
        """
        self.stop()
        # Pre-flight: confirm the bind address is actually assignable on this
        # machine. This gives a clear error and avoids half-constructing a sender
        # (whose __del__ would otherwise error) when the NIC is wrong/absent.
        if self.bind_address and self.bind_address != "0.0.0.0":
            try:
                _probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                _probe.bind((self.bind_address, 0))
                _probe.close()
            except OSError as e:
                raise OSError(f"Cannot bind to NIC {self.bind_address}: {e}")
        try:
            self.sender = sacn.sACNsender(cid=tuple(self._cid_uuid.bytes), source_name=self.source_name,
                                          bind_address=self.bind_address)
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
        except Exception:
            self.stop()  # tear down any partially-built sender before propagating
            raise

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

    def reconfigure(self, channel_map=None, destination_ip=None, bind_address=None):
        """Reconfigure and reconnect. Returns (True, "") on success or (False, reason) on failure."""
        if channel_map is not None:
            self.channel_map = channel_map
        if destination_ip is not None:
            self.destination_ip = destination_ip if destination_ip != "" else None
        if bind_address is not None:
            self.bind_address = bind_address if bind_address != "" else "0.0.0.0"
        try:
            self.connect()
            return True, ""
        except Exception as e:  # why: never let a (re)connect failure crash the Tk button callback
            self.stop()
            return False, str(e)

    def bounce(self):
        """Stop and immediately restart the sender with the current configuration.

        A quick health check: receivers see this source drop and re-appear, and any
        bind/NIC problem surfaces as an error. Returns (True, "") on success or
        (False, reason) on failure.
        """
        try:
            self.connect()  # connect() stops the existing sender first, then re-activates outputs
            return True, ""
        except Exception as e:  # why: never let a bounce failure crash the Tk button callback
            self.stop()
            return False, str(e)

    def stop(self):
        if self.sender:
            try:
                self.sender.stop()
            except Exception:
                pass
            self.sender = None
