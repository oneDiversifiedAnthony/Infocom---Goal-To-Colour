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

"""Web Server tab -- hosts a live status page showing current colours,
sound playback state, and the game schedule.

Runs a lightweight HTTP server in a background thread on a configurable port.
The page auto-refreshes every 2 seconds via meta-refresh.
"""

import tkinter as tk
import threading
import socket
import json
import webbrowser
import base64
import os
from urllib.parse import unquote_plus
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


# Load logo as base64 for embedding in HTML
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "Diversified_logo.png")
try:
    with open(_LOGO_PATH, "rb") as _f:
        _LOGO_B64 = base64.b64encode(_f.read()).decode("ascii")
except FileNotFoundError:
    _LOGO_B64 = ""

# Load flag SVG data
_FLAGS_PATH = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "assets", "Flags.json")
try:
    with open(_FLAGS_PATH, "r", encoding="utf-8") as _f:
        _FLAGS_DATA = json.load(_f).get("flags", {})
except (FileNotFoundError, json.JSONDecodeError):
    _FLAGS_DATA = {}


def _flag_svg(name, width=48, height=32):
    """Return an inline flag SVG element for a country, or empty string."""
    entry = _FLAGS_DATA.get(name)
    if not entry:
        return ""
    svg = entry.get("svg", "")
    if not svg:
        return ""
    # Wrap in a sized container div
    return (
        f'<div style="display:inline-block;width:{width}px;height:{height}px;'
        f'border:1px solid #555;border-radius:2px;overflow:hidden;vertical-align:middle;'
        f'margin-right:4px;">{svg}</div>'
    )

