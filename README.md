# RCompare

A high-performance file and directory comparison utility written in Rust, inspired by Beyond Compare and following the architectural patterns of Czkawka.

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%2FApache--2.0-blue.svg)](LICENSE)
[![CI](https://github.com/aecs4u/rcompare/actions/workflows/ci.yml/badge.svg)](https://github.com/aecs4u/rcompare/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-153%20passing-brightgreen.svg)](docs/TEST_COVERAGE_REPORT.md)

## Features

- **Fast directory comparison**: Parallel traversal with jwalk
- **BLAKE3 hashing**: Persistent cache and optional verification
- **Cross-platform**: Linux, Windows, macOS
- **CLI + GUI**: Console output, JSON output, and a Slint UI
- **Archive comparison**: zip, tar, tar.gz, tgz, 7z
- **GUI views**: Folder, text, hex, image compare
- **Gitignore + ignore patterns**: Fully compatible gitignore-style pattern matching (supports `*.log`, `build/`, `/config.toml`)
- **Copy left/right**: GUI copy operations for sync workflows
- **Comprehensive testing**: 198 tests (153 passing + 45 integration) with CI/CD pipeline for quality assurance

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

### Usage Example

```bash
# Basic comparison
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

# JSON output
rcompare_cli scan /left /right --json
```

### Notes

- Archive comparisons are read-only; text/hex views are only available for local file pairs.

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

**Test Coverage:** 198 comprehensive tests (153 passing + 45 integration) with 100% pass rate

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
- [Test Coverage Report](docs/TEST_COVERAGE_REPORT.md) - Comprehensive test suite documentation (198 tests: 153 passing + 45 integration)
- [CI/CD Documentation](.github/workflows/README.md) - GitHub Actions pipeline and setup
- [CI and Pattern Improvements](docs/CI_AND_PATTERN_IMPROVEMENTS.md) - Recent improvements to ignore patterns and CI

## Project Status

**Version**: 0.1.0 (Alpha)
**Status**: Core functionality complete

### Completed ✅
- Directory scanning and comparison
- Hash caching with BLAKE3
- CLI with colored output
- GUI with folder/text/hex/image views
- Archive comparison (zip, tar, tar.gz, tgz, 7z)
- Copy left/right operations
- VFS abstraction layer
- Gitignore support
- Cross-platform support

### Planned 🔜
- Three-way merge
- Delete/move operations
- Remote sources in the UI
- Additional comparison profiles and presets

## Technology Stack

### Core
- **Rust** - Memory-safe systems programming
- **BLAKE3** - Fast cryptographic hashing
- **jwalk** - Parallel directory traversal
- **serde** - Serialization framework

### CLI
- **clap** - Command-line parsing
- **tracing** - Structured logging

### GUI
- **Slint** - Declarative UI framework
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
