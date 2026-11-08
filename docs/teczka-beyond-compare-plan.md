# Teczka: Beyond Compare Parity Plan

Updated: 2026-11-08. Scope: the **teczka** (PySide6) desktop app.

This is the GUI execution plan, alongside [development-plan.md](development-plan.md)
for Rust/core/CLI work. [roadmap.md](roadmap.md) remains the shared backlog and
source of truth for cross-project status. Recheck this plan against the source
and the minimum supported CLI before starting an item; this document is not a
feature specification for work already implemented elsewhere.

## Goal and working rules

Prioritize reliable folder comparison, then the daily-use gaps that distinguish
Beyond Compare. Reuse existing teczka and CLI capabilities before adding a
second implementation. Keep view behavior, criteria, and filters consistent
between the screen, navigation, summaries, and exported reports.

The current gap inventory is a source review, not a complete hands-on audit.
The Tools, Difference, and Bookmarks menus and every dialog still need a full
inventory before the feature list can be considered complete.

### CLI compatibility

The pre-upgrade installed `rcompare_cli` was checked with `scan --help` and did
not list the newer `--include`, `--exclude`, or `--progress` options. It also
emitted no structured progress events in the earlier GUI comparison. The
current `~/.local/bin/rcompare_cli` has since been replaced with the tested
workspace release build. Any separately packaged CLI used for distribution
still needs to pass capability checks for these features:

- Keep include/exclude filtering and comparison criteria in teczka's
  post-scan processing where practical; do not pass unsupported flags.
- Show an indeterminate progress indicator when no structured progress events
  arrive. Show a percentage only when the CLI supplies a valid total.
- Check the installed executable, not just the repository source, before
  claiming a CLI-dependent feature is available. Retire fallbacks only after
  the minimum shipped CLI is upgraded and verified.

#### Pre-upgrade installed CLI baseline (2026-11-08)

Checked before the update with `~/.local/bin/rcompare_cli` (version 0.1.0,
built Feb 2026):

| Check | Result |
|---|---|
| `scan --include/--exclude` | Rejected (`unexpected argument`) |
| `scan --progress` | Rejected, although `capabilities --json` reports `"supports_progress": true` for `scan` |
| `capabilities --json` | Present (schema 1.0.0, scan JSON schema 1.1.0, exit codes 0/1/2 documented) |
| Flags missing from `capabilities` but accepted by `scan` | `--regex-rule`, `--image-exif`, `--image-tolerance`, `--cache-dir`, `--hide-*`, `--ignore-whitespace`, `--ignore-case` |
| Progress in JSON mode | By design none: the old CLI emitted progress only when output was not JSON and stderr was a terminal, so a GUI reading `--json` output received no progress |

The pre-upgrade 0.1.0 build was an unreliable feature gate: it over-reported
progress and under-reported accepted flags. It has since been replaced by the
workspace release binary, whose capability report derives flags from Clap,
reports build-specific source schemes and progress formats, and passes actual
parser and JSON checks. The package version remains 0.1.0; its capabilities
schema is now 1.2.0.

#### Current workspace release build validated (2026-11-08)

Built `rcompare_cli` from the current workspace into `/tmp` and exercised that
release executable. Its `capabilities --json` report uses schema 1.2.0 and
advertises scan progress formats `terminal-spinner` and `json-stderr-lines`.
The advertised `--include`, `--exclude`, and `--progress` flags match
`scan --help`; a two-file scan included `keep.txt`, excluded `skip.txt`, and
returned exit code 2. With `--progress json`, stdout remained valid scan JSON
and stderr carried six `PROGRESS:` events ending in `done`; `--progress never`
emitted none. The built release binary is now installed at
`~/.local/bin/rcompare_cli`; SHA-256
`9749e657629d514d0775b5a876e6ce82342ce81f8a3a9644ce6dc332bf51f13d` matches
the tested workspace binary. The previous executable is backed up at
`/tmp/rcompare_cli_before_teczka_upgrade`.

The same release binary received SIGTERM during a 50,000-entry scan and exited
130 with a final `cancelled` event and no partial JSON report. An unavailable
source produced exit 1 with a final `failed` event. Through MainWindow, a
100-entry scan consumed seven progress updates through `done`; cancellation
during the 50,000-entry scan stopped the process in about 50 ms, kept the
status at “Cancelled,” and left the progress bar hidden.

#### CLI contract needed by the GUI

Treat this as the compatibility contract for GUI-driven commands. Keep JSON on
stdout and human-readable diagnostics on stderr so the GUI can parse results
without scraping terminal text. Version the report schema and keep field names
and meanings stable across compatible CLI releases.

| Capability | GUI requirement | Priority/state |
|---|---|---|
| Folder scan report | `scan --json` returns a versioned report with a summary and entries. Each entry supplies its relative path, comparison status, directory flag, and side-specific size and modification time where available. Define exit codes for equal results, differences, and fatal errors; the GUI must accept the documented difference exit code as a successful scan. | Required for folder comparison; source exists, verify the packaged contract. |
| Stable command envelope | Give each machine-readable command a documented, versioned envelope with command, status, summary, data, and warnings. Publish JSON Schemas and retain a compatibility window when changing fields or meanings. | ✅ CLI JSON defaults to the v2 envelope for scan, copy, sync, sync-checkpoints, sync-discard, diff-file, and capabilities; `--schema-version 1` preserves the legacy report formats. Schemas are published under `docs/schemas/v2/`. teczka parses both report versions. CLI and GUI source tests cover the contract; verification against the minimum packaged CLI remains. |
| Structured progress | `scan --progress json` emits flushed `PROGRESS:{...}` line events on stderr while the result stays on stdout. Events carry the phase, completed count, and optional total (`0` means unknown); `done` marks normal completion. The GUI shows an animated busy bar for unknown totals and a percentage only for a positive total. Explicit cancelled/failed terminal events precede nonzero exit codes. | The tested workspace release is installed at `~/.local/bin/rcompare_cli`; progress, failed, and cancelled events, exit codes 1/130, `--progress never` suppression, and GUI consumption are verified. Copy-command cancellation remains open; sync cancellation is covered in the Sync results row. |
| Capability discovery | `capabilities --json` reports CLI version, command and report schema versions, supported commands and options, progress formats, source schemes, and relevant operation limits. Keep this list accurate and test it against actual parser behavior. | Flags derive from Clap; v2 reports the default and supported JSON schema versions while retaining the v1 capability report under `--schema-version 1`. Schema 1.2.0 reports `terminal-spinner` and `json-stderr-lines` for scan. The installed release executable matched `scan --help`; operation limits and packaged builds still need an audit. |
| Filter and comparison options | Expose and accurately advertise include/exclude/ignore patterns and supported comparison options (for example text rules and image tolerance). Define whether filtering happens during traversal or after scanning, and keep folder traversal semantics correct for nested matches. The GUI must retain its post-scan fallback until the minimum packaged CLI is verified. | The installed release accepts `--include` and `--exclude`; a local scan verified filtering. Comparison-option parity and packaged-build checks remain. |
| Copy and sync results | `copy --json` and `sync --json` return stable summaries and per-operation outcomes, including missing/skipped/failed items and a nonzero exit code for partial or failed work. Define cancellation and error outcomes explicitly. | Release tests cover copy success and a missing-item partial report with exit 1, plus sync success and a cancelled sync report with exit 130. The GUI accepts valid exit-1 and exit-130 reports and does not retry a failed CLI mutation through its local fallback. CLI checkpoint listing, option-checked restart, and discard are tested, including a fresh-process resume after actual SIGTERM; teczka lists runs for the active root pair and exposes confirmed resume/discard actions. Copy-command cancellation and live GUI recovery remain open. |
| Cancellation | Long-running scans and mutations respond to GUI cancellation promptly, stop scheduling new work, and report whether work completed, was cancelled, or failed. Mutating commands must leave a usable, accurately reported partial result. | Scan cancellation sends a graceful terminate, returns exit 130, and is verified through the GUI. Sync handles SIGTERM between actions and during chunked transfers, reports completed/remaining actions, and journals cancellation; local large-file copies save a checkpoint and validate the source hash before resume. The CLI persists sync-run metadata and provides list, option-checked resume, and discard commands. A CLI integration test resumes in a fresh process after actual SIGTERM. Teczka exposes Stop and tested recovery controls; copy-command cancellation and live GUI Stop/Resume validation remain open. Discard removes checkpoint metadata while leaving any partial destination files in place. |
| Remote-safe access | For each advertised remote scheme, provide the listing, metadata, and file-read operations the GUI needs for comparison and preview. Errors must identify the source and operation without exposing credentials. | CLI VFS support and `source_schemes` are present; GUI scan gating, bounded text-preview reads, staged selected-row viewers, and standalone URL-pair reads are capability-gated and covered by fake-CLI tests. Live endpoint and packaged-CLI checks remain. |
| File preview and diff | `read` returns file bytes without mixing diagnostics into the payload; `diff-file --json` returns a stable, mode-specific result for text, image, and other supported formats. Support two explicit file operands (including different file names) so the GUI can compare a selected pair without scanning parent folders. Both commands must work for every advertised source scheme and report errors without leaking credentials. | `diff-file` accepts two local or remote file operands with different names; source splitting and no-cloud errors have CLI coverage. A local WebDAV fixture verifies remote metadata and reads through `diff-file`. The GUI stages remote folder rows and standalone remote or mixed pairs through streaming `read --out`, then opens existing viewers. Controlled-provider checks for S3, SFTP, and GUI scan/preview/viewer paths remain. |
| Large result streaming | An optional JSONL scan mode emits entry records incrementally and a clearly marked final summary, with documented ordering and error behavior. The GUI can consume it to populate large comparisons progressively while retaining a final summary for counters and reports. | Scale improvement; CLI option exists in source, GUI does not consume it. |

