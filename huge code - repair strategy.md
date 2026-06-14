# Repair Strategy: Step-by-Step Improvement Plan

**Derived from:** `huge code.md` audit (2026-06-12)
**Approach:** Incremental. Each step is a standalone commit that doesn't break anything.
**Rule:** No step should require more than one file to change at a time where possible. Refactors that touch multiple files are broken into sub-steps.

---

## Guiding Principles

1. **Don't rewrite — extract.** Move code out of big files into focused modules. Keep existing function signatures as wrappers initially.
2. **Test after every step.** Launch the app, confirm nothing is broken. This is a live production system for InfoComm.
3. **Dependency direction matters.** New extracted modules should be imported by the old file, not the other way around. No circular imports.
4. **State flows downhill.** `scores.py` is the shared state hub. Everything reads from it. Only `api.py` and `gui.py` write to it. That's fine — just make it cleaner.

---

## Phase 1: Quick Wins (Low Risk, High Clarity)

These changes improve readability without changing any logic. Do them first to build momentum.

### Step 1.1: Replace `[None]` mutable closure pattern with state dataclasses

**Files:** `api.py`, `api_calllog.py`, `timeline.py`, `sounds.py`, `webserver.py`
**What:** Each file that uses the `dirty = [True]`, `last_mtime = [0]` pattern gets a `@dataclass` at the top of the file to hold that tab's mutable state.
**How:**
```python
# Before (scattered throughout build function):
dirty = [True]
last_mtime = [0]
cached = [None]
drawing = [False]

# After (one clear object, defined at module level):
@dataclass
class _CallLogState:
    dirty: bool = True
    last_mtime: float = 0
    cached: Any = None
    drawing: bool = False

# Inside build function:
st = _CallLogState()
# Then use st.dirty, st.last_mtime, etc.
```
**Order:** Do one file at a time. Start with `api_calllog.py` (simplest, only 4 vars), then `timeline.py`, then `api.py`, then `webserver.py`, then `sounds.py` (most complex).
**Risk:** Low. Purely mechanical replacement.

### Step 1.2: Fix private dict access in `gui.py`

**File:** `gui.py`
**What:** `gui.py` directly accesses `scores._scores` (the private dict). Replace with a proper public function call.
**How:** Add a `set_score()` or `goal_scored()` call in `scores.py` if one doesn't already exist, then use it from `gui.py`.
**Risk:** Low. Single call site.

### Step 1.3: Rename `svg_renderer.py::_y()` to something meaningful

**File:** `svg_renderer.py`
**What:** The function `_y()` (67 lines) has a cryptic single-letter name. Rename to `_render_svg_to_photoimage()` or whatever it actually does.
**Risk:** Low. Internal function, grep for all callers.

---

## Phase 2: Break Up God Functions (Medium Risk, High Impact)

Each god function gets split into 2-4 smaller functions within the same file. No new files yet — just internal restructuring.

### Step 2.1: Split `timeline.py::_update_clock()` (210 lines)

**The #1 offender.** This single function loads data, computes times, merges presentations, creates widgets, and paints the display.

**Split into:**
| New Function | Responsibility | ~Lines |
|---|---|---|
| `_gather_timeline_entries()` | Load fixtures from schedule files + presentations JSON, merge and sort by time | ~60 |
| `_build_row_data(entries)` | For each entry, compute display strings (time, teams, score, status, colours) | ~50 |
| `_render_rows(container, rows)` | Create/update tkinter widgets from row data | ~80 |
| `_update_clock()` | Orchestrator — calls the above three, updates header clock | ~20 |

**Sub-steps:**
1. Extract `_gather_timeline_entries()` — move the file-reading and presentation-loading code out. `_update_clock()` calls it.
2. Extract `_build_row_data()` — move the per-entry logic (time formatting, live detection, colour picking) out.
3. Extract `_render_rows()` — move the widget creation loop out.
4. Clean up `_update_clock()` to be a thin orchestrator.

**Test after each sub-step.**

### Step 2.2: Split `webserver.py::_build_html()` (165 lines + 141-line nested function)

