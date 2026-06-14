# Code Audit: Monolithic Files, God Functions & Spaghetti Code

**Generated:** 2026-06-12
**Total Project:** 9,561 lines across 36 Python files

---

## The Sinners List

### Tier 1: The Worst Offenders

#### 1. `src/tabs/sounds.py` — 1,438 lines
**Sin:** Monolithic god-file. Does WAY too many things in one place.
- Waveform drawing, audio playback, level metering, keybindings, UI layout, file management
- `build_sounds_tab()` is a god function (~79 lines) that spawns dozens of nested closures
- `_clear_medits()` — 114 lines doing media editing cleanup
- `_poll_level()` — 87 lines of level meter polling with complex state
- `_draw_waveform()` — 80 lines of canvas drawing
- Heavy use of mutable closure state (`[None]` pattern) — 20+ instances
- Nested functions 3+ levels deep

**Prescription:** Split into modules:
- `sounds_ui.py` — tab layout and widget creation
- `sounds_waveform.py` — waveform drawing logic
- `sounds_playback.py` — audio playback and level metering
- `sounds_keybinds.py` — already partially done with `sound_keybinding.py`

---

#### 2. `src/tabs/webserver.py` — 998 lines
**Sin:** God-file combining HTTP server, HTML generation, JavaScript generation, and game logic.
- `_build_html()` — 165 lines generating a full HTML page with embedded CSS and JS
- `_team_flag()` — 141 lines nested inside `_build_html()` (function-within-a-function)
- `_build_testing_html()` — 87 lines, essentially a duplicate page builder
- Inline JavaScript strings spanning 100+ lines
- HTML/CSS/JS all embedded as Python string concatenation

**Prescription:**
- Extract HTML templates to separate `.html` files or a template engine
- Move JavaScript to `.js` files served statically
- Split into `webserver_routes.py`, `webserver_templates.py`
- `_team_flag()` should be a top-level function, not nested

---

#### 3. `src/tabs/api.py` — 844 lines
**Sin:** God-file managing API polling, rate limiting, auto-tuning, UI, phase detection, event logging, and score change detection.
- `_update_rate_limit()` — 92 lines of rate limit calculation + auto-tuning + UI updates
- `_detect_score_changes()` — 96 lines comparing old/new scores + logging events
- `_parse_live_scores()` — 60 lines parsing API response + updating multiple global stores
- Complex state machine: idle -> pregame -> playing -> break -> postgame
- 15+ mutable closure variables (`[None]` pattern)
- Scheduling logic interleaved with UI updates

**Prescription:**
- Extract `api_ratelimit.py` — token tracking, auto-tuning, prediction
- Extract `api_polling.py` — phase detection, scheduling, cycle management
- Extract `api_parser.py` — response parsing, score change detection, event logging
- Keep `api.py` as thin UI tab wiring only

---

#### 4. `src/tabs/timeline.py` — 511 lines
**Sin:** Contains the single longest function in the codebase.
- **`_update_clock()` — 210 lines** — the #1 god function. Rebuilds the entire timeline display every tick. Mixes data loading, time calculations, presentation merging, widget creation, and layout logic in one massive function.
- `_load_fixtures_from_schedule()` — 94 lines of file I/O + JSON parsing + data transformation
- `build_timeline_tab()` — 74 lines

**Prescription:**
- `_update_clock()` must be split:
  - `_load_timeline_data()` — gather fixtures + presentations
  - `_build_timeline_rows()` — create row data structures
  - `_render_timeline()` — paint widgets from row data
- `_load_fixtures_from_schedule()` should move to a shared data module

---

### Tier 2: Needs Attention

#### 5. `src/tabs/api_schedule.py` — 648 lines
**Sin:** Multiple 80-90 line functions doing too much.
- `_worker()` — 96 lines (API fetch + parse + filter + UI update in one thread worker)
- `_apply_filter()` — 89 lines of complex filtering logic
- `_parse_fixture()` — 89 lines of deeply nested JSON parsing
- `_populate_table()` — 57 lines

**Prescription:**
- `_parse_fixture()` should be a standalone utility (used by other modules too)
- `_worker()` should delegate to smaller functions
- Filter logic could be a class with clear predicates

---

#### 6. `src/gui.py` — 470 lines
**Sin:** Main GUI builder does too many things — tab creation, header updates, web server management, game header, sACN wiring.
- Not as bad as others, but growing. Web game list refresh, presentation tab wiring, and sACN setup all live here.

**Prescription:**
- Extract `web_game_manager.py` for web server game list refresh logic
- Keep `gui.py` focused on tab assembly only

