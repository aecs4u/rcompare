# RCompare

A high-performance file and directory comparison toolkit with a Rust core, CLI, and two desktop frontends (Slint and PySide6), inspired by Beyond Compare and following architectural patterns similar to Czkawka.

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%2FApache--2.0-blue.svg)](LICENSE)
[![CI](https://github.com/aecs4u/rcompare/actions/workflows/ci.yml/badge.svg)](https://github.com/aecs4u/rcompare/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/aecs4u/rcompare/branch/main/graph/badge.svg)](https://codecov.io/gh/aecs4u/rcompare)
[![Tests](https://img.shields.io/badge/tests-210%2B%20passing-brightgreen.svg)](docs/TEST_COVERAGE_REPORT.md)

## Features

### Core Capabilities
- **Fast directory comparison**: Parallel traversal with jwalk
- **BLAKE3 hashing**: Persistent cache and optional verification
- **Cross-platform**: Linux, Windows, macOS
- **CLI + GUI frontends**: Console output, JSON output, Slint GUI (`rcompare_gui`), and PySide6 GUI (`rcompare_pyside`)
- **Archive comparison**: ZIP, TAR, TAR.GZ, TGZ, 7Z with VFS abstraction
- **Gitignore + ignore patterns**: Fully compatible gitignore-style pattern matching
- **Copy operations**: GUI copy left/right operations for sync workflows
- **Per-user persistence**: Last paths, filters, options, and session profile data in the PySide app

### Specialized File Comparisons
- **Text files**: Line-by-line diff with syntax highlighting, whitespace handling (5 modes), case-insensitive comparison, regex rules
- **Binary files**: Hex view with byte-level comparison
- **Images**: Pixel-by-pixel comparison with multiple modes, EXIF metadata comparison, configurable tolerance
- **CSV files**: Row-by-row, column-aware structural comparison
- **Excel files**: Sheet, row, and cell-level comparison (.xlsx, .xls)
- **JSON files**: Path-based structural comparison with type checking
- **YAML files**: Path-based structural comparison with type checking
- **Parquet files**: DataFrame comparison with schema validation and row-level diffing

### Quality Assurance
- **Comprehensive testing**: 170+ tests with CI/CD pipeline
- **Broken symlink handling**: Graceful handling during hash verification
- **Progress indicators**: Progress bars with ETA for long-running operations

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/aecs4u/rcompare
cd rcompare

# Build release binaries (all features)
cargo build --release

# Build with minimal features (no cloud, archives, or specialized comparisons)
cargo build --release --no-default-features

# Build with specific features only
cargo build --release --no-default-features --features "archives,csv-diff"

# Run CLI
./target/release/rcompare_cli scan /path/to/left /path/to/right

# Run Slint GUI
./target/release/rcompare_gui

# Run PySide GUI (Python >= 3.10)
cd rcompare_pyside
uv sync
uv run python -m rcompare_pyside
```

### Feature Flags

RCompare uses Cargo feature flags to allow optional dependencies, reducing binary size and compile time when you don't need all functionality:

**Default features** (enabled by default):
- `cloud` - Cloud storage support (S3, SSH/SFTP, WebDAV)
- `archives` - Archive format support (ZIP, TAR, 7Z, RAR)
- `specialized` - All specialized file format comparisons

**Specialized format features** (enabled with `specialized`):
- `csv-diff` - CSV file comparison
- `excel-diff` - Excel workbook comparison (.xlsx, .xls)
- `json-diff` - JSON/YAML structural comparison
- `parquet-diff` - Parquet DataFrame comparison
- `image-diff` - Image pixel-level comparison with EXIF

**Examples:**

```bash
# Minimal build (core functionality only - ~50% smaller binary)
cargo build --release --no-default-features

# Only archive support (no cloud or specialized comparisons)
cargo build --release --no-default-features --features "archives"

# Only specialized formats (no cloud or archives)
cargo build --release --no-default-features --features "specialized"

# Custom combination (archives + CSV + images only)
cargo build --release --no-default-features --features "archives,csv-diff,image-diff"

# Everything except cloud storage
cargo build --release --no-default-features --features "archives,specialized"
```

**Binary size comparison** (approximate, release mode):
- Full build (all features): ~200 MB
- No cloud: ~180 MB
- No archives: ~190 MB
- No specialized: ~120 MB
- Minimal (no defaults): ~50 MB

### Usage Examples

#### Basic Comparison
```bash
# Basic directory comparison
rcompare_cli scan ~/Documents ~/Backup/Documents

# Compare with ignore patterns
rcompare_cli scan /project /backup -i "*.o" -i "target/" -i "node_modules/"

# Show only differences
rcompare_cli scan /source /dest --diff-only

# Enable hash verification
rcompare_cli scan /left /right --verify-hashes

# Disable hash verification (use size + timestamp)
rcompare_cli scan /left /right --no-verify-hashes

# Compare archives
rcompare_cli scan left.zip right.zip

# JSON output for automation
rcompare_cli scan /left /right --json
```

#### Specialized File Comparison
```bash
# CSV comparison with row-by-row analysis
rcompare_cli scan /data/left /data/right --csv-diff

# Excel comparison with sheet and cell analysis
rcompare_cli scan /reports/left /reports/right --excel-diff

# JSON structural comparison
rcompare_cli scan /configs/left /configs/right --json-diff

# YAML structural comparison
rcompare_cli scan /k8s/left /k8s/right --yaml-diff

# Parquet dataframe comparison
rcompare_cli scan /data/left /data/right --parquet-diff

# Image comparison with pixel-level analysis
rcompare_cli scan /images/left /images/right --image-diff

# Combine multiple specialized comparisons
rcompare_cli scan /project/left /project/right --csv-diff --json-diff --excel-diff
```

#### Text Comparison Options
```bash
# Ignore whitespace when comparing text files
rcompare_cli scan /code/left /code/right --ignore-whitespace all       # Ignore all whitespace
rcompare_cli scan /code/left /code/right --ignore-whitespace leading   # Ignore leading whitespace
rcompare_cli scan /code/left /code/right --ignore-whitespace trailing  # Ignore trailing whitespace
rcompare_cli scan /code/left /code/right --ignore-whitespace changes   # Ignore whitespace changes

# Case-insensitive comparison
rcompare_cli scan /sql/left /sql/right --ignore-case

# Apply regex rules for normalization
rcompare_cli scan /logs/left /logs/right --regex-rule '\d{4}-\d{2}-\d{2}:[DATE]:Normalize dates'
rcompare_cli scan /configs/left /configs/right --regex-rule 'v\d+\.\d+\.\d+:[VERSION]:Normalize versions'

# Combine text comparison options
rcompare_cli scan /code/left /code/right --ignore-whitespace all --ignore-case
```

#### Image Comparison Options
```bash
# Compare EXIF metadata (camera settings, GPS, timestamps)
rcompare_cli scan /photos/left /photos/right --image-diff --image-exif

# Adjust pixel difference tolerance (0-255, default: 1)
rcompare_cli scan /images/left /images/right --image-diff --image-tolerance 10

# Combine image comparison options
rcompare_cli scan /photos/left /photos/right --image-diff --image-exif --image-tolerance 5
```

## Specialized Comparison Modes

### CSV Comparison (`--csv-diff`)
Analyzes CSV files with row-by-row and column-aware comparison:
- Detects added, removed, and modified rows
- Shows column-level differences within modified rows
- Reports total rows, identical rows, and differences
- Displays sample differences with column names

### Excel Comparison (`--excel-diff`)
Compares Excel workbooks (.xlsx, .xls) at multiple levels:
- Sheet-level comparison (added/removed/modified sheets)
- Row and column count differences
- Cell-by-cell value comparison
- Detects formula vs value differences

### JSON Comparison (`--json-diff`)
Structural comparison of JSON files:
- Path-based diffing (e.g., `root.user.name`)
- Type mismatch detection (string vs number)
- Handles nested objects and arrays
- Reports added/removed/modified paths

### YAML Comparison (`--yaml-diff`)
Structural comparison of YAML files:
- Converted to JSON for unified comparison
- Path-based diffing with type checking
- Handles complex YAML structures
- Reports structural differences

### Parquet Comparison (`--parquet-diff`)
DataFrame-level comparison for Parquet files:
- Schema validation (column names and types)
- Row-by-row value comparison
- Support for key-based or index-based matching
- Shows sample differences with column details

### Image Comparison (`--image-diff`)
Pixel-level comparison of image files:
- Multiple comparison modes: exact, threshold, perceptual
- Dimension validation
- Pixel difference percentage
- Mean absolute difference per channel
- **EXIF metadata comparison** (`--image-exif`): Compare camera settings, GPS coordinates, timestamps, and more
- **Tolerance adjustment** (`--image-tolerance`): Configure pixel difference threshold (0-255, default: 1)

## GUI Features

RCompare currently ships two GUI frontends:

### Slint GUI (`rcompare_gui`)
- Fast native Rust desktop UI with folder scan/compare workflows
- Folder/text/hex/image views
- Copy actions and filtering support

### PySide6 GUI (`rcompare_pyside`)
- **Multi-session tabs** and persistent per-user state
- **Folder view options**: compare structure, files-only, ignore structure, always-show-folders
- **Diff option presets**: differences/orphans/newer-side focused views
- **Multi-selection** in LH/RH trees with synchronized scrolling/expand state
- **Rich right-click commands**: copy/move/delete/rename/touch/new-folder, attributes, exclude, synchronize
- **File-type aware double-click**: opens/reuses text/image/hex compare tabs
- **Synchronize Folders preview** with summary and planned operations
- **Session Profiles dialog** and auto-save of last session profile on close
- **KDE-style Options and Help dialogs**, plus startup splash with license viewer
- **Logfire-integrated logging** with stdlib fallback

## Notes

- Archive comparisons are read-only; text/hex views are only available for local file pairs
- Specialized comparisons only analyze files that differ or are unchecked
- Progress bars with ETA are shown for long-running specialized comparisons
- Use `--no-color` to disable colored output in CI/CD environments

## Architecture

RCompare follows a modular workspace structure with strict separation of concerns:

```
rcompare/
├── rcompare_common/      # Shared types, traits, and errors
├── rcompare_core/        # Core business logic (UI-agnostic)
├── rcompare_cli/         # Command-line interface
├── rcompare_gui/         # Graphical interface (Slint)
├── rcompare_pyside/      # Graphical interface (PySide6)
└── rcompare_ffi/         # C FFI layer (libkomparediff2-compatible)
```

### Key Components

- **VFS Layer**: Virtual File System abstraction for local/archive/remote filesystems
- **Scanner**: Parallel directory traversal with gitignore support
- **Comparison Engine**: Size, timestamp, and hash-based file comparison
- **Hash Cache**: Persistent BLAKE3 hash cache to avoid re-computation
- **Patch Engine**: Parse, manipulate, and serialize diff/patch files (unified, context, normal formats)
- **FFI Layer**: C-compatible API for integration with C/C++ applications

### C/C++ Integration (FFI)

RCompare provides a libkomparediff2-compatible C API for parsing and manipulating diff/patch files:

```c
#include "rcompare.h"

// Parse diff
PatchSetHandle* handle = NULL;
rcompare_parse_diff(diff_data, diff_len, &handle);

// Access metadata
size_t file_count = rcompare_patchset_file_count(handle);
const char* source = rcompare_filepatch_source(handle, 0);

// Blend with original file
rcompare_blend_file(handle, 0, original_data, original_len);

// Apply/unapply patches
rcompare_apply_difference(handle, 0, diff_idx);
rcompare_unapply_difference(handle, 0, diff_idx);

// Serialize back to diff
char* output = rcompare_serialize_diff(handle);
rcompare_free_string(output);

// Cleanup
rcompare_free_patchset(handle);
```

Features:
- Parse multiple diff formats (unified, context, normal, RCS, ed)
- Auto-detect generators (CVS, Perforce, Subversion)
- Apply/unapply individual or all differences
- Blend original file content with patch
- Serialize back to unified diff format
- Arena-based memory management for strings

See [rcompare_ffi/README.md](rcompare_ffi/README.md) for complete documentation and examples.

## Output Symbols

### CLI
- `==` : Identical files
- `!=` : Different files
- `<<` : Left-only files (orphans)
- `>>` : Right-only files (orphans)
- `??` : Unchecked (same size, not verified)

### GUI
- 🟢 Green: Identical files
- 🔴 Red: Different files
- 🟡 Yellow: Left-only files
- 🔵 Blue: Right-only files

## Performance

- **BLAKE3 Hashing**: ~3GB/s on modern CPUs
- **Parallel Traversal**: Saturates I/O bandwidth
- **Persistent Cache**: Avoids re-hashing unchanged files
- **Memory Usage**: ~100-200 bytes per file

## Build & Test

### Building

```bash
# Debug build
cargo build

# Release build (optimized)
cargo build --release
```

### Testing

**Test Coverage:** 170+ comprehensive tests covering core library, VFS operations, specialized comparisons, and CLI integration

```bash
# Run all tests
cargo test

# Run tests with output
cargo test -- --nocapture

# Run specific test suites
cargo test -p rcompare_core --lib                    # Core library tests
cargo test -p rcompare_core --lib scanner::tests     # Scanner tests
cargo test -p rcompare_core --lib vfs::tests_local   # Local VFS tests
cargo test -p rcompare_core --lib vfs::tests_archive # Archive VFS tests
cargo test -p rcompare_cli                           # CLI tests

# GUI tests
# Build-only UI compile test runs by default
# Opt-in GUI smoke test (requires a display backend)
RCOMPARE_GUI_SMOKE_TEST=1 cargo test -p rcompare_gui

# Headless CI (compile-only GUI test)
cargo test -p rcompare_gui --test ui_compile

# PySide GUI lint/smoke checks
cd rcompare_pyside
uv sync
uv run ruff check rcompare_pyside
QT_QPA_PLATFORM=offscreen uv run python -m rcompare_pyside
```

### Continuous Integration

RCompare uses GitHub Actions for automated testing:

- ✅ **Multi-platform testing** (Linux, Windows, macOS)
- ✅ **Core library tests** (required for merge)
- ✅ **CLI integration tests** (required for merge)
- ✅ **Code quality checks** (rustfmt, clippy)
- ✅ **Test gating** prevents regressions

See [CI Documentation](.github/workflows/README.md) for details.

## Documentation

### Architecture & Design
- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed architecture specification
- [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) - Current implementation status
- [CLAUDE.md](CLAUDE.md) - Development guidelines for Claude Code

### User Guides
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide and examples
- [ROADMAP.md](ROADMAP.md) - Current roadmap and planned milestones

### Testing & CI/CD
- [Test Coverage Report](docs/TEST_COVERAGE_REPORT.md) - Comprehensive test suite documentation (170+ tests)
- [CI/CD Documentation](.github/workflows/README.md) - GitHub Actions pipeline and setup
- [CI and Pattern Improvements](docs/CI_AND_PATTERN_IMPROVEMENTS.md) - Recent improvements to ignore patterns and CI

## Project Status

**Version**: 0.1.0 (Alpha)
**Status**: Core functionality complete

### Completed ✅
- Directory scanning and comparison
- Hash caching with BLAKE3
- CLI with colored output and progress bars with ETA
- Slint GUI with folder/text/hex/image views
- PySide GUI with multi-tab sessions, profile persistence, sync preview, rich context commands
- Archive comparison (zip, tar, tar.gz, tgz, 7z)
- Copy left/right operations
- VFS abstraction layer
- Gitignore support with pattern matching
- Cross-platform support (Linux, Windows, macOS)
- **Specialized file comparisons:**
  - CSV files (row-by-row, column-aware)
  - Excel files (.xlsx, .xls with sheet/cell analysis)
  - JSON files (structural, path-based)
  - YAML files (structural, path-based)
  - Parquet files (DataFrame with schema validation)
  - Images (pixel-level with multiple modes)

### Planned 🔜
- Three-way merge comparison
- Database schema and data comparison
- Remote sources in the UI (S3, SFTP, WebDAV)
- Additional comparison profiles and presets

## Technology Stack

### Core
- **Rust** - Memory-safe systems programming
- **BLAKE3** - Fast cryptographic hashing
- **jwalk** - Parallel directory traversal
- **rayon** - Data parallelism
- **serde** - Serialization framework

### File Format Support
- **csv** - CSV parsing and processing
- **calamine** - Excel file reading (.xlsx, .xls)
- **serde_json** - JSON parsing
- **serde_yaml** - YAML parsing
- **polars** - DataFrame operations and Parquet support
- **image** - Image decoding and processing
- **syntect** - Syntax highlighting

### Archive Support
- **zip** - ZIP archive handling
- **tar** - TAR archive handling
- **sevenz-rust** - 7-Zip archive handling
- **flate2** - GZIP compression
- **bzip2** - BZIP2 compression
- **xz2** - XZ compression
- **unrar** - RAR archive handling

### CLI
- **clap** - Command-line parsing with derive macros
- **indicatif** - Progress bars with ETA
- **tracing** - Structured logging

### GUI
- **Slint 1.9** - Declarative UI framework
- **native-dialog** - Native file dialogs
- **PySide6** - Python desktop frontend
- **logfire** - Structured application logging/telemetry backend

## Use Cases

- **Backup Verification**: Ensure backups match source files
- **Code Synchronization**: Compare local and remote codebases
- **Deployment Validation**: Verify deployed files match build artifacts
- **Directory Deduplication**: Find duplicate directory structures
- **Migration Checks**: Validate data migrations

## Examples

RCompare includes several example programs demonstrating different use cases:

### Basic Directory Comparison
```bash
cargo run --example basic_comparison -- /path/to/left /path/to/right
```
Demonstrates fundamental directory comparison with detailed output of differences.

### Archive Comparison
```bash
cargo run --example archive_comparison -- backup1.zip backup2.tar.gz
```
Shows how to compare files inside ZIP and TAR archives without extraction using the VFS abstraction.

### Specialized Format Comparison
```bash
# Text file comparison with syntax highlighting
cargo run --example specialized_formats -- text left.rs right.rs

# Image comparison with pixel-level analysis
cargo run --example specialized_formats -- image photo1.png photo2.png

# CSV structural comparison
cargo run --example specialized_formats -- csv data1.csv data2.csv

# JSON path-based comparison
cargo run --example specialized_formats -- json config1.json config2.json
```
Demonstrates specialized comparison engines for different file types.

### Cloud Storage Comparison
```bash
cargo run --example cloud_storage_example
```
Shows integration with S3 and SSH/SFTP for comparing cloud-stored files.

All examples include detailed comments and error handling to serve as templates for your own integrations.

## Development

### Running Tests

```bash
# Run all tests
cargo test

# Run tests for a specific package
cargo test --package rcompare_core

# Run tests with output
cargo test -- --nocapture
```

### Running Benchmarks

RCompare uses [Criterion](https://github.com/bheisler/criterion.rs) for performance benchmarking:

```bash
# Run all benchmarks
cargo bench

# Run specific benchmark group
cargo bench scanner
cargo bench comparison
cargo bench hash_cache

# Generate HTML report (saved to target/criterion/)
cargo bench --bench core_benchmarks
```

Benchmark results are saved in `target/criterion/` with detailed HTML reports showing:
- Performance metrics (mean, median, std dev)
- Comparison with previous runs
- Regression detection
- Detailed plots and statistics

**Benchmark categories:**
- **Scanner benchmarks**: Directory traversal performance (small, medium, large trees)
- **Hash cache benchmarks**: Cache lookup and insertion performance
- **Comparison benchmarks**: File comparison at different scales
- **Workflow benchmarks**: End-to-end scan and compare operations

### Code Quality

```bash
# Format code
cargo fmt --all

# Run Clippy lints
cargo clippy --all-targets --all-features -- -D warnings

# Run security audit
cargo audit

# Check dependencies for issues
cargo deny check
```

### Documentation

```bash
# Build and view API documentation
cargo doc --no-deps --open

# Check for documentation warnings
cargo doc --no-deps 2>&1 | grep warning
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

**Quick start:**

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following our [coding standards](CONTRIBUTING.md#coding-standards)
4. Add tests for new functionality
5. Run tests and linters (`cargo test && cargo clippy`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

**Before submitting:**
- ✅ All tests pass (`cargo test`)
- ✅ Code is formatted (`cargo fmt --all -- --check`)
- ✅ No Clippy warnings (`cargo clippy --all-targets -- -D warnings`)
- ✅ Documentation updated for API changes
- ✅ Examples added/updated if relevant

## Design Philosophy

RCompare follows the Czkawka model:

- **Memory Safety**: Written in safe Rust with minimal unsafe code
- **Performance**: Zero-cost abstractions and parallel processing
- **Privacy-first defaults**: Works offline; optional remote telemetry depends on explicit Logfire token/configuration
- **Modularity**: Clean separation between core logic and UI

## License

This repository currently includes the MIT license text in [LICENSE](LICENSE).
The Cargo workspace metadata is `MIT OR Apache-2.0`.

## Acknowledgments

- Inspired by [Beyond Compare](https://www.scootersoftware.com/)
- Architecture based on [Czkawka](https://github.com/qarmin/czkawka)
- Uses [BLAKE3](https://github.com/BLAKE3-team/BLAKE3) for fast hashing
- UI built with [Slint](https://slint.rs/)

## Contact

- **Repository**: https://github.com/aecs4u/rcompare
- **Issues**: https://github.com/aecs4u/rcompare/issues

---

Made with Rust
