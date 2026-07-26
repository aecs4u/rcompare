# Changelog

All notable changes to RCompare will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
