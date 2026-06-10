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

"""Response Raw sub-tab -- displays pretty-printed JSON or raw text."""

import json
import tkinter as tk


def build_raw_subtab(result_notebook):
    """Build the Response Raw sub-tab. Returns (frame, update_fn, clear_fn)."""
    frame = tk.Frame(result_notebook)
    result_notebook.add(frame, text="Response Raw")

    text_widget = tk.Text(frame, wrap="word", font=("Consolas", 9),
                          state="disabled", cursor="arrow")
    scroll = tk.Scrollbar(frame, command=text_widget.yview)
    text_widget.config(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    text_widget.pack(fill="both", expand=True)

    def update(parsed, raw_text):
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        if parsed is not None:
            text_widget.insert("1.0", json.dumps(parsed, indent=2, ensure_ascii=False))
        else:
            text_widget.insert("1.0", raw_text)
        text_widget.config(state="disabled")

    def show_error(msg):
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", f"ERROR:\n{msg}")
        text_widget.config(state="disabled")

    def clear():
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.config(state="disabled")

    return frame, update, show_error, clear