**Split into:**
| New Function | Responsibility | ~Lines |
|---|---|---|
| `_build_head_html()` | `<head>`, CSS, meta tags | ~30 |
| `_build_countdown_html()` | Countdown area for next game | ~25 |
| `_build_live_game_html(fid, info)` | Single live game card with score, events, clock | ~50 |
| `_build_schedule_html(fixtures)` | Full schedule table | ~40 |
| `_build_js()` | All JavaScript (fetch loop, clocks) | ~40 |
| `_team_flag_html(team, score, side)` | **Promote from nested to module-level** | ~40 (trimmed) |

**Critical:** Move `_team_flag()` out of the nested scope first. It's 141 lines hidden inside another function.

### Step 2.3: Split `api_calllog.py::_draw_with_data()` (156 lines)

**Split into:**
| New Function | Responsibility | ~Lines |
|---|---|---|
| `_compute_graph_coords(entries, w, h)` | Convert entries to (x, y) pixel coordinates | ~25 |
| `_draw_grid(canvas, coords, max_t, min_t)` | Grid lines and Y-axis labels | ~15 |
| `_draw_line_graph(canvas, coords, colours)` | The actual line + fill + dots | ~30 |
| `_draw_markers(canvas, markers, coords, n)` | State change / goal / event vertical lines | ~50 |
| `_draw_legend(canvas, w, margin_t)` | Legend in top-right corner | ~15 |

### Step 2.4: Split `api.py::_detect_score_changes()` (96 lines)

**Split into:**
| New Function | Responsibility | ~Lines |
|---|---|---|
| `_compare_scores(old_scores, new_data)` | Pure comparison, returns list of changes | ~30 |
| `_log_changes(changes)` | Write to call log file | ~20 |
| `_trigger_goal_actions(changes)` | Fire goal sound/flash/web callbacks | ~20 |
| `_detect_score_changes()` | Orchestrator | ~15 |

### Step 2.5: Split `api.py::_update_rate_limit()` (92 lines)

**Split into:**
| New Function | Responsibility | ~Lines |
|---|---|---|
| `_calculate_token_prediction(tokens, reset_at, game_rate)` | Pure math: predict tokens at reset | ~20 |
| `_auto_tune_game_rate(tokens, reset_at, current_rate)` | Compute new rate, apply smoothing | ~25 |
| `_update_rate_limit_ui(tokens, reset_at, prediction)` | Update labels and progress bar | ~30 |

---

## Phase 3: Extract New Modules (Medium Risk, Structural Change)

Now we move code into new files. Each extraction creates one new file and updates imports in the old file.

### Step 3.1: Extract `src/match_state.py` from `scores.py`

**What moves out:**
- `_state_ids` dict and `update_state()`, `STATE_NAMES`
- `_periods` dict and `update_periods()`, `get_current_period()`, `get_period_info()`
- `get_match_clock()`, `get_time_remaining()`, `get_match_minute()`, `get_match_minute_display()`

**What stays in `scores.py`:**
- `_scores` dict — score storage
- `register_fixtures()`, `goal_scored()`, `get_score()`, `get_score_display()`
- `update_from_live()`, `get_all_scores()`, `get_live_games()`
- `_events` dict (or move to match_state too)

**Backward compatibility:** `scores.py` re-exports everything from `match_state.py` so existing callers don't break. Remove re-exports later once callers are updated.

### Step 3.2: Extract `src/poll_phase.py` from `scores.py`

**What moves out:**
- `_PREGAME_STATE_IDS`, `_PLAYING_STATE_IDS`, `_BREAK_STATE_IDS`, `_FINISHED_STATE_IDS`
- `PHASE_*` constants
- `get_poll_phase()`, `get_next_game_today()`
- `POSTGAME_COOLDOWN_SEC`

**Dependencies:** Needs to import from `match_state.py` for `_state_ids` access. Provide a `get_state_ids()` accessor.

### Step 3.3: Extract `src/tabs/api_ratelimit.py` from `api.py`

