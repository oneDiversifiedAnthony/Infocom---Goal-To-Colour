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

"""Logged Changes sub-tab -- tracks changes to data/add_ons/widgets/bundles/message
fields and writes timestamped JSON files to the Call Log directory."""

import datetime
import hashlib
import json
import os
import tkinter as tk


TRACKED_FIELDS = ("data", "add_ons", "widgets", "bundles", "message")
CHANGES_LOG_FILE = "changes.log"


def build_changes_subtab(result_notebook, call_log_dir):
    """Build the Logged Changes sub-tab. Returns (frame, check_fn)."""
    frame = tk.Frame(result_notebook)
    result_notebook.add(frame, text="Logged Changes")

    text_widget = tk.Text(frame, wrap="none", font=("Consolas", 9),
                          state="disabled", cursor="arrow")
    xscroll = tk.Scrollbar(frame, orient="horizontal", command=text_widget.xview)
    yscroll = tk.Scrollbar(frame, command=text_widget.yview)
    text_widget.config(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
    yscroll.pack(side="right", fill="y")
    xscroll.pack(side="bottom", fill="x")
    text_widget.pack(fill="both", expand=True)

    changes_file = os.path.join(call_log_dir, CHANGES_LOG_FILE)
    # Store only a hash of the previous snapshot and per-field summaries for comparison
    prev_hash = [None]
    prev_summaries = [{}]

    def _extract_tracked(data):
        if not isinstance(data, dict):
            return {}
        return {k: data.get(k) for k in TRACKED_FIELDS if k in data}

    def _summarise(val):
        if val is None:
            return "(absent)"
        if isinstance(val, list):
            return f"[{len(val)} items]"
        if isinstance(val, str):
            return f'"{val[:80]}"' if len(val) > 80 else f'"{val}"'
        return str(val)[:100]

    def _hash_tracked(tracked):
        """Return a hash of the tracked fields for lightweight comparison."""
        raw = json.dumps(tracked, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _refresh_display():
        """Read the changes log file and display its contents."""
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        try:
            with open(changes_file, "r", encoding="utf-8") as f:
                content = f.read()
            if content.strip():
                text_widget.insert("1.0", content)
            else:
                text_widget.insert("1.0", "(no changes detected yet)")
        except FileNotFoundError:
            text_widget.insert("1.0", "(no changes detected yet)")
        text_widget.see("end")
        text_widget.config(state="disabled")

    def check_and_log(data):
        """Compare tracked fields against previous call; log and save file on change."""
        current_tracked = _extract_tracked(data)
        current_hash = _hash_tracked(current_tracked)
        current_summaries = {k: _summarise(v) for k, v in current_tracked.items()}

        if prev_hash[0] is None:
            prev_hash[0] = current_hash
            prev_summaries[0] = current_summaries
            return

        if current_hash == prev_hash[0]:
            return

        # Something changed
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ts_file = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        changes = []

        for field in TRACKED_FIELDS:
            prev_s = prev_summaries[0].get(field, "(absent)")
            curr_s = current_summaries.get(field, "(absent)")
            if prev_s != curr_s:
                changes.append(f"  {field}: {prev_s} -> {curr_s}")

        if changes:
            entry = f"[{timestamp}] CHANGE DETECTED:\n" + "\n".join(changes) + "\n\n"

            # Append to changes log file
            with open(changes_file, "a", encoding="utf-8") as f:
                f.write(entry)

            # Write timestamped JSON snapshot to Call Log dir
            log_file = os.path.join(call_log_dir, f"{ts_file}.json")
            log_content = {
                "timestamp": timestamp,
                "tracked_fields": current_tracked,
            }
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(log_content, f, indent=2, ensure_ascii=False)
            # Clear the full response from memory immediately
            del log_content

        # Store only lightweight comparison data
        prev_hash[0] = current_hash
        prev_summaries[0] = current_summaries
        _refresh_display()

    return frame, check_and_log
