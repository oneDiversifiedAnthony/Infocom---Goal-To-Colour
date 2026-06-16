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

"""Sounds tab -- scans Sound Files folder, displays waveform buttons with play/stop and level meter."""

import array
import glob
import json
import math
import os
import struct
import threading
import time
import tkinter as tk
from tkinter import ttk

from src import audio_engine
from src import scores

from src.tabs.sound_keybinding import bind_sound_keys, F_KEYS

from src.config import SOUND_DIR, ANTHEMS_DIR, get_config, set_config
MEDITS_FILE = os.path.join(SOUND_DIR, "medits.json")

# Master / anthem output device name ("" or None = system default). Sound cards
# set to "Default" play on this device; cards with their own device play on
# theirs. The multi-device audio engine keeps a stream open per device, so all
# play simultaneously.
_master_device = [None]
WAVEFORM_W = 300
WAVEFORM_H = 60
LEVEL_W = 20
LEVEL_H = WAVEFORM_H
LEVEL_POLL_MS = 50
PEAK_MAGIC = b"PEAK"
PEAK_VERSION = 1
PEAK_CACHE_POINTS = 4000


def _peak_path(sound_filepath):
    """Return the .peak cache path for a sound file."""
    return os.path.splitext(sound_filepath)[0] + ".peak"


def _save_peak_cache(filepath, peaks_l, peaks_r):
    """Write normalised peaks to a binary .peak file."""
    n = len(peaks_l)
    with open(filepath, "wb") as f:
        f.write(PEAK_MAGIC)
        f.write(struct.pack("<HI", PEAK_VERSION, n))
        for i in range(n):
            f.write(struct.pack("<ff", peaks_l[i], peaks_r[i]))


def _load_peak_cache(peak_file, sound_file):
    """Load cached peaks if the .peak file exists and is newer than the sound file."""
    if not os.path.exists(peak_file):
        return None
    if os.path.getmtime(peak_file) < os.path.getmtime(sound_file):
        return None
    try:
        with open(peak_file, "rb") as f:
            magic = f.read(4)
            if magic != PEAK_MAGIC:
                return None
            ver, n = struct.unpack("<HI", f.read(6))
            if ver != PEAK_VERSION or n == 0:
                return None
            data = f.read(n * 8)
            if len(data) < n * 8:
                return None
            peaks_l = []
            peaks_r = []
            for i in range(n):
                l, r = struct.unpack_from("<ff", data, i * 8)
                peaks_l.append(l)
                peaks_r.append(r)
            return peaks_l, peaks_r
    except (OSError, struct.error):
        return None


def _resample_peaks(peaks_l, peaks_r, num_points):
    """Resample cached peaks to the desired number of display points."""
    n = len(peaks_l)
    if n == 0:
        return [0] * num_points, [0] * num_points
    if num_points >= n:
        return list(peaks_l), list(peaks_r)
    out_l = []
    out_r = []
    for i in range(num_points):
        start = int(i * n / num_points)
        end = max(start + 1, int((i + 1) * n / num_points))
        out_l.append(max(peaks_l[start:end]))
        out_r.append(max(peaks_r[start:end]))
    return out_l, out_r


