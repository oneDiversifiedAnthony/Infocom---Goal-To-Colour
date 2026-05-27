# World Cup Colour sACN

A Windows desktop application for controlling lighting via sACN/DMX during FIFA World Cup 2026 events. Built with Python and tkinter, it lets operators send team flag colours, trigger goal flash animations, and run multi-step colour chases to sACN-enabled lighting fixtures.

## Features

- **Colour Generator** - Three RGB colour slots with sliders, manual hex entry, and a random colour mode.
- **Groups** - Browse all World Cup 2026 groups (A-L) with team flag colours and match fixtures.
- **Schedule** - Chronological list of all fixtures with one-click "Send" to push team colours and "GOAL!" to trigger goal flash animations.
- **Flags** - Grid of all teams displayed as colour-coded tiles for quick colour selection.
- **Chases** - Multi-step colour animation pattern editor with adjustable timing. Save and load patterns from file.
- **Goal Animations** - 30-second flash sequences that dim and pulse team colours on goal events.
- **Country Editor** - Edit team flag colours and configure per-team sACN trigger channels.
- **sACN Config** - Configure destination IP (unicast/multicast), per-colour channel and universe mapping, and view local network addresses.

## Requirements

- Python 3.10+
- [sacn](https://pypi.org/project/sacn/) (sACN/E1.31 sender library)
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
assets/
  worldcup_teams.json    Team data and flag colours
  countries.json         Country metadata
  patterns.json          Saved chase patterns
  Version.json           Auto-incremented build version (YYYYMMDD.HHMM)
src/
  gui.py                 Main application window and tab layout
  sACN.py                sACN config tab and connection UI
  ScanMockDevice.py      sACN sender wrapper (unicast/multicast)
  tabs.py                Colour Generator tab
  goal.py                Goal flash animation controller
  groups.py              Groups tab
  schedule.py            Schedule tab
  flags.py               Flags grid tab
  chases.py              Chase pattern editor and controller
  country_editor.py      Team colour editor tab
  countries.py           Country/group browser window
  theme.py               Dark theme styling
  statusbar.py           Status bar with colour swatches and trigger info
```

## Versioning

The application version is stored in `assets/Version.json` and automatically updates to the current date and time (`YYYYMMDD.HHMM`) each time the application is launched. The version is displayed in the window title.