Recommended CLI delivery order: rebuild and contract-test the minimum packaged
CLI against the v2 envelope and capability report; complete cancellation for
the copy command; then add streamed scan consumption and validate remote scan,
preview, and staged-view paths against controlled endpoints. Keep the GUI's
current post-scan filtering and indeterminate progress behavior until each
replacement is proven against the minimum packaged CLI.

Before relying on a row, add contract tests that exercise the minimum packaged
CLI—not only source-level unit tests. Compare `capabilities --json` with the
actual parser, and cover schema validation, equal and differing scans,
malformed or unavailable paths, filter traversal, partial mutation failure,
cancellation, progress event parsing, and remote read/diff behavior as
applicable. The GUI should fall back safely when optional capabilities are
absent and must not infer support from a CLI version string alone.

## Result pipeline

Every result the user sees passes through the same stages, in this order.
New features must plug into one stage instead of adding a parallel path:

1. **Scan** (`rcompare_cli scan --json`): status, sizes, times per entry.
2. **Criteria** (`utils/criteria.py`): re-classifies paired files as same or
   different (size, time, tolerance, whole-hour offsets), then recomputes the
   summary.
3. **File filter** (`utils/file_filter.py`): drops excluded and non-included
   entries, keeps folders that still contain a match, then recomputes the
   summary.
4. **Unimportant-text rules** (`utils/unimportant_text.py`): for content-mode
   folder comparisons, reclassifies paired UTF-8 text files after applying
   ordered Python regular-expression replacements line by line. Unreadable,
   invalid UTF-8, non-text, and unpaired entries keep their scan status. Text
   previews use the same rules when opened from a content-mode folder
   comparison; standalone file comparisons always use the active rules.
5. **Tree build** (`models/comparison.py`).
6. **View filters** (pills, search, Newer-side mode in
   `models/tree_model.py`). The default `show_differences` mode adds no
   restriction of its own: the Identical/Different/Left/Right pills alone decide
   which statuses are visible. The tree and
   `main_window._get_diff_entries()` share quick-find, status-pill, and
   Diff Options predicates.

Stages 2-5 run in `ComparisonWorker._parse_report_and_tree`, so exports,
navigation and the tree all see the same entries. Stage 6 shares the quick-find
matcher and status/Diff Options predicates through `utils/view_filter.py`.
Directory rows roll up descendant status for the visible tree summary; the
summary tooltip distinguishes those rows from the file-only navigation count.

## Baseline measurements

Large manual dataset: `/data/aecs4u.it/real-estates/outputs/` (LHS) versus
`/data/aecs4u.it/ocular/outputs/` (RHS), 123,385 differing entries in a report of
15,807 identical, 10 different, 2,169 left only and 121,860 right only. CLI is
the pre-upgrade installed 0.1.0 build (SHA-256
`807cc10b31598b1fb3c69a586f25cd82aa7215f1361f38e49f471200c427ea10`). These
are historical timings from before the current release was installed; they do
not establish its performance. Wall-clock times on the development machine:

| Operation | Time | Notes |
|---|---|---|
| Compare, content mode, first run | 203 s | Cold disk cache (assumed, not measured) |
| Compare, content mode, later runs | ~37 s | Warm cache; the same time with file filter `*.json;-*.tmp` or criteria size+time ±2 s |
| Left Newer / Right Newer filter | 0.7 s / 0.5 s | 9 left-newer, 1 right-newer |
| Back to all differences | 0.8 s | |
| Next / Prev | 0.09 s / 0.01 s | Prev was 4.7 s before the indexed lookup |

Later runs the same day (same CLI file, other code changed meanwhile; cache state
not controlled):

| Operation | Time | Notes |
|---|---|---|
| Compare, content mode | 85 s, then 52 s | two separate scripted runs |
| File filter `*.json;-*.tmp` | 40-48 s | 61,382 differing entries after filtering |
| Criteria size+time ±2 s | 25 s | fastest run, same counts as content mode |
| Left / Right Newer, back to all | 0.3 s each | 9 and 1 files |
| Identical pill off / on | 0.65 s / 0.73 s | 2,113 / 2,115 top-level rows |
| Fit columns to contents | 0.5 s | bounded sample of 300 rows |
| Switch on an attribute column | ~0.4 s for the first, ~1.0-1.5 s with four on | lstat of visible rows; includes a 0.2 s wait in the script |

**Metric distinction from the live GUI run (2026-11-08):** on the supplied
folders, the CLI report contained 139,846 entries with 15,807 identical, 10
different, 2,169 left only and 121,860 right only. The GUI footer showed 14,209
identical, 27,521 different, 1,572 left only and 96,544 right only. The footer
counts accepted tree rows, where directory statuses are rolled up from their
descendants; the CLI summary counts original scan entries. They have the same
total but are different metrics. The run took about 238 seconds end to end
(212 seconds in the CLI and 26 seconds parsing/building the tree); cache state
was not measured. Earlier run-to-run status changes may still include dataset
or CLI drift, so record raw report and visible tree counts separately.

Criteria size+time did not speed up the warm-cache run (traversal dominates) and
matched content mode's counts; re-measure on a cold cache and on a pair where
timestamps differ without content differences before claiming a gain. Record
cache state and CLI build with every new row.

## Status

