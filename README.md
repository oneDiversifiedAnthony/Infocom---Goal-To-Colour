# World Cup Colour sACN

A Windows desktop application for controlling lighting via sACN/DMX during FIFA World Cup 2026 events. Built with Python and tkinter, it lets operators send team flag colours, trigger goal flash animations with national anthems, run colour chases, and serve a live status web page for remote monitoring and testing.

## Features

- **Colour Generator** - Three RGB colour slots with sliders, manual hex entry, and a random colour mode.
- **Timeline** - Chronological schedule with UTC and Las Vegas time display, live clocks, and one-click "Send" / "GOAL!" buttons per fixture.
- **Flags** - Grid of all teams displayed as colour-coded tiles for quick colour selection and goal triggering.
- **Chases** - Multi-step colour animation pattern editor with adjustable timing. Save and load patterns from file.
- **Goal Animations** - Flash sequences that pulse team colours on goal events with a configurable timeout and progress bar. Blackout on expiry.
- **Country Editor** - Edit team flag colours, configure per-team sACN trigger channels, view anthem file paths, and audition anthems with a play button. Fixed header row for easy scrolling.
- **sACN Config** - Configure destination IP (unicast/multicast), per-colour channel and universe mapping, and view local network addresses. Auto-connects on launch.
- **API Tab** - Fetch live sports data from SportMonks API with auto-refresh (default 1400ms), rate limit tracking with colour-coded progress bar, and call log graphing (today's data only).
- **Sounds** - Multi-channel sound player with waveform visualization, zoom, cue points, gain control, pre/post fader VU meters, half-speed playback, fade in/out, loop, and F-key bindings.
- **National Anthems** - Dedicated anthem channel with volume control, L/R VU meters, elapsed/remaining time display, and fade out. Auto-plays country anthem on goal. Crossfades between anthems over 2 seconds.
- **Web Server** - Built-in HTTP server with live status page (colour swatches, game schedule, UTC/Las Vegas clocks) and a remote testing page for triggering goals from any device. Testing page can be toggled on/off.
- **Status Bar** - Live colour output swatches with RGB overlay, trigger countdown progress bar, sACN connection indicator, and API rate limit display.

## Requirements

- Python 3.10+
- [sacn](https://pypi.org/project/sacn/) (sACN/E1.31 sender library)
- [pygame-ce](https://pypi.org/project/pygame-ce/) (sound playback and waveform rendering)
- tkinter (included with standard Python on Windows)

## Usage

```bash
python main.py
```

## Building an Executable

```bash
python compiletoexe.py
```

This uses PyInstaller to produce a single `.exe` in the `.claude/` directory, bundling all JSON assets. The executable is timestamped with the build date.

## Project Structure

```
main.py                  Entry point
compiletoexe.py          PyInstaller build script
youtube_mp3.py           YouTube to MP3 downloader utility
assets/
  worldcup_teams.json    Groups, games, and schedule data
  countries.json         Team colours, triggers, and anthem file references
  patterns.json          Saved chase patterns
  Version.json           Auto-incremented build version (YYYYMMDD.HHMM)
Sound Files/
  Anthems/               EBU R128 normalized national anthem MP3s
  Anthems - RAW/         Original unnormalized anthem MP3s
  *.mp3, *.wav, *.ogg    Sound effects for the sound player
  medits.json            Cue points, gain, and event bindings per sound file
src/
  gui.py                 Main application window and tab orchestration
  goal.py                Goal flash animation controller
  theme.py               Dark theme styling constants
  statusbar.py           Status bar with swatches, triggers, sACN, and API info
  sacn_connection.py     sACN sender wrapper (unicast/multicast)
  constants.py           Shared constants (universes, timing, sizes)
  tabs/
    sacn.py              sACN configuration tab
    generator.py         Colour Generator tab
    timeline.py          Timeline/schedule tab with UTC and Las Vegas clocks
    flags.py             Flags grid tab
    chases.py            Chase pattern editor and controller
    country_editor.py    Team colour editor with anthem preview
    api.py               API fetch tab with auto-refresh and rate limiting
    api_raw.py           API raw JSON sub-tab
    api_tree.py          API tree view sub-tab
    api_table.py         API table sub-tab
    api_changes.py       API changes detection sub-tab
    api_calllog.py       API call log graph sub-tab (today only)
    sounds.py            Sound player with waveform, VU meters, anthem channel
    sound_keybinding.py  F-key bindings for sound player
    webserver.py         Built-in HTTP server with status and testing pages
    readme_tab.py        README.md renderer tab
```

## Versioning

The application version is stored in `assets/Version.json` and automatically updates to the current date and time (`YYYYMMDD.HHMM`) each time the application is launched. The version is displayed in the window title.
