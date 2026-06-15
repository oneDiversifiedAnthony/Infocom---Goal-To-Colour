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

"""sACN tabs.

build_sacn_tab -- "sACN Config": IP entry, channel mapping grid, connect/disconnect,
and CID display.
build_sacn_manual_tab -- "sACN Manual": live DMX fader banks for Universe 1 (top) and
Universe 2 (below) for manual channel control.

Handles events:
    - Connect reads the channel map and destination IP, then starts sACN output.
    - Disconnect stops the sACN sender.
    - Copy button copies the source CID to the clipboard.
    - Fader changes push updated DMX values to the sACN sender in real time.

Key design decisions:
    - Blank IP defaults to multicast for zero-config setup on local networks.
    - Channel map is editable per-colour (R/G/B channels + universe) for flexible
      fixture patching across multiple universes.
    - on_connect callback allows the App to auto-switch to the Flags tab after connection.
    - Universe 1 faders are grouped as 3 lamps × RGB for clear fixture identification.
    - The manual fader banks live on their own tab so the config tab stays compact;
      Universe 1 stacks above Universe 2 (rather than side-by-side) so the 50-channel
      Universe 2 bank gets the full tab width.
"""

import tkinter as tk
import socket
import subprocess
from src.theme import FG_DIM
from src.constants import DMX_CHANNEL_COUNT
from src.config import get_config, set_config


def _get_interfaces():
    """Return a list of (alias, ip) for up IPv4 interfaces on this machine.

    Uses PowerShell's Get-NetIPAddress because socket.getaddrinfo(gethostname())
    only reports the default-route NIC and misses the lighting/Dante NICs we need
    to bind sACN multicast to.
    """
    results = []
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetIPAddress -AddressFamily IPv4 | "
             "Where-Object { $_.IPAddress -ne '127.0.0.1' } | "
             "ForEach-Object { \"$($_.InterfaceAlias)|$($_.IPAddress)\" }"],
            capture_output=True, text=True, timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in out.stdout.splitlines():
            line = line.strip()
            if "|" in line:
                alias, ip = line.split("|", 1)
                alias, ip = alias.strip(), ip.strip()
                if ip and not any(ip == r[1] for r in results):
                    results.append((alias, ip))
    except Exception:
        pass
    if not results:  # why: fall back to the limited socket method if PowerShell is unavailable
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if not any(ip == r[1] for r in results):
                    results.append(("", ip))
        except socket.gaierror:
            pass
    return results


def _get_local_ips():
    """Return a list of local IP address strings on this machine."""
    ips = [ip for _alias, ip in _get_interfaces()]
    if not ips:
        ips.append("127.0.0.1")
    return ips


def _intensity_colour(value, channel_type):
    """Return a hex colour reflecting intensity for a given channel type (r/g/b or generic)."""
    v = max(0, min(255, value))
    if channel_type == "r":
        return f"#{v:02x}0000"
    elif channel_type == "g":
        return f"#00{v:02x}00"
    elif channel_type == "b":
        return f"#0000{v:02x}"
    # generic grey
    return f"#{v:02x}{v:02x}{v:02x}"