**What moves out:**
- Token prediction math
- Auto-tune game rate logic
- Rate limit floor calculations
- `TOKEN_RESERVE`, `RATE_SMOOTHING` constants

**Interface:** Pure functions that take current tokens, reset time, game rate and return new values. No UI code.

### Step 3.4: Extract `src/tabs/webserver_templates.py` from `webserver.py`

**What moves out:**
- `_build_head_html()`
- `_build_js()`
- All HTML generation functions from Step 2.2
- CSS strings

**What stays in `webserver.py`:**
- HTTP server setup, request handler
- Route dispatch
- State management, game list refresh

### Step 3.5: Extract `src/tabs/sounds_waveform.py` from `sounds.py`

**What moves out:**
- `_draw_waveform()` and related canvas drawing code
- Waveform data computation

**What stays:**
- Tab layout, audio playback, level metering, keybinding wiring

---

## Phase 4: Reduce Coupling (Lower Risk Once Phase 3 Done)

### Step 4.1: Thread safety for `scores.py`

**What:** Add a `threading.Lock` around `_scores` dict mutations. Currently `api.py` writes from a background thread callback while `webserver.py` reads from the HTTP handler thread.
**How:** Simple lock acquire/release in `update_from_live()`, `register_fixtures()`, `get_all_scores()`.
**Risk:** Low — lock contention is negligible at these call rates.

### Step 4.2: Consolidate `webserver.py` parallel state

**What:** `webserver.py` maintains its own `_state` dict with game info that partially duplicates `scores.py`. Migrate to reading directly from `scores.py` (which it mostly already does).
**Risk:** Medium. Need to verify all web endpoints still work.

### Step 4.3: Event bus for score changes (optional, nice-to-have)

**What:** Instead of `api.py` directly calling `gui.py` callbacks for goals, use a simple observer/callback registry in `scores.py`.
**How:**
```python
# scores.py
_listeners = []
def on_score_change(callback):
    _listeners.append(callback)
def _notify(fixture_id, change_type):
    for cb in _listeners:
        cb(fixture_id, change_type)
```
**Risk:** Low but touches multiple files. Do this last.

---

## Phase 5: Structural Cleanup (Polish)

### Step 5.1: Move `_load_fixtures_from_schedule()` to shared module

**Currently in:** `timeline.py` (94 lines)
**Also needed by:** `gui.py` (for web game list), `webserver.py`
**Move to:** `src/schedule_loader.py`
**Benefit:** Single source of truth for reading schedule JSON files.

### Step 5.2: Extract inline JavaScript from `webserver.py`

**What:** The ~100+ lines of JavaScript (fetch loop, DOM update, clocks) should live in `assets/web/main.js` served as a static file.
**How:** Add a route in the HTTP handler for `/static/main.js`. Replace inline `<script>` with `<script src="/static/main.js">`.
**Benefit:** JS gets proper syntax highlighting, linting, easier debugging.

### Step 5.3: Audit and trim `sounds.py`

After Phase 1 (dataclass state) and Phase 3.5 (waveform extraction), `sounds.py` should be ~1000 lines. Further splits:
- `sounds_playback.py` — audio engine, level polling
- `sounds_ui.py` — widget layout, button handlers
- `sounds.py` — thin `build_sounds_tab()` that wires the pieces together

---

## Execution Order & Priority

