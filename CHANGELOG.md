# Changelog

All notable changes to RCompare will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed (2026-07-26) — teczka Phase 5: correctness and contract

Implements `docs/development-plan.md` WI-5.1 through WI-5.11. Every item below
was a *verified* runtime defect, not a refinement; each now has a test.

**Visible state is authoritative (WI-5.7).** The redesigned shell created a
visible session bar, path bar and status bar, then kept hidden `FilterBar`,
`ColorLegend`, `QTabBar`, status-label and progress widgets as compatibility
shims that still owned the behaviour:

- 49 operations wrote to `statusBar().showMessage()` after the native status
  bar had been hidden, so copy, delete, rename, sync, bookmark and drag/drop
  produced no visible feedback at all. All of them now route through
  `IntegratedStatusBar.show_message()`.
- Structured progress updated a detached `QProgressBar`/`QLabel` pair, leaving
  the visible bar at 0%. It now drives the real bar and stage label.
- `IntegratedStatusBar.set_diff_position()` had no caller, so the difference
  counter read `0/0` permanently. Next/Previous now updates it.
- Every compatibility shim is deleted. A test rejects new `statusBar()` writes.

**Sessions, documents and 3-Way Merge (WI-5.8).**

- `_on_close_tab()` compared a visible session index against the number of
  *view* tabs (6), so the first six session tabs could not be closed and any
  close that did happen deleted the wrong session. Session indices are now
  their own space.
- Comparisons opened by double-clicking a file were registered in a *hidden*
  tab bar: the document appeared in the view stack with no visible tab, no
  close action and no return path. New `DocumentTabBar` makes them real.
- The sidebar offered a "3-Way Merge" destination the view stack did not
  have, so selecting it did nothing. The merge view is now built at a fixed
  stack index and the destination works.
- Home emitted `profile_selected` into nothing, and read its profile list from
  `comparison_settings["profiles"]` — a key `ProfileManager` never writes. Both
  sides now go through `ProfileManager`.
- Home rendered a Recent Sessions section that no production code populated. A
  completed comparison now records the pair.

**Filters agreed with results (WI-5.9).** Filter state lived in four places at
once and they disagreed:

- the proxy defaulted to `show_differences` while all four status pills showed
  as enabled, so "Identical" read *on* while identical rows were hidden;
- View-menu toggles wrote only into the hidden `FilterBar`, whose signals were
  never connected, so they changed nothing;
- clicking a visible status pill passed `show_files_only=True`, silently hiding
  every folder row;
- session capture later read the stale hidden values;
- `Ctrl+F` focused the hidden search field, so typing went nowhere;
- Find Next/Previous always targeted Folder view even from Text/Hex/Image/Table.

One typed `FolderFilterState` is now the single source of truth, and a
state-matrix test drives each input surface and asserts the proxy, menu, footer
and persisted session agree.

**Settings round-trip (WI-5.10).** Two Settings handlers existed: the connected
one discarded `get_config_updates()`, so Theme and CLI Path were silently
dropped, while the more complete one was wired to nothing. They are now one
handler, and:

- the Diff Options page (whitespace, case, specialised comparisons, regex) and
  the Files page (encoding, EOL, binary patterns) are persisted and reach the
  scan as real `rcompare_cli` flags — previously none of them were even read
  back from the dialog;
- the theme is applied at startup and live on change. Neither stylesheet had
  ever been loaded. A new "Follow system" default applies no stylesheet, so
  Plasma dark mode, the user's accent colour and high-contrast schemes show
  through;
- an unusable CLI path is rejected with a reason instead of surfacing later as
  a failed comparison, and the error message names Settings rather than the
  nonexistent "Tools > Options".

**Path commands and action state (WI-5.11).** `CompactPathBar` swapped its own
breadcrumbs *and* emitted `swap_requested`, whose handler swapped again — two
swaps, no visible change. The widget now only signals intent. Compare is
disabled until both paths and a working CLI are present, and copy/sync/apply/
save/print are enabled only where the active document supports them, each with
a tooltip explaining any block.

**Keyboard (WI-5.1).** `QKeySequence.StandardKey.Quit` resolves to the `Exit`
*multimedia* key on Linux, so `Ctrl+Q` did not quit; `StandardKey.Preferences`
hit the same trap. `Ctrl+P` was bound to both Print and Profiles, and `Ctrl+Y`
to both Redo and Synchronize. Bindings are validated, the two collisions are
rebound, and the About dialog's keyboard table is generated from the live
action registry instead of a hand-maintained second copy that had drifted.

