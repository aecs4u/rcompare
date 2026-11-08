# Changelog

All notable changes to RCompare will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (2026-11-08) — Remote file-pair viewing

- Open a selected remote comparison row in the existing text, table, image, or
  hex viewer by staging both sides through the CLI.
- Accept supported remote file URLs in the standalone file-pair dialog and
  compare remote or mixed local/remote pairs with different names.
- Accept explicit remote file URLs in `rcompare_cli diff-file`; capability
  output documents those schemes for scan, read, and file diff.
- Convert `dav`/`davs` endpoints to their HTTP(S) transport URLs before
  connecting, and cover direct remote file diffs with a local WebDAV fixture.
- Stream CLI `read --out` data to a sibling temporary file, preserve existing
  destinations when a read fails, and replace the destination after success.

### Added (2026-11-08) — Side-by-side file properties

- Replace the basic Attributes alert with a Properties dialog that compares
  both sides and shows missing items, type, size, permissions, owner/group,
  timestamps, symlink targets, and copyable paths.

### Added (2026-11-08) — Open With application picker

- Choose an external application for a file, pass its path as a separate
  argument, and optionally save the handler for that file extension. Keep the
  operating-system default and saved handler as separate Open With actions.

### Added (2026-11-08) — Criteria-based bulk selection

- Add Edit → Smart Select on LHS for visible rows by status, path glob, and
  left-side size, with All, None, Invert, select, and deselect actions.

### Fixed (2026-11-08) — Three-way merge conflict grouping

- Merge overlapping edits by their complete base-line region, so edits that
  start on different lines are shown as one unresolved conflict instead of
  being silently combined.
- Route background worker exception logging to its owning Qt thread to avoid
  concurrent Rich/structlog rendering from worker threads.

### Fixed (2026-11-08) — Text diff worker lifetime

- Keep file-diff workers alive until their threads finish, route results through
  the owning TextView, and avoid destroying a view-owned QThread mid-run.

### Added (2026-11-08) — Graceful sync cancellation

- Stop sync between actions or during chunked file transfers, report completed
  and remaining work, and journal cancelled actions. Local file copies persist
  resumable checkpoints and verify source hashes before continuing.
- Route the GUI Stop button through graceful CLI termination and show the
  partial sync outcome; checkpoint discovery and explicit resume controls are
  still in progress.

### Added (2026-11-08) — Merge-view regression coverage

- Add focused GUI tests for independent and identical edits, overlapping and
  same-point conflicts, conflict resolution and line offsets, asynchronous
  loading, stale results, read errors, and saving.

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
