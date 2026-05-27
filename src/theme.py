import tkinter as tk
from tkinter import ttk

BG = "#1e1e1e"
BG_LIGHT = "#2d2d2d"
BG_ENTRY = "#3c3c3c"
FG = "#e0e0e0"
FG_DIM = "#999999"
ACCENT = "#4fc3f7"


def apply_dark_theme(root):
    root.configure(bg=BG)
    root.option_add("*Background", BG)
    root.option_add("*Foreground", FG)
    root.option_add("*activeBackground", BG_LIGHT)
    root.option_add("*activeForeground", FG)
    root.option_add("*selectBackground", ACCENT)
    root.option_add("*selectForeground", "#000000")
    root.option_add("*Entry.Background", BG_ENTRY)
    root.option_add("*Entry.Foreground", FG)
    root.option_add("*Entry.insertBackground", FG)
    root.option_add("*Listbox.Background", BG_ENTRY)
    root.option_add("*Listbox.Foreground", FG)
    root.option_add("*Scale.troughColor", BG_LIGHT)
    root.option_add("*Canvas.Background", BG_LIGHT)
    root.option_add("*highlightBackground", BG)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=FG, fieldbackground=BG_ENTRY,
                    borderwidth=0)
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=BG_LIGHT, foreground=FG,
                    padding=[10, 4])
    style.map("TNotebook.Tab",
              background=[("selected", BG), ("active", "#3d3d3d")],
              foreground=[("selected", ACCENT)])
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("TLabelframe", background=BG, foreground=FG)
    style.configure("TLabelframe.Label", background=BG, foreground=FG)
    style.configure("TSeparator", background=BG_LIGHT)
    style.configure("TScrollbar", background=BG_LIGHT, troughcolor=BG,
                    borderwidth=0, arrowcolor=FG)
    style.configure("TCombobox", fieldbackground=BG_ENTRY, background=BG_LIGHT,
                    foreground=FG, arrowcolor=FG)
    style.map("TCombobox", fieldbackground=[("readonly", BG_ENTRY)])
