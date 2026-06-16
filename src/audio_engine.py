# Copyright (c) 2026 oneDiversified.
#
# This software, its source code, and all associated functions, scripts, and
# documentation are the proprietary and confidential property of oneDiversified.

"""Multi-device audio playback engine.

pygame.mixer can only hold ONE output device open at a time, so routing
different sounds to different Dante Virtual Soundcard channel pairs (1-2, 3-4,
5-6 ...) simultaneously is impossible with it -- switching devices reinitialises
the mixer and stops everything.

This engine instead keeps one persistent ``sounddevice`` (PortAudio) output
stream open per device and mixes the voices assigned to that device in the
stream callback. Any number of sounds can therefore play to any number of
devices at the same time, and every card stays "at the ready" on its own output.

Decoding is delegated to pygame (its Sound loader handles mp3/ogg/wav and
resamples to the mixer rate); the mixer device it opens is used ONLY to decode,
never for output. ``Sound``/``Channel`` mirror the small slice of the pygame API
the rest of the app relies on (get_raw, get_length, play, stop, set_volume,
get_busy) so callers barely change.
"""

import atexit
import threading

import numpy as np
import sounddevice as sd
import pygame

SAMPLE_RATE = 48000   # why: matches the Dante Virtual Soundcard clock
CHANNELS = 2
_BLOCKSIZE = 512      # why: ~10 ms at 48 kHz -- low latency without underruns

# Host APIs preferred in this order (full, untruncated device names + low latency)
_HOSTAPI_PREFERENCE = ("wasapi", "directsound", "wdm-ks", "mme")

_decoder_ready = [False]
_decoder_lock = threading.Lock()


def _ensure_decoder():
    """Initialise a pygame mixer purely for decoding files to 48k/16-bit/stereo."""
    if _decoder_ready[0]:
        return
    with _decoder_lock:
        if _decoder_ready[0]:
            return
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=CHANNELS, buffer=1024)
        _decoder_ready[0] = True


def prime_decoder():
    """Initialise the decoder up front (call from the main thread at startup).

    Sounds are decoded on background threads; initialising SDL audio off the main
    thread is risky, so prime it here first.
    """
    _ensure_decoder()


# ── Device resolution ────────────────────────────────────────────────────────
def _host_rank(hostapi_index):
    try:
        name = sd.query_hostapis(hostapi_index)["name"].lower()
    except Exception:
        return len(_HOSTAPI_PREFERENCE)
    for rank, key in enumerate(_HOSTAPI_PREFERENCE):
        if key in name:
            return rank
    return len(_HOSTAPI_PREFERENCE)


def resolve_device(name):
    """Map a device name (as saved in config/medits) to a sounddevice index.

    Returns None to mean the system default output. MME truncates names to 31
    chars, so we match on exact name, truncation, or a loose contains test, and
    prefer WASAPI/DirectSound (which expose the full name and lower latency).
    """
    if not name:
        return None
    try:
        devices = sd.query_devices()
    except Exception:
        return None
    candidates = []
    for i, d in enumerate(devices):
        if d["max_output_channels"] <= 0:
            continue
        dn = d["name"]
        if dn == name or dn.startswith(name[:31]) or name.startswith(dn):
            candidates.append((_host_rank(d["hostapi"]), i))
    if not candidates:
        key = name[:20]
        for i, d in enumerate(devices):
            if d["max_output_channels"] <= 0:
                continue
            if key in d["name"] or d["name"][:20] in name:
                candidates.append((_host_rank(d["hostapi"]), i))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def list_output_devices():
    """Return de-duplicated full output device names, best host API first."""
    try:
        devices = sd.query_devices()
    except Exception:
        return []
    seen = {}
    for d in devices:
        if d["max_output_channels"] <= 0:
            continue
        name = d["name"]
        rank = _host_rank(d["hostapi"])
        # Keep the best-ranked (and thus full-named) entry per device name
        if name not in seen or rank < seen[name]:
            seen[name] = rank
    # Drop names that are prefixes of a longer name (MME truncations)
    names = sorted(seen.keys())
    result = []
    for name in names:
        if any(other != name and other.startswith(name) for other in names):
            continue  # truncated duplicate of a fuller name
        result.append(name)
    return result