| # | Work item | State |
|---|---|---|
| 0a | Diff counter follows active filters | ✅ implemented |
| 0b | Prev/Next uses indexed path lookup | ✅ implemented; retain the large-tree performance check |
| 0c | Pill colours and readability | ✅ root cause fixed (Qt reads 8-digit hex as `#AARRGGBB`, so the old `+ "cc"` alpha gave purple Identical and cyan Left Only; now `rgba()`); verified in a Wayland render, dark-theme check pending |
| 1 | Newer-side filtering | ✅ implemented |
| 2 | File include/exclude filters, dialog, presets, status pill | ✅ implemented |
| 3 | Comparison criteria and timestamp tolerance | ✅ implemented; MainWindow test and large-folder run done; dialog screenshot and cold-cache timing pending |
| 0d | Folder selection, scan feedback, and result visibility | 🚧 Live run on the supplied output-folder pair switched to Folder view immediately, showed an indeterminate bar, populated 139,847 tree nodes (including root) and 2,115 top-level rows, then hid progress. The default MainWindow selected the installed release CLI, processed 100 entries, received progress through `done`, and hid the bar. Cancellation during a 50,000-entry run stopped in ~50 ms and kept “Cancelled” visible with progress hidden. Automated tests cover both Browse buttons, missing/file path rejection, and graceful process termination. Live desktop interaction remains pending. |
| 0e | Missing-side cells in folder view | 🚧 orphan rows now show a grey “—” and a side-specific tooltip; model tests pass, live theme check pending |
| 0f | Visible status summary | ✅ summary counts follow the active folder proxy filters; its tooltip explains aggregated folder rows, while Next/Previous is file-only |
| 4 | Auto-refresh | 🚧 recursive watcher, stale Refresh action, opt-in debounce, view-state restore, and bounded fallback implemented; focused suite passes; large-tree/live check pending |
| 5 | Folder and text reports | 🚧 CSV/JSON/text/HTML/XML and side-by-side text HTML implemented; focused tests and headless browser check pass; live dialog check pending |
| 6 | Remote folder comparison in the GUI | 🚧 Capability-gated scans, URL-safe breadcrumbs/logging, staged remote text/table/image/hex viewers, a capability-gated standalone URL picker, local-only watchers, and mutation guards implemented; live provider checks remain |
| 7 | Resume interrupted sync | 🚧 CLI checkpoint list/resume/discard and GUI recovery controls are implemented and covered by tests; validate the live GUI Stop/Resume interaction |
| 8 | Touch/attributes audit | 🚧 side-by-side Properties dialog now shows both sides, missing status, type, size, permissions, owner/group, timestamps, and symlink target; permissions, owner, group and access/change times are also optional columns (item 12); permission *editing* still absent; live UI check pending |
| 9 | Standalone file-only comparison | 🚧 file-pair picker accepts local files and supported remote URLs, and two-file drop opens local pairs in existing text/table/image/hex views; GUI tests pass, and a local WebDAV fixture verifies remote CLI comparison of different basenames; live interaction check pending |
| 10 | Identical pill works in the default mode | ✅ the default `show_differences` mode no longer hides identical files itself, so the pills alone decide visibility; leaving a Newer mode restores the previous pills (see Phase E) |
| 11 | Select identical on LHS, then delete | ✅ implemented with a files-only / also-folders choice; trash and dry-run safeguards; real trash path and real-folder run still untested (see Phase E) |
| 12 | Columns fit contents; header attribute columns | ✅ implemented and checked on the large dataset; popup-menu visual check pending (see Phase E) |
| 13 | Selection scope: both panels or one | ✅ mirrored by default; Alt+Left / Alt+Right limit to one panel; verified in a live Wayland window (see Phase E) |
| 14 | Smart bulk selection | 🚧 Edit > Smart Select filters rows accepted by the active view filters (including collapsed descendants) by status, newer side, path glob, and LHS size; selection can target the left, right, or both panels. All/None/Invert, right-newer selection, ties, and two-panel orphan selection are tested; live interaction pending |

| 15 | Beyond Compare review and backlog (Phase F) | ✅ review complete; BC 5.2.7 was explored live in an isolated display and against its help; P1 and P2 are implemented, P3 is in progress, and D1–D3 are decided |

Items 1–3 have focused tests in `teczka/tests/test_main_window_smoke.py`,
`test_file_filter.py`, and `test_criteria.py`; items 10–14 are covered in
`test_main_window_smoke.py`, `test_bulk_select.py`, `test_folder_view_navigation.py`,
and `test_smart_select.py`. Their existence does not replace pending live visual
checks. The current installed CLI has separate direct and MainWindow integration
checks; packaged builds still need verification.

**GUI test run (2026-11-08):** the full teczka suite passed with
`QT_QPA_PLATFORM=offscreen` (198 passed). Pytest reported only the existing
`pytest-asyncio` fixture-loop-scope deprecation and a cache write warning caused
by the parent directory being read-only.

## Phase 0 — Reliability and feedback

### 0d. Folder selection and scan feedback

Folder selection updates the LHS/RHS roots; the user then starts a comparison
with **Compare**. The panels should show the previous result while a refresh is
running, or show the folder-comparison view during a first scan. They must not
leave the user staring at the Home view with no indication that work is
underway.

- **Touches:** `widgets/compact_path_bar.py`,
  `widgets/integrated_status_bar.py`, `workers/comparison_worker.py`,
  `main_window.py`, and `views/folder_view.py` as needed.
- **Done when:** when Compare starts from Home, the folder view becomes visible
  immediately; when another comparison view is already active, it remains
  usable. A progress indicator appears immediately; results replace the old
  tree when ready; the status summary matches the result; progress is hidden
  on success, error, or cancellation. When the CLI sends structured events,
  the bar tracks them; otherwise it remains an animated busy indicator instead
  of displaying a false percentage.
- **Validation:** exercise Browse for each side, path replacement, Compare,
  cancel, invalid paths, and a full run. Confirm non-empty model and visible
  rows after a successful scan, using the user's real output-folder pair as a
  large manual smoke dataset. Keep an automated small fixture for repeatable
  assertions; do not make tests depend on those machine-specific paths.
- **Live result (2026-11-08):** the supplied pair completed in about 238 seconds.
  Folder view and an indeterminate progress bar appeared immediately; the
  result contained 139,846 report entries, 139,847 tree nodes including root,
  and 2,115 top-level rows. Progress hid on completion. The footer counts
  aggregated visible tree rows; its tooltip explains the difference from raw
  CLI summary counts and the file-only Next/Previous counter. Automated GUI
  tests cover Browse replacement on each side, invalid-path rejection before
  scanning, cancel-state/progress cleanup, and cancelling a running process.
  A second automated GUI check against the release CLI compared 100 entries,
  showed seven structured events through `done`, and hid progress on success.
  In a 50,000-entry run, cancelling through MainWindow stopped the CLI in about
  50 ms, preserved the “Cancelled” status, and kept progress hidden. The tested
  release is now installed; live desktop interaction remains open.

### 0e. Missing-side metadata clarity

For a row whose status is **Left Only** or **Right Only**, show a grey “—” in
the absent side's size and date cells, with a tooltip that says which side has
no item. Keep real metadata visible on the side that contains the item. Leave
other unavailable metadata blank; a missing value by itself is not proof that
the item is absent.

- **Touches:** `models/tree_model.py`.
- **Done when:** both orphan directions render the marker and accurate tooltip,
  and all present-side values remain unchanged.
- **Validation:** model tests cover both directions; check contrast in the
  user's light and dark themes during the live UI review.

## Phase A — Tier 1

### A4. Auto-refresh

