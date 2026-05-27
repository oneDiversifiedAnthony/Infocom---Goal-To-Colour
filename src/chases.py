import tkinter as tk
from tkinter import ttk, messagebox
import json
import os

PATTERNS_FILE = os.path.join(os.path.dirname(__file__), os.pardir, "assets", "patterns.json")

COLOUR_OPTIONS = ["Colour 1", "Colour 2", "Colour 3", "Black", "White"]
COLOUR_MAP = {
    "Black": [0, 0, 0],
    "White": [255, 255, 255],
}


def _resolve_colour(choice, team_colours):
    """Resolve a dropdown choice to an RGB list."""
    if choice in COLOUR_MAP:
        return list(COLOUR_MAP[choice])
    if team_colours:
        idx = {"Colour 1": 0, "Colour 2": 1, "Colour 3": 2}.get(choice, 0)
        if idx < len(team_colours):
            return list(team_colours[idx])
    return [0, 0, 0]


def _load_patterns():
    if os.path.exists(PATTERNS_FILE):
        with open(PATTERNS_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_patterns(patterns):
    with open(PATTERNS_FILE, "w") as f:
        json.dump(patterns, f, indent=2)


class ChaseController:
    """Runs a chase pattern by stepping through frames."""

    def __init__(self, root, draw_swatches_cb, get_team_colours_cb):
        self.root = root
        self.draw_swatches = draw_swatches_cb
        self.get_team_colours = get_team_colours_cb
        self.timer_id = None
        self.steps = []
        self.current_step = 0
        self.running = False

    def start(self, steps):
        """Start running a chase pattern (list of step dicts)."""
        self.stop()
        if not steps:
            return
        self.steps = steps
        self.current_step = 0
        self.running = True
        self._run_step()

    def stop(self):
        self.running = False
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

    @property
    def is_active(self):
        return self.running

    def _run_step(self):
        if not self.running or not self.steps:
            return

        step = self.steps[self.current_step]
        team_colours = self.get_team_colours()

        colours = [
            _resolve_colour(step["ch1"], team_colours),
            _resolve_colour(step["ch2"], team_colours),
            _resolve_colour(step["ch3"], team_colours),
        ]
        self.draw_swatches(colours)

        delay_ms = int(float(step.get("time", 0.5)) * 1000)
        delay_ms = max(50, delay_ms)

        self.current_step = (self.current_step + 1) % len(self.steps)
        self.timer_id = self.root.after(delay_ms, self._run_step)


def build_chases_tab(notebook, root, draw_swatches_cb, get_team_colours_cb):
    """Build the Chases tab with pattern editor."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Chases")

    chase = ChaseController(root, draw_swatches_cb, get_team_colours_cb)
    patterns = _load_patterns()

    # ── Top: pattern selector ─────────────────────────────────────────
    sel_frame = tk.LabelFrame(tab, text="Saved Patterns", font=("Segoe UI", 10), padx=8, pady=4)
    sel_frame.pack(fill="x", padx=10, pady=(10, 5))

    pattern_var = tk.StringVar()
    pattern_combo = ttk.Combobox(sel_frame, textvariable=pattern_var,
                                  font=("Segoe UI", 10), state="readonly", width=25)
    pattern_combo["values"] = list(patterns.keys())
    pattern_combo.pack(side="left", padx=(0, 8))

    step_rows = []  # list of dicts with StringVars

    def _refresh_combo():
        nonlocal patterns
        patterns = _load_patterns()
        pattern_combo["values"] = list(patterns.keys())

    def _load_selected():
        name = pattern_var.get()
        if not name or name not in patterns:
            return
        _clear_steps()
        for step_data in patterns[name]:
            _add_step(step_data.get("ch1", "Black"),
                      step_data.get("ch2", "Black"),
                      step_data.get("ch3", "Black"),
                      str(step_data.get("time", 0.5)))

    def _delete_selected():
        name = pattern_var.get()
        if not name or name not in patterns:
            return
        del patterns[name]
        _save_patterns(patterns)
        _refresh_combo()
        pattern_var.set("")

    tk.Button(sel_frame, text="Load", font=("Segoe UI", 9),
              command=_load_selected).pack(side="left", padx=2)
    tk.Button(sel_frame, text="Delete", font=("Segoe UI", 9),
              command=_delete_selected).pack(side="left", padx=2)

    # ── Middle: step editor ───────────────────────────────────────────
    editor_frame = tk.LabelFrame(tab, text="Pattern Steps", font=("Segoe UI", 10), padx=8, pady=4)
    editor_frame.pack(fill="both", expand=True, padx=10, pady=5)

    # Header
    hdr = tk.Frame(editor_frame)
    hdr.pack(fill="x")
    tk.Label(hdr, text="Step", font=("Segoe UI", 9, "bold"), width=5).pack(side="left")
    tk.Label(hdr, text="Colour 1", font=("Segoe UI", 9, "bold"), width=12).pack(side="left")
    tk.Label(hdr, text="Colour 2", font=("Segoe UI", 9, "bold"), width=12).pack(side="left")
    tk.Label(hdr, text="Colour 3", font=("Segoe UI", 9, "bold"), width=12).pack(side="left")
    tk.Label(hdr, text="Time (s)", font=("Segoe UI", 9, "bold"), width=8).pack(side="left")
    ttk.Separator(editor_frame, orient="horizontal").pack(fill="x", pady=2)

    # Scrollable steps area
    steps_container = tk.Frame(editor_frame)
    steps_container.pack(fill="both", expand=True)

    canvas = tk.Canvas(steps_container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(steps_container, orient="vertical", command=canvas.yview)
    steps_frame = tk.Frame(canvas)
    steps_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=steps_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _add_step(ch1="Black", ch2="Black", ch3="Black", time_val="0.5"):
        idx = len(step_rows)
        row_frame = tk.Frame(steps_frame)
        row_frame.pack(fill="x", pady=1)

        tk.Label(row_frame, text=f"{idx + 1}", font=("Consolas", 9), width=5).pack(side="left")

        ch1_var = tk.StringVar(value=ch1)
        ch2_var = tk.StringVar(value=ch2)
        ch3_var = tk.StringVar(value=ch3)
        time_var = tk.StringVar(value=time_val)

        ttk.Combobox(row_frame, textvariable=ch1_var, values=COLOUR_OPTIONS,
                     state="readonly", width=10, font=("Segoe UI", 9)).pack(side="left", padx=2)
        ttk.Combobox(row_frame, textvariable=ch2_var, values=COLOUR_OPTIONS,
                     state="readonly", width=10, font=("Segoe UI", 9)).pack(side="left", padx=2)
        ttk.Combobox(row_frame, textvariable=ch3_var, values=COLOUR_OPTIONS,
                     state="readonly", width=10, font=("Segoe UI", 9)).pack(side="left", padx=2)
        tk.Entry(row_frame, textvariable=time_var, width=6, font=("Consolas", 9)).pack(side="left", padx=4)

        def _remove():
            row_frame.destroy()
            step_rows.remove(row_data)
            _renumber()

        tk.Button(row_frame, text="X", font=("Segoe UI", 8), fg="red",
                  command=_remove).pack(side="left", padx=2)

        row_data = {"frame": row_frame, "ch1": ch1_var, "ch2": ch2_var,
                    "ch3": ch3_var, "time": time_var}
        step_rows.append(row_data)

    def _renumber():
        for i, rd in enumerate(step_rows):
            for w in rd["frame"].winfo_children():
                if isinstance(w, tk.Label):
                    w.config(text=f"{i + 1}")
                    break

    def _clear_steps():
        for rd in step_rows[:]:
            rd["frame"].destroy()
        step_rows.clear()

    def _get_steps_data():
        result = []
        for rd in step_rows:
            try:
                t = float(rd["time"].get())
            except ValueError:
                t = 0.5
            result.append({
                "ch1": rd["ch1"].get(),
                "ch2": rd["ch2"].get(),
                "ch3": rd["ch3"].get(),
                "time": t,
            })
        return result

    # ── Bottom: buttons ───────────────────────────────────────────────
    btn_frame = tk.Frame(tab)
    btn_frame.pack(fill="x", padx=10, pady=(5, 10))

    tk.Button(btn_frame, text="+ Add Step", font=("Segoe UI", 10),
              command=_add_step).pack(side="left", padx=4)

    tk.Button(btn_frame, text="Clear All", font=("Segoe UI", 10),
              command=_clear_steps).pack(side="left", padx=4)

    # Save
    save_name_var = tk.StringVar()
    tk.Entry(btn_frame, textvariable=save_name_var, font=("Segoe UI", 10),
             width=15).pack(side="left", padx=(20, 4))

    def _save():
        name = save_name_var.get().strip()
        if not name:
            messagebox.showwarning("Save", "Enter a pattern name.")
            return
        data = _get_steps_data()
        if not data:
            messagebox.showwarning("Save", "Add at least one step.")
            return
        patterns[name] = data
        _save_patterns(patterns)
        _refresh_combo()
        pattern_var.set(name)

    tk.Button(btn_frame, text="Save", font=("Segoe UI", 10, "bold"),
              command=_save).pack(side="left", padx=2)

    # Run / Stop
    status_label = tk.Label(btn_frame, text="", font=("Segoe UI", 9), fg="#888888")
    status_label.pack(side="right", padx=8)

    def _run():
        steps_data = _get_steps_data()
        if not steps_data:
            return
        chase.start(steps_data)
        status_label.config(text="Running...", fg="green")

    def _stop():
        chase.stop()
        status_label.config(text="Stopped", fg="red")

    tk.Button(btn_frame, text="STOP", font=("Segoe UI", 10, "bold"),
              bg="#cc0000", fg="white", padx=12,
              command=_stop).pack(side="right", padx=4)
    tk.Button(btn_frame, text="RUN", font=("Segoe UI", 10, "bold"),
              bg="#28a745", fg="white", padx=12,
              command=_run).pack(side="right", padx=4)

    return chase