**CLI contract (WI-5.2).** `rcompare_cli` emits `schema_version`; teczka never
read it and parsed by direct subscripting, so drift surfaced as a `KeyError`
inside a worker thread. The version is checked at the boundary and a mismatch
names both the expected and received versions.

**CSV row alignment (WI-5.3).** Rows were aligned positionally, so a left-only
and a right-only row were paired and reported as "different" while the summary
claimed zero left-only and zero right-only — wrong output, not just a
limitation. One inserted row cascaded through the whole file. Added
`--csv-key` to `rcompare_cli scan`, plus a key-column selector and a "first row
is a header" toggle in teczka's table view (which also retires the hardcoded
`Col 1/2/3` labels that left no column name to select).

**Worker cancellation (WI-5.4).** `FunctionWorker` had no cancellation path, so
a long parse could only be orphaned — and would still deliver its result. Added
a cooperative `CancelToken`; a cancelled worker can never update the GUI.

**EXIF comparison (WI-5.5).** `rcompare_core` implements EXIF comparison and
the CLI exposes `--image-exif`, but the image view never requested or displayed
it. The image view now shows a differences table, fed either locally via Pillow
or from the CLI report.

**Drag and drop (WI-5.6).** Dropping more than two paths kept the first two and
discarded the rest in silence; the discarded paths are now named.

### Changed (2026-07-26) — teczka accessibility and presentation

Opportunistic slices of Phase 7 that the Phase 5 work touched directly:

- The four folder-status pills failed WCAG AA for normal text — measured at
  2.78:1 (green), 3.63:1 (red), 3.59:1 (blue) and 3.76:1 (right-only red)
  against white. Recoloured above 4.5:1, with the measured ratios pinned as
  test fixtures. In the unchecked state foreground and background both resolved
  to `palette(mid)`, making the label invisible; fixed.
- Status is no longer communicated by colour alone: each pill carries a
  distinct non-colour marker that survives monochrome and common colour-vision
  deficiencies.
- `NoFocus` removed from the status pills and the difference-navigation
  buttons, which had made the whole filter row unreachable without a mouse.
- Accessible names added to the icon-only swap, browse and navigation controls;
  Home cards expose their title as the button's own accessible name rather than
  only as a child label.
- Icon lookup for the path bar and Home now falls back to embedded SVGs, so a
  session without a complete FreeDesktop theme no longer renders blank controls.
- Home is a responsive scrollable grid instead of a fixed 2x2 of 180x140 cards
  that clipped at the declared 800x600 minimum, and it now covers every
  reachable comparison type including Table and 3-Way Merge.
- Folder-only chrome (status pills, name filter, folder paths) is disabled or
  hidden outside Folder Compare, where it controlled nothing.
- Removed the "Configure Toolbars..." placeholder, which had no configurable
  toolbar behind it since the toolbar was removed. "About KDE" appears only in
  a KDE session.


### Changed (2026-07-26) — teczka renders comparisons while they run

- teczka now drives `rcompare_cli --jsonl` and builds the folder tree
  incrementally as entries stream in, instead of buffering the whole JSON
  document and parsing it after the process exits. On a 40k-entry comparison
  the first results appear at **~415 ms instead of ~1230 ms**, the total is
  known from the first line (the summary is emitted first), and the worst
  event-loop stall drops to **72 ms with no pause over 100 ms**.
- Decoding is capped per event-loop pass and partial trees are published on a
  timer that backs off as the result set grows, so snapshot cost stays a
  roughly fixed share of runtime rather than dominating large comparisons.
- `--jsonl` is feature-detected through `rcompare_cli capabilities` and cached;
  binaries that predate the flag keep the previous all-at-once behaviour. The
  GUI and the CLI are installed independently, so a stale
  `~/.cargo/bin/rcompare_cli` must not be assumed to match the GUI.
- Folder filter changes are coalesced behind a 120 ms timer. Applying filters
  walks the whole tree and was running inline on every pill click.

### Fixed (2026-07-26) — teczka startup and CLI error reporting

- Restored startup: `_build_toolbar()` was still called after the toolbar was
  removed, and `_tb_compare`/`_tb_cancel` were still toggled in four places;
  the session tab bar's `set_comparing()` already covers both. Also supplied
  the missing `_close_session`, `_on_home_profile_selected`,
  `_record_recent_session` and `_update_action_states` methods, and converted
  the two remaining `_on_filters_changed` callers to `_apply_filter_state`.
- A CLI invocation that fails argument parsing is no longer reported as a
  successful empty comparison. `clap` exits 2 on a usage error, which teczka
  treated as "differences found"; an empty result with diagnostic output on
  stderr is now surfaced as an error.

