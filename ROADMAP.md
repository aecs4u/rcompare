# RCompare Roadmap

This document outlines the development roadmap for RCompare, organized by priority and implementation status.

## Legend

- ✅ **Completed**: Fully implemented and tested
- 🚧 **In Progress**: Currently being developed
- 📋 **Planned**: Scheduled for future development
- 🔮 **Future**: Long-term goals, not yet scheduled

---

## Phase 1: Core Foundation ✅

### File Comparison Engine ✅
- ✅ BLAKE3 hashing with persistent cache
- ✅ Size and timestamp-based comparison
- ✅ Parallel directory traversal with jwalk
- ✅ Gitignore pattern support
- ✅ Cross-platform support (Linux, Windows, macOS)

### Basic UI ✅
- ✅ CLI with progress indicators
- ✅ JSON output for automation
- ✅ Slint GUI with file tree view
- ✅ Settings dialog with config persistence
- ✅ Copy operations (left/right)

### VFS & Archives ✅
- ✅ VFS abstraction layer
- ✅ ZIP, TAR, TAR.GZ, TGZ support
- ✅ 7Z support (read-only via extraction)
- ✅ Archive comparison without extraction

---

## Phase 2: Specialized Formats ✅

### Text & Binary ✅
- ✅ Line-by-line text diff with syntax highlighting
- ✅ Whitespace handling (5 modes)
- ✅ Case-insensitive comparison
- ✅ Binary hex view

### Structured Data ✅
- ✅ CSV row/column comparison
- ✅ Excel sheet/cell comparison (.xlsx, .xls)
- ✅ JSON structural comparison
- ✅ YAML structural comparison
- ✅ Parquet DataFrame comparison

### Media ✅
- ✅ Image pixel-by-pixel comparison
- ✅ EXIF metadata comparison
- ✅ Configurable tolerance for images

---

## Phase 3: Patch System & FFI ✅

### Patch Operations ✅
- ✅ Parse multiple diff formats (unified, context, normal, RCS, ed)
- ✅ Auto-detect generators (CVS, Perforce, Subversion)
- ✅ Apply/unapply individual differences
- ✅ Blend original file with patch
- ✅ Serialize back to unified diff

### C/C++ Integration ✅
- ✅ C FFI layer (libkomparediff2-compatible)
- ✅ Opaque handle pattern
- ✅ CMake integration
- ✅ C examples and documentation
- ✅ 37 comprehensive FFI tests

---

## Phase 4: Advanced Features 🚧

### Performance Optimization 🚧
- ✅ **Parallel hash computing** (completed)
  - Multi-threaded BLAKE3 hashing with rayon
  - `hash_files_parallel()` API for batch operations
  - Adaptive buffer sizing (64KB → 1MB for large files)
  - Progress callback support
  - Result: 2-3x faster on 4-8 core systems (6-9GB/s)

- ✅ **Streaming large file comparison** (completed)
  - Chunk-by-chunk comparison (1MB chunks)
  - Configurable threshold (default: 100MB)
  - Constant memory usage (~2MB)
  - Early exit on mismatch
  - Handles multi-GB files without OOM

- 📋 SQLite index for very large trees

### CLI Improvements ✅
- ✅ **Diff-aware exit codes** (completed)
  - Exit 0: No differences found
  - Exit 1: Error occurred
  - Exit 2: Differences found
- ✅ **JSON schema versioning** (completed)
  - Schema v1.1.0 with specialized diff reports
  - Backward compatibility tracking
- ✅ **Progress indicators** (completed)
  - Scanning progress bar
  - Comparison progress bar with ETA

### CI/CD Enhancements ✅
- ✅ **FFI build in CI** (completed)
  - Multi-platform CI (Linux, Windows, macOS)
  - Static library artifact uploads
  - Comprehensive FFI testing

### GUI Enhancements 🚧
- 🚧 **Three-way merge** (core completed, UI pending)
  - ✅ Core `MergeEngine` with conflict detection
  - ✅ Auto-merge for non-conflicting changes
  - ✅ Four conflict types (BothModified, ModifyDelete, BothAdded, TypeConflict)
  - ✅ 12 comprehensive tests
  - 📋 Three-pane GUI layout
  - 📋 Conflict resolution UI
- 📋 Tabs for multiple comparisons
- 📋 Synced scrolling with gutter diff map

### Copy Operations ✅
- ✅ **Post-copy verification** (completed)
  - BLAKE3 hash verification
  - Automatic retry logic (configurable max retries)
  - Hash mismatch detection with detailed reporting
  - Corrupted file cleanup and retry
- ✅ **Resumable copies** (completed)
  - Checkpoint-based progress tracking
  - Automatic resume from interruption
  - BLAKE3 hash verification for partial files
  - 4MB chunk copying with 100MB checkpoints
  - 50MB threshold for resumable mode
  - Progress callback support

---

## Phase 5: Reporting & Workflow 📋

- 📋 HTML/Markdown/CSV report export
- 📋 JUnit XML for CI integration
- 📋 Diff statistics dashboard
- 📋 Comparison presets (save/load)
- 📋 .rcompare-ignore file support

---

## Phase 6: Cloud & Remote 🔮

- 🔮 Additional cloud providers (GCS, Azure, Dropbox)
- 🔮 SSH improvements (key auth, pooling)
- 🔮 Watch mode for continuous monitoring
- 🔮 API server (REST/gRPC)

---

## Phase 7: AI & Platform Integration 🔮

- 🔮 Semantic diff (refactoring detection, AST-based)
- 🔮 macOS/Windows/Linux platform integrations
- 🔮 Differential backup system
- 🔮 Plugin/extension system

Last updated: 2026-01-30
