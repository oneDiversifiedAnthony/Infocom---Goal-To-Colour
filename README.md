# World Cup Colour sACN

A Windows desktop application for controlling lighting via sACN/DMX during FIFA World Cup 2026 events. Built with Python and tkinter, it lets operators send team flag colours, trigger goal flash animations with national anthems, run colour chases, and serve a live status web page for remote monitoring and testing.

Developed by **oneDiversified** for the 2026 FIFA World Cup (United States, Canada, Mexico).

---

## Quick Start

### Option 1 -- Launcher (Recommended)

Double-click **`Launch.bat`**. This will:

1. Prompt for Administrator elevation (UAC)
2. Set all network adapters (Wi-Fi, Ethernet) to **Private** profile
3. Create Windows Firewall rules for sACN, the web server, ping, and API access
4. Enable Network Discovery
5. Launch `main.py` in a **watchdog loop** that auto-restarts the app on crash

The app will keep running until you close it cleanly (exit code 0) or press Ctrl+C in the PowerShell window.

### Option 2 -- Direct

```bash
python main.py
```

Dependencies are auto-installed on first run if missing.

---

## Features

### Timeline

Chronological view of all World Cup fixtures loaded from the cached SportMonks schedule data. Displays each match with:

- **Dual timezone** -- Las Vegas (primary) and UTC kick-off times
- **Date headers** grouped by Las Vegas date
- **Colour swatches** for home and away team flag colours
- **Live indicators** -- green dot and green text when a match is in progress
- **Live scores** -- updated from the API in real time, also re-read from schedule files every 5 minutes for completed games
- **Match clock** -- shows period time (e.g. `45+2:30` for injury time), half-time, full-time, etc. from API period data
- **Venue names** resolved from `assets/venues.json`
- **Group labels** (A-L) for group stage fixtures
- **Game ID** for each fixture
- **Next game countdown** with hours:minutes:seconds and match name
- **Live clocks** for Las Vegas, Toronto, and UTC in the right panel

Scores are sourced exclusively from:
- The **SportMonks livescores API** (real-time during matches)
- The **Schedule JSON files** (ground truth for completed games, re-read every 5 minutes)

UI actions (flags, GOAL buttons) trigger celebrations only -- they never modify scores.

### Flags

Full-screen grid of all 48 teams displayed as colour-coded tiles with country flags (SVG rendered). Clicking any tile triggers the goal celebration sequence (flash, sound, DMX trigger, anthem) and sends that team's colours to sACN output. A **BLACKOUT** tile in position (0,0) provides emergency access to kill all output.

- 7x7 grid layout that scales with window size
- Drop-cap style country names for quick scanning
- Yellow highlight border on the active team

### Colour Generator

Three RGB colour slots with:
- Individual R/G/B sliders (0-255)
- Hex colour entry
- Large preview swatches (100x100)
- Random colour cycling mode (3-second interval)
- Manual override of any slot

### Goal Animations

When a goal is detected (via API) or manually triggered (via UI), the system:

1. Flashes the scoring team's colours at 400ms intervals
2. Plays the configured goal sound effect
3. Plays the team's national anthem with 2-second crossfade
4. Sends a DMX trigger pulse on the team's configured trigger channel/universe
5. Displays a 30-second countdown progress bar
6. Blacks out all output when the celebration ends

### Chases

Multi-step colour animation pattern editor:
- Add/remove/reorder colour steps
- Adjustable timing per step
- Save and load patterns from `assets/patterns.json`
- Live preview on sACN output

### Country Editor

Edit team configuration with a scrollable table:
- Flag colours (three RGB slots per team)
- sACN trigger channel and universe assignment
- Anthem file path reference
- Audition anthems with inline play button
- Fixed header row for easy scrolling

### sACN Configuration

Found under **Settings > sACN**:
- Destination IP (blank = multicast, or enter IP for unicast)
- Per-colour DMX channel and universe mapping (3 colours x R/G/B/Universe)
- Local network address display
- Auto-connects on launch
- Universe 1 for colour data, Universe 2 for trigger channels (configurable)

### API Livescore

Fetches live match data from the **SportMonks API**:
- Configurable URL with `{{api_token}}` placeholder
- API token field (loaded from `.env` file or environment variable `SPORTMONKS_API_TOKEN`)
- **Manual fetch** (Get button) or **auto-refresh** (configurable interval, default 1500ms)
- Auto-refresh countdown progress bar
- **Rate limit tracking** -- colour-coded progress bar (green > yellow > red), flashing when below 10%
- Rate limit reset countdown and max speed calculation
- **Score change detection** -- compares each API response to the previous, logs changes to `Call Log/changes.log`, and auto-triggers goal celebrations
- **State tracking** -- stores match state_id, period data, and events per fixture
- Link to SportMonks dashboard

