# Copyright (c) 2026 oneDiversified.
#
# This software, its source code, and all associated functions, scripts, and
# documentation are the proprietary and confidential property of oneDiversified.

"""OSC WAVE backend -- drives a Yamaha DM7 (or any OSC fader receiver) over UDP.

Based on the reference script: python-osc SimpleUDPClient + osc_message_builder,
sending one OSC message per fader carrying (channel:int, level:float), animated as
a travelling sine wave. The blocking ``while True`` loop is replaced with a daemon
thread so the Tk GUI stays responsive; ``_stop.wait()`` makes the 20 ms tick
interruptible for a clean stop.

OSC is fire-and-forget UDP: "connect" just prepares the client socket (and binds
it to the chosen NIC so traffic egresses the right interface). There is no
handshake/ack from the console.
"""

import atexit
import math
import threading
import time

from pythonosc import udp_client
from pythonosc import osc_message_builder

# Defaults for the Yamaha DM7 (IP persisted in config.ini [osc_wave])
DEFAULT_IP = "10.201.100.14"
DEFAULT_PORT = 49900

# DM7 OSC fader-level parameter, per the DM7 OSC Specifications V1.1.0:
#   /yosc:req/set/MIXER:Current/InCh/Fader/Level/<ch>  <level:int>
# The channel number is appended to the address path; the single integer argument
# is the level in centi-dB (raw = dB * 100): 0 = 0 dB, -2000 = -20 dB, -32768 = -inf.
DEFAULT_FADER_ADDRESS = "/yosc:req/set/MIXER:Current/InCh/Fader/Level"

FADER_COUNT = 16        # VEGAS MODE waves across input faders 1-16
WAVE_SPEED = 5.0        # sine angular speed (rad/s) -- from the reference (5 * t)
CHANNEL_PHASE = 0.5     # per-channel phase offset (rad) -> travelling wave down the bank
TICK_SEC = 0.02         # 20 ms between frames -- clean traffic + fluid motion

# Wave sweeps fader level between these centi-dB values (raw = dB * 100).
# -4000 = -40 dB (trough) .. 0 = 0 dB / unity (crest). DM7 range is -32768..1000.
LEVEL_MIN_CDB = -4000
LEVEL_MAX_CDB = 0


class OscWaveEngine:
    """Holds the OSC UDP client and runs the VEGAS MODE wave on a background thread."""

    def __init__(self):
        self.client = None
        self.ip = DEFAULT_IP
        self.port = DEFAULT_PORT
        self.bind_ip = None
        self.address = DEFAULT_FADER_ADDRESS
        self.connected = False
        self._thread = None
        self._stop = threading.Event()
        atexit.register(self.disconnect)

    def connect(self, ip, port, bind_ip=None, address=None):
        """Prepare the OSC UDP client. Returns (True, "") or (False, reason)."""
        self.stop_vegas()
        try:
            port = int(port)
        except (TypeError, ValueError):
            return False, "Port must be a number"
        if address:
            self.address = address
        try:
            client = udp_client.SimpleUDPClient(ip, port)
            # Bind the source socket to the chosen NIC so OSC egresses that interface
            if bind_ip and bind_ip not in ("", "0.0.0.0"):
                client._sock.bind((bind_ip, 0))
        except OSError as e:
            self.client = None
            self.connected = False
            return False, str(e)
        self.client = client
        self.ip = ip
        self.port = port
        self.bind_ip = bind_ip or None
        self.connected = True
        return True, ""

    def disconnect(self):
        self.stop_vegas()
        sock = getattr(self.client, "_sock", None)
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self.client = None
        self.connected = False

    @property
    def vegas_active(self):
        return self._thread is not None and self._thread.is_alive()

    def start_vegas(self):
        """Start the sine-wave fader animation. No-op if not connected or already running."""
        if not self.client or self.vegas_active:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_wave, daemon=True)
        self._thread.start()

    def stop_vegas(self):
        """Stop the wave and join the thread."""
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=1.0)
        self._thread = None

    def _run_wave(self):
        # monotonic clock so the wave keeps accurate phase even under load
        start = time.monotonic()
        while not self._stop.is_set():
            t = time.monotonic() - start
            for ch in range(1, FADER_COUNT + 1):
                # Normalised 0.0-1.0 sine; per-channel phase makes the wave travel
                wave = 0.5 + 0.5 * math.sin(WAVE_SPEED * t - ch * CHANNEL_PHASE)  # 0..1
                # Map to fader level in centi-dB (raw = dB * 100), per DM7 Table 1
                level = int(round(LEVEL_MIN_CDB + wave * (LEVEL_MAX_CDB - LEVEL_MIN_CDB)))
                # DM7 address: channel number is the X index appended to the param path
                builder = osc_message_builder.OscMessageBuilder(address=f"{self.address}/{ch}")
                builder.add_arg(level)  # single integer argument (type tag 'i')
                try:
                    self.client.send(builder.build())
                except OSError:
                    return  # socket gone -- stop quietly
            # interruptible 20 ms tick
            if self._stop.wait(TICK_SEC):
                break