**Implementation progress (2026-11-08):** Local file and directory paths are
indexed off the GUI thread and watched in batches. Paths rejected by the OS are
checked by a non-overlapping, two-second background metadata poll; the
coverage and 300,000-path inventory cap are reported in the status-bar
tooltip. Folder changes mark the current session stale immediately, and the
existing Refresh/F5 action becomes **Refresh Now ***. An opt-in setting waits
one second after the last event before re-comparing. Refresh preserves the
selected path and both tree scroll positions. Session switches and closes stop
the active watcher. Small-fixture tests pass; the large manual dataset and live
desktop check remain pending, so auto-refresh stays off by default.

- **Behaviour:** watch both roots and mark the session stale when contents
  change. Offer one-click refresh; automatic re-compare is opt-in and debounced.
- **Touches:** a watcher worker, `main_window.py`, and a setting in
  `settings_dialog.py`. Preserve the selected relative path and scroll position
  across a refresh.
- **Done when:** a controlled edit under either root marks the result stale
  within 2 seconds; opt-in auto-refresh runs after a quiet period; watchers stop
  when their session closes. If the platform cannot watch every directory,
  report that limit and use a bounded fallback rather than silently missing
  changes.
- **Risk:** OS watch limits and event coalescing on large trees. Start disabled
  by default and validate with the large manual dataset before enabling it for
  large trees.

### A5. Reports

**Audit result (2026-11-08):**
[`dialogs/export_dialog.py`](../teczka/teczka/dialogs/export_dialog.py) was not
connected to the File menu. It now exports CSV, JSON, plain text, HTML, and XML
from the folder view's accepted rows; this uses the post-criteria and
post-file-filter report and the active view proxy for status, search, and newer
filters. A separate File menu action exports the active two-sided text view as
side-by-side HTML. HTML values are escaped, XML uses an XML serializer, and
focused tests verify the summaries and paths, and a headless Chrome check
  successfully rendered the folder HTML. MainWindow tests now trigger both File
  menu actions and exercise their destination controls with temporary outputs;
  live desktop dialog interaction remains pending.

- **Behaviour:** folder report in HTML/CSV/XML as needed, using the active
  criteria and filters; side-by-side HTML for a text diff.
- **Done when:** report counts match the corresponding visible result set,
  column values and paths are correctly escaped, and the HTML opens in a
  browser. Add tests for filtered and criteria-adjusted reports.

### A6. Remote folder comparison

Separate remote **read/compare** from remote **copy/sync**. The CLI VFS supports
S3, SFTP, and WebDAV schemes in cloud builds. Teczka now preserves URL syntax in
the breadcrumb bar, skips local `Path.exists()` checks for remote roots, and
requires the configured CLI to advertise each scheme through
`capabilities --json` before starting the scan.

**Implemented:** source capability discovery is feature-gated in the CLI;
remote roots are sanitized in logs and rejected when URLs embed credentials,
queries, or fragments; stale CLIs without `source_schemes` fail with an update
message. The folder preview uses CLI `read --out` for remote text files up to
64 KB. Activating a selected remote row reads both sides through streaming
`read --out`, stages them in a private temporary directory, and opens the
existing text, table, image, or hex viewer. The staged files are removed after
the local viewer finishes loading. Fake-CLI GUI tests cover type routing,
cleanup, traversal rejection, and credential-safe errors. Local watchers
receive only local roots. Attribute columns avoid local `stat()` calls for
remote roots. Copy, sync, delete, rename, touch, and other direct local file
actions are disabled for remote sessions, with a UI explanation. The
standalone file-pair dialog also accepts supported remote URLs, capability-
checks them, and stages remote or mixed local/remote pairs through the CLI;
per-side relative names allow different basenames.

- **Credentials:** the GUI passes endpoint URLs without embedded secrets and
  inherits the CLI's configured provider chain/environment for AWS, SFTP, and
  WebDAV authentication. Logs include only the scheme and host. A dedicated
  keyring UI remains out of scope until a shared credential contract exists.
- **Remaining scope:** verify scans, previews, and staged file pairs against
  controlled S3, SFTP, and WebDAV endpoints using the minimum packaged CLI,
  including actionable unavailable-endpoint errors and credential-safe
  diagnostics.
- **Done when:** local comparisons are unchanged; each advertised remote scheme
  passes controlled scan, preview, and selected-row viewer integration checks;
  unavailable endpoints show the CLI's actionable error; remote previews and
  mutations cannot fall through to local filesystem operations.

### A7. Resume interrupted sync

The CLI handles graceful sync cancellation between actions and during chunked
file transfers. It saves an atomic run manifest under the configured checkpoint
directory, exposes `sync-checkpoints` and `sync-discard`, and resumes with
`sync --resume-checkpoint ID` after checking that roots and sync options match.
Resume rescans both roots to build the current action list; completed paths fall
out of that list, while partial large-file copies validate the source and
destination hashes before continuing. Teczka's Stop button asks the CLI to stop
gracefully, passes a persistent checkpoint directory, and reports completed
and remaining actions. Teczka's Sync dialog lists saved runs for the active root
pair. It restores their sync options when resuming and requires confirmation
before resuming or discarding. Discard removes the manifest and matching
per-file checkpoint metadata; partial destination files remain.

- **Done when:** a GUI-started sync can be interrupted and resumed without
  recopying completed work, changed sources are detected before continuation,
  and the UI reports completed, remaining, and failed actions accurately.
- **Validation so far:** core tests cover interrupted large-file copy/resume
  and changed-source invalidation; CLI tests send SIGTERM during sync and verify
  exit 130, a cancelled JSON report, and cancellation journal events. Checkpoint
  unit tests cover metadata round-trip, option mismatch, and discard; a CLI
  integration test covers manifest creation, listing, resume, and discard.
  Qt worker tests cover parsing the exit-130 report, and GUI tests cover saved
  run filtering, resume option restoration, and resume/discard confirmation.
  CLI integration sends SIGTERM to a real sync process, confirms the cancelled
  manifest, then resumes it in a new process and verifies the copied file.
  Live GUI Stop/Resume interaction remains open.

### A8. Touch and attributes audit

**Source audit (2026-11-08):** Touch and copy-timestamp exist
(`os.utime` in `main_window.py`). The **Attributes** context-menu command now
opens a side-by-side Properties dialog with file type, size, mode, owner/group,
timestamps, symlink target, and an explicit missing-side state. Automated tests
cover both sides, symlinks, and path copying. There is no `chmod` or permission
editing; confirm the dialog in the live UI, then decide whether permission
editing is wanted. If so, add it for local sources only and keep it disabled
for remote sources until they have remote-safe implementations.

## Phase E — Folder-view workflow (implemented 2026-11-08)

Daily-use behaviour added after the first Tier 1 items. Code is in
`views/folder_view.py`, `models/tree_model.py`, `bulk_actions.py`,
`utils/bulk_select.py` and the two dialogs named below.

### E1. Identical pill and Newer-mode restore

The default mode used to hide identical files regardless of the Identical pill,
so ticking the pill did nothing. The default now defers to the pills. Entering a
Newer mode remembers the pills and returning to **All Differences** restores
them; switching between Left and Right Newer keeps the first saved state.

### E2. Select identical on the LHS, then delete

- **Select:** **Edit → Select Identical on LHS…** (`dialogs/identical_select_dialog.py`)
  offers *files only* or *also folders that contain only identical items*, with
  live counts. A folder qualifies only if it exists on both sides and every
  entry beneath it is an identical item present on both sides. Only top-most
  folders are returned. Selection switches to LHS-only (E4).
- **Folder safety:** the folder option is disabled while a file filter or ignore
  patterns are active, because files excluded from the comparison could still
  sit inside a folder that looks identical.