### Added (2026-07-25) — teczka folder selection

- Added folder-picker ("Browse") buttons to both sides of the path bar, and a
  third for the base path in three-way mode. Previously the only folder chooser
  was buried in a menu action.
- Folder selection now goes through `QFileDialog.getExistingDirectoryUrl` with
  the desktop's native/portal chooser (`teczka/utils/path_picker.py`), so
  network locations (SFTP/SMB/WebDAV/MTP) reachable from the system file
  dialog can be selected. Locations the desktop mounts locally (kio-fuse,
  GVfs) are handed to the comparison engine as ordinary paths; unmounted
  remote schemes are reported instead of being passed down as unusable strings.
- teczka now prefers the XDG desktop portal platform theme when the session
  provides one, and no longer forces the Fusion widget style over the
  system's (e.g. Breeze on Plasma).

### Fixed (2026-07-25) — teczka UI defects found while reviewing against Beyond Compare

- The integrated status bar stayed on "Comparing..." forever: it was set when a
  scan started and reset on cancel and error, but never on success. It now
  shows the comparison summary.
- Path breadcrumbs were clipped along their lower edge. The scroll area was
  pinned to a `QLineEdit`'s height while its horizontal scrollbar rendered
  inside that height, cutting off the segment text; the row height was also
  hardcoded at 32px, which clipped further under display scaling. The
  scrollbar is gone (breadcrumbs auto-scroll to the deepest segment) and both
  row heights now derive from the current font.
- The hex compare view was pinned to the bottom of its pane with roughly half
  the area left empty, because its title label and the splitter both had a
  zero stretch factor and the label absorbed the extra space.
- The welcome dialog no longer blocks every launch: it is skipped when left or
  right paths are supplied (command line, desktop file, `xdg-open`) and offers
  a "don't show this again" choice that is remembered.

### Changed (2026-07-25) — Documentation consolidation

- Replaced five overlapping/stale roadmap docs (`GAPS.md`, `ROADMAP.md`,
  `ROADMAP_VFS.md`, `docs/RCOMPARE_CLI_FEATURE_ROADMAP.md`,
  `docs/RCOMPARE_PYSIDE_GITHUB_PLAN.md`) and the stale `DEVELOPMENT_STATUS.md`/
  `COMPLIANCE_MATRIX.md`/`CLOUD_FEATURES_SUMMARY.md` with a source-verified
  set: `docs/roadmap.md` (remaining work for competitive parity), `docs/status.md`,
  and one doc per workspace module under `docs/modules/`.
- A source audit while writing these found the deleted docs wrong in both
  directions: archive write (ZIP/TAR/7Z), RAR read, and Union/Filtered VFS are
  real and tested in `rcompare_core` but unreachable from `rcompare_cli` or
  teczka; the `ResumableCopy` checkpoint engine has zero callers; and several
  teczka features marked "planned" were already implemented (multi-tab
  sessions, session profiles, sync-preview dialog, drag-and-drop, a working
  three-way merge view, synced scrolling with a gutter map, a hex viewer).
  Also found three real WebDAV bugs: digest auth silently falls back to
  Basic, PROPFIND parsing is a substring search rather than real XML, and
  file mtimes are never actually read (`parse_date()` always returns "now").
  See `docs/roadmap.md` for the full, prioritized list.
- Moved dated point-in-time reports (`PR_SUMMARY.md`, `REVIEW_REPORT.md`,
  `WINMERGE_PARITY.md`/`_PHASE1.md`, `CI_AND_PATTERN_IMPROVEMENTS.md`,
  `TEST_COVERAGE_REPORT.md`) into `docs/history/` — content unchanged, just
  relocated for discoverability without cluttering the main docs hub.
- Corrected stale rows in `FEATURE_COMPARISON.md` (drag-and-drop and 3-way
  merge UI were marked "planned"; both are implemented) and added wiring-status
  callouts to `docs/CLOUD_STORAGE.md`/`docs/QUICK_START_CLOUD.md`.

### Added (2026-07-25)

#### Release Pipeline
- `release.yml` now packages the `teczka` (PySide6/Qt6) GUI with PyInstaller per platform
  (Linux/Windows/macOS x86_64, macOS arm64) and publishes it alongside the CLI binary.
- CLI release archives are named by Rust target triple and match `cargo-binstall`'s
  default template (`[package.metadata.binstall]` added to `rcompare_cli/Cargo.toml`).
- Release now publishes a `SHA256SUMS` file covering every asset.

