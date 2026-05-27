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

"""Read Me tab -- renders README.md with markdown formatting inside a tkinter Text widget.

Handles events:
    - On tab creation, loads and renders README.md into a read-only Text widget.

Key design decisions:
    - Custom markdown renderer because tkinter has no native markdown widget.
    - Supports PyInstaller bundling via sys._MEIPASS fallback for frozen executables.
    - Regex-based parsing handles headers, bullets, code blocks, bold, and inline code.
"""

import tkinter as tk
from tkinter import font as tkfont
import os
import sys
import re


# why: sys._MEIPASS is set by PyInstaller for bundled apps; fallback uses project root for development
_BASE = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
README_FILE = os.path.join(_BASE, "README.md")


def _render_markdown(text_widget, md):
    """Parse markdown and insert formatted text into a tk.Text widget."""

    # Define fonts
    base_family = "Segoe UI"
    mono_family = "Consolas"

    f_h1 = tkfont.Font(family=base_family, size=18, weight="bold")
    f_h2 = tkfont.Font(family=base_family, size=14, weight="bold")
    f_h3 = tkfont.Font(family=base_family, size=12, weight="bold")
    f_body = tkfont.Font(family=base_family, size=10)
    f_bold = tkfont.Font(family=base_family, size=10, weight="bold")
    f_code_inline = tkfont.Font(family=mono_family, size=9)
    f_code_block = tkfont.Font(family=mono_family, size=9)

    # Configure tags
    text_widget.tag_configure("h1", font=f_h1, spacing3=8, foreground="#ffffff")
    text_widget.tag_configure("h2", font=f_h2, spacing1=12, spacing3=6, foreground="#e0e0e0")
    text_widget.tag_configure("h3", font=f_h3, spacing1=10, spacing3=4, foreground="#cccccc")
    text_widget.tag_configure("body", font=f_body, foreground="#bbbbbb")
    text_widget.tag_configure("bold", font=f_bold, foreground="#dddddd")
    text_widget.tag_configure("code_inline", font=f_code_inline, background="#2d2d2d",
                              foreground="#66d9ef")
    text_widget.tag_configure("code_block", font=f_code_block, background="#1e1e1e",
                              foreground="#a6e22e", lmargin1=20, lmargin2=20, spacing1=4,
                              spacing3=4)
    text_widget.tag_configure("bullet", font=f_body, lmargin1=20, lmargin2=34,
                              foreground="#bbbbbb")
    text_widget.tag_configure("hr", font=f_body, foreground="#555555")

    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Code block (```)
        if line.strip().startswith("```"):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                text_widget.insert("end", lines[i] + "\n", "code_block")
                i += 1
            i += 1  # skip closing ```
            continue

        # Headings
        if line.startswith("### "):
            text_widget.insert("end", line[4:] + "\n", "h3")
        elif line.startswith("## "):
            text_widget.insert("end", line[3:] + "\n", "h2")
        elif line.startswith("# "):
            text_widget.insert("end", line[2:] + "\n", "h1")
        # Horizontal rule
        elif re.match(r"^-{3,}$", line.strip()) or re.match(r"^\*{3,}$", line.strip()):
            text_widget.insert("end", "\u2500" * 60 + "\n", "hr")
        # Bullet points
        elif re.match(r"^\s*[-*]\s+", line):
            content = re.sub(r"^\s*[-*]\s+", "", line)
            _insert_inline(text_widget, "\u2022  " + content + "\n", "bullet")
        # Empty line
        elif line.strip() == "":
            text_widget.insert("end", "\n", "body")
        # Regular text
        else:
            _insert_inline(text_widget, line + "\n", "body")

        i += 1


def _insert_inline(text_widget, line, base_tag):
    """Insert a line handling **bold** and `code` inline formatting."""
    parts = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", line)  # why: regex splits on bold (**) and inline code (`) for tag-based formatting
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            text_widget.insert("end", part[2:-2], "bold")
        elif part.startswith("`") and part.endswith("`"):
            text_widget.insert("end", part[1:-1], "code_inline")
        else:
            text_widget.insert("end", part, base_tag)


def build_readme_tab(notebook):
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Read Me")

    text = tk.Text(tab, wrap="word", padx=16, pady=16,
                   state="disabled", cursor="arrow",
                   background="#1a1a1a", borderwidth=0, highlightthickness=0)
    scrollbar = tk.Scrollbar(tab, command=text.yview)
    text.config(yscrollcommand=scrollbar.set)

    scrollbar.pack(side="right", fill="y")
    text.pack(fill="both", expand=True)

    try:
        with open(README_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = "README.md not found."

    text.config(state="normal")
    _render_markdown(text, content)
    text.config(state="disabled")