def build_sacn_tab(notebook, sacn, on_connect=None):
    tab = tk.Frame(notebook)
    notebook.add(tab, text="sACN Config")

    tk.Label(tab, text="sACN Connection Settings",
             font=("Segoe UI", 14, "bold")).pack(pady=(20, 10))

    AUTO_NIC = "Auto (default route)"

    # Destination IP
    ip_frame = tk.Frame(tab)
    ip_frame.pack(pady=6)
    tk.Label(ip_frame, text="Destination IP:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 8))
    saved_dest = get_config("sacn", "destination_ip", fallback="")
    ip_var = tk.StringVar(value=saved_dest)  # why: blank defaults to multicast for zero-config setup
    tk.Entry(ip_frame, textvariable=ip_var, font=("Consolas", 11), width=20).pack(side="left")
    tk.Label(ip_frame, text="(blank = multicast)", font=("Segoe UI", 9), fg="#888888").pack(side="left", padx=(8, 0))

    # Output NIC -- which interface multicast/unicast egresses from (binds sACN socket)
    nic_frame = tk.Frame(tab)
    nic_frame.pack(pady=6)
    tk.Label(nic_frame, text="Output NIC:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 8))
    saved_bind = get_config("sacn", "bind_address", fallback="")  # "" / "0.0.0.0" = Auto
    nic_var = tk.StringVar(value=AUTO_NIC)
    nic_label_to_ip = {AUTO_NIC: ""}

    def _nic_label(alias, ip):
        return f"{alias} — {ip}" if alias else ip

    def _populate_nics():
        """(Re)enumerate interfaces and rebuild the NIC dropdown, preserving selection."""
        nic_label_to_ip.clear()
        nic_label_to_ip[AUTO_NIC] = ""
        for alias, ip in _get_interfaces():
            nic_label_to_ip[_nic_label(alias, ip)] = ip
        # why: keep a saved-but-currently-absent NIC selectable so a setup-time unplug
        # doesn't silently revert sACN output to the wrong interface.
        if saved_bind and saved_bind not in ("0.0.0.0",) and \
                saved_bind not in nic_label_to_ip.values():
            nic_label_to_ip[f"(saved) {saved_bind}"] = saved_bind

        menu = nic_menu["menu"]
        menu.delete(0, "end")
        for label in nic_label_to_ip:
            menu.add_command(label=label, command=lambda v=label: nic_var.set(v))

        # Restore selection to the saved bind IP if present, else Auto
        if saved_bind and saved_bind not in ("0.0.0.0",):
            match = next((lbl for lbl, ip in nic_label_to_ip.items() if ip == saved_bind), None)
            nic_var.set(match or AUTO_NIC)
        else:
            nic_var.set(AUTO_NIC)

    nic_menu = tk.OptionMenu(nic_frame, nic_var, AUTO_NIC)
    nic_menu.config(font=("Segoe UI", 10), width=34)
    nic_menu.pack(side="left")
    tk.Button(nic_frame, text="Refresh", font=("Segoe UI", 9), padx=8,
              command=_populate_nics).pack(side="left", padx=(8, 0))
    _populate_nics()

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
        bind_ip = nic_label_to_ip.get(nic_var.get(), "")
        # Persist so the startup auto-connect (gui.py) reuses the chosen NIC + destination
        set_config("sacn", "bind_address", bind_ip)
        set_config("sacn", "destination_ip", ip)
        ok, err = sacn.reconfigure(channel_map=channel_map, destination_ip=ip or None,
                                   bind_address=bind_ip)  # why: None dest triggers multicast; bind pins the NIC
        if not ok:
            sacn_status.config(
                text=f"Connection failed: {err}", fg="red"
            )
            return
        universes = sorted(set(m["universe"] for m in channel_map) | sacn.extra_universes)
        mode = f"unicast {ip}" if ip else "multicast"
        nic_desc = f" via {bind_ip}" if bind_ip else ""
        sacn_status.config(
            text=f"Connected - Universe(s) {', '.join(map(str, universes))}, {mode}{nic_desc}", fg="green"
        )
        if on_connect:
            on_connect()  # why: allows auto-switching to Flags tab after connection

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

    return _connect


def build_sacn_manual_tab(notebook, sacn, countries_db=None):
    """Build the "sACN Manual" tab: live DMX fader banks for Universe 1 and 2.

    Returns _update_country_name(name) so the app can highlight the active country's
    fader label in Universe 2.
    """
    tab = tk.Frame(notebook)
    notebook.add(tab, text="sACN Manual")

    tk.Label(tab, text="Manual DMX Control",
             font=("Segoe UI", 14, "bold")).pack(pady=(12, 4))

    # ── DMX Fader Banks ─────────────────────────────────────────────────
    FADERS_PER_UNI = 50
    POLL_MS = 100

    # why: Universe 1 (3 lamps × RGB) stacks on top; Universe 2 (50 ch) fills below
    fader_container = tk.Frame(tab)
    fader_container.pack(fill="both", expand=True, padx=8, pady=(5, 8))

    # Track fader state per universe: {universe: [IntVar * FADERS_PER_UNI]}
    fader_vars = {}
    fader_canvases = {}

    country_name_labels = {}  # {(universe, channel_idx): Label}
    active_country = [None]

    def _build_fader_bank(parent, universe, labels, expand=True, channel_names=None):
        """Build a bank of vertical faders for a universe.

        labels: list of (channel_number, display_label, channel_type) tuples.
        channel_names: optional dict {channel_number: country_name} for labels below faders.
        """
        frame = tk.LabelFrame(parent, text=f"Universe {universe}",
                               font=("Segoe UI", 10, "bold"), padx=4, pady=4)
        # why: stack vertically (Universe 1 on top, Universe 2 below) so the wide
        # 50-channel Universe 2 bank can use the full tab width
        frame.pack(side="top", fill="both", expand=expand, padx=4, pady=(0, 4))

        # Scrollable inner frame
        name_height = 80 if channel_names else 0
        scroll_canvas = tk.Canvas(frame, highlightthickness=0, height=220 + name_height)
        scrollbar = tk.Scrollbar(frame, orient="horizontal", command=scroll_canvas.xview)
        inner = tk.Frame(scroll_canvas)

        inner.bind("<Configure>",
                   lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.create_window((0, 0), window=inner, anchor="nw")
        scroll_canvas.configure(xscrollcommand=scrollbar.set)

        scroll_canvas.pack(fill="both", expand=True)
        scrollbar.pack(fill="x")

        num_faders = len(labels)
        uni_vars = [None] * FADERS_PER_UNI
        uni_canvases = [None] * FADERS_PER_UNI

        # Track resizable widgets for dynamic sizing
        all_sliders = []
        all_intensity = []
        all_ch_labels = []
        all_val_labels = []
        all_name_canvases = []
        all_cols = []

        for ch_num, display_label, ch_type in labels:
            idx = ch_num - 1
            col = tk.Frame(inner)
            col.pack(side="left", padx=1)
            all_cols.append(col)

            # Channel label at top
            ch_label = tk.Label(col, text=display_label, font=("Consolas", 6),
                     fg="#aaaaaa")
            ch_label.pack()
            all_ch_labels.append(ch_label)

            var = tk.IntVar(value=0)
            uni_vars[idx] = var

            # Intensity canvas
            intensity_cv = tk.Canvas(col, width=14, height=10,
                                      bg="#000000", highlightthickness=0)
            intensity_cv.pack(pady=(1, 0))
            uni_canvases[idx] = (intensity_cv, ch_type)
            all_intensity.append(intensity_cv)

            # Fader
            slider = tk.Scale(col, from_=255, to=0, orient="vertical",
                              variable=var, length=140, width=14,
                              sliderlength=10, showvalue=False,
                              font=("Consolas", 6),
                              troughcolor="#2a2a2a", activebackground="#ffcc00")
            slider.pack()
            all_sliders.append(slider)

            # Scroll wheel support
            def _on_scroll(event, v=var):
                delta = 1 if event.delta > 0 else -1
                v.set(max(0, min(255, v.get() + delta)))

            slider.bind("<MouseWheel>", _on_scroll)

            # Glow on hover
            def _on_enter(event, s=slider):
                s.config(troughcolor="#444444")

            def _on_leave(event, s=slider):
                s.config(troughcolor="#2a2a2a")

            slider.bind("<Enter>", _on_enter)
            slider.bind("<Leave>", _on_leave)

            # Value label
            val_label = tk.Label(col, text="0", font=("Consolas", 6), fg="#888888")
            val_label.pack()
            all_val_labels.append(val_label)

            # Country name (rotated 90°) below fader
            name_cv = None
            if channel_names and ch_num in channel_names:
                name = channel_names[ch_num]
                name_cv = tk.Canvas(col, width=16, height=70,
                                     highlightthickness=0)
                name_cv.pack()
                name_cv.create_text(8, 35, text=name, fill="#ffffff",
                                    font=("Segoe UI", 6), angle=90, anchor="center")
                country_name_labels[(universe, idx)] = name_cv
            elif channel_names:
                name_cv = tk.Canvas(col, width=16, height=70, highlightthickness=0)
                name_cv.pack()
            if name_cv:
                all_name_canvases.append((name_cv, ch_num, idx))

            def _on_change(*_args, v=var, lbl=val_label, cv=intensity_cv, ct=ch_type, u=universe, i=idx):
                val = v.get()
                lbl.config(text=str(val))
                cv.config(bg=_intensity_colour(val, ct))
                _push_universe(u)

            var.trace_add("write", _on_change)

        # Dynamic resize based on container width
        resize_debounce = [None]

        def _on_frame_resize(event):
            if resize_debounce[0]:
                frame.after_cancel(resize_debounce[0])
            resize_debounce[0] = frame.after(150, lambda: _apply_sizes(event.width))

        def _apply_sizes(container_w):
            if num_faders == 0 or container_w < 20:
                return
            col_w = max(10, (container_w - 20) // num_faders)
            fader_w = max(8, col_w - 4)
            intensity_w = max(8, col_w - 4)
            font_size = max(5, min(9, col_w // 4))
            name_font = max(5, min(8, col_w // 3))
            name_cv_w = max(10, col_w - 2)

            for s in all_sliders:
                s.config(width=fader_w)
            for cv in all_intensity:
                cv.config(width=intensity_w)
            for lbl in all_ch_labels:
                lbl.config(font=("Consolas", font_size))
            for lbl in all_val_labels:
                lbl.config(font=("Consolas", font_size))
            for ncv, ch_num, idx in all_name_canvases:
                ncv.config(width=name_cv_w)
                ncv.delete("all")
                cname = channel_names.get(ch_num, "") if channel_names else ""
                if cname:
                    fill = "#ffcc00" if cname == active_country[0] else "#ffffff"
                    fnt = ("Segoe UI", name_font, "bold") if cname == active_country[0] else ("Segoe UI", name_font)
                    ncv.create_text(name_cv_w // 2, 35, text=cname, fill=fill,
                                    font=fnt, angle=90, anchor="center")

        scroll_canvas.bind("<Configure>", _on_frame_resize)

        fader_vars[universe] = uni_vars
        fader_canvases[universe] = uni_canvases
        return frame

    def _push_universe(universe):
        """Send current fader values for a universe to sACN."""
        if not sacn.sender:
            return
        if universe not in sacn._active_universes:
            return
        uni_v = fader_vars.get(universe)
        if not uni_v:
            return
        data = [0] * DMX_CHANNEL_COUNT
        for i in range(FADERS_PER_UNI):
            if uni_v[i] is not None:
                data[i] = uni_v[i].get()
        try:
            output = sacn.sender[universe]
            if output is not None:
                output.dmx_data = tuple(data)
        except (KeyError, TypeError):
            pass

    def _update_faders_from_output():
        """Poll sACN output and update fader positions to reflect current values."""
        if sacn.sender:
            for universe, uni_v in fader_vars.items():
                if universe not in sacn._active_universes:
                    continue
                try:
                    output = sacn.sender[universe]
                    if output is None or not output.dmx_data:
                        continue
                except (KeyError, TypeError):
                    continue
                dmx = output.dmx_data
                for i in range(FADERS_PER_UNI):
                    if uni_v[i] is not None:
                        current = uni_v[i].get()
                        actual = dmx[i] if i < len(dmx) else 0
                        if current != actual:
                            uni_v[i].set(actual)
        tab.after(POLL_MS, _update_faders_from_output)

    # Universe 1: 3 lamps × RGB (channels 1-9 only)
    u1_labels = []
    lamp_colours = ["r", "g", "b"]
    for lamp in range(3):
        for ci, colour in enumerate(lamp_colours):
            ch = lamp * 3 + ci + 1
            u1_labels.append((ch, f"L{lamp+1}\n{colour.upper()}", colour))

    # Build channel→country mapping for Universe 2
    u2_channel_names = {}
    if countries_db:
        for team_name, team_data in countries_db.get("teams", {}).items():
            trigger = team_data.get("trigger")
            if trigger and trigger.get("universe") == 2:
                u2_channel_names[trigger["channel"]] = team_name

    # Universe 2: generic channels 1-50 with country names
    u2_labels = [(ch, f"{ch}", "x") for ch in range(1, FADERS_PER_UNI + 1)]

    u1_frame = _build_fader_bank(fader_container, 1, u1_labels, expand=False)
    _build_fader_bank(fader_container, 2, u2_labels, expand=True,
                      channel_names=u2_channel_names)

    # Combined colour swatches for each lamp in Universe 1
    swatch_frame = tk.Frame(u1_frame)
    swatch_frame.pack(fill="x", pady=(4, 0))
    lamp_swatches = []
    for lamp in range(3):
        sf = tk.Frame(swatch_frame)
        sf.pack(side="left", expand=True, fill="x", padx=2)
        tk.Label(sf, text=f"L{lamp+1}", font=("Consolas", 6), fg="#aaaaaa").pack(side="left")
        cv = tk.Canvas(sf, width=30, height=14, bg="#000000", highlightthickness=1,
                       highlightbackground="#333333")
        cv.pack(side="left", fill="x", expand=True, padx=(2, 0))
        lamp_swatches.append(cv)

    def _update_lamp_swatches(*_args):
        uni_v = fader_vars.get(1)
        if not uni_v:
            return
        for lamp in range(3):
            r_var = uni_v[lamp * 3]
            g_var = uni_v[lamp * 3 + 1]
            b_var = uni_v[lamp * 3 + 2]
            r = r_var.get() if r_var else 0
            g = g_var.get() if g_var else 0
            b = b_var.get() if b_var else 0
            lamp_swatches[lamp].config(bg=f"#{r:02x}{g:02x}{b:02x}")

    # Hook swatch update to each U1 fader
    uni1_vars = fader_vars.get(1, [])
    for i in range(9):
        if uni1_vars[i] is not None:
            uni1_vars[i].trace_add("write", _update_lamp_swatches)

    def _update_country_name(name):
        # Reset previous active label to white
        if active_country[0]:
            for (uni, idx), cv in country_name_labels.items():
                ch = idx + 1
                cname = u2_channel_names.get(ch, "")
                if cname == active_country[0]:
                    cw = max(10, cv.winfo_width())
                    cv.delete("all")
                    cv.create_text(cw // 2, 35, text=cname, fill="#ffffff",
                                   font=("Segoe UI", 6), angle=90, anchor="center")
        # Highlight new active label in yellow
        active_country[0] = name
        if name:
            for (uni, idx), cv in country_name_labels.items():
                ch = idx + 1
                cname = u2_channel_names.get(ch, "")
                if cname == name:
                    cw = max(10, cv.winfo_width())
                    cv.delete("all")
                    cv.create_text(cw // 2, 35, text=cname, fill="#ffcc00",
                                   font=("Segoe UI", 6, "bold"), angle=90, anchor="center")

    # Start polling
    tab.after(POLL_MS, _update_faders_from_output)

    return _update_country_name