# Shared state dict updated by the main app
_state = {
    "colours": [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
    "team_name": "",
    "goal_active": False,
    "games": [],          # list of game dicts from schedule
    "teams": {},          # {name: {"colours": [[r,g,b], ...]}}
    "api_remaining": "",  # e.g. "2950 / 3000"
    "sacn_connected": False,
}

_lv_tz = ZoneInfo("America/Los_Angeles")

# Callbacks set by the main app (called from HTTP thread via root.after)
_callbacks = {
    "goal_pressed": None,   # fn(colours, country_name)
    "set_colours": None,    # fn(colours, country_name)
    "root": None,           # tkinter root for after() scheduling
}


def update_state(*, colours=None, team_name=None, goal_active=None,
                 games=None, teams=None, api_remaining=None,
                 sacn_connected=None):
    """Update shared state from the main app. Thread-safe for reads."""
    if colours is not None:
        _state["colours"] = colours
    if team_name is not None:
        _state["team_name"] = team_name
    if goal_active is not None:
        _state["goal_active"] = goal_active
    if games is not None:
        _state["games"] = games
    if teams is not None:
        _state["teams"] = teams
    if api_remaining is not None:
        _state["api_remaining"] = api_remaining
    if sacn_connected is not None:
        _state["sacn_connected"] = sacn_connected


def _build_html():
    """Generate the status HTML page."""
    colours = _state["colours"]
    team = _state["team_name"] or "None"
    goal = _state["goal_active"]
    games = _state["games"]
    teams = _state["teams"]

    now_utc = datetime.now(timezone.utc)
    now_lv = now_utc.astimezone(_lv_tz)

    # Colour swatches HTML
    swatch_html = ""
    for i, rgb in enumerate(colours):
        hex_col = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        swatch_html += (
            f'<div style="display:inline-block;width:120px;height:120px;'
            f'background:{hex_col};border:2px solid #555;margin:8px;'
            f'border-radius:8px;vertical-align:top;text-align:center;'
            f'line-height:120px;">'
            f'<span style="color:#fff;text-shadow:1px 1px 2px #000;'
            f'font-size:14px;">{rgb[0]},{rgb[1]},{rgb[2]}</span></div>'
        )

    # Goal banner
    goal_html = ""
    if goal:
        goal_html = (
            '<div style="background:#ff4444;color:white;padding:16px;'
            'text-align:center;font-size:28px;font-weight:bold;'
            'border-radius:8px;margin:12px 0;animation:blink 0.5s infinite alternate;">'
            f'GOAL! {_flag_svg(team, width=48, height=32)} {team}</div>'
        )

    def _team_flag(name):
        """Generate an inline flag for a team in the schedule."""
        return _flag_svg(name, width=30, height=20)

    # Schedule table
    schedule_rows = ""
    date_order = {f"Jun {d}": d for d in range(11, 28)}
    sorted_games = sorted(games, key=lambda g: (
        date_order.get(g.get("date", ""), 99), g.get("time_utc", "99:99")
    ))

    current_date = None
    for g in sorted_games:
        d = g.get("date", "TBD")
        if d != current_date:
            current_date = d
            schedule_rows += (
                f'<tr><td colspan="4" style="background:#0066cc;color:white;'
                f'padding:6px 12px;font-weight:bold;font-size:16px;">{d}</td></tr>'
            )
        time_utc = g.get("time_utc", "")
        time_lv = ""
        if time_utc:
            try:
                utc_dt = datetime.strptime(f"2026 {d} {time_utc}", "%Y %b %d %H:%M")
                utc_dt = utc_dt.replace(tzinfo=timezone.utc)
                lv_dt = utc_dt.astimezone(_lv_tz)
                time_lv = lv_dt.strftime("%H:%M")
            except ValueError:
                pass
        time_display = f"{time_utc} UTC"
        if time_lv:
            time_display += f" / {time_lv} LV"
        venue = g.get("venue", "")
        group = g.get("group", "")
        home = g.get("home", "")
        away = g.get("away", "")
        schedule_rows += (
            f'<tr style="border-bottom:1px solid #333;">'
            f'<td style="padding:6px;color:#0088ff;font-family:monospace;">{time_display}</td>'
            f'<td style="padding:6px;color:#888;">{group}</td>'
            f'<td style="padding:6px;font-weight:bold;">'
            f'{_team_flag(home)} {home} vs {away} {_team_flag(away)}</td>'
            f'<td style="padding:6px;color:#888;font-size:13px;">{venue}</td></tr>'
        )

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="2">
<title>World Cup Colour - Live Status</title>
<style>
  @keyframes blink {{ 0% {{ opacity:1; }} 100% {{ opacity:0.4; }} }}
  body {{ background:#1a1a1a; color:#e0e0e0; font-family:'Segoe UI',sans-serif;
         margin:0; padding:20px; }}
  .container {{ max-width:1000px; margin:0 auto; }}
  h1 {{ color:#0066cc; margin:0; }}
  h2 {{ color:#0088ff; margin-top:24px; }}
  .header {{ display:flex; align-items:center; justify-content:space-between;
             border-bottom:2px solid #0066cc; padding-bottom:12px; margin-bottom:16px; }}
  .header h1 {{ border:none; margin:0; padding:0; }}
  .header img {{ height:60px; }}
  .clocks {{ display:flex; gap:40px; margin:16px 0; align-items:center; }}
  .clock {{ background:#222; padding:20px 32px; border-radius:8px; text-align:center; }}
  .clock-label {{ font-size:28px; font-weight:bold; }}
  .clock-time {{ font-size:56px; font-family:Consolas,monospace; font-weight:bold; }}
  .clock-date {{ font-size:28px; color:#888; font-family:Consolas,monospace; }}
  table {{ width:100%; border-collapse:collapse; margin-top:8px; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>World Cup Colour - Live Status</h1>
  <img src="data:image/png;base64,{_LOGO_B64}" alt="Diversified">
</div>

<div class="clocks">
  <div class="clock">
    <div class="clock-label" style="color:#0066cc;">UTC</div>
    <div class="clock-time" style="color:#0066cc;">{now_utc.strftime("%H:%M:%S")}</div>
    <div class="clock-date">{now_utc.strftime("%a %d %b %Y")}</div>
  </div>
  <div class="clock">
    <div class="clock-label" style="color:#cc6600;">Las Vegas</div>
    <div class="clock-time" style="color:#cc6600;">{now_lv.strftime("%H:%M:%S")}</div>
    <div class="clock-date">{now_lv.strftime("%a %d %b %Y")}</div>
  </div>
</div>

{goal_html}

<h2>Current Colours — {team}</h2>
<div style="display:flex;align-items:center;gap:24px;">
<div>{swatch_html}</div>
{_flag_svg(team, width=200, height=133)}
</div>

<h2>Schedule</h2>
<table>{schedule_rows}</table>

</div>
</body>
</html>"""
    return html


def _build_api_json():
    """Return state as JSON for API consumers."""
    return json.dumps({
        "colours": _state["colours"],
        "team_name": _state["team_name"],
        "goal_active": _state["goal_active"],
    }, indent=2)


def _build_testing_html():
    """Generate the testing/flags HTML page."""
    teams = _state["teams"]
    sorted_names = sorted(teams.keys())

    buttons_html = ""
    # Blackout button
    buttons_html += (
        '<form method="POST" action="/testing" style="display:inline-block;margin:4px;">'
        '<input type="hidden" name="action" value="send">'
        '<input type="hidden" name="team" value="BLACKOUT">'
        '<button type="submit" style="width:140px;height:100px;background:#1a1a1a;'
        'border:2px solid #555;border-radius:8px;cursor:pointer;padding:4px;'
        'vertical-align:top;">'
        '<div style="color:#fff;font-size:16px;font-weight:bold;">BLACKOUT</div>'
        '<div style="display:flex;gap:2px;margin-top:6px;">'
        '<div style="flex:1;height:24px;background:#000;border:1px solid #333;border-radius:3px;"></div>'
        '<div style="flex:1;height:24px;background:#000;border:1px solid #333;border-radius:3px;"></div>'
        '<div style="flex:1;height:24px;background:#000;border:1px solid #333;border-radius:3px;"></div>'
        '</div></button></form>'
    )

    active_team = _state["team_name"] or ""
    for name in sorted_names:
        team = teams[name]
        colours = team.get("colours", [[0, 0, 0], [0, 0, 0], [0, 0, 0]])
        swatches = ""
        for rgb in colours:
            hex_c = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            swatches += (
                f'<div style="flex:1;height:20px;background:{hex_c};'
                f'border:1px solid #333;border-radius:3px;"></div>'
            )
        # Escape name for HTML
        safe_name = name.replace('"', '&quot;').replace("'", "&#39;")
        first = name[0]
        rest = name[1:]
        trigger = team.get("trigger", {})
        ch = trigger.get("channel", "")
        ch_label = f' <span style="color:#888;font-size:10px;">({ch})</span>' if ch else ""
        is_active = name == active_team
        active_cls = " active-team" if is_active else ""
        flag = _flag_svg(name, width=54, height=36)
        buttons_html += (
            f'<form method="POST" action="/testing" style="display:inline-block;margin:4px;">'
            f'<input type="hidden" name="action" value="goal">'
            f'<input type="hidden" name="team" value="{safe_name}">'
            f'<button type="submit" class="{active_cls}" style="width:160px;height:100px;background:#2a2a2a;'
            f'border:2px solid #555;border-radius:8px;cursor:pointer;padding:4px;'
            f'vertical-align:top;">'
            f'<div style="color:#fff;font-size:11px;font-weight:bold;">'
            f'<span style="font-size:16px;">{first}</span>{rest}{ch_label}</div>'
            f'<div style="display:flex;align-items:center;gap:4px;margin-top:3px;">'
            f'{flag}'
            f'<div style="display:flex;flex:1;gap:2px;">{swatches}</div>'
            f'</div>'
            f'</button></form>'
        )

    # Current colours and status for display below flags
    colours = _state["colours"]
    team_name = _state["team_name"] or "None"
    goal_active = _state["goal_active"]
    api_remaining = _state["api_remaining"]
    sacn_connected = _state["sacn_connected"]

    cur_swatches = ""
    for rgb in colours:
        hex_c = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        cur_swatches += (
            f'<div style="display:inline-block;width:80px;height:80px;'
            f'background:{hex_c};border:2px solid #555;margin:4px;'
            f'border-radius:6px;text-align:center;line-height:80px;">'
            f'<span style="color:#fff;text-shadow:1px 1px 2px #000;'
            f'font-size:12px;">{rgb[0]:>3},{rgb[1]:>3},{rgb[2]:>3}</span></div>'
        )

    goal_banner = ""
    if goal_active:
        goal_banner = (
            f'<div style="background:#ff4444;color:white;padding:10px;'
            f'text-align:center;font-size:22px;font-weight:bold;'
            f'border-radius:6px;margin:8px 0;animation:blink 0.5s infinite alternate;">'
            f'GOAL! {_flag_svg(team_name, width=40, height=27)} {team_name}</div>'
        )

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="2">
<title>World Cup Colour - Testing</title>
<style>
  @keyframes blink {{ 0% {{ opacity:1; }} 100% {{ opacity:0.4; }} }}
  @keyframes glow {{ 0% {{ box-shadow:0 0 8px #ff4444,0 0 16px #ff4444; }} 100% {{ box-shadow:0 0 4px #ff8800,0 0 8px #ff8800; }} }}
  body {{ background:#1a1a1a; color:#e0e0e0; font-family:'Segoe UI',sans-serif;
         margin:0; padding:20px; }}
  .container {{ max-width:1200px; margin:0 auto; }}
  .header {{ display:flex; align-items:center; justify-content:space-between;
             border-bottom:2px solid #0066cc; padding-bottom:12px; margin-bottom:16px; }}
  h1 {{ color:#0066cc; margin:0; }}
  .status {{ background:#222; padding:12px 20px; border-radius:8px; margin-top:16px; }}
  .active-team {{ border:2px solid #ff4444 !important; animation:glow 0.6s infinite alternate; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>Testing - Remote Flags</h1>
  <img src="data:image/png;base64,{_LOGO_B64}" alt="Diversified" style="height:60px;">
</div>
<p style="color:#888;">Click a country to trigger a goal celebration.</p>
{buttons_html}

{goal_banner}

<div class="status">
  <div style="font-size:18px;font-weight:bold;margin-bottom:8px;">Current: {_flag_svg(team_name, width=40, height=27)} {team_name}</div>
  {cur_swatches}
</div>

<div class="status" style="margin-top:8px;display:flex;gap:24px;align-items:center;">
  <div>
    <span style="font-size:14px;color:#0088ff;font-weight:bold;">API Calls Remaining: </span>
    <span style="font-size:14px;font-family:Consolas,monospace;">{api_remaining if api_remaining else '--'}</span>
  </div>
  <div>
    <span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:{'#28a745' if sacn_connected else '#ff0000'};vertical-align:middle;margin-right:6px;"></span>
    <span style="font-size:14px;font-weight:bold;color:{'#28a745' if sacn_connected else '#ff0000'};">sACN {'Connected' if sacn_connected else 'Disconnected'}</span>
  </div>
</div>

</div>
</body>
</html>"""
    return html


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            body = _build_api_json().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/testing":
            if not _testing_enabled[0]:
                body = b"<html><body style='background:#1a1a1a;color:#ff4444;font-family:sans-serif;text-align:center;padding:80px;'><h1>Testing page is disabled</h1></body></html>"
                self.send_response(403)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = _build_testing_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = _build_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        if self.path == "/testing":
            if not _testing_enabled[0]:
                self.send_response(403)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            params = {}
            for pair in body.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[k] = unquote_plus(v)
            action = params.get("action", "")
            team_name = params.get("team", "")
            root = _callbacks.get("root")
            print(f"[WebServer] POST /testing action={action} team={team_name} "
                  f"root={'yes' if root else 'no'} "
                  f"goal_cb={'yes' if _callbacks.get('goal_pressed') else 'no'} "
                  f"team_found={'yes' if team_name in _state['teams'] else 'no'}")
            if team_name == "BLACKOUT":
                colours = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
                cb = _callbacks.get("set_colours")
                if cb and root:
                    root.after(0, lambda: cb(colours, "BLACKOUT"))
            elif team_name and team_name in _state["teams"]:
                colours = _state["teams"][team_name].get("colours",
                           [[0, 0, 0], [0, 0, 0], [0, 0, 0]])
                if action == "goal":
                    cb = _callbacks.get("goal_pressed")
                    if cb and root:
                        root.after(0, lambda c=colours, n=team_name: cb(c, n))
                else:
                    cb = _callbacks.get("set_colours")
                    if cb and root:
                        root.after(0, lambda c=colours, n=team_name: cb(c, n))
            # Redirect back to testing page
            self.send_response(303)
            self.send_header("Location", "/testing")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress console logging


_server_instance = [None]
_server_thread = [None]
_testing_enabled = [True]


def _start_server(port, status_label):
    """Start the HTTP server on the given port."""
    if _server_instance[0]:
        _stop_server(status_label)
    try:
        server = HTTPServer(("0.0.0.0", port), _Handler)
        _server_instance[0] = server
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        _server_thread[0] = t
        status_label.config(text=f"Running on port {port}", fg="#28a745")
    except OSError as e:
        status_label.config(text=f"Error: {e}", fg="red")


def _stop_server(status_label):
    """Stop the HTTP server."""
    if _server_instance[0]:
        _server_instance[0].shutdown()
        _server_instance[0] = None
        _server_thread[0] = None
    status_label.config(text="Stopped", fg="red")


def _get_local_ips():
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


def build_webserver_tab(notebook, port=8080, goal_pressed_cb=None,
                        set_colours_cb=None):
    """Build the Web Server tab. Returns update_state function."""
    tab = tk.Frame(notebook)
    notebook.add(tab, text="Web Server")

    _callbacks["root"] = notebook.winfo_toplevel()
    if goal_pressed_cb:
        _callbacks["goal_pressed"] = goal_pressed_cb
    if set_colours_cb:
        _callbacks["set_colours"] = set_colours_cb

    tk.Label(tab, text="Web Server",
             font=("Segoe UI", 14, "bold")).pack(pady=(20, 10))

    # Port config
    port_frame = tk.Frame(tab)
    port_frame.pack(pady=6)
    tk.Label(port_frame, text="Port:", font=("Segoe UI", 11)).pack(side="left", padx=(0, 8))
    port_var = tk.IntVar(value=port)
    tk.Entry(port_frame, textvariable=port_var, font=("Consolas", 11),
             width=8, justify="center").pack(side="left")

    # Status
    status_label = tk.Label(tab, text="Stopped", font=("Consolas", 10), fg="red")

    # Buttons
    btn_frame = tk.Frame(tab)
    btn_frame.pack(pady=15)

    def _start():
        _start_server(port_var.get(), status_label)

    def _stop():
        _stop_server(status_label)

    tk.Button(btn_frame, text="Start", font=("Segoe UI", 11, "bold"),
              bg="#28a745", fg="white", padx=20, pady=4,
              command=_start).pack(side="left", padx=8)

    tk.Button(btn_frame, text="Stop", font=("Segoe UI", 11),
              padx=20, pady=4, command=_stop).pack(side="left", padx=8)

    def _best_ip():
        ips = _get_local_ips()
        for ip in ips:
            if ip != "127.0.0.1":
                return ip
        return ips[0] if ips else "localhost"

    def _open_browser():
        webbrowser.open(f"http://{_best_ip()}:{port_var.get()}/")

    tk.Button(btn_frame, text="Open in Web Browser", font=("Segoe UI", 11, "bold"),
              bg="#0066cc", fg="white", padx=20, pady=4,
              command=_open_browser).pack(side="left", padx=8)

    def _open_testing():
        webbrowser.open(f"http://{_best_ip()}:{port_var.get()}/testing")

    tk.Button(btn_frame, text="Open Testing Page", font=("Segoe UI", 11, "bold"),
              bg="#ff4444", fg="white", padx=20, pady=4,
              command=_open_testing).pack(side="left", padx=8)

    status_label.pack(pady=(5, 10))

    # Testing page toggle
    testing_var = tk.BooleanVar(value=True)

    def _on_testing_toggle(*_args):
        _testing_enabled[0] = testing_var.get()

    testing_var.trace_add("write", _on_testing_toggle)
    tk.Checkbutton(tab, text="Enable Testing Page (/testing)",
                   font=("Segoe UI", 11), variable=testing_var,
                   onvalue=True, offvalue=False).pack(pady=(0, 10))

    # URLs
    url_frame = tk.LabelFrame(tab, text="Access URLs", font=("Segoe UI", 10),
                               padx=12, pady=8)
    url_frame.pack(padx=30, pady=(5, 10), fill="x")

    url_labels = []
    for ip in _get_local_ips():
        lbl = tk.Label(url_frame, text="", font=("Consolas", 10), fg="#0088ff",
                       anchor="w")
        lbl.pack(anchor="w")
        url_labels.append((lbl, ip))

    api_label = tk.Label(url_frame, text="", font=("Consolas", 9), fg="#888888",
                          anchor="w")
    api_label.pack(anchor="w", pady=(8, 0))

    def _update_urls(*_args):
        p = port_var.get()
        for lbl, ip in url_labels:
            lbl.config(text=f"http://{ip}:{p}/")
        api_label.config(text=f"JSON API: http://localhost:{p}/api/status    |    Testing: http://localhost:{p}/testing")

    port_var.trace_add("write", _update_urls)
    _update_urls()

    # Auto-start
    tab.after(500, _start)

    return update_state
