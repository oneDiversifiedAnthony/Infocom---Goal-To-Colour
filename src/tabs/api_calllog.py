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

"""Call Log graph sub-tab -- plots tokens remaining over time from callcounter_*.log files.

Only renders when the tab is visible. Polls for file changes every 60 seconds."""

import datetime
import glob
import os
import threading
import tkinter as tk


RATE_LIMIT_TOTAL = 2500

# Colours for each call type
CALL_TYPE_COLOURS = {
    "scores": "#0099ff",   # blue for lightweight score polls
    "events": "#cc44ff",   # purple for full event fetches
    "unknown": "#28a745",  # green fallback
}


def build_calllog_subtab(result_notebook, call_log_dir, tab):
    """Build the Call Log graph sub-tab. Returns frame."""
    frame = tk.Frame(result_notebook, bg="black")
    result_notebook.add(frame, text="Call Log")

    # Refresh button bar (hidden until dirty)
    btn_bar = tk.Frame(frame, bg="black")
    refresh_btn = tk.Button(btn_bar, text="Refresh", font=("Segoe UI", 9, "bold"),
                            bg="#0066cc", fg="white", padx=12, pady=2)
    refresh_btn.pack(side="right", padx=8, pady=4)

    canvas = tk.Canvas(frame, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    last_mtime = [0]
    dirty = [True]
    cached_entries = [None]
    configure_debounce_id = [None]
    drawing = [False]

    def _parse():
        """Read callcounter_*.log files and return today's entries and markers.

        Returns (entries, markers) where:
            entries: list of (label, tokens, call_type) tuples
            markers: list of (index_in_entries, time, marker_type, description)
                marker_type: "state", "goal", or "event"
        """
        entries = []
        markers = []
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        pattern = os.path.join(call_log_dir, "callcounter_*.log")
        files = sorted(glob.glob(pattern))
        for filepath in files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        date_part = line.split(" ")[0] if " " in line else ""
                        if date_part != today_str:
                            continue
                        time_part = line.split(" ")[1] if " " in line else ""
                        # Check for marker lines
                        if ", STATE_CHANGE: " in line:
                            desc = line.split(", STATE_CHANGE: ", 1)[1]
                            markers.append((len(entries), time_part, "state", desc))
                            continue
                        if ", GOAL: " in line:
                            desc = line.split(", GOAL: ", 1)[1]
                            markers.append((len(entries), time_part, "goal", desc))
                            continue
                        if ", EVENT: " in line:
                            desc = line.split(", EVENT: ", 1)[1]
                            markers.append((len(entries), time_part, "event", desc))
                            continue
                        parts = line.split(", tokens_remaining: ")
                        if len(parts) == 2:
                            try:
                                time_part = parts[0].split(" ")[1] if " " in parts[0] else parts[0]
                                remainder = parts[1]
                                call_type = "unknown"
                                if ", call: " in remainder:
                                    tok_str, rest = remainder.split(", call: ", 1)
                                    tokens = int(tok_str)
                                    call_type = rest.split(",")[0].strip()
                                else:
                                    tokens = int(remainder)
                                entries.append((time_part, tokens, call_type))
                            except (ValueError, IndexError):
                                pass
            except (FileNotFoundError, PermissionError):
                pass
        return entries, markers

    def _parse_async(callback):
        """Parse log files in a background thread, then call callback on the main thread."""
        def _worker():
            result = _parse()
            tab.after(0, lambda: callback(result))
        threading.Thread(target=_worker, daemon=True).start()

    def _draw_with_data(parse_result):
        """Draw the graph using pre-parsed entries. Runs on the main thread."""
        entries, markers = parse_result
        drawing[0] = True
        canvas.delete("all")

        if not entries:
            canvas.create_text(
                canvas.winfo_width() // 2, canvas.winfo_height() // 2,
                text="No call log data yet", fill="#888888", font=("Segoe UI", 12))
            drawing[0] = False
            return

        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 50 or h < 50:
            drawing[0] = False
            return

        margin_l, margin_r, margin_t, margin_b = 60, 20, 20, 40
        plot_w = w - margin_l - margin_r
        plot_h = h - margin_t - margin_b

        n = len(entries)
        tokens = [t for _, t, _ in entries]
        call_types = [ct for _, _, ct in entries]
        max_t = max(tokens)
        min_t = min(tokens)
        t_range = max_t - min_t if max_t != min_t else 1

        coords = []
        colours = []
        x_labels = []
        step = max(1, n // 8)
        for i in range(n):
            px = margin_l + (int(plot_w * i / (n - 1)) if n > 1 else plot_w // 2)
            py = margin_t + int(plot_h * (max_t - tokens[i]) / t_range)
            coords.append((px, py))
            colours.append(CALL_TYPE_COLOURS.get(call_types[i], CALL_TYPE_COLOURS["unknown"]))
            if i % step == 0:
                x_labels.append((px, entries[i][0]))

        # Grid lines and Y-axis labels
        for i in range(5):
            y = margin_t + int(plot_h * i / 4)
            val = max_t - int(t_range * i / 4)
            canvas.create_line(margin_l, y, w - margin_r, y, fill="#333333")
            canvas.create_text(margin_l - 5, y, text=str(val),
                               fill="#888888", font=("Consolas", 8), anchor="e")

        if n == 1:
            x, y = coords[0]
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3,
                               fill=colours[0], outline=colours[0])
        else:
            bottom_y = margin_t + plot_h
            for i in range(n - 1):
                x1, y1 = coords[i]
                x2, y2 = coords[i + 1]
                col = colours[i]

                canvas.create_polygon(
                    x1, bottom_y, x1, y1, x2, y2, x2, bottom_y,
                    fill=col, outline="", stipple="gray25")

                canvas.create_line(x1, y1, x2, y2, fill=col, width=2)

            for i, (x, y) in enumerate(coords):
                canvas.create_oval(x - 2, y - 2, x + 2, y + 2,
                                   fill=colours[i], outline=colours[i])

            for x, label in x_labels:
                canvas.create_text(x, h - margin_b + 12, text=label,
                                   fill="#888888", font=("Consolas", 7), anchor="n")

        canvas.create_text(margin_l // 2, margin_t - 8, text="Tokens",
                           fill="#aaaaaa", font=("Segoe UI", 8), anchor="s")

        # ── Markers: state changes, goals, events ──
        STATE_MARKER_COLOURS = {
            "NS": "#888888", "1H": "#28a745", "HT": "#ffcc00", "2H": "#28a745",
            "FT": "#ff0000", "ET": "#cc44ff", "AET": "#ff0000", "FTP": "#ff0000",
            "PEN": "#cc44ff", "BRK": "#ffcc00",
        }
        MARKER_TYPE_COLOURS = {
            "goal":  "#ffcc00",
            "event": "#ff6600",
            "state": "#ffffff",
        }
        EVENT_LABEL_COLOURS = {
            "GOAL": "#ffcc00",
            "YELLOW_CARD": "#ffcc00",
            "RED_CARD": "#ff0000",
            "SUBSTITUTION": "#0088ff",
        }

        # Stagger labels vertically to avoid overlap
        label_y_offset = [0]

        for idx, time_str, marker_type, desc in markers:
            # Map index to x position on the graph
            if n <= 1:
                px = margin_l + plot_w // 2
            else:
                ci = min(idx, n - 1)
                px = margin_l + int(plot_w * ci / (n - 1))

            if marker_type == "state":
                new_state = desc.split("-> ")[-1].strip().rstrip("]")
                marker_col = STATE_MARKER_COLOURS.get(new_state, "#ffffff")
                top_label = new_state
            elif marker_type == "goal":
                marker_col = "#ffcc00"
                # Show "GOAL team" as label
                top_label = "GOAL"
            else:
                # event — pick colour by event type
                event_type = desc.split(" ")[0] if desc else "EVENT"
                marker_col = EVENT_LABEL_COLOURS.get(event_type, "#ff6600")
                top_label = event_type

            # Vertical dashed line
            dash_gap = 4 if marker_type == "state" else 6
            line_width = 2 if marker_type == "goal" else 1
            for dy in range(margin_t, margin_t + plot_h, dash_gap * 2):
                canvas.create_line(px, dy, px, min(dy + dash_gap, margin_t + plot_h),
                                   fill=marker_col, width=line_width)

            # Label at top (staggered)
            ly_pos = margin_t - 2 - (label_y_offset[0] % 3) * 10
            label_y_offset[0] += 1
            canvas.create_text(px + 2, ly_pos, text=top_label,
                               fill=marker_col, font=("Consolas", 7, "bold"), anchor="sw")

            # Goal markers get a circle highlight
            if marker_type == "goal":
                cy = margin_t + plot_h // 2
                canvas.create_oval(px - 6, cy - 6, px + 6, cy + 6,
                                   fill="", outline=marker_col, width=2)
                canvas.create_text(px, cy, text="\u26BD", font=("Segoe UI", 8))

        # Legend
        lx = w - margin_r - 10
        ly = margin_t + 6
        for label, col in [("scores", CALL_TYPE_COLOURS["scores"]),
                           ("events", CALL_TYPE_COLOURS["events"]),
                           ("state", "#ffffff"),
                           ("goal", "#ffcc00"),
                           ("card/sub", "#ff6600")]:
            canvas.create_oval(lx - 6, ly - 4, lx, ly + 2, fill=col, outline=col)
            canvas.create_text(lx - 10, ly - 1, text=label, fill=col,
                               font=("Segoe UI", 8), anchor="e")
            ly += 16

        drawing[0] = False

    def _draw():
        """Trigger an async parse + draw. Skips if already drawing."""
        if drawing[0]:
            return
        _parse_async(_draw_with_data)

    def _is_visible():
        try:
            return result_notebook.index(result_notebook.select()) == result_notebook.index(frame)
        except Exception:
            return False

    def _on_configure(event=None):
        if not _is_visible():
            return
        if configure_debounce_id[0]:
            tab.after_cancel(configure_debounce_id[0])
        configure_debounce_id[0] = tab.after(300, _draw)

    canvas.bind("<Configure>", _on_configure)

    def _refresh_clicked():
        dirty[0] = False
        btn_bar.pack_forget()
        _draw()

    refresh_btn.config(command=_refresh_clicked)

    def _show_refresh_bar():
        btn_bar.pack(fill="x", before=canvas)

    def _on_tab_changed(event=None):
        if _is_visible() and dirty[0]:
            _show_refresh_bar()

    result_notebook.bind("<<NotebookTabChanged>>", _on_tab_changed)

    def _get_latest_mtime():
        """Get the most recent modification time across all callcounter log files."""
        pattern = os.path.join(call_log_dir, "callcounter_*.log")
        files = glob.glob(pattern)
        if not files:
            return 0
        return max(os.path.getmtime(f) for f in files)

    def _poll():
        mtime = _get_latest_mtime()
        if mtime != last_mtime[0]:
            last_mtime[0] = mtime
            dirty[0] = True
            if _is_visible():
                _show_refresh_bar()
        tab.after(60000, _poll)

    tab.after(60000, _poll)

    return frame