Sub-tabs:
- **Raw** -- full JSON response
- **Tree** -- expandable tree view of the response
- **Table** -- parsed fixture table
- **Changes** -- detected score changes
- **Call Log** -- API call rate graph (current session)

### API Schedule

Fetches team schedules from SportMonks and caches them locally:
- Fetches only teams playing **today or tomorrow** to conserve API tokens
- Saves each team's schedule to `assets/Schedule/{team_name}.json`
- Fetches and caches venue details to `assets/venues.json`
- **Auto-pulls every 15 minutes** (at :00, :15, :30, :45)
- Sortable, filterable fixture table with date range controls
- Green highlighting for recently fetched teams

### Sounds

Multi-channel sound player found under the **Sounds** tab:
- Scans `Sound Files/` folder for `.mp3`, `.wav`, `.ogg` files
- **Waveform visualization** with zoom (mouse wheel), pan, and hover position display
- **Cue points** -- set cue-in and cue-out with `[` and `]` keys
- **Gain control** per channel
- **Pre-fader and post-fader VU meters** with peak hold
- **Half-speed playback** button
- **Fade in/out** controls
- **Loop** toggle
- **F-key bindings** (F1-F12) for quick triggering
- **Event binding** -- assign each sound to trigger on "Goal" or "Goal by Team" (with team selector)
- **Active card** selection for keyboard control

#### PreGame Auto-Trigger

Place a file called **`PreGame.mp3`** in the `Sound Files/` folder. It will automatically play **2 minutes before kick-off** for each game. The trigger fires once per fixture and resets for the next game.

### National Anthems

Dedicated anthem playback channel:
- Auto-plays the scoring team's anthem on goal events
- **2-second crossfade** between anthems
- Independent volume control
- L/R VU meters
- Elapsed and remaining time display
- Fade out button
- Anthem files stored in `Sound Files/Anthems/` (EBU R128 normalized)

### Web Server

Found under **Settings > Web Server**:
- Built-in HTTP server on configurable port (default **8080**)
- **Status page** (`/`) -- live colour swatches, current team, game schedule with scores, UTC/Las Vegas/Toronto clocks, auto-refreshes every 2 seconds
- **Testing page** (`/testing`) -- grid of all team flags for remotely triggering goals from any device on the network. Can be toggled on/off via checkbox
- Displays all local IP addresses for easy access from other devices
- Open in browser button

### Status Bar

Persistent bottom bar showing:
- Three live colour output swatches with RGB value overlay
- Current team name
- Trigger channel indicator with 30-second countdown progress bar
- sACN connection status (green/red dot)
- API rate limit display

### Game Header

Persistent top bar showing:
- **During a live match**: "LIVE" indicator with score and match clock in green
- **Before next game**: countdown timer (HH:MM:SS) with team names in yellow

---

## Launcher and Firewall

### Launch.bat / Launch.ps1

The launcher script handles everything needed to run the application on a fresh Windows machine:

1. **Self-elevates** to Administrator via UAC prompt
2. **Network profile** -- switches all connected adapters (Wi-Fi, Ethernet) from Public to Private, which is required for inbound connections
3. **Firewall rules** (created once, idempotent on re-run):

| Rule | Protocol | Port | Direction | Purpose |
|---|---|---|---|---|
| sACN E1.31 Out | UDP | 5568 | Outbound | Multicast/unicast DMX output |
| sACN E1.31 In | UDP | 5568 | Inbound | sACN responses |
| Web Server In | TCP | 8080 | Inbound | Live status web page |
| SportMonks API Out | TCP | 443 | Outbound | Livescore API calls |
| Allow Ping (ICMPv4) | ICMPv4 | -- | Inbound | Allows other machines to ping this computer |

4. **Network Discovery** -- enables the built-in Windows Network Discovery firewall rule group
5. **Watchdog loop** -- starts `main.py` and monitors it:
   - On crash (non-zero exit code): waits 5 seconds, then restarts
   - On clean exit (code 0, user closed window): stops
   - Logs crash count and timestamps to the console

All firewall rules are prefixed `WorldCupColour` for easy identification in Windows Firewall.

### Setup-Firewall.ps1

Standalone firewall setup script (same rules as above) for running separately without the watchdog. Requires `Run as Administrator`.

---

## Requirements