| Priority | Step | Impact | Risk | Est. Effort |
|----------|------|--------|------|-------------|
| **NOW** | 1.1 Dataclass state | High clarity | Low | 1-2 hours |
| **NOW** | 1.2 Fix private dict access | Correctness | Low | 15 min |
| **NOW** | 2.1 Split `_update_clock()` | Biggest win | Medium | 1 hour |
| **SOON** | 2.2 Split `_build_html()` | Major clarity | Medium | 1 hour |
| **SOON** | 2.3 Split `_draw_with_data()` | Clean graphs | Low | 30 min |
| **SOON** | 2.4-2.5 Split api.py functions | Maintainability | Medium | 1 hour |
| **LATER** | 3.1-3.2 Extract from scores.py | Architecture | Medium | 1-2 hours |
| **LATER** | 3.3 Extract api_ratelimit.py | Clean API tab | Low | 30 min |
| **LATER** | 3.4 Extract webserver templates | Clean web | Medium | 1 hour |
| **LATER** | 3.5 Extract sounds waveform | Start sounds cleanup | Low | 30 min |
| **OPTIONAL** | 4.1-4.3 Coupling reduction | Robustness | Medium | 2 hours |
| **OPTIONAL** | 5.1-5.3 Polish | Long-term health | Low | 2 hours |
| **NOW** | 6.1 Fix Python file casing/typo | Professionalism | Low | 15 min |
| **SOON** | 6.2 Fix folder names (spaces) | Path safety | Medium | 1 hour |
| **SOON** | 6.3 Fix JSON asset casing | Consistency | Low | 30 min |
| **SOON** | 6.4 Fix script casing | Consistency | Low | 15 min |
| **SOON** | 6.5 Move misplaced files | Organization | Low | 15 min |
| **LATER** | 6.6 Rename ambiguous Python files | Clarity | Medium | 1-2 hours |

---

## Success Metrics

After completing Phases 1-3, the codebase should show:

| Metric | Before | Target |
|--------|--------|--------|
| Largest file | 1,438 lines (sounds.py) | < 800 lines |
| Longest function | 210 lines (_update_clock) | < 60 lines |
| Functions over 100 lines | 6 | 0 |
| Functions over 50 lines | 24 | < 10 |
| Mutable closure vars | ~50+ | 0 (all in dataclasses) |
| Files over 500 lines | 5 | 2-3 (with cleaner internals) |
| Private dict access across modules | 1 (gui.py -> scores._scores) | 0 |
| Folders with spaces in name | 2 (Call Log, Sound Files) | 0 |
| PascalCase files (should be snake_case) | 8 | 0 |
| Misspelled file names | 1 (DependancyCheck) | 0 |
| Asset files in src/tabs/ | 1 (logo PNG) | 0 |

---

## Phase 6: File & Folder Naming Cleanup

This phase addresses naming inconsistencies, ambiguities, and convention violations across the project structure.

### Current Structure (Annotated)

```
PROJECT ROOT
  .env                              OK - standard
  .gitignore                        OK - standard
  config.ini                        OK - standard
  main.py                           OK - clear entry point
  compiletoexe.py                   ISSUE - camelCase, unclear name
  Launch.bat                        ISSUE - PascalCase (rest is snake_case)
  Launch.ps1                        ISSUE - PascalCase
  Setup-Firewall.ps1                ISSUE - PascalCase + kebab-case hybrid
  README.md                         OK - standard
  huge code.md                      META - audit artifact (not app code)
  huge code - repair strategy.md    META - audit artifact

  assets/
    countries.json                  OK
    DiversifiedPresentations.json   ISSUE - PascalCase, verbose
    Flags.json                      ISSUE - PascalCase (others are lowercase)
    patterns.json                   OK
    venues.json                     OK
    Version.json                    ISSUE - PascalCase
    worldcup_teams.json             OK - snake_case
    Schedule/                       ISSUE - PascalCase folder
      Argentina.json ...            OK within folder (proper nouns)

  Call Log/                         ISSUE - space in folder name, Title Case
    callcounter_*.log               OK - snake_case, timestamped
    changes.log                     OK
    *.json                          OK - timestamped API snapshots

  Candidates/                       ISSUE - PascalCase, contains build artifacts
    build/                          OK
    *.exe, *.zip                    OK - build outputs

  Sound Files/                      ISSUE - space in folder name, Title Case
    Anthems/                        OK within context
    medits.json                     ISSUE - cryptic abbreviation
    *.mp3, *.peak                   OK - media files
    Get_anthems_youtube_mp3.py      ISSUE - mixed case, loose script in asset dir

  src/
    __init__.py                     OK
    colour_generator.py             OK - but is this still used?
    config.py                       OK
    constants.py                    OK
    countries.py                    OK
    DependancyCheck.py              ISSUE - PascalCase, misspelled ("Dependancy")
    goal.py                         OK
    gui.py                          AMBIGUOUS - could be "app.py" or "main_window.py"
    sacn_connection.py              OK - descriptive
    scores.py                       AMBIGUOUS - does far more than scores now
    statusbar.py                    OK
    svg_renderer.py                 OK
    theme.py                        OK

  src/tabs/
    __init__.py                     OK
    api.py                          AMBIGUOUS - "api" what? This is the livescore poller
    api_calllog.py                  OK - clear sub-module of api
    api_changes.py                  OK
    api_raw.py                      OK
    api_schedule.py                 OK
    api_table.py                    OK (but not referenced in tree listing?)
    api_tree.py                     OK
    chase_controller.py             OK
    chase_patterns.py               OK
    chases.py                       AMBIGUOUS - is it the UI tab or the engine?
    country_editor.py               OK
    Diversified_logo.png            ISSUE - asset file mixed in with Python code
    flags.py                        OK
    generator.py                    AMBIGUOUS - generates what? (it's the RGB colour generator)
    groups.py                       OK
    presentations.py                OK
    readme_tab.py                   OK - clear distinction from root README.md
    sacn.py                         AMBIGUOUS - is this the connection or the settings tab?
    schedule.py                     AMBIGUOUS - schedule display? schedule fetcher?
    sound_keybinding.py             OK
    sounds.py                       OK
    timeline.py                     OK
    webserver.py                    OK
```

