# RCompare

A high-performance file and directory comparison utility written in Rust, inspired by Beyond Compare and following the architectural patterns of Czkawka.

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%2FApache--2.0-blue.svg)](LICENSE)
[![CI](https://github.com/aecs4u/rcompare/actions/workflows/ci.yml/badge.svg)](https://github.com/aecs4u/rcompare/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-170%2B%20passing-brightgreen.svg)](docs/TEST_COVERAGE_REPORT.md)

## Features

### Core Capabilities
- **Fast directory comparison**: Parallel traversal with jwalk
- **BLAKE3 hashing**: Persistent cache and optional verification
- **Cross-platform**: Linux, Windows, macOS
- **CLI + GUI**: Console output, JSON output, and a Slint UI
- **Archive comparison**: ZIP, TAR, TAR.GZ, TGZ, 7Z with VFS abstraction
- **Gitignore + ignore patterns**: Fully compatible gitignore-style pattern matching
- **Copy operations**: GUI copy left/right operations for sync workflows

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

# Build release binaries
cargo build --release

# Run CLI
./target/release/rcompare_cli scan /path/to/left /path/to/right

# Run GUI
./target/release/rcompare_gui
```

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

The Slint-based GUI provides an intuitive interface for file comparison:

### Core Features
- **Auto-comparison**: Automatically compares folders when both are selected
- **Last directory memory**: Browse dialogs remember your last location
- **Responsive layout**: Adapts to different window sizes with min/max constraints
- **Tree view**: Collapsible folder structure with expand/collapse all
- **Multiple views**: Folder, text diff, hex diff, and image comparison views
- **Filter controls**: Show/hide identical, different, left-only, and right-only files
- **Search**: Real-time search within comparison results

### Comparison Views
- **Text Diff**: Syntax-highlighted side-by-side comparison
- **Hex Diff**: Byte-level binary comparison with offset display
- **Image Diff**: Visual comparison with dimension and pixel difference stats

### Operations
- **Copy left→right / right→left**: File copy operations
- **Profile management**: Save and load comparison sessions
- **Settings**: Configure ignore patterns, symlink following, hash verification
- **Sync dialog**: Bidirectional sync with dry-run support

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
└── rcompare_gui/         # Graphical interface (Slint)
```

### Key Components

- **VFS Layer**: Virtual File System abstraction for local/archive/remote filesystems
- **Scanner**: Parallel directory traversal with gitignore support
- **Comparison Engine**: Size, timestamp, and hash-based file comparison
- **Hash Cache**: Persistent BLAKE3 hash cache to avoid re-computation

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
- GUI with folder/text/hex/image views
- GUI auto-comparison and last directory memory
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
- Delete/move operations
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

## Use Cases

- **Backup Verification**: Ensure backups match source files
- **Code Synchronization**: Compare local and remote codebases
- **Deployment Validation**: Verify deployed files match build artifacts
- **Directory Deduplication**: Find duplicate directory structures
- **Migration Checks**: Validate data migrations

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Design Philosophy

RCompare follows the Czkawka model:

- **Memory Safety**: Written in safe Rust with minimal unsafe code
- **Performance**: Zero-cost abstractions and parallel processing
- **Privacy**: No telemetry, completely offline
- **Modularity**: Clean separation between core logic and UI

## License

This project is licensed under either of:

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE))
- MIT License ([LICENSE-MIT](LICENSE-MIT))

at your option.

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
