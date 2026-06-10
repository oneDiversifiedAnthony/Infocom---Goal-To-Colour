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

"""Response Table sub-tab -- flat table of the top-level data array."""

import json
import tkinter as tk
from tkinter import ttk


def build_table_subtab(result_notebook):
    """Build the Response Table sub-tab. Returns (frame, update_fn)."""
    frame = tk.Frame(result_notebook)
    result_notebook.add(frame, text="Response Table")

    table_tree = ttk.Treeview(frame, show="headings")
    xscroll = tk.Scrollbar(frame, orient="horizontal", command=table_tree.xview)
    yscroll = tk.Scrollbar(frame, command=table_tree.yview)
    table_tree.config(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
    yscroll.pack(side="right", fill="y")
    xscroll.pack(side="bottom", fill="x")
    table_tree.pack(fill="both", expand=True)

    def update(parsed):
        for item in table_tree.get_children():
            table_tree.delete(item)
        for col in table_tree["columns"]:
            table_tree.heading(col, text="")
        table_tree["columns"] = ()

        if parsed is None:
            return

        rows = []
        if isinstance(parsed, dict) and "data" in parsed and isinstance(parsed["data"], list):
            rows = parsed["data"]
        elif isinstance(parsed, list):
            rows = parsed

        if not rows or not isinstance(rows[0], dict):
            return

        columns = list(rows[0].keys())
        table_tree["columns"] = columns
        for col in columns:
            table_tree.heading(col, text=col, anchor="w")
            table_tree.column(col, width=100, anchor="w")

        for row in rows:
            vals = []
            for col in columns:
                v = row.get(col, "")
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                vals.append(str(v))
            table_tree.insert("", "end", values=vals)

    return frame, update