- **Delete:** **Edit → Delete Selected (LHS)…** reuses `DeleteDialog` with a
  warning when some selected items are not identical, a dry run ticked by
  default, and Move to trash ticked by default. It deletes relative to the root
  that was actually scanned (`report.left`), never the path bar, and never
  touches the right side.
- **Undo:** trash relies on the system trash. A permanent delete asks for a
  second confirmation and is not undoable; no backup copy is made because
  copying every identical file would double disk use (the dev machine's disk was
  ~98% full).
- **Still to verify:** tests use permanent delete in a temporary folder, so the
  real `QFile.moveToTrash` path has not run; the flow has not been run on the
  large dataset.

### E3. Column fit and header column chooser

- **Fit:** columns fit their visible contents on load, expand, collapse and
  filter changes, sampling a bounded 300 rows so large trees stay fast. A manual
  drag stops auto-fit for the session; **View → Fit Columns to Contents**
  (`Ctrl+Shift+W`) or the header menu re-fits. The Name column is capped at 60%
  of the viewport. Saved widths no longer block fitting on a new comparison.
- **Chooser:** right-click a column header to toggle Size, Date, Status, Type,
  Permissions, Owner, Group, Accessed, Changed and Folder, plus Fit and Reset.
  Each panel shows its own side's value; a missing side shows “—”.
  Left-click is left free for future sorting.