### Naming Issues Found

#### Issue 1: Inconsistent Casing Convention
**Problem:** The project mixes PascalCase, snake_case, Title Case with spaces, and kebab-case.

| Current Name | Convention Used | Should Be |
|---|---|---|
| `Launch.bat` | PascalCase | `launch.bat` |
| `Launch.ps1` | PascalCase | `launch.ps1` |
| `Setup-Firewall.ps1` | Pascal-kebab | `setup_firewall.ps1` |
| `compiletoexe.py` | No separator | `compile_to_exe.py` |
| `DependancyCheck.py` | PascalCase + typo | `dependency_check.py` |
| `DiversifiedPresentations.json` | PascalCase | `presentations.json` |
| `Flags.json` | PascalCase | `flags.json` |
| `Version.json` | PascalCase | `version.json` |

**Rule:** All file names should be `snake_case` for Python files. JSON and config files should be `lowercase` or `snake_case`. Scripts (`.bat`, `.ps1`) should be `snake_case`.

#### Issue 2: Spaces in Folder Names
**Problem:** `Call Log/` and `Sound Files/` have spaces. This causes quoting headaches in scripts, paths, and git commands.

| Current | Proposed |
|---|---|
| `Call Log/` | `call_log/` |
| `Sound Files/` | `sound_files/` |
| `Candidates/` | `candidates/` (or `dist/` — standard build output name) |
| `assets/Schedule/` | `assets/schedule/` |

#### Issue 3: Ambiguous File Names
**Problem:** Several files don't communicate their purpose clearly.

| File | Ambiguity | Suggested Rename | Reason |
|---|---|---|---|
| `src/gui.py` | "gui" is too generic | `src/app.py` or `src/main_window.py` | It's the main application window builder, not a general GUI utility |
| `src/scores.py` | Does scores, events, periods, state, phase detection, clocks | `src/match_store.py` | Reflects its role as the central match data store |
| `src/tabs/api.py` | "api" what? | `src/tabs/livescore.py` or `src/tabs/api_livescore.py` | It specifically polls the livescores API |
| `src/tabs/chases.py` | Is it the UI or the engine? | `src/tabs/chase_tab.py` | Clarifies it's the tab UI (controller & patterns are separate) |
| `src/tabs/generator.py` | Generates what? | `src/tabs/colour_picker.py` | It's the RGB colour picker / random colour tab |
| `src/tabs/sacn.py` | Connection or settings? | `src/tabs/sacn_settings.py` | Distinguishes from `src/sacn_connection.py` |
| `src/tabs/schedule.py` | Display or fetcher? | `src/tabs/schedule_display.py` | Distinguishes from `api_schedule.py` which fetches |
| `src/colour_generator.py` | Sounds like tab/generator.py | `src/colour_cycler.py` or **delete if unused** | Legacy standalone app, may be dead code |

