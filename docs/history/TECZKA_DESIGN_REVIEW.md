# teczka Design Review

**Date:** 2026-07-25
**Reviewed at:** commit `c17ea5d` plus the uncommitted fixes made during this
review (listed in §0).
**Scope:** `teczka/teczka/` — 16,742 lines of Python across 60 modules.

This is a dated, point-in-time report. Per
[docs/README.md](../README.md)'s consolidation rules it is not maintained; if
the app is re-reviewed later, add a new document rather than rewriting this one.

## Method

Findings are runtime-verified, not read off the source alone. The app was
launched on a live Wayland/Plasma session and driven in-process through a
scripted `MainWindow` — real `rcompare_cli` subprocess, real comparison of a
15-file fixture covering identical / modified / orphan / CSV / JSON / binary
cases — with each view screenshotted and the widget tree interrogated
programmatically. Beyond Compare 5.2.4 was run against the same fixture as a
baseline. Claims that could not be verified this way are marked as such.

---

## 0. Fixes applied during the review

These were found and fixed in the same pass; the review below describes the
state *after* them.

| Fix | Location |
|---|---|
| Status bar stuck on "Comparing..." forever (set on start, reset on cancel/error, never on success) | `main_window.py` `_on_comparison_finished` |
| Path breadcrumbs clipped along their lower edge (scroll area pinned to a `QLineEdit`'s height with its h-scrollbar rendering inside it; row height also hardcoded at 32px) | `widgets/breadcrumb_bar.py`, `widgets/compact_path_bar.py` |
| Hex view pinned to the bottom of its pane, ~half the area empty (title label and splitter both at stretch 0) | `views/hex_view.py` |
| Welcome dialog gating every launch, including CLI/`xdg-open` invocations | `app.py`, `dialogs/splash_dialog.py` |
| No folder picker on the path bar; only chooser was a buried menu action using local-only `getExistingDirectory` | new `utils/path_picker.py`, `widgets/compact_path_bar.py` |
| Fusion style forced over the system widget style | `app.py` |

---

## 1. Feature verification

Claims taken from [FEATURE_COMPARISON.md](../../FEATURE_COMPARISON.md) and
[docs/modules/teczka.md](../modules/teczka.md), checked against the running app.

### Confirmed present and working

| Feature | Evidence |
|---|---|
| Multi-tab sessions | `_sessions`, `_capture_session_state`/`_apply_session_state` genuinely snapshot per-tab paths, settings and 3-way flag |
| Session profiles + auto-save on close | `ProfileManager`, `_save_profile_on_close` |
| Sync preview dialog | `dialogs/sync_dialog.py`, reachable |
| Three-way merge UI | `views/merge_view.py`; four panes, conflict navigation, Take Left/Right/Base/Both, "0 unresolved of 2 regions" counter correct on a real merge |
| Drag and drop | `acceptDrops()` true; verified |
| Undo history | `OperationHistory` |
| Folder-view modes | `_folder_view_mode()` → `compare_structure` / files-only / ignore-structure |
| Expand/collapse all, preview panel, bookmarks | present and wired |
| Hex viewer | byte-level diff verified correct on a 4-byte injected change at offset 0x64, ASCII column included |
| CSV/table cell diff | per-cell colouring verified |
| Intra-line text diff | verified — `hello` → `hello world` highlights only `world` |
| Text options (whitespace / case / regex) | present in settings dialog |
| Persistent per-user options | `AppConfig`, 13 persisted fields |

### Claims that do not hold

| Claim | Reality |
|---|---|
| "Syntax highlighting ✅ Yes" (`FEATURE_COMPARISON.md:53`) | **No syntax highlighting exists.** There is no `QSyntaxHighlighter` anywhere in the codebase. The CLI's `highlighted_segments` drives intra-line insert/delete tinting only (`views/text_view.py:411`). Beyond Compare renders the same file with full Python highlighting. *(Corrected in the doc during this review.)* |
| "EXIF metadata comparison ✅ Yes" | True of the **CLI only**. `rcompare_core::image_diff` implements `ExifMetadata`/`exif_differences` and the CLI exposes `--image-exif`, but `views/image_view.py` never requests or displays it — the file contains no reference to EXIF and does its own dimension comparison instead. |
| KDE compliance "Collision-Free 100%" (`KDE_COMPLIANCE.md`) | **Two live shortcut collisions** — see §2.6. |

### Algorithmic limitation found

**CSV rows are aligned positionally, never by key.**
`rcompare_core/src/csv_diff.rs:201-204` walks `for i in 0..max_rows` pairing
`left[i]` with `right[i]`. In the fixture, a left-only row (`cherry`) and a
right-only row (`date`) were paired and reported as "different", and the
summary read *"0 left-only, 0 right-only"* — actively misleading. A single
inserted row near the top of a file cascades every subsequent row as changed.

The fix already exists and is unused: `CsvDiffEngine::with_key_columns()`
(`csv_diff.rs:94`) implements key-based alignment and has **zero callers** in
either the CLI or teczka.

---

## 2. Design review

### 2.1 What is genuinely well designed

Stated first because the critique below is long, and these are real:

- **View/widget decoupling is good.** Views and widgets communicate outward
  through declared Qt signals (`session_tab_bar.py` 5, `integrated_status_bar.py`
  4, `compact_path_bar.py` 4, …) and there are only **2** `parent()`/`window()`
  traversals in the whole of `views/` + `widgets/`. Child components do not
  reach back into the application. This is the app's strongest structural
  property and it is what makes the God Object in §2.2 fixable rather than fatal.
- **The model layer is correct Qt.** `models/tree_model.py` implements a real
  `QAbstractItemModel` with a `QSortFilterProxyModel` subclass for filtering,
  including a memoised descendant-match cache with explicit invalidation
  (`invalidateFilter` override, `tree_model.py:298`). This is the right design,
  not the `QStandardItemModel`-plus-manual-rebuild shortcut that a GUI of this
  age usually accumulates.
- **Heavy work is off the GUI thread.** Comparisons run via `QProcess`
  asynchronously and result parsing/tree building happens in a `FunctionWorker`
  thread, so the event loop stays live. Measured: 0.20 s end-to-end for the
  fixture against 23 ms for the CLI alone — the GUI overhead is real but small,
  and it does not block.
- **Config persistence is done carefully** — atomic write via
  `tempfile.mkstemp` + `os.replace`, with failures deliberately swallowed and a
  comment explaining why losing preferences beats crashing on exit
  (`utils/config.py:126-131`).

### 2.2 `MainWindow` is a God Object — the dominant structural problem

| Metric | Value |
|---|---|
| Lines | 3,407 (20% of the whole app) |
| Methods defined on the class | 138 |
| of which `_on_*` slot handlers | 73 |
| Instance attributes | 120 |

Everything routes through this one class: menu construction, toolbar, status
bar, session/tab lifecycle, path state, comparison orchestration, copy/move/
delete/rename/touch file operations, sync planning **and** a local sync
fallback implementation, profile save/load, print/preview document building,
diff navigation, and every dialog invocation.

Two consequences visible in the code:

1. **Business logic lives in the window.** `_plan_sync_actions`,
   `_sync_local_fallback`, `_copy_paths_local_fallback` and `_sync_copy_path`
   implement file-operation semantics *inside the widget class* — duplicating
   logic that `rcompare_core` already owns and that the CLI already exposes.
   These fallbacks can drift from the engine they shadow.
2. **It is effectively untestable.** Instantiating any part of this logic
   requires constructing the whole window. That is the direct cause of §2.8's
   thin test coverage; the tests that exist cover `config`, `models`, `utils`
   and `widgets` — precisely the four areas *not* inside `MainWindow`.

**Recommendation:** extract, in order of payoff — (a) a `SyncController` /
`FileOpsController` holding the operation logic, (b) a `SessionManager` owning
the tab/session lifecycle, (c) a `MenuBuilder` for the ~600 lines of action
construction. Each is mechanical, and the good signal-based decoupling means
none of it requires touching the views.

### 2.3 `AppState` is a designed-then-abandoned architecture

`state.py` (204 lines) defines an `AppState(QObject)` with 10 signals
(`view_changed`, `compare_started`, `compare_finished`, `results_updated`,
`paths_changed`, …), path properties, a results dict, bookmark management and
settings persistence. It is the shared observable store the app was evidently
designed around.

Measured reality:

- **0** connections to any of its 10 signals, anywhere.
- Paths are **written** at two sites (`main_window.py:1007`, `:1015`) and
  **never read**.
- `MainWindow` uses its own `self._left_path` in **29** places.

So the app carries two parallel state models, one of which is write-only dead
weight that can silently diverge from the one actually in use. This is worse
than having no store at all: a future contributor reading `state.py` will
reasonably conclude that setting `_app_state.left_path` propagates somewhere.

**Recommendation:** decide deliberately. Either finish it — route path/result
state through `AppState` and connect the signals, which would meaningfully
shrink `MainWindow` — or delete it. Leaving it is the one option with no
upside.

### 2.4 The CLI contract is unvalidated

teczka's entire data model comes from `rcompare_cli --json`. The CLI emits
`{"schema_version":"1.1.0", …}`. **teczka never reads that field.**

`utils/cli_bridge.py:103` parses with direct subscripting —
`data["summary"]["total"]`, `data["entries"]`, `e["left"]["size"]` — so any
schema change surfaces as a `KeyError` raised inside a worker thread rather
than a diagnosable "unsupported CLI version" message.

This matters more than it looks: `docs/roadmap.md` §3 plans a **unified JSON
schema v2** across commands. On the day that lands, teczka breaks with a stack
trace unless it is version-aware first.

**Recommendation:** check `schema_version` at the boundary, accept a declared
major range, and fail with an actionable message naming both versions. Cheap
now, load-bearing later.

### 2.5 Theming will not follow the desktop

`resources/themes.py` is 1,531 lines containing **390 hardcoded hex colours**
and **zero** `palette(...)` references. Diff colours elsewhere are similarly
literal (`views/hex_view.py:41` `_DIFF_BG = QColor("#ffe1e1")`).

Consequences: Plasma's dark mode, accent colour, and high-contrast
accessibility themes are not honoured by any of it. Note that some widgets
*do* use `palette(...)` in their stylesheets (`breadcrumb_bar.py`,
`sidebar.py`), so the codebase is inconsistent — the newer widget code is
theme-aware and the older resource file is not.

A related environmental fact worth recording: this PySide6 ships only
`['Windows', 'Fusion']` styles, so Breeze is not loadable by the bundled Qt at
all. Removing the forced `setStyle("Fusion")` (done in §0) is necessary but not
sufficient — on a distro-packaged PySide6 it now inherits Breeze, but the
hardcoded palette in `themes.py` will still fight it.

### 2.6 Keyboard: two collisions and a dead Quit

Verified by walking the live menu tree:

| Shortcut | Bound to | Cause |
|---|---|---|
| `Ctrl+P` | **Print** *and* **Profiles** | Print uses `StandardKey.Print` (correct); Profiles hardcodes `Ctrl+P` |
| `Ctrl+Y` | **Redo** *and* **Synchronize** | `StandardKey.Redo` includes `Ctrl+Y` on this platform; Synchronize hardcodes it |

**`Ctrl+Q` does not quit the application.** `main_window.py:227` uses
`QKeySequence.StandardKey.Quit`, which resolves on this platform to the `Exit`
multimedia key, not `Ctrl+Q`. The same trap applies to
`StandardKey.Preferences` → `Settings`. This is a KDE HIG violation hiding
inside code that looks maximally correct — using the standard-key API is the
right instinct, but these two constants need an explicit fallback.

Also: **59 leaf menu actions, 0 with icons**, and 31 with no shortcut. KDE menus
are conventionally iconed, and `_themed_icon()` already exists and is used for
the toolbar — the helper simply is not applied to menu actions.

### 2.7 Internationalisation is built but never called

`localizer.py` wraps `fluent.runtime`, and `i18n/en/teczka.ftl` holds a
152-line message catalogue. There are **zero call sites** outside the localizer
itself — every user-visible string in the app is a bare literal. This is the
same failure mode as §2.3: infrastructure that looks like a working feature but
is inert. It also explains the KDE compliance doc's WS6 (A11y/i18n) score of
1/12.

### 2.8 Testing is thin where risk is highest

36 tests across `test_config.py`, `test_models.py`, `test_utils.py`,
`test_widgets.py`. They pass in 0.36 s and are real `pytest-qt` tests, not
mocks. But coverage maps inversely to risk: nothing covers the merge view, any
dialog, drag-and-drop, the CLI bridge's parsing, or session/tab state
transitions — i.e. everything inside `MainWindow`. §2.2 is the reason, and
fixing §2.2 is what unblocks this.

Note also that `workers/function_worker.py` subclasses `QThread` and exposes
**no cancellation path**; long parses cannot be interrupted, only orphaned.

### 2.9 Interaction design gaps vs. the Beyond Compare baseline

- **Split navigation model.** Built-in views are switched via a left icon rail;
  dynamically opened comparisons go into a `_view_switcher` tab bar that is
  *empty and hidden* (0 tabs) until something is added. Two different mental
  models for "change what I'm looking at". BC uses one tab strip for
  everything.
- **Orphan rows are ambiguous.** A left-only folder renders on **both** sides
  with the same red "different" tint, distinguished only by empty Size/Date
  cells. BC leaves a blank aligned gap on the opposite side — unmistakable at a
  glance.
- **Sparse toolbar.** teczka exposes a single `Compare` button; BC surfaces
  All/Diffs/Same/Files, Rules, Copy, Expand/Collapse, Refresh, Swap and a live
  filter box. teczka *has* most of these as menu actions — they are simply not
  discoverable.
- **No per-pane file metadata.** BC shows type, encoding, EOL style, size and
  mtime above each pane; teczka shows a truncated path.
- **Merge view source panes carry no diff colouring** — only the merged output
  pane is tinted, so the user cannot see which regions are in conflict in
  Left/Base/Right. This is the single biggest usability gap in the app's
  youngest feature.
- **75 `QMessageBox` call sites.** Errors are consistently reported, which is
  good, but almost entirely as modal interruptions; there is an
  `integrated_status_bar` that could carry non-fatal messages instead.

---

## 3. Prioritized recommendations

**Tier 1 — correctness and contract (days)**

1. Fix the two shortcut collisions; give `Quit`/`Preferences` explicit
   `Ctrl+Q` / `Ctrl+,` fallbacks.
2. Validate `schema_version` in `cli_bridge` before the schema v2 work lands.
3. Wire `CsvDiffEngine::with_key_columns()` + a "first row is header" toggle
   (also fixes the hardcoded `Col 1/2/3` headers at `table_view.py:381`).
4. Add cancellation to `FunctionWorker`.

**Tier 2 — the structural work (weeks)**

5. Extract `SyncController`/`FileOpsController`, then `SessionManager`, then
   `MenuBuilder` out of `MainWindow`; move the sync/copy fallbacks onto the
   core engine they duplicate.
6. Resolve `AppState`: finish it or delete it.
7. Backfill tests against the newly extracted controllers — this is where the
   coverage gap actually closes.

**Tier 3 — presentation (parallel, independent)**

8. Replace `themes.py`'s 390 hardcoded colours with palette-derived roles;
   make diff colours theme-aware.
9. Colour the merge view's source panes.
10. Add a `QSyntaxHighlighter` (Pygments is already a declared dependency).
11. Icons on menu actions via the existing `_themed_icon()`.
12. Unify navigation on one tab model; blank-gap rendering for orphan rows.
13. Route strings through the existing localizer, or remove it.

**Deliberately not recommended:** rewriting the view layer. It is the healthiest
part of the codebase, and the signal-based decoupling is what makes Tier 2
tractable.

---

## 4. Summary judgement

teczka is a substantially more complete application than its documentation
suggests — the feature inventory is largely real, the model layer is properly
built, and the view decoupling is better than typical for a GUI this size. Its
problems are concentrated rather than diffuse: one 3,400-line class holding
logic that belongs elsewhere, two abandoned subsystems (`AppState`, i18n) that
read as working features, an unvalidated contract with the CLI it depends on
entirely, and a presentation layer that does not participate in the desktop's
theming.

The recurring pattern across the whole project shows up here too. Counting only
what this review touched: EXIF comparison and key-based CSV alignment both
exist in `rcompare_core`, are reachable from the CLI, and are invisible in the
GUI — joining archive-write, cloud VFS, resumable copy and union VFS on the
list of built-but-unwired capabilities that
[docs/development-plan.md](../development-plan.md) is organised around. The
cheapest wins in this codebase continue to be wiring, not building.
