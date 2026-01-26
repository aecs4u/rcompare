# Changelog

All notable changes to RCompare will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **GitHub Actions CI/CD Pipeline** - Comprehensive multi-platform testing
  - Core library tests on Linux, Windows, macOS (required for merge)
  - CLI integration tests on all platforms (required for merge)
  - Code quality checks with rustfmt and clippy (required for merge)
  - VFS integration tests for cloud services (optional)
  - GUI build verification (optional)
  - Smart test gating with final CI success gate
  - Aggressive caching for fast feedback (3-5 min with cache)
- **Scanner Tests** - Added 6 comprehensive tests for directory scanning
  - Gitignore-style pattern matching tests
  - Root-relative pattern tests (`/config.toml`)
  - Directory-only pattern tests (`build/`)
  - Root entry exclusion verification
- **CI Documentation** - Comprehensive guide for CI setup and usage
  - Branch protection configuration
  - Local testing instructions
  - Troubleshooting guide
  - Performance optimization details
- **Pattern Improvements Documentation** - Detailed report of all improvements made

### Changed
- **Scanner Pattern Matching** - Replaced custom glob implementation with `ignore` crate
  - Now uses gitignore-compatible pattern matching
  - Patterns like `build/` properly exclude entire directory trees
  - Root-relative patterns (`/file.txt`) work correctly
  - Directory-only patterns (`temp/`) distinguish files from directories
  - Added parent directory checking to ensure proper exclusion
- **Test Coverage** - Increased from 144 to 148 tests (+4 scanner tests)
  - All 148 unit tests passing (100% pass rate)
  - 32 integration tests (marked as ignored, require external services)
- **Documentation Updates**
  - Updated TEST_COVERAGE_REPORT.md with scanner tests and CI information
  - Updated README.md with CI badges and testing section
  - Added CI and Pattern Improvements documentation
  - Reorganized documentation into Architecture, User Guides, and Testing sections

### Fixed
- **Ignore Pattern Semantics** - Fixed custom ignore patterns to match gitignore behavior
  - Patterns now properly exclude parent directories and all contents
  - Cross-platform path normalization working correctly
  - Pattern precedence and priority handled correctly
- **Scanner Accuracy** - Verified root entry exclusion and accurate counting
  - Root directory never included in results
  - File counts are accurate across all scan types
  - Entry counting properly tested and documented

### Testing
- **Scanner Tests (6 tests)**
  - `test_scanner_basic` - Basic scanning with accurate entry counts
  - `test_scanner_ignore_patterns` - Simple glob patterns
  - `test_scanner_gitignore_style_patterns` - Complex gitignore-style patterns
  - `test_scanner_root_relative_patterns` - Root-only matching
  - `test_scanner_directory_only_patterns` - Directory-only exclusion
  - `test_scanner_no_root_entry` - Explicit root exclusion verification

## [0.1.0] - 2026-01-25

### Initial Release
- Core directory comparison functionality
- BLAKE3 hash-based verification with persistent cache
- CLI with colored output and JSON export
- GUI with Slint framework
- Archive comparison support (ZIP, TAR, 7z)
- VFS abstraction layer
- Multi-platform support (Linux, Windows, macOS)
- Gitignore support
- Parallel directory traversal

---

[Unreleased]: https://github.com/aecs4u/rcompare/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aecs4u/rcompare/releases/tag/v0.1.0