#### Issue 4: Asset File in Code Directory
**Problem:** `src/tabs/Diversified_logo.png` is an image file sitting among Python source files.
**Fix:** Move to `assets/Diversified_logo.png`. Update the single reference in the code.

#### Issue 5: Stray Script in Asset Directory
**Problem:** `Sound Files/Get_anthems_youtube_mp3.py` is a utility script buried in a media folder. It's not part of the app.
**Fix:** Move to `tools/get_anthems.py` or `scripts/get_anthems.py`. If it's a one-time script that's already been run, consider deleting it or adding to `.gitignore`.

#### Issue 6: Cryptic Abbreviation
**Problem:** `Sound Files/medits.json` — "medits" is not a recognizable word.
**Fix:** Rename to `sound_files/media_edits.json` or `sound_files/sound_config.json` (whatever it actually stores).

#### Issue 7: Misspelling
**Problem:** `src/DependancyCheck.py` — "Dependancy" is misspelled (should be "Dependency").
**Fix:** Rename to `src/dependency_check.py`.

### Step-by-Step Rename Execution Plan

**Important:** Renames must be done carefully because imports, file paths in code, and the PowerShell launcher all reference these names. Each rename is one commit.

#### Step 6.1: Fix Python file casing and typo (highest impact, most import references)

Do these one at a time. After each rename, grep the entire project for the old name and update all references.

| Order | Rename | Files to Update |
|---|---|---|
| 1 | `src/DependancyCheck.py` -> `src/dependency_check.py` | `main.py` or wherever it's imported |
| 2 | `compiletoexe.py` -> `compile_to_exe.py` | Standalone, no imports to update |
| 3 | `Sound Files/Get_anthems_youtube_mp3.py` -> `scripts/get_anthems.py` (or delete) | Nothing references it |

#### Step 6.2: Fix folder names (requires updating all path references in code)

**This is the riskiest rename step.** Multiple Python files reference these paths as strings.

| Order | Rename | Code References to Update |
|---|---|---|
| 1 | `Call Log/` -> `call_log/` | `api.py` (log writing), `api_calllog.py` (log reading), `gui.py` (dir creation) |
| 2 | `Sound Files/` -> `sound_files/` | `sounds.py`, `sound_keybinding.py`, `gui.py`, `config.ini` |
| 3 | `assets/Schedule/` -> `assets/schedule/` | `timeline.py`, `api_schedule.py`, `gui.py`, `webserver.py` |
| 4 | `Candidates/` -> `dist/` | `compiletoexe.py` (or `compile_to_exe.py` by then) |

**Approach for each:**
1. `git mv "Old Name" new_name`
2. Grep entire project for old path string
3. Update all string references
4. Test the app
5. Commit

#### Step 6.3: Fix JSON asset file casing

| Rename | Code References |
|---|---|
| `assets/Flags.json` -> `assets/flags.json` | `flags.py`, possibly `gui.py` |
| `assets/Version.json` -> `assets/version.json` | `gui.py`, `statusbar.py` |
| `assets/DiversifiedPresentations.json` -> `assets/presentations.json` | `timeline.py`, `webserver.py`, `presentations.py` |

#### Step 6.4: Fix script casing

| Rename | References |
|---|---|
| `Launch.ps1` -> `launch.ps1` | `Launch.bat` (which becomes `launch.bat`) |
| `Launch.bat` -> `launch.bat` | Desktop shortcut or manual launch |
| `Setup-Firewall.ps1` -> `setup_firewall.ps1` | Manual run only |

#### Step 6.5: Move misplaced files

| Move | References |
|---|---|
| `src/tabs/Diversified_logo.png` -> `assets/diversified_logo.png` | `readme_tab.py` or whichever tab loads it |
| `Sound Files/medits.json` -> `sound_files/media_edits.json` | `sounds.py` |