- **How values are read:** extra attributes are `lstat`ed lazily for visible
  rows against the scanned roots (recorded on the tree's root node), cached up
  to 50,000 entries, and blank for remote or unreadable sources.
- **Persistence:** the chosen columns are stored with the widths in
  `folder_columns["visible"]`.
- **Bug found and fixed:** hiding or showing a column emits `sectionResized`,
  which was mistaken for a user drag and turned auto-fit off.

### E4. Selection scope

Selecting a row in one panel selects it in the other. **Alt+Left** limits the
selection to the LHS panel, **Alt+Right** to the RHS panel, and pressing the same
shortcut again restores both. In a limited mode the other panel cannot hold a
selection. The status bar reports the mode. Plain Left/Right stay with the tree
(collapse/expand) and Alt+Down is already taken by the app, so neither is used.

### E5. Smart selection by status and criteria

**Edit → Smart Select…** opens the existing Smart Selection dialog. It can
select or deselect rows accepted by the active view filters by status, newer
side, relative-path glob, and LHS size. This includes rows inside collapsed
folders. The selection can target the LHS panel, RHS panel, or both. Quick
**All**, **None**, and **Invert** actions follow the selected panel scope.
Search and view filters remain active. Status matching uses the folder tree's
aggregated statuses, so groups such as **Left Only** and **Different** can be
selected without selecting unrelated rows. When both status and newer-side
filters are set, a row must match both; multiple choices within either group
are alternatives.
Newer compares the raw modification times, so equal or missing timestamps do
not match either side.

- **Validation:** pure tests cover status, glob, size, both newer-side
  comparisons, and timestamp ties; FolderView tests cover replace/add/remove
  semantics; MainWindow tests cover selecting and deselecting Left Only rows,
  selecting newer rows on the RHS, and selecting orphans on both panels. The
  focused selection tests and complete 198-test GUI suite pass. Live dialog
  interaction remains open.

## Phase F — Beyond Compare 5 review and new feature backlog (2026-11-08)

**Method.** Beyond Compare 5.2.7 (trial mode) was driven live inside an
isolated virtual X display (Xvfb) with synthetic mouse and keyboard input, on a
small test pair covering identical, changed, newer-right, orphan, text, CSV,
binary and image files. The first attempt on the real desktop was abandoned
because input reached other windows. The tables below combine what was seen
live with BC's bundled offline help (`/usr/share/doc/bcompare/help`) and a
search of teczka's source. "Not found" means no matching teczka code.

**Seen live in BC**

- **Colour and marker model.** Orphans purple, differences red, the older side
  grey, plus a middle-gutter `≠` marker column and per-row timestamps. Teczka
  already colours by status; the gutter marker column is a candidate.
- **Quick tests only by default.** With size + timestamp (2 s tolerance), a
  same-size file with the same timestamp (`bin.dat`, `t.csv`) shows as
  *same*. After opening such a file in a viewer, BC updated the folder row to
  *different*: **opening a file re-compares it and updates the folder status.**
  Teczka should do the same instead of leaving a stale status.
- **Per-view scope of settings.** Session Settings has tabs Specs, Comparison,
  Handling, Name Filters, Other Filters and Misc, and every settings dialog
  has a scope selector ("Use for this view only" / session / defaults).
- **Folder toolbar:** Home, Sessions, All / Diffs / Same, Files, **Minor**
  (ignore unimportant differences), **Rules**, Copy, Expand, Collapse, Select,
  Files, Refresh, Swap, Stop, a Filters box with history, and **Peek**.
- **Menus.** Session has New Session / Tab / Window, Open Session, **Load
  Workspace** and Save Workspace As (a workspace is a saved set of tabs),
  Save Session, Locked, Back (**Alt+Left**), Forward, Browse for Folder and Up
  One Level. View has the full filter family (Show Left Newer, Right Newer,
  Left/Right Orphans and combinations), Always Show Folders, Compare Files
  and Folder Structure, Only Compare Files, Ignore Folder Structure,
  Suppress Filters, Columns, Legend, Log and Toolbar. Tools has Options, File
  Formats, Profiles, Export/Import Settings, Restore Factory Defaults, **Save
  Snapshot** and View Patch.
- **Text Compare:** per-pane info bar (date, size, grammar, encoding, line
  ending), copy arrows in the gutter, Context, Minor, Rules, Format, Next/Prev
  Section, thumbnail map, Isolate, Replacement, Convert File, bookmarks,
  Copy File and Open Next Difference.
- **Picture Compare:** Tol / Range / Blend buttons, a tolerance slider
  (default 25), offset and zoom readout with 1:1 and fit buttons, a dimmed
  difference thumbnail, and a Meta (metadata) button.
- **Hex Compare:** side-by-side hex and ASCII with address column, differing
  bytes highlighted, Next/Prev Diff. **Table Compare:** CSV with detected
  format, header row, delimiter and date-format selectors in the info bar,
  difference markers on rows and columns.
- **Conflict to avoid:** BC uses Alt+Left/Alt+Right for Back/Forward. Teczka
  uses the same keys for the selection scope (E4); consider whether users
  coming from BC will expect history instead.
- **Folder Sync session (live).** A dedicated view with an Operations
  dropdown (Update Left, Update Right, Update Both, Mirror to Left, Mirror to
  Right), a plain-language summary ("Copy 3 file(s) and 1 folder(s) to left, 8
  bytes … Prompt for 2 file(s)"), a per-row planned-action arrow column on
  each side, `?` for conflicts that need a decision, and per-row overrides
  (Leave Alone, Copy Left to Right, Delete Left). **Peek** temporarily shows
  the rows the sync filter hides (identical items, tinted teal). Teczka's
  sync dialog has a text preview only; a per-row action column in the folder
  view is the main upgrade (see F1.1).
- **Options pages:** Startup (load/save workspace, quick compare dialog),
  Tabs, Appearance, Text Editing, Next Difference, Backups, File Operations,
  Archive Types, Commands, Open With, Tweaks.
  - **Confirmations** are separate switches: copy, move, replacing read-only
    or system files, overwriting newer files, content compare, delete,
    merge; a synchronize policy (Prompt, Yes to All, No to All); and
    "Require explicit side selection in the Delete dialog".
  - **Filtered Items:** "Include hidden items by default" (off). Actions on a
    folder only touch items hidden by filters when this is on. This matches
    teczka's E2 rule that folder deletes are disabled while filters are
    active; BC offers an explicit opt-in instead of a block.
  - **Backups:** back up before copy and before save, with naming patterns
    (`abc.~txt`, `abc.txt~`, `abc.bak`, `~abc.txt`, `abc.bak.txt`) or a
    separate backup folder; all off by default. Teczka has no backup copy
    because of the disk-space constraint; trash is the only safety net.
  - **Next Difference:** go to first difference on load, advance after a
    copy, limit "Next Difference Files" to the current folder, wrap around,
    message panel.
- **Filters dialog (live).** The Name Filters tab has four lists: include
  files, exclude files, include folders, exclude folders, with **Add To
  Presets…** and Clear; defaults are `*.*` and `*`. A scope selector at the
  bottom picks "this view only" / session / defaults. The **Other Filters**
  tab adds items that filter on **Date modified** (older/newer than N days),
  **Size**, **file Content** (text inside the file), or **Unix file type**,
  each set to include or exclude. Teczka's filter dialog covers the name
  lists and presets; date, size, content and file-type filters are the gap
  (F1.11), and content filtering would need a scan-time hook.
- **Folder Merge (live).** A three-way folder view: Left, Ancestor (centre)
  and Right panes plus a **Merge to** target (Left, Right or another folder)
  and an action column. Toolbar: Minor, **Same OK** (ignore same changes),
  Rules, **Merge**, **To Output**. Colours: orange = conflict (both sides
  changed), cyan = changed on one side only, purple = orphan. Per-row
  arrows show the planned merge step. View has Show Changes, **Show
  Conflicts**, Show Left/Right Changes, **Show Mergeable**, Show Unchanged,
  Center Pane toggle. Actions has **Merge…** (opens the three-way text
  merge for that file), **Copy to Output…**, and Compare Contents. Teczka
  has a three-way *file* merge but no folder-level equivalent (already Phase
  C "recursive three-way folder merge"); this is its reference design.
- Opening a comparison **auto-saves a session** under Sessions → Auto-saved →
  Today; this also happened for the test pair in the real BC profile.

### F1. Gaps in Folder Compare (highest value, because this is the main view)

| # | BC feature | Teczka today | Size |
|---|---|---|---|
| F1.0 | **Re-compare a pair after opening it in a viewer** and update the folder row status (seen live; quick tests can miss same-size, same-time edits) | ✅ For paired files opened from a folder scan using quick criteria, a background byte comparison updates the report entry, tree row and ancestors, summary, and navigation cache; content-mode scans already compare contents | Implemented and covered by focused tests; live interaction remains open |
| F1.1 | **Sync modes and sync view**: Update Left/Right/Both and **Mirror to Left/Right** (mirror replaces differing items, deletes orphans on the target); a summary line ("Copy N files to left, X bytes … Prompt for M"); a **planned-action column** per row with `?` for conflicts; per-row overrides (Leave Alone, Copy, Delete); **Peek** to show hidden rows | Update Left/Right/Both and Mirror to Left/Right are available. The text preview summarizes action counts and lists up to 300 operations; mirror execution confirms deletes and defaults to trash. No byte totals, per-row action column/overrides, or Peek yet. | Mirror modes and count summary implemented; remaining work is byte totals and the per-row planned-action workflow, including Peek |
| F1.2 | **Select Newer / Select Orphans** on Left, Right or Both | ✅ Smart Select supports left-newer/right-newer criteria and sends the resulting row selection to the left, right, or both panels | Implemented; pure and MainWindow tests cover side comparison, ties, right-panel selection, and both-panel orphan selection; live dialog interaction remains open |
| F1.3 | **Invert Selection**, **Select All Files** | All/None/Invert exist for rows accepted by the active filters (E5); the Files Only folder-view mode limits the available rows to files | Done; All follows filtered rows, including collapsed descendants, so use Files Only mode for file-only selection |
| F1.4 | **Up One Level** (Left/Right/Both), **Set as Base Folder** on this or the other side, **Compare Parent Folders**, Back/Forward history of base folders | Breadcrumbs can set a base; no Up One Level or Back/Forward | S–M |
| F1.5 | **Quick Compare** of two selected files regardless of position, and **Compare To** (pick one, click a second) | A "Compare Selected" action exists in the file context menus; no cross-position folder-view equivalent | M |
| F1.6 | **Align With** for folder rows (manual alignment override for renamed files), **Align filenames with different extensions / Unicode forms** | An Align dialog exists for text; not for folder rows | M |
| F1.7 | **Session Settings dialog** per session: base folders, description, **Disable editing** (read-only protect), Locked | Settings are spread across menus; no per-session read-only lock | M: a read-only lock is cheap and guards the destructive actions |
| F1.8 | **Folder Compare Info** (statistics) and **Legend** | A stats dialog and a colour legend exist | Verify parity only |
| F1.9 | **Handling options**: follow symbolic links, archives as files / as folders, expand only subfolders with differences when loading, background subfolder scan | Archive browsing exists; the other switches are not exposed | M |
| F1.10 | **Comparison options**: ignore DST and timezone differences, compare filename case, compare Unix permissions/owner/group, "skip content test if quick tests say same", "override quick test results" | Criteria dialog covers size/time criteria and tolerance. The listed BC options are not implemented. | Layer-specific: timestamp tolerance belongs in `criteria.py`; filename-case pairing needs CLI traversal/schema support; Unix metadata needs CLI and report/model fields; skip-content changes scanner policy; override-quick-results needs an explicit GUI policy |
| F1.11 | **Other filters**: Date modified (older/newer than N days), Size, file **Content**, Unix file type, each include or exclude; "exclude protected OS files" | Name include/exclude filters exist; these additional filters are not implemented | Date and size can be post-scan predicates; content needs bounded per-file reads or a scan-time hook; Unix type needs CLI metadata; protected-OS exclusions need a documented cross-platform rule |
| F1.12 | **Copy / Move to Folder**, **New Folder**, **Rename**, **Touch**, **Attributes**, **Exchange**, **Copy Filename**, **Explorer** context menu (reveal in file manager) | Most exist; Exchange and "reveal in file manager" not found | S |
| F1.13 | **Compare Contents** on selected rows only (re-run a content check without a rescan), **Refresh Selection** | Full refresh only | M: needs per-path CLI scan |
| F1.14 | **Log panel** showing operation results | Status bar messages only; no log panel found | S–M |

| F1.15 | **Confirmation and backup policy**: separate confirm switches (copy, move, overwrite newer, replace read-only/system, delete, content compare); "require explicit side selection" in Delete; "Include hidden items by default" for folder actions on filtered folders; optional backup before copy/save with naming patterns | One confirm flow per action; trash and dry-run defaults; folder delete blocked while filters are active; no backups (disk is nearly full) | S–M: a settings page plus passing the policy to `bulk_actions` and the sync dialog. Backups stay out of scope until disk space allows |
| F1.16 | **Settings scope selector** ("this view only" / session / defaults) on every settings dialog | File filters and criteria are per-session and saved in app config, with no explicit scope choice | S–M, UI plus `SessionState`/`AppConfig` split |

### F2. Gaps in the file viewers

| View | BC feature | Size |
|---|---|---|
| Text | **Go To line/column**, **Replace**, bookmarks 0–9, **Isolate** lines, **Align With** lines | S–M each |
| Text | **Convert File**: trim trailing whitespace, tabs↔spaces, line-ending change | S |
| Text | **Show Context** exists; **Show Same** and **Show None** filters; **Next/Previous Difference Section**; **Next Edit** | S |
| Text | **Open Clipboard** into a pane and **Compare Selection to Clipboard** | S |
| Text | **Copy File to Right/Left and Open Next Difference** (one-key review workflow from a folder session) | S–M, high daily value |
| Text | **Over-Under layout**, **Thumbnail** change map, **Ruler**, **Alignment details**, **Webpage** preview for HTML | M each; thumbnail map is the most useful |
| Hex | **Data inspector** (little/big endian values at cursor), **Go To byte**, byte-address toggle | S–M |
| Table | **Insert/Delete Row and Column**, **Hide Same Columns**, **Resize Columns to Fit**, **Next Difference Sheet**, **Sort** | M |
| Picture | **Tolerance, Mismatch Range, Blend** modes exist; missing: **rotate/flip**, **Compare Metadata (EXIF)**, **Reset Difference Offset**, **Auto Scale** | S–M |
| Merge | Three-way merge exists; check **Take Both** ordering and conflict navigation against BC's merge output pane | Verify only |

### F3. Platform and workflow features

| # | Feature | Notes | Size |
|---|---|---|---|
| F3.1 | **Snapshots** (`.bcss`): a read-only listing of a folder with size, time, attributes and optional CRC, loadable as a base folder | Not found in teczka. It needs a CLI `snapshot` command or a Python writer; CRC mode detects bit rot | L |
| F3.2 | **Session files and workspaces**: save/load named sessions, a **workspace** (saved set of tabs) loaded at startup, auto-saved recent sessions, open one from the command line | A session tab bar and profiles exist; confirm save/reload fidelity, and whether the profiles dialog already covers workspaces | M |
| F3.3 | **Scripting and command line** (`bcompare @script`, `/fv`, `/qc`) | Teczka has few CLI options. A small `teczka --left L --right R --mode folder` entry point is cheap | S |
| F3.4 | **Difftool/mergetool integration** for git | Already listed in Phase B | S |
| F3.5 | **Folder Merge**: Left/Ancestor/Right panes, Merge-to target, orange conflicts and cyan one-sided changes, Show Conflicts / Mergeable filters, Merge… and Copy to Output… | Phase C; needs a CLI three-way folder classification before any GUI work | L |
| F3.6 | **Source control submenu** (add, check in, show history) | Skip unless a git workflow is requested | L |
| F3.7 | **Registry, MP3 tags, executable version** compare | Not relevant on Linux or low demand; skip | — |

### F4. Work packages, in order

Each package lists its first deliverable, completion check, and current state.
Delivery conventions below apply to all of them.

| # | Package | First deliverable | Done when | Status |
|---|---|---|---|---|
| P1 | **F1.0 re-compare on open** | After opening a folder-pair file under quick criteria, compare its bytes in a background worker and update the row, ancestor folders, summary, and navigation | A same-size, same-time pair with different bytes flips from Identical to Different after opening; counts, pills and Next/Previous follow | **Status 2026-11-08: ✅ implemented** (`_prepare_opened_pair_recompare`, `test_file_pair.py::test_opening_file_recompares_content_and_updates_folder_status`; automated checks pass; live interaction remains open) |
| P2 | **F1.2 Select Newer / Orphans** | Add newer-side criteria to Smart Select and allow the resulting row selection on Left, Right, or Both | Pure tests cover each newer side and timestamp ties; MainWindow tests cover RHS selection and two-panel orphan selection | **Status 2026-11-08: ✅ implemented** (`bulk_select.py`, `SelectDialog`, `bulk_actions.py`; tests cover both newer sides, ties, RHS and both-panel selection; live dialog interaction remains open) |
| P3 | **F1.1 Mirror sync and preview summary** | Complete mirror validation and add the planned copy byte total; later work can add per-row actions and Peek | Preview lists every delete; dry run changes nothing; trash is the default; tests cover mirror modes and orphan policies | **Status 2026-11-08: 🚧 partial** (Update Left/Right/Both and Mirror Left/Right, action-count summary, confirmation, trash default, and preview tests exist; byte totals, per-row overrides, Peek, and live execution check remain) |
| P4 | **F1.7 read-only lock** | A per-session "Disable editing" flag that blocks copy, move, delete, rename, touch and the E2 workflow, shown in the status bar | Every destructive action is blocked with a clear reason; the flag is saved per session | Planned |
| P5 | **F1.15 confirmation and filtered-item policy** | Add explicit confirmation controls and a policy for actions on folders with filtered-out children; keep backups deferred under D2 | Each covered operation follows its saved policy; folder actions disclose whether hidden items are included; tests prove cancellation and dry-run behavior | Planned |
| P6 | **F1.4 navigation** | Up One Level (Left, Right, Both), Set as Base on the other side, Back/Forward base-folder history | See decision D1 for the shortcut; history survives a rescan | Planned |
| P7 | **F2 Copy File and Open Next Difference**, **Go To**, **Replace** | Two Difference-menu actions that copy the whole file and open the next differing pair; Go To line and Replace in the text view | A scripted review of three differing files needs no mouse; undo restores the copy | Planned |
| P8 | **F1.10 / F1.11 options and filters** | Case, DST/timezone and Unix metadata criteria; date and size filters | Each criterion has a pure test; "bin.dat"-style quick-test misses are covered by P1 | Planned; filename pairing and Unix metadata need CLI/schema work |
| P9 | **F1.14 log panel, F1.12 reveal in file manager, F2 Convert File** | A collapsible log of operations with timestamps | Bulk delete and sync write their results to the log | Planned |
| P10 | **F2 thumbnail change map, hex data inspector, F1.5/F1.6 Compare To and Align** | One at a time | Each has its own widget test and a live check | Planned |
| P11 | **F3.1 snapshots, F3.3 command line, F3.5 folder merge** | A design note each, before code | A design note is reviewed before any implementation starts | Planned |

### F5. Open decisions

- **D1. Alt+Left / Alt+Right — decided 2026-11-08.** Keep them for the panel
  selection scope (E4). Base-folder Back/Forward (P6) uses
  `Alt+Shift+Left` / `Alt+Shift+Right`.
- **D2. Backups — decided.** Not planned while the disk stays near full;
  revisit if the data moves to a roomier volume.
- **D3. Folder-delete opt-in — decided.** Keep the block while filters are
  active; add an "include hidden items" switch (F1.15) that is off by default.
- **D4. Content filters (F1.11).** Needs per-file reads. Decide whether a
  size limit and a text-only restriction are acceptable.
- **D5. CLI dependencies.** P1 uses a local background byte check and needs no
  CLI change. P3 uses the current sync command's mirror mode; verify it against
  the minimum packaged CLI before enabling mirror in a release. F3.1 snapshots
  need a snapshot command or a defined Python format, and F3.5 needs a CLI
  three-way folder classification before GUI work.

Not planned: Registry, MP3 tags, executable version compare, and the source
control submenu (F3.6, F3.7).

## Phase B — Tier 2 daily-use polish

| Item | Direction |
|---|---|
| Syntax highlighting | ✅ `QSyntaxHighlighter` applies theme-aware token colors to Python, Rust, C/C++, Java, JavaScript/TypeScript, Go, shell, SQL, JSON, YAML, TOML, HTML/XML, and CSS files. Diff row and character backgrounds remain painted by the existing editor. Widget tests and the full 198-test GUI suite pass; live dark/light theme review remains pending. |
| Unimportant-text rules | ✅ View > Unimportant Text Rules edits ordered pattern/replacement/description rows with validation; rules persist per session and in app config. Content-mode folder scans apply them before tree construction, update summaries and exports, and text previews keep the original text while suppressing normalized differences. Standalone text file comparisons also use the active rules. Invalid replacement references, invalid UTF-8, and unsafe relative paths are rejected or left at the scan result. GUI tests cover the dialog, session restore, report reclassification, and preview policy. Rules currently use Python `re`; the CLI's `--regex-rule` affects text-diff output but does not normalize scan statuses, so GUI normalization remains local until the CLI contract does both. |
| Text-view options | ✅ Font and tab size come from Preferences. View > Word Wrap applies to both panes and persists per session and in app config. View > Text Context offers all lines, 1/3/5 unchanged context lines, or differences only; omitted runs show their line count, source line numbers remain visible, and editing is disabled while lines are collapsed. The selection persists per session and in app config. Focused and MainWindow tests pass; live layout check pending. |
| Standalone file-only comparison | Implemented: the File menu accepts two local files or supported remote file URLs; remote and mixed pairs are capability-checked, staged with the CLI, and routed to existing text/table/image/hex views. Dropping two local files opens a comparison directly, without scanning parent folders. Differing basenames are supported; unmatched types use hex comparison. Focused picker, MainWindow, remote CLI, and drop tests pass; a local WebDAV fixture exercises remote metadata and file reads; live desktop interaction remains pending. CLI `diff-file` accepts two local file operands without `--path`, while retaining shared-relative-path mode for source roots. |
| Image comparison modes | ✅ Image Compare now offers Side by side, Overlay/blend, Swipe, Difference, and 500 ms Blink modes. Overlay opacity and swipe boundary share a slider; Difference uses Qt composition, and swipe clipping is verified with a rendered-scene test. Pixel tolerance is adjustable from 0 to 255 and follows the CLI's per-channel `difference > tolerance` rule (default 1). Focused widget tests and the full 198-test GUI suite pass; live desktop layout and image review remain pending. |
| Folder-view navigation | 🚧 Quick find offers contains, wildcard, and regular-expression modes over relative paths. The folder tree and Next/Previous list use the same matcher, malformed regexes show an inline error, and search mode/text persist per session and in app config. The context menu now expands only folders containing differences. Open With separates the system default from a saved per-extension application, and the picker can save an application command without shell expansion. Attributes opens the side-by-side Properties dialog. Matcher, proxy, widget, MainWindow, properties, handler, and tree-navigation tests pass. A live 1400 px desktop capture confirmed the search controls fit beside the counter and the filtered rows remain readable; application-picker interaction still needs a live check. |
| VCS and shell integration | Difftool/mergetool setup, “select left / compare to,” clipboard comparison, and git revision comparison. Size each separately. |

## Phase C — Tier 3 or individually sized

Snapshots, batch scripting, audio tags, Windows Registry, executable version
information, PDF comparison, recursive three-way folder merge, nested archive
comparison, and a plugin API. The three-way file merge UI already exists; do
not describe that existing view as missing. Archive mutation is already wired
through the CLI; plan archive-specific GUI work only where the GUI cannot reach
that capability. Schedule these items individually after Tier 1 and Tier 2
priorities.

## Delivery and verification conventions

1. Before implementation, inspect the current source, menus, and CLI
   capabilities. Record whether the feature is missing, partial, or present but
   unreachable from the GUI.
2. For CLI-backed features, verify the JSON/progress contract against the
   minimum packaged executable and add a compatibility test before enabling
   controls that depend on it.
3. Persist user choices per session through `SessionState` and the app config;
   restore them in `_restore_persistent_state` and check tab switching. View-wide
   choices (visible columns, widths) live in `folder_columns`.
   Destructive actions default to dry run and trash, act only on the scanned
   roots, and say plainly when they cannot be undone.
4. Each logic change gets a focused unit test and a MainWindow-level smoke test.
   Add a live or screenshot check when layout, colors, focus, or interaction
   changes; visual changes are not considered verified by offscreen rendering
   alone.
5. Keep Next/Prev and filter changes under 1 second on the current large-tree
   benchmark. Record hardware, CLI build, entry count, and cold/warm cache state
   with measurements; do not compare unlike runs.
6. For report and filter work, use the same accepted-entry logic for rows,
   navigation, counters, and exports.
7. Deliver one reviewable feature per change set, including its tests and
   updated roadmap status. Avoid creating a commit unless requested.

## Known open issues

- `pytest-qt` is listed in the `dev` dependency group and version 4.5.0 is
  importable in the current test venv; the complete GUI suite passes (198
  tests, 2026-11-08). New environments must sync the dev group before running
  GUI tests. The tree proxy uses Qt's filter-change transaction API when
  available and keeps a fallback for PySide6 6.6–6.9.
- During this verification, two full-suite attempts exited with a native Qt
  segmentation fault while pytest processed events. The 86-test ordered prefix
  including all MergeView tests passed, the error-path MergeView test passed
  in isolation, and the final full-suite rerun passed all 198 tests. Revisit if
  the native crash recurs.
- The installed `~/.local/bin/rcompare_cli` is SHA-256 matched to the tested
  workspace release and the default MainWindow consumes its structured scan
  progress. The package version remains 0.1.0, so use the capability schema and
  executable hash rather than the version string to identify this build.
- Release tests verify scan, copy, and sync JSON behavior. The configured local
  executable is current; any separately packaged or distributed executable
  still needs the same contract checks before it can be treated as equivalent.
- Filter pills: the colour bug is fixed, but check contrast in the dark theme;
  offscreen rendering is not evidence for the user's desktop theme.
- The status bar is crowded at ~1300 px (summary, five pills, three new
  buttons, search, counter). The summary label now shrinks with a tooltip, but
  decide whether the Newer and Filters controls belong in a menu or a second
  row at narrow widths.
- The pre-upgrade `capabilities --json` over-reported `scan` progress and
  omitted accepted flags (see the CLI verification table). The installed
  release now derives reported flags from Clap; verify separately packaged
  builds before relying on their capability reports.
- Unimportant-text patterns use Python `re`, whose syntax and edge cases can
  differ from the Rust regex implementation used by the CLI. Keep the GUI's
  behavior explicit until both paths share a tested rule contract.
- Next/Prev and the tree proxy share quick-find, status-pill, and Diff Options
  predicates from `utils/name_search.py` and `utils/view_filter.py`; parity tests
  cover all ten Diff Options modes and multiple pill combinations.
- Report export uses the active folder proxy; focused tests, MainWindow action
  flows, and headless browser rendering pass, but live desktop dialog
  interaction remains unverified.
- Phase E gaps: the header column menu was exercised through its code paths,
  not by looking at the popup; the trash delete path and the select-and-delete
  flow have not run on real folders; Alt+Left/Right is verified only in the
  Wayland session used for testing; attribute columns cost about a second to
  switch on at ~120k entries.
- The merge view now has focused automated coverage for its merge algorithm,
  conflict resolution, background loading, stale results, errors, and saving.
  Broader merge interaction plus sync, export, profile, and remote flows remain
  thin; see [roadmap.md §4 and §6](roadmap.md#4-teczka-gui).

## Suggested order

Finish the pending live checks for 0d, A8, A5 and Phase E (trash delete, header
menu, Alt+arrow scope), then validate A4 against the large manual dataset and
re-baseline the measurements after the dataset-drift question is settled.
Phase F P1 and P2 are implemented with automated coverage; their remaining
work is live interaction review. Next, finish P3 by adding the planned byte
total and validating mirror preview/dry-run/trash behavior, then implement P4's
per-session read-only lock and P5's confirmation/filter policy. Continue with
P6 navigation and P7 viewer workflow, then the remaining Phase B verification,
A6 remote comparison, and A7 live GUI Stop/Resume validation. The CLI restart
after real cancellation and GUI recovery controls are covered by automated
tests. Reorder when the roadmap or CLI capability baseline changes.
