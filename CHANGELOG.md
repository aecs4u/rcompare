# Changelog

All notable changes to RCompare will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