- **Python 3.10+**
- **Windows 10/11** (uses tkinter, Windows Firewall, and Windows-specific networking)
- Dependencies (auto-installed on first run):
  - [sacn](https://pypi.org/project/sacn/) -- sACN/E1.31 sender library
  - [pygame-ce](https://pypi.org/project/pygame-ce/) -- sound playback and waveform rendering
  - [Pillow](https://pypi.org/project/Pillow/) -- image processing for flag SVG rendering

### Network Requirements

| Service | Protocol | Port | Notes |
|---|---|---|---|
| sACN / E1.31 | UDP | 5568 | Multicast group `239.255.0.x` or unicast to a specific IP |
| Web Server | TCP | 8080 | Configurable in the Web Server tab |
| SportMonks API | TCP | 443 | Outbound HTTPS, requires API token |

---

## Configuration

### config.ini

```ini
[paths]
sound_files = Sound Files
call_log = Call Log
```

### .env

```
SPORTMONKS_API_TOKEN=your_token_here
```

The API token can also be entered directly in the API tab or set as an environment variable.

### assets/countries.json

Team database containing:
- Team names and flag colours (3 RGB triplets)
- SportMonks team IDs for API matching
- sACN trigger channel/universe assignments
- Anthem file references

### assets/worldcup_teams.json

Group stage structure with groups, games, and match dates.

---

## Building an Executable

```bash
python compiletoexe.py
```

Uses PyInstaller to produce a single `.exe` in the `Candidates/build/` directory, bundling all JSON assets and sound files. The executable is timestamped with the build date.

---

## Project Structure

```
Launch.bat               Double-click to run (firewall + watchdog + app)
Launch.ps1               PowerShell launcher (self-elevating)
Setup-Firewall.ps1       Standalone firewall setup
main.py                  Python entry point
compiletoexe.py          PyInstaller build script
config.ini               Path configuration

assets/
  worldcup_teams.json    Groups, games, and schedule data
  countries.json         Team colours, triggers, anthem refs, SportMonks IDs
  patterns.json          Saved chase patterns
  venues.json            Venue names/cities (auto-fetched from API)
  Version.json           Auto-incremented build version (YYYYMMDD.HHMM)
  Schedule/              Cached SportMonks schedule JSONs (one per team)

Sound Files/
  Anthems/               EBU R128 normalized national anthem MP3s
  Anthems - RAW/         Original unnormalized anthem MP3s
  PreGame.mp3            Auto-triggered 2 min before each game
  *.mp3, *.wav, *.ogg    Sound effects for the sound player
  medits.json            Cue points, gain, and event bindings per sound file

Call Log/                API call logs and score change logs

src/
  gui.py                 Main App window and tab orchestration
  goal.py                Goal flash animation controller
  scores.py              Shared score tracking (API + schedule as sources)
  theme.py               Dark theme styling constants
  statusbar.py           Status bar with swatches, triggers, sACN, API info
  sacn_connection.py     sACN sender wrapper (unicast/multicast, CID-based)
  constants.py           Shared constants (universes, timing, sizes)
  config.py              Config.ini loader
  countries.py           Reusable country picker window
  colour_generator.py    Colour generator logic
  DependancyCheck.py     Auto-installs missing pip packages on first run
  svg_renderer.py        SVG to tkinter image renderer for flags

  tabs/
    timeline.py          Timeline tab (chronological fixtures, live scores, clocks)
    flags.py             Flags grid tab (7x7 country tiles)
    generator.py         Colour Generator tab
    chases.py            Chase pattern editor and controller
    chase_patterns.py    Chase pattern definitions
    chase_controller.py  Chase animation engine
    country_editor.py    Team colour/trigger editor with anthem preview
    schedule.py          Schedule tab (legacy group-based view)
    groups.py            Groups tab
    sacn.py              sACN configuration tab
    api.py               API Livescore tab (fetch, auto-refresh, rate limiting)
    api_raw.py           Raw JSON sub-tab
    api_tree.py          Tree view sub-tab
    api_table.py         Table sub-tab
    api_changes.py       Score change detection sub-tab
    api_calllog.py       Call log graph sub-tab
    api_schedule.py      Schedule fetch sub-tab (today/tomorrow teams)
    sounds.py            Sound player (waveform, VU, cue points, events)
    sound_keybinding.py  F-key bindings for sound player
    webserver.py         HTTP server (status page + testing page)
    readme_tab.py        In-app README renderer tab
```

---

## Versioning

The application version is stored in `assets/Version.json` and automatically updates to the current date and time (`YYYYMMDD.HHMM`) each time the application is launched. The version is displayed in the window title bar.

---

## Score Tracking

Scores displayed in the Timeline and Web Server come from two authoritative sources only:

1. **SportMonks Livescores API** -- real-time updates during in-play matches via the `/livescores/inplay` endpoint. Scores, match state, period data, and events are pushed into the shared scores module on every API poll.

2. **Schedule JSON files** -- cached per-team schedule data re-fetched every 15 minutes from the SportMonks schedules endpoint. The Timeline re-reads these files every 5 minutes to pick up final scores from completed matches.

UI interactions (clicking flags, pressing GOAL buttons, the web testing page) trigger **celebrations only** (flash animation, sound, DMX trigger, anthem). They never modify the score data.

---

## License

Copyright (c) 2026 oneDiversified. All rights reserved.

This software is proprietary and confidential. Unauthorized copying, distribution, modification, or disclosure is strictly prohibited.