---

#### 7. `src/scores.py` — 451 lines
**Sin:** Started as a simple score store, now manages scores, events, periods, state IDs, match clocks, time remaining, phase detection, and fixture registration.
- `get_match_clock()` — 51 lines with complex period/injury-time logic
- `get_poll_phase()` — 40 lines of phase state machine
- Too many global dicts: `_scores`, `_fixture_times`, `_events`, `_state_ids`, `_periods`

**Prescription:**
- Extract `match_state.py` — clock, periods, state tracking
- Extract `phase_detector.py` — polling phase logic
- Keep `scores.py` as pure score store

---

#### 8. `src/tabs/api_calllog.py` — 341 lines
**Sin:** `_draw_with_data()` is 156 lines of canvas drawing code — lots of coordinate math mixed with style logic.

**Prescription:**
- Extract marker drawing into helper functions
- Separate data transform (entries -> coordinates) from rendering

---

#### 9. `src/tabs/country_editor.py` — 259 lines
**Sin:** `_add_editor_row()` at 53 lines — builds complex UI rows with multiple widgets and callbacks.

**Prescription:** Minor. Could extract widget factory helpers but not critical.

---

#### 10. `src/tabs/chases.py` — 236 lines
**Sin:** Moderate size, manageable but has mixed concerns (UI + chase logic).

**Prescription:** Low priority. Fine for now.

---

### Tier 3: On the Watch List (approaching 200 lines)

| File | Lines | Notes |
|------|-------|-------|
| `src/tabs/flags.py` | 199 | Just under threshold, fine |
| `src/statusbar.py` | 174 | Clean, focused |
| `src/countries.py` | 174 | Data + file I/O, acceptable |
| `src/svg_renderer.py` | 174 | `_y()` at 67 lines — cryptic name |
| `src/tabs/presentations.py` | 161 | `build_presentations_tab()` at 108 lines — big but single-purpose |
| `src/sacn_connection.py` | 160 | Clean, protocol-focused |

---

## Anti-Patterns Found Across the Codebase

### 1. Mutable Closure State (`[None]` pattern)
**Where:** `sounds.py`, `api.py`, `api_calllog.py`, `timeline.py`, `webserver.py`
**Problem:** Using `last_mtime = [0]`, `dirty = [True]`, `drawing = [False]` etc. to work around Python's closure scoping. Creates hidden state that's hard to track and debug.
**Fix:** Use a simple state class or dataclass instead:
```python
# Before (scattered across closures):
dirty = [True]
last_mtime = [0]
cached = [None]

# After (one clear object):
@dataclass
class TabState:
    dirty: bool = True
    last_mtime: float = 0
    cached: Any = None
state = TabState()
```

### 2. Nested Function Spaghetti
**Where:** `sounds.py`, `api.py`, `webserver.py`
**Problem:** Functions defined inside functions defined inside functions. `build_sounds_tab()` defines 20+ nested functions that all share closure state. Makes it impossible to test individual pieces.
**Fix:** Move nested functions to module level or methods on a class. Pass state explicitly.

### 3. Inline HTML/JS/CSS
**Where:** `webserver.py`
**Problem:** 400+ lines of HTML/JavaScript/CSS as Python string concatenation. No syntax highlighting, no linting, error-prone.
**Fix:** Use template files or at minimum `textwrap.dedent` with clearly separated blocks.

### 4. God Functions That Build + Update + Render
**Where:** `timeline.py::_update_clock()`, `sounds.py::build_sounds_tab()`, `api.py::build_api_tab()`
**Problem:** Single functions that create widgets, load data, compute values, and render output. Violates single responsibility.
**Fix:** Separate data preparation from rendering. Build once, update incrementally.

---

## Summary Stats

| Metric | Count |
|--------|-------|
| Files over 200 lines | 13 |
| Files over 500 lines | 5 |
| Files over 1000 lines | 1 |
| Functions over 50 lines | 24 |
| Functions over 100 lines | 6 |
| Functions over 200 lines | 1 |
| Mutable closure vars (`[None]`) | ~50+ instances |

## Top 5 Functions to Refactor First

1. **`timeline.py::_update_clock()`** — 210 lines. Split into load/build/render.
2. **`webserver.py::_build_html()`** — 165 lines + 141-line nested function. Extract templates.
3. **`api_calllog.py::_draw_with_data()`** — 156 lines. Separate data transform from rendering.
4. **`sounds.py::_clear_medits()`** — 114 lines. Break into discrete cleanup steps.
5. **`api.py::_detect_score_changes()`** — 96 lines. Extract comparison logic from logging.