def _load_medits():
    """Load cue point metadata from medits.json."""
    try:
        with open(MEDITS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_medits(data):
    """Save cue point metadata to medits.json."""
    os.makedirs(os.path.dirname(MEDITS_FILE), exist_ok=True)
    with open(MEDITS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _extract_waveform(sound, num_points):
    """Extract waveform peaks from a pygame Sound. Returns (left_peaks, right_peaks) normalised 0-1."""
    raw = sound.get_raw()
    sample_size = 2  # 16-bit signed
    channels = 2     # stereo
    frame_size = sample_size * channels
    num_frames = len(raw) // frame_size
    if num_frames == 0:
        return [0] * num_points, [0] * num_points

    chunk = max(1, num_frames // num_points)
    peaks_l = []
    peaks_r = []
    for i in range(num_points):
        start = i * chunk * frame_size
        end = min(start + chunk * frame_size, len(raw))
        if start >= len(raw):
            peaks_l.append(0)
            peaks_r.append(0)
            continue
        max_l = 0
        max_r = 0
        for j in range(start, end, frame_size):
            if j + 4 <= len(raw):
                l_sample, r_sample = struct.unpack_from("<hh", raw, j)
                max_l = max(max_l, abs(l_sample))
                max_r = max(max_r, abs(r_sample))
        peaks_l.append(max_l)
        peaks_r.append(max_r)

    peak_max = max(max(peaks_l), max(peaks_r)) if peaks_l else 1
    if peak_max == 0:
        peak_max = 1
    return [p / peak_max for p in peaks_l], [p / peak_max for p in peaks_r]


def _draw_waveform(canvas, waveform_data, cue_in=None, cue_out=None,
                   colour_l="#00cc66", colour_r="#0099ff",
                   view_start=0.0, view_end=1.0, loop_point=None):
    """Draw stereo waveform with optional cue and loop markers.

    view_start/view_end define the visible fraction range (0.0-1.0) for zoom.
    """
    canvas.delete("all")
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    if w < 2 or h < 2:
        return

    peaks_l, peaks_r = waveform_data
    n = len(peaks_l)
    if n == 0:
        return

    # Determine visible sample range
    i_start = max(0, int(view_start * n))
    i_end = min(n, int(view_end * n))
    vis_n = i_end - i_start
    if vis_n <= 0:
        return

    quarter = h // 4
    mid_l = quarter
    mid_r = h - quarter
    bar_w = max(1, w / vis_n)
    bw = max(1, int(bar_w) - 1)

    # Dim regions outside cue points
    dim_l = "#0a4a2a"
    dim_r = "#003366"

    for vi in range(vis_n):
        i = i_start + vi
        x = int(vi * bar_w)
        frac = i / n if n > 1 else 0
        in_region = True
        if cue_in is not None and frac < cue_in:
            in_region = False
        if cue_out is not None and frac > cue_out:
            in_region = False
        cl = colour_l if in_region else dim_l
        cr = colour_r if in_region else dim_r
        amp_l = int(peaks_l[i] * quarter * 0.9)
        canvas.create_line(x, mid_l - amp_l, x, mid_l + amp_l, fill=cl, width=bw)
        amp_r = int(peaks_r[i] * quarter * 0.9)
        canvas.create_line(x, mid_r - amp_r, x, mid_r + amp_r, fill=cr, width=bw)

    # Centre lines and channel labels
    canvas.create_line(0, h // 2, w, h // 2, fill="#555555")
    canvas.create_line(0, mid_l, w, mid_l, fill="#333333")
    canvas.create_line(0, mid_r, w, mid_r, fill="#333333")
    canvas.create_text(4, 2, text="L", fill=colour_l, font=("Consolas", 7), anchor="nw")
    canvas.create_text(4, h // 2 + 2, text="R", fill=colour_r, font=("Consolas", 7), anchor="nw")

    # Zoom level indicator
    view_span = view_end - view_start
    if view_span < 0.99:
        zoom_pct = int(1.0 / view_span * 100)
        canvas.create_text(w - 4, 2, text=f"{zoom_pct}%", fill="#888888",
                          font=("Consolas", 7), anchor="ne")

    # Cue-in marker (mapped to visible range)
    if cue_in is not None and cue_in >= view_start and cue_in <= view_end:
        cx = int((cue_in - view_start) / (view_end - view_start) * w)
        canvas.create_line(cx, 0, cx, h, fill="#00ff00", width=2, tags="cue")
        canvas.create_text(cx + 3, 2, text="[", fill="#00ff00",
                          font=("Consolas", 9, "bold"), anchor="nw", tags="cue")

    # Cue-out marker (mapped to visible range)
    if cue_out is not None and cue_out >= view_start and cue_out <= view_end:
        cx = int((cue_out - view_start) / (view_end - view_start) * w)
        canvas.create_line(cx, 0, cx, h, fill="#ffaa00", width=2, tags="cue")
        canvas.create_text(cx - 3, 2, text="]", fill="#ffaa00",
                          font=("Consolas", 9, "bold"), anchor="ne", tags="cue")

    # Loop-point marker (mapped to visible range)
    if loop_point is not None and view_start <= loop_point <= view_end:
        lx = int((loop_point - view_start) / (view_end - view_start) * w)
        canvas.create_line(lx, 0, lx, h, fill="#c060ff", width=2, tags="cue")
        canvas.create_text(lx + 3, 2, text="L", fill="#c060ff",
                          font=("Consolas", 9, "bold"), anchor="nw", tags="cue")


EVENT_TYPES = ["None", "Goal", "Goal Home", "Goal Away", "Goal by Team"]


def _get_audio_devices():
    """Return list of available audio output device names."""
    return audio_engine.list_output_devices()


def _set_master_device(devicename):
    """Set the master/anthem output device used by the anthem and Default cards.

    Returns True if the device resolved to a real output (or default).
    """
    target = devicename or None
    _master_device[0] = target
    if target is None:
        return True
    return audio_engine.resolve_device(target) is not None


def build_sounds_tab(notebook, countries_db=None, stop_editor_preview=None):
    """Build the Sounds tab. Returns fire_event_fn."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Sounds")

    team_names = sorted(countries_db.get("teams", {}).keys()) if countries_db else []

    # Master/anthem output device from saved preference
    saved_device = get_config("audio", "output_device", fallback="")
    _set_master_device(saved_device or None)
    audio_engine.prime_decoder()  # why: init the decoder on the main thread before background loads

    # Toolbar
    toolbar = tk.Frame(tab)
    toolbar.pack(fill="x", padx=12, pady=(8, 4))
    refresh_btn = tk.Button(toolbar, text="Refresh", font=("Segoe UI", 9, "bold"),
                            bg="#0066cc", fg="white", padx=12, pady=2,
                            takefocus=False)
    refresh_btn.pack(side="left")

    # The master/anthem audio device selector now lives inside the National
    # Anthem box (built below) per request — see "Anthem Output" there.

    tk.Label(toolbar, text="Render:", font=("Segoe UI", 9)).pack(side="right", padx=(8, 4))
    render_var = tk.StringVar(value="Medium")
    render_menu = tk.OptionMenu(toolbar, render_var, "Fast", "Medium", "Detailed")
    render_menu.config(font=("Segoe UI", 9), width=8)
    render_menu.pack(side="right")

    # ── Anthem channel ────────────────────────────────────────────────
    anthem_frame = tk.LabelFrame(tab, text="National Anthem", font=("Segoe UI", 10, "bold"),
                                  fg="#cc6600", padx=4, pady=2)
    anthem_frame.pack(fill="x", padx=12, pady=(4, 4))

    # ── Anthem output device selector ──────────────────────────────────
    # This is the master pygame mixer device (e.g. the Dante Virtual Soundcard).
    # The anthem plays on it, as do all sound cards set to "Default".
    anthem_output_row = tk.Frame(anthem_frame)
    anthem_output_row.pack(fill="x", pady=(0, 2))
    tk.Label(anthem_output_row, text="Anthem Output:", font=("Segoe UI", 9),
             fg="#cc6600").pack(side="left", padx=(4, 4))

    devices = _get_audio_devices()
    device_choices = ["System Default"] + devices
    current = saved_device if saved_device in devices else "System Default"
    device_var = tk.StringVar(value=current)
    device_menu = tk.OptionMenu(anthem_output_row, device_var, *device_choices)
    device_menu.config(font=("Segoe UI", 9), width=30)
    device_menu.pack(side="left")

    device_status = tk.Label(anthem_output_row, text="", font=("Segoe UI", 8), fg="#888888")
    device_status.pack(side="left", padx=(4, 0))

    def _apply_device(*_args):
        chosen = device_var.get()
        dev = "" if chosen == "System Default" else chosen
        ok = _set_master_device(dev or None)
        set_config("audio", "output_device", dev)
        if ok:
            device_status.config(text=f"({chosen})", fg="#28a745")
        else:
            device_status.config(text="(not found — using default)", fg="#ff0000")

    device_var.trace_add("write", _apply_device)
    if saved_device:
        device_status.config(text=f"({current})", fg="#28a745")

    anthem_content = tk.Frame(anthem_frame)
    anthem_content.pack(fill="x")

    anthem_status = tk.Label(anthem_content, text="No anthem playing",
                              font=("Segoe UI", 10), fg="#888888", width=30, anchor="w")
    anthem_status.pack(side="left", padx=(4, 12))

    anthem_fade_btn = tk.Button(anthem_content, text="Fade Out", font=("Segoe UI", 9, "bold"),
                                 bg="#ff6600", fg="white", padx=12, state="disabled")
    anthem_fade_btn.pack(side="left", padx=(0, 16))

    anthem_time_label = tk.Label(anthem_content, text="", font=("Consolas", 10), fg="#888888",
                                  width=18, anchor="center")
    anthem_time_label.pack(side="left", padx=(0, 16))

    # Anthem gain slider
    anthem_gain_frame = tk.Frame(anthem_content)
    anthem_gain_frame.pack(side="left", padx=(0, 16))
    tk.Label(anthem_gain_frame, text="Vol", font=("Consolas", 7), fg="#888888").pack(side="left")
    anthem_gain_var = tk.DoubleVar(value=0.0)
    anthem_gain_slider = tk.Scale(anthem_gain_frame, from_=-60, to=15, resolution=0.5,
                                   variable=anthem_gain_var, orient="horizontal",
                                   font=("Consolas", 7), length=160,
                                   sliderlength=16, width=18, showvalue=True)
    anthem_gain_slider.pack(side="left", padx=4)
    anthem_gain_slider.bind("<Button-3>", lambda e: anthem_gain_var.set(0.0))

    # Anthem VU meters (L/R)
    anthem_meter_frame = tk.Frame(anthem_content)
    anthem_meter_frame.pack(side="left", padx=(8, 4))
    tk.Label(anthem_meter_frame, text="L", font=("Consolas", 6), fg="#888888").pack(side="left")
    anthem_vu_l = tk.Canvas(anthem_meter_frame, width=80, height=18,
                             bg="#1a1a1a", highlightthickness=1,
                             highlightbackground="#333333")
    anthem_vu_l.pack(side="left", padx=1)
    tk.Label(anthem_meter_frame, text="R", font=("Consolas", 6), fg="#888888").pack(side="left")
    anthem_vu_r = tk.Canvas(anthem_meter_frame, width=80, height=18,
                             bg="#1a1a1a", highlightthickness=1,
                             highlightbackground="#333333")
    anthem_vu_r.pack(side="left", padx=1)

    anthem_channel = [None]  # pygame Channel
    anthem_sound = [None]    # pygame Sound
    anthem_playing = [False]
    anthem_poll_id = [None]
    anthem_start_time = [0.0]
    anthem_fading = [False]
    anthem_fade_timer = [None]
    ANTHEM_FADE_DURATION_MS = 3000
    ANTHEM_FADE_STEP_MS = 50

    def _anthem_db_to_vol(db):
        if db <= -60:
            return 0.0
        return min(1.0, 10 ** (db / 20) * 0.18)

    def _anthem_apply_gain(*_args):
        if anthem_channel[0] and anthem_playing[0] and not anthem_fading[0]:
            anthem_channel[0].set_volume(_anthem_db_to_vol(anthem_gain_var.get()))

    anthem_gain_var.trace_add("write", _anthem_apply_gain)

    def _draw_h_meter(canvas_widget, rms_val):
        w = canvas_widget.winfo_width()
        h = canvas_widget.winfo_height()
        canvas_widget.delete("all")
        bar_w = min(int(rms_val * w * 2), w)
        if rms_val > 0.7:
            colour = "#ff0000"
        elif rms_val > 0.4:
            colour = "#ff6600"
        else:
            colour = "#00cc66"
        canvas_widget.create_rectangle(0, 1, bar_w, h - 1, fill=colour, outline="")

    def _anthem_poll():
        if not anthem_playing[0] or not anthem_channel[0]:
            return
        if not anthem_channel[0].get_busy():
            _anthem_stop()
            return
        if anthem_sound[0]:
            raw = anthem_sound[0].get_raw()
            length_s = anthem_sound[0].get_length()
            rms_l = rms_r = 0
            if length_s > 0 and len(raw) > 0:
                frame_size = 4
                total_frames = len(raw) // frame_size
                elapsed = (time.time() - anthem_start_time[0]) % length_s
                pos_frame = int((elapsed / length_s) * total_frames)
                chunk_frames = min(2048, total_frames)
                start_byte = max(0, (pos_frame - chunk_frames // 2)) * frame_size
                end_byte = min(len(raw), start_byte + chunk_frames * frame_size)
                chunk = raw[start_byte:end_byte]
                if len(chunk) >= 4:
                    n = len(chunk) // frame_size
                    sum_l = sum_r = 0
                    for fi in range(n):
                        off = fi * frame_size
                        sl, sr = struct.unpack_from("<hh", chunk, off)
                        sum_l += sl * sl
                        sum_r += sr * sr
                    rms_l = math.sqrt(sum_l / n) / 32768
                    rms_r = math.sqrt(sum_r / n) / 32768
            gain_mult = _anthem_db_to_vol(anthem_gain_var.get()) / 0.18
            _draw_h_meter(anthem_vu_l, rms_l * gain_mult)
            _draw_h_meter(anthem_vu_r, rms_r * gain_mult)
            # Update time display
            if length_s > 0:
                elapsed = time.time() - anthem_start_time[0]
                remaining = max(0, length_s - elapsed)
                e_m, e_s = int(elapsed) // 60, int(elapsed) % 60
                r_m, r_s = int(remaining) // 60, int(remaining) % 60
                t_m, t_s = int(length_s) // 60, int(length_s) % 60
                anthem_time_label.config(
                    text=f"{e_m}:{e_s:02d} / {t_m}:{t_s:02d}  -{r_m}:{r_s:02d}",
                    fg="#cc6600" if remaining > 5 else "#ff0000")
        anthem_poll_id[0] = tab.after(LEVEL_POLL_MS, _anthem_poll)

    def _anthem_fade_tick(step):
        if not anthem_playing[0] or not anthem_fading[0]:
            return
        total_steps = ANTHEM_FADE_DURATION_MS // ANTHEM_FADE_STEP_MS
        if step >= total_steps:
            _anthem_stop()
            return
        frac = 1.0 - (step / total_steps)
        base_vol = _anthem_db_to_vol(anthem_gain_var.get())
        if anthem_channel[0]:
            anthem_channel[0].set_volume(base_vol * frac)
        anthem_fade_timer[0] = tab.after(ANTHEM_FADE_STEP_MS,
                                          lambda: _anthem_fade_tick(step + 1))

    def _anthem_fade_out():
        if not anthem_playing[0]:
            return
        if anthem_fading[0]:
            _anthem_stop()
            return
        anthem_fading[0] = True
        anthem_fade_btn.config(text="Stop", bg="#cc0000")
        _anthem_fade_tick(0)

    ANTHEM_CROSSFADE_MS = 2000
    ANTHEM_CROSSFADE_STEP_MS = 50
    anthem_pending = [None]  # (country_name,) waiting for crossfade to finish
    anthem_crossfade_timer = [None]

    def _anthem_crossfade_tick(step):
        """Fade out current anthem, then start the pending one."""
        total_steps = ANTHEM_CROSSFADE_MS // ANTHEM_CROSSFADE_STEP_MS
        if step >= total_steps or not anthem_playing[0]:
            # Crossfade done — hard stop and play pending
            pending = anthem_pending[0]
            anthem_pending[0] = None
            _anthem_hard_stop()
            if pending:
                _anthem_start(pending)
            return
        frac = 1.0 - (step / total_steps)
        base_vol = _anthem_db_to_vol(anthem_gain_var.get())
        if anthem_channel[0]:
            anthem_channel[0].set_volume(base_vol * frac)
        anthem_crossfade_timer[0] = tab.after(ANTHEM_CROSSFADE_STEP_MS,
                                               lambda: _anthem_crossfade_tick(step + 1))

    def _anthem_start(country_name):
        """Immediately start playing an anthem (no fade check)."""
        teams = countries_db.get("teams", {}) if countries_db else {}
        team = teams.get(country_name, {})
        anthem_file = team.get("anthem", "")
        if not anthem_file:
            return
        filepath = os.path.join(ANTHEMS_DIR, anthem_file)
        if not os.path.exists(filepath):
            return
        try:
            snd = audio_engine.Sound(filepath)
            anthem_sound[0] = snd
            anthem_start_time[0] = time.time()
            anthem_channel[0] = snd.play(device=_master_device[0])  # anthem uses the master/anthem output
            if anthem_channel[0]:
                anthem_channel[0].set_volume(_anthem_db_to_vol(anthem_gain_var.get()))
            anthem_playing[0] = True
            anthem_fading[0] = False
            anthem_status.config(text=f"Playing: {country_name}", fg="#cc6600")
            anthem_fade_btn.config(state="normal", text="Fade Out", bg="#ff6600")
            _anthem_poll()
        except Exception:
            pass

    def _anthem_play(country_name):
        """Play the national anthem for the given country.
        If one is already playing, crossfade over 2 seconds first."""
        if stop_editor_preview:
            stop_editor_preview()
        if anthem_playing[0]:
            # Crossfade: fade out current, then start new
            anthem_pending[0] = country_name
            if anthem_crossfade_timer[0]:
                tab.after_cancel(anthem_crossfade_timer[0])
            _anthem_crossfade_tick(0)
        else:
            _anthem_start(country_name)

    def _anthem_hard_stop():
        """Immediately stop anthem playback with no fade."""
        if anthem_fade_timer[0]:
            tab.after_cancel(anthem_fade_timer[0])
            anthem_fade_timer[0] = None
        anthem_fading[0] = False
        if anthem_channel[0]:
            anthem_channel[0].stop()
        if anthem_sound[0]:
            anthem_sound[0].stop()
        anthem_playing[0] = False
        anthem_channel[0] = None
        anthem_sound[0] = None
        if anthem_poll_id[0]:
            tab.after_cancel(anthem_poll_id[0])
            anthem_poll_id[0] = None
        anthem_status.config(text="No anthem playing", fg="#888888")
        anthem_fade_btn.config(state="disabled", text="Fade Out", bg="#ff6600")
        anthem_time_label.config(text="", fg="#888888")
        anthem_vu_l.delete("all")
        anthem_vu_r.delete("all")

    def _anthem_stop():
        """Stop anthem, cancelling any crossfade in progress."""
        if anthem_crossfade_timer[0]:
            tab.after_cancel(anthem_crossfade_timer[0])
            anthem_crossfade_timer[0] = None
        anthem_pending[0] = None
        _anthem_hard_stop()

    anthem_fade_btn.config(command=_anthem_fade_out)

    # Scrollable container for sound cards
    cards_outer = tk.Frame(tab)
    cards_outer.pack(fill="both", expand=True)

    cards_canvas = tk.Canvas(cards_outer, highlightthickness=0)
    cards_scrollbar = tk.Scrollbar(cards_outer, orient="vertical", command=cards_canvas.yview)
    cards_frame = tk.Frame(cards_canvas)

    cards_frame.bind("<Configure>",
                     lambda e: cards_canvas.configure(scrollregion=cards_canvas.bbox("all")))
    cards_canvas_window = cards_canvas.create_window((0, 0), window=cards_frame, anchor="nw")

    def _on_cards_canvas_resize(event):
        cards_canvas.itemconfig(cards_canvas_window, width=event.width)

    cards_canvas.bind("<Configure>", _on_cards_canvas_resize)
    cards_canvas.configure(yscrollcommand=cards_scrollbar.set)
    cards_canvas.pack(side="left", fill="both", expand=True)
    cards_scrollbar.pack(side="right", fill="y")

    # Mouse wheel scrolling
    def _on_mousewheel(event):
        cards_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _bind_mousewheel(event):
        cards_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_mousewheel(event):
        cards_canvas.unbind_all("<MouseWheel>")

    cards_canvas.bind("<Enter>", _bind_mousewheel)
    cards_canvas.bind("<Leave>", _unbind_mousewheel)

    active_channels = []
    stop_fns = []
    recompute_fns = []
    sound_controls = []
    medits = [_load_medits()]
    active_card = [None]  # index of card that receives [ ] keys
    _keys_bound = [False]

    def _on_render_change(*_args):
        for fn in recompute_fns:
            try:
                fn()
            except Exception:
                pass

    render_var.trace_add("write", _on_render_change)

    # ── Game-window auto-loop monitor ───────────────────────────────────
    WINDOW_POLL_MS = 2000  # how often to check the live match window

    def _window_monitor():
        """Auto start/stop looped sounds based on the live game window
        (1st half / half time / 2nd half)."""
        try:
            window = scores.get_game_window()
        except Exception:
            window = None
        for ctrl in sound_controls:
            win_fn = ctrl.get("window_enabled")
            auto = ctrl.get("auto_window")  # single-element list, holds the armed window
            if win_fn is None or auto is None:
                continue
            try:
                enabled = window is not None and win_fn(window)
                if enabled:
                    # Arm once per window entry; respect a manual stop afterwards
                    if auto[0] != window:
                        auto[0] = window
                        if not ctrl["is_playing"]():
                            pl = ctrl.get("play_loop")
                            if pl:
                                pl()
                else:
                    # Window no longer allows this sound -> stop if we started it
                    if auto[0] is not None and ctrl["is_playing"]():
                        ctrl["stop"]()
                    auto[0] = None
            except Exception:
                pass
        tab.after(WINDOW_POLL_MS, _window_monitor)

    def _scan_and_populate():
        """Stop all playback, clear cards, re-scan folder, and rebuild."""
        # Stop all playing sounds
        for fn in stop_fns:
            try:
                fn()
            except Exception:
                pass
        stop_fns.clear()
        active_channels.clear()
        recompute_fns.clear()
        sound_controls.clear()

        # Clear all widgets in cards_frame
        for widget in cards_frame.winfo_children():
            widget.destroy()

        # Scan for sound files
        patterns = ["*.mp3", "*.wav", "*.ogg"]
        files = []
        for pat in patterns:
            files.extend(glob.glob(os.path.join(SOUND_DIR, pat)))
        files.sort()

        if not files:
            tk.Label(cards_frame, text="No sound files found in Sound Files/",
                     font=("Segoe UI", 12), fg="#888888").pack(pady=40)
            return

        # Calculate card height: divide available space equally, min 180px
        tab.update_idletasks()
        available_h = cards_canvas.winfo_height()
        if available_h < 50:
            available_h = 500
        card_h = max(220, available_h // len(files))

        for i, filepath in enumerate(files):
            _build_sound_card(filepath, i, card_h)

        if not _keys_bound[0]:
            bind_sound_keys(tab.winfo_toplevel(), sound_controls)

            def _on_bracket_left(event):
                idx = active_card[0]
                if idx is not None and idx < len(sound_controls):
                    sound_controls[idx]["set_cue_in"]()

            def _on_bracket_right(event):
                idx = active_card[0]
                if idx is not None and idx < len(sound_controls):
                    sound_controls[idx]["set_cue_out"]()

            def _on_loop_key(event):
                # Ignore when typing in a text field so "l" stays a normal key there
                try:
                    if event.widget.winfo_class() in (
                            "Entry", "TEntry", "Spinbox", "TSpinbox", "Text", "TCombobox"):
                        return
                except Exception:
                    pass
                idx = active_card[0]
                if idx is not None and idx < len(sound_controls):
                    fn = sound_controls[idx].get("set_loop_point")
                    if fn:
                        fn()

            root = tab.winfo_toplevel()
            root.bind("<bracketleft>", _on_bracket_left, add=True)
            root.bind("<bracketright>", _on_bracket_right, add=True)
            root.bind("<KeyPress-l>", _on_loop_key, add=True)
            root.bind("<KeyPress-L>", _on_loop_key, add=True)
            _keys_bound[0] = True
            # Start the game-window auto-loop monitor once
            _window_monitor()

    def _build_sound_card(filepath, card_index, card_height=200):
        filename = os.path.splitext(os.path.basename(filepath))[0]
        file_basename = os.path.basename(filepath)
        file_medits = medits[0].get(file_basename, {})
        fkey = F_KEYS[card_index] if card_index < len(F_KEYS) else ""
        label = f"[{fkey}]  {filename}" if fkey else filename

        card = tk.LabelFrame(cards_frame, text=label, font=("Segoe UI", 10, "bold"),
                             fg="#cccccc", padx=4, pady=2, height=card_height)
        card.pack(fill="x", padx=8, pady=2)
        card.pack_propagate(False)

        content = tk.Frame(card)
        content.pack(fill="both", expand=True)

        # Play button on the left (200px wide, full height)
        play_frame = tk.Frame(content, width=200)
        play_frame.pack(side="left", fill="y", padx=(0, 8))
        play_frame.pack_propagate(False)

        fkey_label = F_KEYS[card_index] if card_index < len(F_KEYS) else ""
        play_text = f"Play\n{fkey_label}" if fkey_label else "Play"
        play_btn = tk.Button(play_frame, text=play_text, font=("Segoe UI", 18, "bold"),
                             bg="#cc0000", fg="white")
        play_btn.pack(fill="both", expand=True)

        # Controls on the right (fixed width)
        ctrl = tk.Frame(content)
        ctrl.pack(side="right", fill="y", padx=8)

        half_btn = tk.Button(ctrl, text="\u00bdx Play", font=("Segoe UI", 9, "bold"),
                             bg="#6600cc", fg="white", width=6)
        half_btn.pack(pady=(0, 4))

        loop_var = tk.BooleanVar(value=False)
        tk.Checkbutton(ctrl, text="Loop", variable=loop_var,
                       font=("Segoe UI", 9)).pack()

        # Loop windows: game states this sound auto-loops in (1st half / HT / 2nd half)
        loop_win_vars = {
            "first_half":  tk.BooleanVar(value=file_medits.get("loop_first_half", False)),
            "half_time":   tk.BooleanVar(value=file_medits.get("loop_half_time", False)),
            "second_half": tk.BooleanVar(value=file_medits.get("loop_second_half", False)),
        }
        # Free Run: pressing Play loops continuously, independent of game windows
        free_run_var = tk.BooleanVar(value=file_medits.get("loop_free_run", False))
        win_frame = tk.LabelFrame(ctrl, text="Loop window", font=("Segoe UI", 7), fg="#aaaaaa")
        win_frame.pack(fill="x", pady=(2, 2))
        tk.Checkbutton(win_frame, text="Free Run", variable=free_run_var,
                       font=("Segoe UI", 7, "bold"), command=lambda: _save_cue()).pack(anchor="w")
        tk.Checkbutton(win_frame, text="1st Half", variable=loop_win_vars["first_half"],
                       font=("Segoe UI", 7), command=lambda: _save_cue()).pack(anchor="w")
        tk.Checkbutton(win_frame, text="Half Time", variable=loop_win_vars["half_time"],
                       font=("Segoe UI", 7), command=lambda: _save_cue()).pack(anchor="w")
        tk.Checkbutton(win_frame, text="2nd Half", variable=loop_win_vars["second_half"],
                       font=("Segoe UI", 7), command=lambda: _save_cue()).pack(anchor="w")

        # Set a loop point at the hover position (also bound to the "L" key)
        loop_btn = tk.Button(ctrl, text="Set Loop (L)", font=("Segoe UI", 8),
                             bg="#9b59b6", fg="white",
                             command=lambda: _loop_at_hover())
        loop_btn.pack(fill="x", pady=(2, 0))

        def _clear_medits():
            cue_in[0] = None
            cue_out[0] = None
            loop_point[0] = None
            gain_var.set(0.0)
            sound_trimmed[0] = None
            sound_trimmed_half[0] = None
            event_var.set("None")
            free_run_var.set(False)
            for _v in loop_win_vars.values():
                _v.set(False)
            if file_basename in medits[0]:
                del medits[0][file_basename]
                _save_medits(medits[0])
            zoom_view[0] = 0.0
            zoom_view[1] = 1.0
            if waveform_data[0]:
                _draw_waveform(waveform_canvas, waveform_data[0], None, None)

        clear_btn = tk.Button(ctrl, text="Clear Medits", font=("Segoe UI", 8),
                              bg="#666666", fg="white", command=_clear_medits)
        clear_btn.pack(pady=(4, 2))

        duration_label = tk.Label(ctrl, text="", font=("Consolas", 8), fg="#888888")
        duration_label.pack(pady=(4, 0))

        # Event trigger dropdowns
        event_frame = tk.Frame(ctrl)
        event_frame.pack(pady=(6, 0), fill="x")
        tk.Label(event_frame, text="Event:", font=("Segoe UI", 7), fg="#aaaaaa").pack(anchor="w")

        saved_event = file_medits.get("event", "None")
        saved_event_team = file_medits.get("event_team", "")

        event_var = tk.StringVar(value=saved_event)
        event_menu = ttk.Combobox(event_frame, textvariable=event_var,
                                   values=EVENT_TYPES, state="readonly",
                                   font=("Segoe UI", 7), width=12)
        event_menu.pack(fill="x")

        team_var = tk.StringVar(value=saved_event_team)
        team_menu_frame = tk.Frame(event_frame)
        team_menu_widget = [None]

        # Post-fader level meter (L/R)
        post_frame = tk.Frame(content)
        post_frame.pack(side="right", fill="y", padx=(0, 4))
        tk.Label(post_frame, text="Post", font=("Consolas", 6), fg="#888888").pack(side="top")
        post_meters = tk.Frame(post_frame)
        post_meters.pack(side="top", fill="y", expand=True)
        post_canvas_l = tk.Canvas(post_meters, width=LEVEL_W // 2,
                                   bg="#1a1a1a", highlightthickness=1,
                                   highlightbackground="#333333")
        post_canvas_l.pack(side="left", fill="y", expand=True)
        post_canvas_r = tk.Canvas(post_meters, width=LEVEL_W // 2,
                                   bg="#1a1a1a", highlightthickness=1,
                                   highlightbackground="#333333")
        post_canvas_r.pack(side="left", fill="y", expand=True)

        # Gain slider
        gain_frame = tk.Frame(content)
        gain_frame.pack(side="right", fill="y", padx=(0, 4))
        tk.Label(gain_frame, text="dB", font=("Consolas", 7), fg="#888888").pack(side="top")
        gain_var = tk.DoubleVar(value=file_medits.get("gain_db", 0.0))
        gain_slider = tk.Scale(gain_frame, from_=15, to=-60, resolution=0.5,
                               variable=gain_var, orient="vertical",
                               font=("Consolas", 7), length=60,
                               sliderlength=20, width=76,
                               showvalue=True)
        gain_slider.pack(side="top", fill="y", expand=True)
        gain_slider.bind("<Button-3>", lambda e: gain_var.set(0.0))

        fade_btn = tk.Button(gain_frame, text="Fade Out", font=("Segoe UI", 8),
                             bg="#ff6600", fg="white")
        fade_btn.pack(side="top", pady=(2, 0), fill="x")
        fade_btn.config(width=0)

        # Pre-fader level meter (L/R)
        pre_frame = tk.Frame(content)
        pre_frame.pack(side="right", fill="y", padx=(0, 4))
        tk.Label(pre_frame, text="Pre", font=("Consolas", 6), fg="#888888").pack(side="top")
        pre_meters = tk.Frame(pre_frame)
        pre_meters.pack(side="top", fill="y", expand=True)
        pre_canvas_l = tk.Canvas(pre_meters, width=LEVEL_W // 2,
                                  bg="#1a1a1a", highlightthickness=1,
                                  highlightbackground="#333333")
        pre_canvas_l.pack(side="left", fill="y", expand=True)
        pre_canvas_r = tk.Canvas(pre_meters, width=LEVEL_W // 2,
                                  bg="#1a1a1a", highlightthickness=1,
                                  highlightbackground="#333333")
        pre_canvas_r.pack(side="left", fill="y", expand=True)

        # Waveform canvas (fills remaining space)
        waveform_canvas = tk.Canvas(content, bg="#1a1a1a", highlightthickness=1,
                                     highlightbackground="#333333")
        waveform_canvas.pack(side="left", fill="both", expand=True, padx=(0, 8))

        sound_obj = [None]
        sound_half = [None]
        sound_trimmed = [None]
        sound_trimmed_half = [None]
        channel_obj = [None]
        playing = [False]
        half_speed = [False]
        looping_flag = [False]  # True while the current playback is looping
        overlap_channel = [None]  # the second, overlapping looping voice
        overlap_start = [0.0]     # its start time (for the 2nd position marker)
        overlap_timer = [None]    # scheduled start of the overlap
        waveform_data = [None]
        peak_cache = [None]  # cached high-res peaks (peaks_l, peaks_r)
        zoom_view = [0.0, 1.0]  # [view_start, view_end] as fraction 0.0-1.0
        poll_id = [None]
        play_start_time = [0.0]
        ending_blink = [False]
        ending_blink_timer = [None]
        ENDING_WARN_S = 5
        ENDING_BLINK_MS = 250

        # Cue points as fraction 0.0-1.0
        cue_in = [file_medits.get("cue_in")]
        cue_out = [file_medits.get("cue_out")]
        # Loop point as fraction 0.0-1.0 (where a loop returns to); None = none set
        loop_point = [file_medits.get("loop_point")]
        # Tracks whether the current playback was started by the auto window monitor
        auto_window_active = [None]

        def _rebuild_team_menu():
            for w in team_menu_frame.winfo_children():
                w.destroy()
            if event_var.get() == "Goal by Team" and team_names:
                tm = ttk.Combobox(team_menu_frame, textvariable=team_var,
                                  values=team_names, state="readonly",
                                  font=("Segoe UI", 7), width=12)
                tm.pack(fill="x")
                team_menu_widget[0] = tm
                team_menu_frame.pack(fill="x")
            else:
                team_menu_frame.pack_forget()
                team_var.set("")

        def _on_event_change(*_args):
            _rebuild_team_menu()
            _save_event()

        def _on_team_change(*_args):
            _save_event()

        def _save_event():
            entry = medits[0].get(file_basename, {})
            ev = event_var.get()
            if ev != "None":
                entry["event"] = ev
                if ev == "Goal by Team" and team_var.get():
                    entry["event_team"] = team_var.get()
                elif "event_team" in entry:
                    del entry["event_team"]
            else:
                entry.pop("event", None)
                entry.pop("event_team", None)
            if entry:
                medits[0][file_basename] = entry
            elif file_basename in medits[0]:
                del medits[0][file_basename]
            _save_medits(medits[0])

        event_var.trace_add("write", _on_event_change)
        team_var.trace_add("write", _on_team_change)
        _rebuild_team_menu()

        # Output device selector
        dev_frame = tk.Frame(ctrl)
        dev_frame.pack(pady=(4, 0), fill="x")
        tk.Label(dev_frame, text="Output:", font=("Segoe UI", 7), fg="#aaaaaa").pack(anchor="w")
        saved_device = file_medits.get("output_device", "")
        dev_choices = ["Default"] + _get_audio_devices()
        dev_current = saved_device if saved_device in dev_choices else "Default"
        dev_var = tk.StringVar(value=dev_current)
        dev_menu = ttk.Combobox(dev_frame, textvariable=dev_var,
                                 values=dev_choices, state="readonly",
                                 font=("Segoe UI", 7), width=20)
        dev_menu.pack(fill="x")

        def _on_dev_change(*_args):
            entry = medits[0].get(file_basename, {})
            chosen = dev_var.get()
            if chosen and chosen != "Default":
                entry["output_device"] = chosen
            else:
                entry.pop("output_device", None)
            if entry:
                medits[0][file_basename] = entry
            elif file_basename in medits[0]:
                del medits[0][file_basename]
            _save_medits(medits[0])

        dev_var.trace_add("write", _on_dev_change)

        def _get_target_device():
            """Return the device name this sound should play on, or None for default."""
            d = dev_var.get()
            return d if d and d != "Default" else None

        def _make_half_speed(raw):
            """Duplicate each stereo frame to produce half-speed audio."""
            frame_size = 4  # 16-bit stereo
            out = bytearray()
            for i in range(0, len(raw), frame_size):
                frame = raw[i:i + frame_size]
                out.extend(frame)
                out.extend(frame)
            return bytes(out)

        def _load_sound():
            def _worker():
                try:
                    s = audio_engine.Sound(filepath)
                    raw = s.get_raw()
                    half_raw = _make_half_speed(raw)
                    s_half = audio_engine.Sound(buffer=half_raw)
                    # Load or build peak cache
                    pf = _peak_path(filepath)
                    cached = _load_peak_cache(pf, filepath)
                    if cached is None:
                        cached = _extract_waveform(s, PEAK_CACHE_POINTS)
                        _save_peak_cache(pf, cached[0], cached[1])
                    try:
                        tab.after(0, lambda: _on_sound_loaded(s, s_half, cached))
                    except RuntimeError:
                        pass  # main loop already destroyed
                except Exception as e:
                    msg = str(e)
                    try:
                        tab.after(0, lambda: duration_label.config(text=f"Error: {msg}") if duration_label.winfo_exists() else None)
                    except RuntimeError:
                        pass  # main loop already destroyed
            threading.Thread(target=_worker, daemon=True).start()

        def _on_sound_loaded(s, s_half, cached_peaks):
            if not duration_label.winfo_exists():
                return
            sound_obj[0] = s
            sound_half[0] = s_half
            peak_cache[0] = cached_peaks
            length = s.get_length()
            duration_label.config(text=f"{int(length) // 60}:{int(length) % 60:02d}")
            if cue_in[0] is not None or cue_out[0] is not None:
                _build_trimmed()
            _recompute_waveform()

        def _recompute_waveform():
            """Resample cached peaks to current canvas width."""
            if peak_cache[0] is None:
                return
            try:
                w = max(100, waveform_canvas.winfo_width())
            except tk.TclError:
                return
            mode = render_var.get()
            if mode == "Fast":
                w = w // 4
            elif mode == "Detailed":
                w = w * 2
            w = max(50, w)
            cached_l, cached_r = peak_cache[0]
            resampled = _resample_peaks(cached_l, cached_r, w)
            _finish_waveform(resampled)

        def _redraw():
            """Redraw waveform with current zoom and cue state."""
            if waveform_data[0]:
                _draw_waveform(waveform_canvas, waveform_data[0], cue_in[0], cue_out[0],
                              view_start=zoom_view[0], view_end=zoom_view[1],
                              loop_point=loop_point[0])

        def _finish_waveform(stereo_peaks):
            waveform_data[0] = stereo_peaks
            _redraw()

        def _build_trimmed():
            """Build trimmed Sound objects from cue points."""
            if sound_obj[0] is None:
                return
            raw = sound_obj[0].get_raw()
            frame_size = 4
            total_frames = len(raw) // frame_size
            start_frame = int((cue_in[0] or 0) * total_frames)
            end_frame = int((cue_out[0] or 1.0) * total_frames)
            start_byte = start_frame * frame_size
            end_byte = end_frame * frame_size
            trimmed_raw = raw[start_byte:end_byte]
            if len(trimmed_raw) < frame_size:
                sound_trimmed[0] = None
                sound_trimmed_half[0] = None
                return
            sound_trimmed[0] = audio_engine.Sound(buffer=trimmed_raw)
            half_raw = _make_half_speed(trimmed_raw)
            sound_trimmed_half[0] = audio_engine.Sound(buffer=half_raw)

        def _save_cue():
            """Save current cue points and gain to medits.json."""
            entry = medits[0].get(file_basename, {})
            # Update cue fields
            if cue_in[0] is not None:
                entry["cue_in"] = round(cue_in[0], 6)
            else:
                entry.pop("cue_in", None)
            if cue_out[0] is not None:
                entry["cue_out"] = round(cue_out[0], 6)
            else:
                entry.pop("cue_out", None)
            g = gain_var.get()
            if g != 0.0:
                entry["gain_db"] = g
            else:
                entry.pop("gain_db", None)
            # Loop point
            if loop_point[0] is not None:
                entry["loop_point"] = round(loop_point[0], 6)
            else:
                entry.pop("loop_point", None)
            # Loop windows + free-run
            for key, var in (("loop_free_run", free_run_var),
                             ("loop_first_half", loop_win_vars["first_half"]),
                             ("loop_half_time", loop_win_vars["half_time"]),
                             ("loop_second_half", loop_win_vars["second_half"])):
                if var.get():
                    entry[key] = True
                else:
                    entry.pop(key, None)
            if entry:
                medits[0][file_basename] = entry
            elif file_basename in medits[0]:
                del medits[0][file_basename]
            _save_medits(medits[0])

        def _set_cue_in():
            """Set cue-in at current playhead position."""
            if not playing[0] or sound_obj[0] is None:
                return
            length_s = sound_obj[0].get_length()
            if half_speed[0]:
                length_s *= 2
            if length_s <= 0:
                return
            elapsed = (time.time() - play_start_time[0]) % length_s
            frac = elapsed / length_s
            if cue_out[0] is not None and frac >= cue_out[0]:
                return
            cue_in[0] = frac
            _save_cue()
            _build_trimmed()
            _redraw()

        def _set_cue_out():
            """Set cue-out at current playhead position."""
            if not playing[0] or sound_obj[0] is None:
                return
            length_s = sound_obj[0].get_length()
            if half_speed[0]:
                length_s *= 2
            if length_s <= 0:
                return
            elapsed = (time.time() - play_start_time[0]) % length_s
            frac = elapsed / length_s
            if cue_in[0] is not None and frac <= cue_in[0]:
                return
            cue_out[0] = frac
            _save_cue()
            _build_trimmed()
            _redraw()

        def _set_loop_point():
            """Set the loop point at the current playhead position."""
            if not playing[0] or sound_obj[0] is None:
                return
            length_s = sound_obj[0].get_length()
            if half_speed[0]:
                length_s *= 2
            if length_s <= 0:
                return
            frac = ((time.time() - play_start_time[0]) % length_s) / length_s
            loop_point[0] = frac
            _save_cue()
            _redraw()

        def _clear_loop_point():
            loop_point[0] = None
            _save_cue()
            _redraw()

        def _db_to_volume(db):
            """Convert dB gain (-60 to +15) to pygame volume (0.0 to 1.0)."""
            if db <= -60:
                return 0.0
            return min(1.0, 10 ** (db / 20) * 0.18)

        def _apply_gain(*_args):
            if channel_obj[0] and playing[0]:
                channel_obj[0].set_volume(_db_to_volume(gain_var.get()))

        gain_save_debounce = [None]

        def _on_gain_change(*_args):
            _apply_gain()
            if gain_save_debounce[0]:
                tab.after_cancel(gain_save_debounce[0])
            gain_save_debounce[0] = tab.after(500, _save_cue)

        gain_var.trace_add("write", _on_gain_change)

        def _get_play_sound(is_half):
            """Return the correct Sound object considering cue trim and half-speed."""
            has_cue = cue_in[0] is not None or cue_out[0] is not None
            if is_half:
                return sound_trimmed_half[0] if has_cue and sound_trimmed_half[0] else sound_half[0]
            return sound_trimmed[0] if has_cue and sound_trimmed[0] else sound_obj[0]

        def _loop_start_frames(is_half):
            """Frame in the about-to-play buffer that a loop should return to.

            The loop point is a fraction of the FULL sound; map it into whichever
            buffer is actually played (cue-trimmed and/or half-speed)."""
            if loop_point[0] is None or sound_obj[0] is None:
                return 0
            played = _get_play_sound(is_half)
            if played is None:
                return 0
            full_frames = len(sound_obj[0].get_raw()) // 4
            played_frames = len(played.get_raw()) // 4
            trimmed = sound_trimmed_half[0] if is_half else sound_trimmed[0]
            has_cue = (cue_in[0] is not None or cue_out[0] is not None) and trimmed is not None
            ci = (cue_in[0] or 0.0) if has_cue else 0.0
            frame = int((loop_point[0] - ci) * full_frames)
            if is_half:
                frame *= 2
            return max(0, min(frame, played_frames - 1))

        def _card_device():
            """Output device for this card: its own if set, else the master/anthem device."""
            return _get_target_device() or _master_device[0]

        def _clear_overlap():
            """Stop and forget the overlapping voice and any pending start."""
            if overlap_timer[0]:
                try:
                    tab.after_cancel(overlap_timer[0])
                except Exception:
                    pass
                overlap_timer[0] = None
            if overlap_channel[0]:
                try:
                    overlap_channel[0].stop()
                except Exception:
                    pass
                overlap_channel[0] = None

        def _start_overlap():
            """Start the second voice from the loop point, overlapping the first."""
            overlap_timer[0] = None
            if not playing[0] or loop_point[0] is None:
                return
            snd = _get_play_sound(half_speed[0])
            if snd is None:
                return
            try:
                ch = snd.play(loops=-1, device=_card_device(),
                              loop_start=_loop_start_frames(half_speed[0]))
            except Exception:
                return
            if ch:
                ch.set_volume(_db_to_volume(gain_var.get()))
                overlap_channel[0] = ch
                overlap_start[0] = time.time()
                active_channels.append(ch)

        def _maybe_schedule_overlap():
            """When looping with a loop point, schedule one overlapping voice so the
            sound plays over top of itself (bounded to a single extra voice)."""
            _clear_overlap()
            if not looping_flag[0] or loop_point[0] is None:
                return
            delay_ms = int(_loop_start_frames(half_speed[0]) / audio_engine.SAMPLE_RATE * 1000)
            overlap_timer[0] = tab.after(max(1, delay_ms), _start_overlap)

        def _play(force_loop=False):
            if sound_obj[0] is None:
                return
            if playing[0]:
                _stop()
                return
            active_card[0] = card_index
            sound_obj[0].stop()
            if sound_half[0]:
                sound_half[0].stop()
            if sound_trimmed[0]:
                sound_trimmed[0].stop()
            if sound_trimmed_half[0]:
                sound_trimmed_half[0].stop()
            half_speed[0] = False
            loops = -1 if (loop_var.get() or free_run_var.get() or force_loop) else 0
            looping_flag[0] = (loops == -1)
            play_start_time[0] = time.time()
            snd = _get_play_sound(False)
            channel_obj[0] = snd.play(loops=loops, device=_card_device(),
                                      loop_start=_loop_start_frames(False))
            if channel_obj[0]:
                channel_obj[0].set_volume(_db_to_volume(gain_var.get()))
                active_channels.append(channel_obj[0])
            playing[0] = True
            _maybe_schedule_overlap()
            stop_text = f"Stop\n{fkey_label}" if fkey_label else "Stop"
            play_btn.config(text=stop_text, bg="#28a745")
            half_btn.config(bg="#6600cc")
            fade_btn.config(text="Fade Out")
            _poll_level()

        def _play_half():
            if sound_half[0] is None:
                return
            if playing[0]:
                _stop()
                return
            active_card[0] = card_index
            sound_obj[0].stop()
            sound_half[0].stop()
            if sound_trimmed[0]:
                sound_trimmed[0].stop()
            if sound_trimmed_half[0]:
                sound_trimmed_half[0].stop()
            half_speed[0] = True
            loops = -1 if (loop_var.get() or free_run_var.get()) else 0
            looping_flag[0] = (loops == -1)
            play_start_time[0] = time.time()
            snd = _get_play_sound(True)
            channel_obj[0] = snd.play(loops=loops, device=_card_device(),
                                      loop_start=_loop_start_frames(True))
            if channel_obj[0]:
                channel_obj[0].set_volume(_db_to_volume(gain_var.get()))
                active_channels.append(channel_obj[0])
            playing[0] = True
            _maybe_schedule_overlap()
            half_btn.config(text="Stop", bg="#cc0000")
            play_btn.config(bg="#cc0000")
            fade_btn.config(text="Fade Out")
            _poll_level()

        def _ending_blink():
            if not ending_blink[0] or not playing[0]:
                return
            cur = play_btn.cget("bg")
            play_btn.config(bg="#331a00" if cur == "#ff9800" else "#ff9800")
            ending_blink_timer[0] = tab.after(ENDING_BLINK_MS, _ending_blink)

        def _stop_ending_blink():
            ending_blink[0] = False
            if ending_blink_timer[0]:
                tab.after_cancel(ending_blink_timer[0])
                ending_blink_timer[0] = None

        def _stop():
            if channel_obj[0]:
                channel_obj[0].stop()
            if sound_trimmed[0]:
                sound_trimmed[0].stop()
            if sound_trimmed_half[0]:
                sound_trimmed_half[0].stop()
            playing[0] = False
            half_speed[0] = False
            looping_flag[0] = False
            _clear_overlap()
            _stop_ending_blink()
            if fading[0]:
                fading[0] = False
                fade_direction[0] = None
                _stop_fade_blink()
            play_btn.config(text=play_text, bg="#cc0000")
            half_btn.config(text="\u00bdx Play", bg="#6600cc")
            fade_btn.config(text="Fade In")
            if poll_id[0]:
                tab.after_cancel(poll_id[0])
                poll_id[0] = None
            pre_canvas_l.delete("all")
            pre_canvas_r.delete("all")
            post_canvas_l.delete("all")
            post_canvas_r.delete("all")
            waveform_canvas.delete("playhead")
            _redraw()

        fading = [False]
        fade_direction = [None]  # "out" or "in"
        fade_timer = [None]
        fade_blink_timer = [None]
        pre_fade_gain = [0.0]
        FADE_OUT_DURATION_MS = 5000
        FADE_IN_DURATION_MS = 1000
        FADE_STEP_MS = 50
        FADE_BLINK_MS = 300

        def _fade_blink():
            if not fading[0]:
                fade_btn.config(bg="#ff6600")
                return
            cur = fade_btn.cget("bg")
            fade_btn.config(bg="#332200" if cur == "#ff6600" else "#ff6600")
            fade_blink_timer[0] = tab.after(FADE_BLINK_MS, _fade_blink)

        def _stop_fade_blink():
            if fade_blink_timer[0]:
                tab.after_cancel(fade_blink_timer[0])
                fade_blink_timer[0] = None
            fade_btn.config(bg="#ff6600")

        def _update_fade_label():
            if not playing[0]:
                fade_btn.config(text="Fade In")
            else:
                fade_btn.config(text="Fade Out")

        def _fade_btn_pressed():
            if fading[0]:
                # Reverse direction
                if fade_timer[0]:
                    tab.after_cancel(fade_timer[0])
                    fade_timer[0] = None
                if fade_direction[0] == "out":
                    # Switch to fade in (back to target gain)
                    fade_direction[0] = "in"
                    _fade_tick_in(0, gain_var.get())
                else:
                    # Switch to fade out
                    fade_direction[0] = "out"
                    _fade_tick_out(0, gain_var.get())
                return

            if not playing[0]:
                # Fade in: start playback at -infinity, fade up to prescribed gain
                if sound_obj[0] is None:
                    return
                pre_fade_gain[0] = gain_var.get()
                gain_var.set(-60)
                _play()
                fading[0] = True
                fade_direction[0] = "in"
                _fade_blink()
                _fade_tick_in(0, -60)
            else:
                # Fade out
                pre_fade_gain[0] = gain_var.get()
                fading[0] = True
                fade_direction[0] = "out"
                _fade_blink()
                _fade_tick_out(0, gain_var.get())

        def _fade_tick_out(elapsed, start_db):
            if not fading[0] or not playing[0] or fade_direction[0] != "out":
                return
            frac = min(1.0, elapsed / FADE_OUT_DURATION_MS)
            current_db = start_db * (1.0 - frac) + (-60) * frac
            gain_var.set(round(current_db, 1))
            if frac >= 1.0:
                fading[0] = False
                fade_direction[0] = None
                _stop_fade_blink()
                _stop()
                gain_var.set(pre_fade_gain[0])
                _update_fade_label()
                return
            fade_timer[0] = tab.after(FADE_STEP_MS,
                                      lambda: _fade_tick_out(elapsed + FADE_STEP_MS, start_db))

        def _fade_tick_in(elapsed, start_db):
            if not fading[0] or not playing[0] or fade_direction[0] != "in":
                return
            frac = min(1.0, elapsed / FADE_IN_DURATION_MS)
            current_db = start_db * (1.0 - frac) + pre_fade_gain[0] * frac
            gain_var.set(round(current_db, 1))
            if frac >= 1.0:
                fading[0] = False
                fade_direction[0] = None
                _stop_fade_blink()
                gain_var.set(pre_fade_gain[0])
                _update_fade_label()
                return
            fade_timer[0] = tab.after(FADE_STEP_MS,
                                      lambda: _fade_tick_in(elapsed + FADE_STEP_MS, start_db))

        fade_btn.config(command=_fade_btn_pressed, text="Fade In")

        def _draw_meter(canvas_widget, rms_val):
            """Draw a single meter bar on a canvas."""
            h = canvas_widget.winfo_height()
            w = canvas_widget.winfo_width()
            canvas_widget.delete("all")
            bar_h = min(int(rms_val * h * 2), h)
            y_top = h - bar_h
            if rms_val > 0.7:
                colour = "#ff0000"
            elif rms_val > 0.4:
                colour = "#ff6600"
            else:
                colour = "#00cc66"
            canvas_widget.create_rectangle(1, y_top, w - 1, h, fill=colour, outline="")

        def _poll_level():
            if not playing[0] or not channel_obj[0]:
                return
            if not channel_obj[0].get_busy():
                _stop()
                return

            has_cue = cue_in[0] is not None or cue_out[0] is not None
            playing_snd = _get_play_sound(half_speed[0])
            raw = playing_snd.get_raw()
            length_s = playing_snd.get_length()
            rms_l = 0
            rms_r = 0
            if length_s > 0 and len(raw) > 0:
                frame_size = 4  # 16-bit stereo
                total_frames = len(raw) // frame_size
                elapsed = (time.time() - play_start_time[0]) % length_s
                pos_frame = int((elapsed / length_s) * total_frames)
                chunk_frames = min(2048, total_frames)
                start_byte = max(0, (pos_frame - chunk_frames // 2)) * frame_size
                end_byte = min(len(raw), start_byte + chunk_frames * frame_size)
                chunk = raw[start_byte:end_byte]
                if len(chunk) >= 4:
                    num_frames_chunk = len(chunk) // frame_size
                    sum_l = 0
                    sum_r = 0
                    for fi in range(num_frames_chunk):
                        off = fi * frame_size
                        sl, sr = struct.unpack_from("<hh", chunk, off)
                        sum_l += sl * sl
                        sum_r += sr * sr
                    rms_l = math.sqrt(sum_l / num_frames_chunk) / 32768
                    rms_r = math.sqrt(sum_r / num_frames_chunk) / 32768

            # Pre-fader meters
            _draw_meter(pre_canvas_l, rms_l)
            _draw_meter(pre_canvas_r, rms_r)

            # Post-fader meters
            gain_mult = _db_to_volume(gain_var.get()) / 0.18
            _draw_meter(post_canvas_l, rms_l * gain_mult)
            _draw_meter(post_canvas_r, rms_r * gain_mult)

            waveform_canvas.delete("playhead")
            if length_s > 0:
                wf_w = waveform_canvas.winfo_width()
                wf_h = waveform_canvas.winfo_height()
                elapsed = (time.time() - play_start_time[0]) % length_s
                frac = elapsed / length_s
                # Map trimmed fraction into full waveform position
                if has_cue:
                    ci = cue_in[0] or 0.0
                    co = cue_out[0] or 1.0
                    frac = ci + frac * (co - ci)
                # Map global fraction through zoom view to screen position
                vs, ve = zoom_view
                if vs < frac < ve and ve > vs:
                    x = int((frac - vs) / (ve - vs) * wf_w)
                    tri = 6
                    # Red line
                    waveform_canvas.create_line(x, tri, x, wf_h - tri,
                                                fill="#ff0000", width=2, tags="playhead")
                    # Top triangle pointing down
                    waveform_canvas.create_polygon(
                        x - tri, 0, x + tri, 0, x, tri,
                        fill="#ff0000", outline="", tags="playhead")
                    # Bottom triangle pointing up
                    waveform_canvas.create_polygon(
                        x - tri, wf_h, x + tri, wf_h, x, wf_h - tri,
                        fill="#ff0000", outline="", tags="playhead")

                # Second position marker: the overlapping voice playing the loop
                # region over top of the first. Tracks its own position.
                if (overlap_channel[0] is not None and loop_point[0] is not None
                        and overlap_channel[0].get_busy() and sound_obj[0] is not None):
                    region_start = loop_point[0]
                    region_end = cue_out[0] or 1.0
                    span = region_end - region_start
                    full_len = sound_obj[0].get_length() * (2 if half_speed[0] else 1)
                    region_dur = span * full_len
                    if span > 0 and region_dur > 0:
                        ov_elapsed = time.time() - overlap_start[0]
                        ov_frac = region_start + (ov_elapsed % region_dur) / region_dur * span
                        if vs < ov_frac < ve:
                            ox = int((ov_frac - vs) / (ve - vs) * wf_w)
                            tri = 6
                            waveform_canvas.create_line(ox, tri, ox, wf_h - tri,
                                                        fill="#ff7777", width=2, tags="playhead")
                            waveform_canvas.create_polygon(
                                ox - tri, 0, ox + tri, 0, ox, tri,
                                fill="#ff7777", outline="", tags="playhead")
                            waveform_canvas.create_polygon(
                                ox - tri, wf_h, ox + tri, wf_h, ox, wf_h - tri,
                                fill="#ff7777", outline="", tags="playhead")

            # Blink play button orange when ≤5 seconds remaining (non-looping only)
            if not loop_var.get() and length_s > 0:
                elapsed_s = (time.time() - play_start_time[0])
                remaining_s = length_s - (elapsed_s % length_s)
                if remaining_s <= ENDING_WARN_S and not ending_blink[0]:
                    ending_blink[0] = True
                    _ending_blink()
            elif ending_blink[0]:
                _stop_ending_blink()
                stop_text = f"Stop\n{fkey_label}" if fkey_label else "Stop"
                play_btn.config(bg="#28a745", text=stop_text)

            poll_id[0] = tab.after(LEVEL_POLL_MS, _poll_level)

        resize_debounce = [None]

        def _on_waveform_resize(event=None):
            if resize_debounce[0]:
                tab.after_cancel(resize_debounce[0])
            resize_debounce[0] = tab.after(300, _recompute_waveform)

        waveform_canvas.bind("<Configure>", _on_waveform_resize)

        # Waveform hover cursor for cue placement
        hover_line = [None]

        def _on_wf_enter(event):
            active_card[0] = card_index

        def _on_wf_motion(event):
            wf_w = waveform_canvas.winfo_width()
            wf_h = waveform_canvas.winfo_height()
            if hover_line[0]:
                waveform_canvas.delete(hover_line[0])
            x = event.x
            hover_line[0] = waveform_canvas.create_line(
                x, 0, x, wf_h, fill="#ff9800", width=2, dash=(4, 2), tags="hover")

        def _on_wf_leave(event):
            if hover_line[0]:
                waveform_canvas.delete(hover_line[0])
                hover_line[0] = None

        def _on_wf_scroll(event):
            """Zoom in/out on the waveform centered on cursor position."""
            if waveform_data[0] is None:
                return
            wf_w = waveform_canvas.winfo_width()
            if wf_w <= 0:
                return
            # Cursor position as fraction within current view
            cursor_frac = max(0.0, min(1.0, event.x / wf_w))
            # Map to global fraction
            vs, ve = zoom_view
            span = ve - vs
            cursor_global = vs + cursor_frac * span

            # Zoom factor
            if event.delta > 0:
                new_span = span / 1.3  # zoom in
            else:
                new_span = span * 1.3  # zoom out
            new_span = max(0.01, min(1.0, new_span))

            # Centre new view on cursor position
            new_start = cursor_global - cursor_frac * new_span
            new_end = new_start + new_span
            # Clamp to 0.0-1.0
            if new_start < 0:
                new_start = 0.0
                new_end = new_span
            if new_end > 1.0:
                new_end = 1.0
                new_start = max(0.0, 1.0 - new_span)
            zoom_view[0] = new_start
            zoom_view[1] = new_end
            _redraw()
            return "break"

        waveform_canvas.bind("<Enter>", _on_wf_enter)
        waveform_canvas.bind("<Motion>", _on_wf_motion)
        waveform_canvas.bind("<Leave>", _on_wf_leave)
        waveform_canvas.bind("<MouseWheel>", _on_wf_scroll)

        def _cue_at_hover(is_in):
            """Set cue point at the hover cursor position."""
            if hover_line[0] is None:
                return
            wf_w = waveform_canvas.winfo_width()
            coords = waveform_canvas.coords(hover_line[0])
            if not coords:
                return
            x = coords[0]
            # Map screen position through zoom view to global fraction
            screen_frac = max(0.0, min(1.0, x / wf_w))
            frac = zoom_view[0] + screen_frac * (zoom_view[1] - zoom_view[0])
            if is_in:
                if cue_out[0] is not None and frac >= cue_out[0]:
                    return
                cue_in[0] = frac
            else:
                if cue_in[0] is not None and frac <= cue_in[0]:
                    return
                cue_out[0] = frac
            _save_cue()
            _build_trimmed()
            _redraw()

        def _loop_at_hover():
            """Set the loop point at the hover cursor position (the L key)."""
            if hover_line[0] is None:
                # No hover -> fall back to the live playhead if playing
                _set_loop_point()
                return
            wf_w = waveform_canvas.winfo_width()
            coords = waveform_canvas.coords(hover_line[0])
            if not coords:
                return
            screen_frac = max(0.0, min(1.0, coords[0] / wf_w))
            loop_point[0] = zoom_view[0] + screen_frac * (zoom_view[1] - zoom_view[0])
            _save_cue()
            _redraw()

        def _window_enabled(window):
            var = loop_win_vars.get(window)
            return bool(var.get()) if var else False

        stop_fns.append(_stop)
        recompute_fns.append(_recompute_waveform)
        sound_controls.append({
            "play": _play,
            "stop": _stop,
            "is_playing": lambda p=playing: p[0],
            "set_cue_in": lambda: _cue_at_hover(True),
            "set_cue_out": lambda: _cue_at_hover(False),
            "set_loop_point": _loop_at_hover,
            "play_loop": lambda: _play(force_loop=True),
            "window_enabled": _window_enabled,
            "auto_window": auto_window_active,
            "event_var": event_var,
            "team_var": team_var,
            "filename": filename,
        })
        play_btn.config(command=_play)
        half_btn.config(command=_play_half)
        _load_sound()

    def fire_event(event_type, team_name=""):
        """Trigger sounds bound to a matching event.

        Args:
            event_type: "Goal", "Goal Home", "Goal Away", or "Goal by Team"
            team_name: country name (only checked for "Goal by Team")
        """
        goal_types = ("Goal", "Goal Home", "Goal Away", "Goal by Team")
        for ctrl in sound_controls:
            ev = ctrl["event_var"].get()
            if ev == "None":
                continue
            if ev == "Goal" and event_type in goal_types:
                # "Goal" fires on ANY goal event
                if not ctrl["is_playing"]():
                    ctrl["play"]()
            elif ev == "Goal Home" and event_type == "Goal Home":
                if not ctrl["is_playing"]():
                    ctrl["play"]()
            elif ev == "Goal Away" and event_type == "Goal Away":
                if not ctrl["is_playing"]():
                    ctrl["play"]()
            elif ev == "Goal by Team" and event_type in goal_types:
                if ctrl["team_var"].get() == team_name:
                    if not ctrl["is_playing"]():
                        ctrl["play"]()
        # Play national anthem for the team
        if team_name and event_type in goal_types:
            _anthem_play(team_name)

    def play_by_name(name):
        """Play a loaded sound card by filename (without extension), e.g. 'PreGame'."""
        name_lower = name.lower()
        for ctrl in sound_controls:
            if ctrl.get("filename", "").lower() == name_lower:
                if not ctrl["is_playing"]():
                    ctrl["play"]()
                return True
        return False

    def stop_by_name(name):
        """Stop a loaded sound card by filename (without extension)."""
        name_lower = name.lower()
        for ctrl in sound_controls:
            if ctrl.get("filename", "").lower() == name_lower:
                ctrl["stop"]()
                return True
        return False

    def list_sounds():
        """Return [{'name', 'playing'}] for every loaded sound (for the web /sounds page)."""
        return [{"name": ctrl.get("filename", ""), "playing": bool(ctrl["is_playing"]())}
                for ctrl in sound_controls]

    refresh_btn.config(command=_scan_and_populate)
    _scan_and_populate()

    return fire_event, play_by_name, stop_by_name, list_sounds
