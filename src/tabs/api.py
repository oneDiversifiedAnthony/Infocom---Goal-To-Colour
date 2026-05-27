import tkinter as tk
from tkinter import ttk
import threading
import urllib.request
import urllib.error


DEFAULT_URL = "https://cricket.sportmonks.com/api/v2.0/livescores?api_token={{api_token}}&include="


def build_api_tab(notebook):
    tab = tk.Frame(notebook)
    notebook.add(tab, text="API")

    # ── URL ────────────────────────────────────────────────────────────
    url_frame = tk.Frame(tab)
    url_frame.pack(fill="x", padx=12, pady=(12, 4))
    tk.Label(url_frame, text="URL:", font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))
    url_var = tk.StringVar(value=DEFAULT_URL)
    tk.Entry(url_frame, textvariable=url_var, font=("Consolas", 9), width=70).pack(side="left", fill="x", expand=True)

    # ── API Token ──────────────────────────────────────────────────────
    token_frame = tk.Frame(tab)
    token_frame.pack(fill="x", padx=12, pady=4)
    tk.Label(token_frame, text="API Token:", font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))
    token_var = tk.StringVar(value="SgWZqK22kfrWuT013yqUZG6U0W7xEovKeZz1SWIIb9OArYUFp6XESiDAiTyk")
    tk.Entry(token_frame, textvariable=token_var, font=("Consolas", 9), width=50).pack(side="left", fill="x", expand=True)

    # ── Controls ───────────────────────────────────────────────────────
    ctrl_frame = tk.Frame(tab)
    ctrl_frame.pack(fill="x", padx=12, pady=(8, 4))

    status_label = tk.Label(ctrl_frame, text="", font=("Segoe UI", 9), fg="#888888")

    auto_timer_id = [None]
    auto_progress_id = [None]
    auto_running = [False]
    auto_elapsed = [0]
    auto_interval = [0]

    def _build_url():
        url = url_var.get().strip()
        token = token_var.get().strip()
        return url.replace("{{api_token}}", token)

    def _fetch():
        final_url = _build_url()
        status_label.config(text="Fetching...", fg="#0066cc")
        result_text.config(state="normal")
        result_text.delete("1.0", "end")
        result_text.config(state="disabled")

        def _do_request():
            try:
                req = urllib.request.Request(final_url)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                tab.after(0, lambda: _show_result(body))
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                msg = f"HTTP Error {e.code}: {e.reason}\n\n{body}"
                tab.after(0, lambda: _show_error(msg))
            except Exception as e:
                tab.after(0, lambda: _show_error(str(e)))

        threading.Thread(target=_do_request, daemon=True).start()

    def _show_result(text):
        result_text.config(state="normal")
        result_text.delete("1.0", "end")
        result_text.insert("1.0", text)
        result_text.config(state="disabled")
        status_label.config(text="OK", fg="green")

    def _show_error(msg):
        result_text.config(state="normal")
        result_text.delete("1.0", "end")
        result_text.insert("1.0", f"ERROR:\n{msg}")
        result_text.config(state="disabled")
        status_label.config(text="Error", fg="red")

    # Get button
    tk.Button(ctrl_frame, text="Get", font=("Segoe UI", 10, "bold"),
              bg="#0066cc", fg="white", padx=16, pady=2,
              command=_fetch).pack(side="left", padx=(0, 12))

    # Auto get controls
    ttk.Separator(ctrl_frame, orient="vertical").pack(side="left", fill="y", padx=8)
    tk.Label(ctrl_frame, text="Auto every", font=("Segoe UI", 10)).pack(side="left", padx=(4, 4))
    interval_var = tk.IntVar(value=10)
    interval_spin = tk.Spinbox(ctrl_frame, from_=1, to=30, textvariable=interval_var,
                                font=("Consolas", 10), width=3, justify="center")
    interval_spin.pack(side="left")
    tk.Label(ctrl_frame, text="sec", font=("Segoe UI", 10)).pack(side="left", padx=(2, 8))

    def _start_auto():
        if auto_running[0]:
            return
        auto_running[0] = True
        auto_btn.config(text="Stop Auto", bg="#cc0000", command=_stop_auto)
        _auto_cycle()

    def _stop_auto():
        auto_running[0] = False
        if auto_timer_id[0]:
            tab.after_cancel(auto_timer_id[0])
            auto_timer_id[0] = None
        if auto_progress_id[0]:
            tab.after_cancel(auto_progress_id[0])
            auto_progress_id[0] = None
        progress["value"] = 0
        auto_btn.config(text="Auto Get", bg="#28a745", command=_start_auto)

    def _auto_cycle():
        if not auto_running[0]:
            return
        _fetch()
        interval_ms = max(1, interval_var.get()) * 1000
        auto_interval[0] = interval_ms
        auto_elapsed[0] = 0
        progress["value"] = 0
        _tick_progress()
        auto_timer_id[0] = tab.after(interval_ms, _auto_cycle)

    def _tick_progress():
        if not auto_running[0]:
            return
        auto_elapsed[0] += 100
        pct = min(100, (auto_elapsed[0] / auto_interval[0]) * 100)
        progress["value"] = pct
        if auto_elapsed[0] < auto_interval[0]:
            auto_progress_id[0] = tab.after(100, _tick_progress)

    auto_btn = tk.Button(ctrl_frame, text="Auto Get", font=("Segoe UI", 10, "bold"),
                         bg="#28a745", fg="white", padx=12, pady=2,
                         command=_start_auto)
    auto_btn.pack(side="left", padx=4)

    status_label.pack(side="right", padx=8)

    # ── Progress bar ───────────────────────────────────────────────────
    progress = ttk.Progressbar(tab, length=200, mode="determinate", maximum=100)
    progress.pack(fill="x", padx=12, pady=(4, 6))

    # ── Results ────────────────────────────────────────────────────────
    result_frame = tk.LabelFrame(tab, text="Response", font=("Segoe UI", 10), padx=6, pady=6)
    result_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    result_text = tk.Text(result_frame, wrap="word", font=("Consolas", 9),
                          state="disabled", cursor="arrow")
    result_scroll = tk.Scrollbar(result_frame, command=result_text.yview)
    result_text.config(yscrollcommand=result_scroll.set)
    result_scroll.pack(side="right", fill="y")
    result_text.pack(fill="both", expand=True)
