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

"""Response Tree sub-tab -- expandable key/value tree view of JSON data."""

import tkinter as tk
from tkinter import ttk


def _populate_tree(parent, data, tree_widget):
    """Recursively insert JSON data into a Treeview."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                node = tree_widget.insert(parent, "end", text=str(key), values=("",))
                _populate_tree(node, value, tree_widget)
            else:
                tree_widget.insert(parent, "end", text=str(key), values=(str(value),))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, (dict, list)):
                node = tree_widget.insert(parent, "end", text=f"[{i}]", values=("",))
                _populate_tree(node, item, tree_widget)
            else:
                tree_widget.insert(parent, "end", text=f"[{i}]", values=(str(item),))


def build_tree_subtab(result_notebook):
    """Build the Response Tree sub-tab. Returns (frame, update_fn, show_error_fn)."""
    frame = tk.Frame(result_notebook, bg="black")
    result_notebook.add(frame, text="Response Tree")

    style = ttk.Style()
    style.configure("APITree.Treeview",
                     background="black", foreground="white",
                     fieldbackground="black", font=("Consolas", 9))
    style.configure("APITree.Treeview.Heading",
                     background="#333333", foreground="white",
                     font=("Segoe UI", 9, "bold"))

    tree_widget = ttk.Treeview(frame, columns=("value",), show="tree headings",
                               style="APITree.Treeview")
    tree_widget.heading("#0", text="Key", anchor="w")
    tree_widget.heading("value", text="Value", anchor="w")
    tree_widget.column("#0", width=250)
    tree_widget.column("value", width=400)
    tree_widget.tag_configure("white", foreground="white")

    scroll = tk.Scrollbar(frame, command=tree_widget.yview)
    tree_widget.config(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    tree_widget.pack(fill="both", expand=True)

    def update(parsed, raw_text=""):
        for item in tree_widget.get_children():
            tree_widget.delete(item)
        if parsed is not None:
            _populate_tree("", parsed, tree_widget)
        else:
            tree_widget.insert("", "end", text="(not valid JSON)", values=(raw_text[:200],))

    def show_error(msg):
        for item in tree_widget.get_children():
            tree_widget.delete(item)
        tree_widget.insert("", "end", text="Error", values=(msg,))

    return frame, update, show_error
