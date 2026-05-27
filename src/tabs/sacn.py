import tkinter as tk
import socket
from src.theme import FG_DIM


def _get_local_ips():
    """Return a list of local IP addresses on this machine."""
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addr = info[4][0]
            if addr not in ips:
                ips.append(addr)
    except socket.gaierror:
        pass
    if not ips:
        ips.append("127.0.0.1")
    return ips


def build_sacn_tab(notebook, sacn, on_connect=None):
    tab = tk.Frame(notebook)
    notebook.add(tab, text="sACN Config")

    tk.Label(tab, text="sACN Connection Settings",
             font=("Segoe UI", 14, "bold")).pack(pady=(20, 10))

    # Destination IP
    ip_frame = tk.Frame(tab)
    ip_frame.pack(pady=6)
    tk.Label(ip_frame, text="Destination IP:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 8))
    ip_var = tk.StringVar(value="")
    tk.Entry(ip_frame, textvariable=ip_var, font=("Consolas", 11), width=20).pack(side="left")
    tk.Label(ip_frame, text="(blank = multicast)", font=("Segoe UI", 9), fg="#888888").pack(side="left", padx=(8, 0))

    # Channel mapping grid
    map_frame = tk.LabelFrame(tab, text="Channel Mapping", font=("Segoe UI", 10), padx=12, pady=8)
    map_frame.pack(padx=30, pady=(10, 10), fill="x")

    headers = ["", "R Ch", "G Ch", "B Ch", "Universe"]
    for c, h in enumerate(headers):
        tk.Label(map_frame, text=h, font=("Segoe UI", 10, "bold")).grid(row=0, column=c, padx=6, pady=(0, 4))

    ch_map_vars = []
    defaults = [
        (1, 2, 3, 1),
        (4, 5, 6, 1),
        (7, 8, 9, 1),
    ]
    for i in range(3):
        row_vars = {}
        tk.Label(map_frame, text=f"Colour {i+1}:", font=("Segoe UI", 10),
                 anchor="e").grid(row=i+1, column=0, padx=(0, 8), pady=4, sticky="e")
        for j, key in enumerate(["r", "g", "b", "universe"]):
            var = tk.StringVar(value=str(defaults[i][j]))
            tk.Entry(map_frame, textvariable=var, font=("Consolas", 11),
                     width=5, justify="center").grid(row=i+1, column=j+1, padx=6, pady=4)
            row_vars[key] = var
        ch_map_vars.append(row_vars)

    # Status label
    sacn_status = tk.Label(tab, text="Disconnected", font=("Consolas", 10), fg="red")

    def _get_channel_map():
        channel_map = []
        for row_vars in ch_map_vars:
            channel_map.append({
                "r": int(row_vars["r"].get()),
                "g": int(row_vars["g"].get()),
                "b": int(row_vars["b"].get()),
                "universe": int(row_vars["universe"].get()),
            })
        return channel_map

    def _connect():
        try:
            channel_map = _get_channel_map()
        except ValueError:
            sacn_status.config(text="Invalid channel or universe value", fg="red")
            return
        ip = ip_var.get().strip()
        sacn.reconfigure(channel_map=channel_map, destination_ip=ip or None)
        universes = sorted(set(m["universe"] for m in channel_map) | sacn.extra_universes)
        mode = f"unicast {ip}" if ip else "multicast"
        sacn_status.config(
            text=f"Connected - Universe(s) {', '.join(map(str, universes))}, {mode}", fg="green"
        )
        if on_connect:
            on_connect()

    def _disconnect():
        sacn.stop()
        sacn_status.config(text="Disconnected", fg="red")

    # Buttons
    btn_frame = tk.Frame(tab)
    btn_frame.pack(pady=15)

    tk.Button(btn_frame, text="Connect", font=("Segoe UI", 11, "bold"),
              bg="#28a745", fg="white", padx=20, pady=4,
              command=_connect).pack(side="left", padx=8)

    tk.Button(btn_frame, text="Disconnect", font=("Segoe UI", 11),
              padx=20, pady=4, command=_disconnect).pack(side="left", padx=8)

    sacn_status.pack(pady=(5, 10))

    # CID display
    cid_frame = tk.LabelFrame(tab, text="Source CID", font=("Segoe UI", 10), padx=12, pady=6)
    cid_frame.pack(padx=30, pady=(5, 10), fill="x")

    cid_row = tk.Frame(cid_frame)
    cid_row.pack(anchor="w")
    tk.Label(cid_row, text=str(sacn.cid), font=("Consolas", 10), fg=FG_DIM).pack(side="left")

    def _copy_cid():
        tab.clipboard_clear()
        tab.clipboard_append(str(sacn.cid))

    tk.Button(cid_row, text="Copy", font=("Segoe UI", 8), padx=6,
              command=_copy_cid).pack(side="left", padx=(8, 0))

    # Local IP addresses
    ip_list_frame = tk.LabelFrame(tab, text="Local IP Addresses", font=("Segoe UI", 10), padx=12, pady=6)
    ip_list_frame.pack(padx=30, pady=(5, 10), fill="x")

    for addr in _get_local_ips():
        tk.Label(ip_list_frame, text=addr, font=("Consolas", 10), fg=FG_DIM, anchor="w").pack(anchor="w")
