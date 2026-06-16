# Copyright (c) 2026 oneDiversified.
#
# This software, its source code, and all associated functions, scripts, and
# documentation are the proprietary and confidential property of oneDiversified.

"""OSC WAVE tab.

Select an output NIC, point it at a Yamaha DM7 (IP + port), connect, then run
"VEGAS MODE" -- a travelling sine wave across faders 1-16 sent over OSC. The
backend lives in src/osc_wave.py. IP/port/address/NIC persist in config.ini.
"""

import tkinter as tk

from src.tabs.sacn import _get_interfaces
from src.osc_wave import OscWaveEngine, DEFAULT_IP, DEFAULT_PORT, DEFAULT_FADER_ADDRESS
from src.config import get_config, set_config


def build_osc_wave_tab(notebook):
    """Build the OSC WAVE tab. Returns the OscWaveEngine instance."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="OSC WAVE")

    engine = OscWaveEngine()

    tk.Label(tab, text="OSC WAVE — Yamaha DM7",
             font=("Segoe UI", 14, "bold")).pack(pady=(20, 4))
    tk.Label(tab, text="Sine-wave fader control over OSC (UDP)",
             font=("Segoe UI", 10), fg="#888888").pack(pady=(0, 10))

    AUTO_NIC = "Auto (default route)"

    # ── Output NIC selection ────────────────────────────────────────────
    nic_frame = tk.Frame(tab)
    nic_frame.pack(pady=6)
    tk.Label(nic_frame, text="Output NIC:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 8))
    saved_bind = get_config("osc_wave", "bind_address", fallback="")
    nic_var = tk.StringVar(value=AUTO_NIC)
    nic_label_to_ip = {AUTO_NIC: ""}

    def _nic_label(alias, ip):
        return f"{alias} — {ip}" if alias else ip

    nic_menu = tk.OptionMenu(nic_frame, nic_var, AUTO_NIC)
    nic_menu.config(font=("Segoe UI", 10), width=34)
    nic_menu.pack(side="left")

    def _populate_nics():
        nic_label_to_ip.clear()
        nic_label_to_ip[AUTO_NIC] = ""
        for alias, ip in _get_interfaces():
            nic_label_to_ip[_nic_label(alias, ip)] = ip
        if saved_bind and saved_bind not in ("0.0.0.0",) and saved_bind not in nic_label_to_ip.values():
            nic_label_to_ip[f"(saved) {saved_bind}"] = saved_bind
        menu = nic_menu["menu"]
        menu.delete(0, "end")
        for label in nic_label_to_ip:
            menu.add_command(label=label, command=lambda v=label: nic_var.set(v))
        if saved_bind and saved_bind not in ("0.0.0.0",):
            match = next((lbl for lbl, ip in nic_label_to_ip.items() if ip == saved_bind), None)
            nic_var.set(match or AUTO_NIC)
        else:
            nic_var.set(AUTO_NIC)

    tk.Button(nic_frame, text="Refresh", font=("Segoe UI", 9), padx=8,
              command=_populate_nics).pack(side="left", padx=(8, 0))
    _populate_nics()

    # ── Console IP / port / OSC address ─────────────────────────────────
    def _row(label, value, width=20):
        f = tk.Frame(tab)
        f.pack(pady=4)
        tk.Label(f, text=label, font=("Segoe UI", 11), width=12, anchor="e").pack(side="left", padx=(0, 8))
        var = tk.StringVar(value=value)
        tk.Entry(f, textvariable=var, font=("Consolas", 11), width=width).pack(side="left")
        return var

    ip_var = _row("Console IP:", get_config("osc_wave", "ip", fallback=DEFAULT_IP))
    port_var = _row("Port:", get_config("osc_wave", "port", fallback=str(DEFAULT_PORT)), width=10)
    addr_var = _row("OSC address:", get_config("osc_wave", "address", fallback=DEFAULT_FADER_ADDRESS))

    status = tk.Label(tab, text="Disconnected", font=("Consolas", 10), fg="red")

    # ── VEGAS MODE button (enabled after connect) ───────────────────────
    vegas_btn = tk.Button(tab, text="VEGAS MODE", font=("Segoe UI", 14, "bold"),
                          bg="#cc0066", fg="white", padx=30, pady=10,
                          state="disabled")

    def _refresh_vegas_btn():
        if engine.vegas_active:
            vegas_btn.config(text="STOP VEGAS", bg="#cc0000")
        else:
            vegas_btn.config(text="VEGAS MODE", bg="#cc0066")

    def _connect():
        bind_ip = nic_label_to_ip.get(nic_var.get(), "")
        ip = ip_var.get().strip()
        port = port_var.get().strip()
        address = addr_var.get().strip() or DEFAULT_FADER_ADDRESS
        ok, err = engine.connect(ip, port, bind_ip=bind_ip, address=address)
        if not ok:
            status.config(text=f"Connect failed: {err}", fg="red")
            return
        # Persist so the next launch reuses these settings
        set_config("osc_wave", "ip", ip)
        set_config("osc_wave", "port", str(port))
        set_config("osc_wave", "address", address)
        set_config("osc_wave", "bind_address", bind_ip)
        nic_desc = f" via {bind_ip}" if bind_ip else ""
        status.config(text=f"Ready → {ip}:{port}{nic_desc}", fg="green")
        vegas_btn.config(state="normal")
        _refresh_vegas_btn()

    def _disconnect():
        engine.disconnect()
        status.config(text="Disconnected", fg="red")
        vegas_btn.config(state="disabled")
        _refresh_vegas_btn()

    btn_frame = tk.Frame(tab)
    btn_frame.pack(pady=14)
    tk.Button(btn_frame, text="Connect", font=("Segoe UI", 11, "bold"),
              bg="#28a745", fg="white", padx=20, pady=4,
              command=_connect).pack(side="left", padx=8)
    tk.Button(btn_frame, text="Disconnect", font=("Segoe UI", 11),
              padx=20, pady=4, command=_disconnect).pack(side="left", padx=8)

    status.pack(pady=(2, 10))

    def _toggle_vegas():
        if engine.vegas_active:
            engine.stop_vegas()
        else:
            engine.start_vegas()
        _refresh_vegas_btn()

    vegas_btn.config(command=_toggle_vegas)
    vegas_btn.pack(pady=(4, 8))

    tk.Label(tab, text="VEGAS MODE waves a sine across faders 1-16.",
             font=("Segoe UI", 9), fg="#888888").pack(pady=(0, 4))

    return engine