# ── Voices and per-device streams ────────────────────────────────────────────
class _Voice:
    __slots__ = ("data", "pos", "loops", "volume", "active", "stopflag")

    def __init__(self, data, loops, volume):
        self.data = data        # float32 array, shape (n, 2)
        self.pos = 0
        self.loops = loops      # remaining loops; -1 = infinite
        self.volume = float(volume)
        self.active = True
        self.stopflag = False


class _DeviceStream:
    def __init__(self, device_index):
        self.lock = threading.Lock()
        self.voices = []
        self.stream = sd.OutputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
            device=device_index, blocksize=_BLOCKSIZE, callback=self._callback)
        self.stream.start()

    def _callback(self, outdata, frames, time_info, status):
        outdata.fill(0.0)
        with self.lock:
            if not self.voices:
                return
            for v in self.voices:
                if v.stopflag:
                    v.active = False
                    continue
                out_off = 0
                remaining = frames
                while remaining > 0:
                    avail = len(v.data) - v.pos
                    if avail <= 0:
                        if v.loops == 0:
                            v.active = False
                            break
                        if v.loops > 0:
                            v.loops -= 1
                        v.pos = 0
                        avail = len(v.data)
                    n = avail if avail < remaining else remaining
                    outdata[out_off:out_off + n] += v.data[v.pos:v.pos + n] * v.volume
                    v.pos += n
                    out_off += n
                    remaining -= n
            if any(not v.active for v in self.voices):
                self.voices = [v for v in self.voices if v.active]
        np.clip(outdata, -1.0, 1.0, out=outdata)

    def add(self, voice):
        with self.lock:
            self.voices.append(voice)

    def close(self):
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


_streams = {}
_streams_lock = threading.Lock()


def _get_stream(device_index):
    with _streams_lock:
        st = _streams.get(device_index)
        if st is None:
            st = _DeviceStream(device_index)
            _streams[device_index] = st
        return st


def shutdown():
    """Close all open output streams and the decoder mixer."""
    with _streams_lock:
        for st in _streams.values():
            st.close()
        _streams.clear()
    if _decoder_ready[0]:
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        _decoder_ready[0] = False


atexit.register(shutdown)


# ── pygame-compatible Sound / Channel ────────────────────────────────────────
class Sound:
    """Decoded audio buffer. Construct from a file path or raw 16-bit stereo bytes."""

    def __init__(self, filepath=None, buffer=None):
        if buffer is not None:
            raw = bytes(buffer)
        else:
            _ensure_decoder()
            raw = pygame.mixer.Sound(filepath).get_raw()
        self._raw = raw
        arr = np.frombuffer(raw, dtype="<i2")
        if arr.size % CHANNELS:
            arr = arr[:arr.size - (arr.size % CHANNELS)]
        # float32 in [-1, 1), shape (frames, 2)
        self._data = (arr.reshape(-1, CHANNELS).astype(np.float32)) / 32768.0
        self._voices = []

    def get_raw(self):
        return self._raw

    def get_length(self):
        n = len(self._data)
        return n / SAMPLE_RATE if n else 0.0

    def play(self, loops=0, device=None, volume=1.0):
        """Start playback on the given device (name or None=default). Returns a Channel."""
        try:
            idx = resolve_device(device)
            stream = _get_stream(idx)
        except Exception:
            return None
        voice = _Voice(self._data, loops, volume)
        self._voices = [v for v in self._voices if v.active and not v.stopflag]
        self._voices.append(voice)
        stream.add(voice)
        return Channel(voice)

    def stop(self):
        """Stop every currently-playing instance of this sound."""
        for v in self._voices:
            v.stopflag = True
        self._voices = []


class Channel:
    """Handle to one playing voice, mirroring the pygame Channel methods used."""

    def __init__(self, voice):
        self._v = voice

    def set_volume(self, volume):
        self._v.volume = float(volume)

    def get_busy(self):
        return self._v.active and not self._v.stopflag

    def stop(self):
        self._v.stopflag = True