### Removed (2026-07-25)
- **`rcompare_gui`**: the deprecated Slint-based Rust GUI crate has been deleted, along
  with the `slint` workspace dependency and its CI/build/release jobs. The desktop GUI is
  now `teczka` (PySide6/Qt6) exclusively.

### Added (2026-01-30)

#### Documentation
- **ROADMAP.md**: Comprehensive development roadmap with 7 phases
- **GAPS.md**: Known limitations and planned improvements
- **DEVELOPMENT_STATUS.md**: Current implementation status snapshot
- **CONTRIBUTING.md**: Professional contribution guidelines (from earlier phase)

#### Patch System & FFI
- **Complete patch parsing system**: Unified, context, normal, RCS, ed diff formats
- **Patch manipulation engine**: Apply/unapply differences, file blending
- **Patch serialization**: Convert back to unified diff format
- **C FFI layer** (`rcompare_ffi`): libkomparediff2-compatible API
  - Opaque handle pattern for memory safety
  - 37 comprehensive tests (lifecycle, accessors, engine, serialization)
  - CMake integration files
  - Complete C header with documentation (rcompare.h)
  - 2 C examples (simple_parse.c, patch_apply.c)
  - Static library builds (librcompare_ffi.a / rcompare_ffi.lib)

#### Performance
- **Parallel hash computing**: Multi-threaded file hashing using rayon
  - `hash_files_parallel()` method for batch processing
  - 2-3x speedup on 4-8 core systems for medium/large files
  - Adaptive buffer sizing (64KB for small files, 1MB for large files)
  - Thread-safe with cache integration
- **Optimized hashing**: Larger buffers for files >10MB

#### CI/CD
- **FFI build integration**: Added to CI pipeline
  - Builds and tests FFI layer on Linux, Windows, macOS
  - Uploads static library artifacts
  - Integrated into CI success gate

### Enhanced
- **README.md**: Added FFI section, feature flags documentation, C/C++ integration examples
- **Test coverage**: Now 270+ tests total (256 unit/integration + parallel hashing tests)

### Fixed
- **Buffer sizes**: Increased from 64KB to 1MB for large files (>10MB)

## [0.1.0] - 2026-01-30

### Added

#### Core Features
- BLAKE3 hashing with persistent cache
- Parallel directory traversal (jwalk)
- Gitignore pattern support
- Cross-platform support (Linux, Windows, macOS)
- Progress indicators with ETA

#### UI
- CLI with JSON output
- Slint GUI with file tree view
- Settings dialog with config persistence
- Copy operations (left/right)

#### VFS & Archives
- VFS abstraction layer
- ZIP, TAR, TAR.GZ, TGZ support
- 7Z support (extraction-based)
- Archive comparison

#### Specialized Formats
- CSV row/column comparison
- Excel sheet/cell comparison
- JSON/YAML structural comparison
- Parquet DataFrame comparison
- Image pixel + EXIF comparison
- Text diff with syntax highlighting

#### Examples & Benchmarks
- 3 Rust examples (basic, archive, specialized formats)
- Criterion benchmark suite (11 benchmarks)

---

## Version Numbering

RCompare follows Semantic Versioning:

- **MAJOR** (1.x.x): Breaking API changes
- **MINOR** (x.1.x): New features, backwards-compatible
- **PATCH** (x.x.1): Bug fixes, performance improvements

Current status: Pre-1.0 (0.x.x) - API may change between minor versions.

---

## Upgrade Guide

### From 0.0.x to 0.1.0
- No breaking changes (initial release)

### Future 0.1.x to 0.2.0
- Parallel hashing API (`hash_files_parallel()`) is stable
- FFI API is stable and follows semver guarantees
- Core comparison API remains backwards-compatible

---

## Performance Improvements Timeline

| Version | Feature | Improvement |
|---------|---------|-------------|
| 0.1.0 (baseline) | Single-threaded hashing | ~3GB/s |
| 0.1.0 (latest) | Parallel hashing | ~6-9GB/s (4-8 cores) |
| 0.2.0 (planned) | Streaming large files | Lower memory usage |
| 0.2.0 (planned) | SQLite index | Support 1M+ files |

---

## Documentation Updates

| Version | Documentation |
|---------|---------------|
| 0.1.0 | README, inline API docs, examples |
| 0.1.0 (latest) | + ROADMAP, GAPS, DEVELOPMENT_STATUS, CONTRIBUTING, FFI docs |
| 0.2.0 (planned) | + User guide, architecture deep-dive, video tutorials |

---

Last updated: 2026-01-30