#### Step 6.6: Rename ambiguous Python files (do LAST — most import churn)

These are optional but improve clarity. Only do them after all other refactoring is stable.

| Rename | Import Updates Needed |
|---|---|
| `src/tabs/api.py` -> `src/tabs/livescore.py` | `src/tabs/__init__.py`, `src/gui.py` |
| `src/tabs/generator.py` -> `src/tabs/colour_picker.py` | `src/tabs/__init__.py`, `src/gui.py` |
| `src/tabs/sacn.py` -> `src/tabs/sacn_settings.py` | `src/tabs/__init__.py`, `src/gui.py` |
| `src/tabs/chases.py` -> `src/tabs/chase_tab.py` | `src/tabs/__init__.py`, `src/gui.py` |
| `src/tabs/schedule.py` -> `src/tabs/schedule_display.py` | `src/tabs/__init__.py`, `src/gui.py` |

**Note:** `src/gui.py` and `src/scores.py` renames are deferred until Phase 3 module extractions are done (Steps 3.1-3.2), since those phases already plan to slim down `scores.py` into a properly-scoped module.

### Proposed Final Structure

```
project_root/
  .env
  .gitignore
  config.ini
  main.py
  compile_to_exe.py
  launch.bat
  launch.ps1
  setup_firewall.ps1
  README.md

  assets/
    countries.json
    diversified_logo.png            (moved from src/tabs/)
    flags.json                      (was Flags.json)
    patterns.json
    presentations.json              (was DiversifiedPresentations.json)
    venues.json
    version.json                    (was Version.json)
    worldcup_teams.json
    schedule/                       (was Schedule/)
      Argentina.json ...

  call_log/                         (was "Call Log/")
    callcounter_*.log
    changes.log
    *.json

  dist/                             (was "Candidates/")
    build/
    *.exe

  sound_files/                      (was "Sound Files/")
    anthems/                        (was Anthems/)
    media_edits.json                (was medits.json)
    *.mp3, *.peak

  scripts/                          (NEW)
    get_anthems.py                  (moved from Sound Files/)

  src/
    __init__.py
    app.py                          (was gui.py — optional, Phase 3+)
    config.py
    constants.py
    countries.py
    dependency_check.py             (was DependancyCheck.py)
    goal.py
    match_store.py                  (was scores.py — after Phase 3 extraction)
    sacn_connection.py
    statusbar.py
    svg_renderer.py
    theme.py

  src/tabs/
    __init__.py
    livescore.py                    (was api.py — optional)
    api_calllog.py
    api_changes.py
    api_raw.py
    api_ratelimit.py                (NEW from Phase 3)
    api_schedule.py
    api_table.py
    api_tree.py
    chase_controller.py
    chase_patterns.py
    chase_tab.py                    (was chases.py — optional)
    colour_picker.py                (was generator.py — optional)
    country_editor.py
    flags.py
    groups.py
    presentations.py
    readme_tab.py
    sacn_settings.py                (was sacn.py — optional)
    schedule_display.py             (was schedule.py — optional)
    sound_keybinding.py
    sounds.py
    sounds_waveform.py              (NEW from Phase 3)
    timeline.py
    webserver.py
    webserver_templates.py          (NEW from Phase 3)
```

---

## What NOT to Do

- **Don't introduce a framework.** No Flask, no Jinja, no dependency injection. This is a tkinter app that runs at a trade show. Keep it simple.
- **Don't refactor everything at once.** Each step is one commit. If a step breaks something, revert just that step.
- **Don't add abstractions for their own sake.** A 40-line function is fine. A class with one method is worse than a function.
- **Don't change the `scores.py` API.** Other files depend on `get_score_display()`, `get_match_clock()`, etc. Keep those signatures stable. Add new modules alongside, then migrate callers one at a time.
- **Don't touch files that are clean.** `constants.py`, `config.py`, `theme.py`, `chase_patterns.py`, `sound_keybinding.py`, `presentations.py` — leave them alone.
