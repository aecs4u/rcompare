# Changelog

All notable changes to RCompare will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### WinMerge Parity Features (Phase 1)
- **Text Comparison: Whitespace Handling** - 5 configurable modes
  - `WhitespaceMode::Exact` - Compare whitespace exactly (default)
  - `WhitespaceMode::IgnoreAll` - Remove all whitespace
  - `WhitespaceMode::IgnoreLeading` - Ignore leading whitespace
  - `WhitespaceMode::IgnoreTrailing` - Ignore trailing whitespace
  - `WhitespaceMode::IgnoreChanges` - Normalize whitespace changes
  - CLI flag: `--ignore-whitespace <MODE>`
- **Text Comparison: Case-Insensitive** - Optional case-insensitive text comparison
  - Converts text to lowercase before diff
  - Useful for SQL, HTML, configuration files
  - CLI flag: `--ignore-case`
- **Text Comparison: Regex Rules** - Pattern-based text preprocessing
  - Support for multiple rules applied sequentially
  - Each rule has pattern, replacement, and description
  - Useful for normalizing timestamps, UUIDs, build IDs
  - CLI flag: `--regex-rule <PATTERN> <REPLACEMENT> <DESCRIPTION>`
- **Image Comparison: EXIF Metadata** - Comprehensive EXIF metadata extraction and comparison
  - 11+ standard fields: Make, Model, DateTime, ExposureTime, FNumber, ISO, FocalLength
  - GPS coordinates: Latitude, Longitude
  - Additional tags stored in HashMap
  - Automatic extraction when comparing image files
  - CLI flag: `--image-diff` (enabled by default)
- **Image Comparison: Tolerance Adjustment** - Configurable pixel difference tolerance
  - Range: 0-255 (default: 1)
  - Applied to all comparison modes
  - Useful for JPEG artifacts and compression differences
  - CLI flag: `--tolerance <VALUE>`
- **Text Diff CLI Integration** - Complete text-specific comparison mode
  - Progress bars with ETA
  - Line statistics (inserted/deleted/equal)
  - Colored output for different line types
  - File-by-file analysis
  - Support for 40+ text file extensions
  - CLI flag: `--text-diff`

#### CI/CD Infrastructure
- **GitHub Actions CI/CD Pipeline** - Comprehensive multi-platform testing
  - Core library tests on Linux, Windows, macOS (required for merge)
  - CLI integration tests on all platforms (required for merge)
  - GUI tests and builds on all platforms (required for merge)
  - Code quality checks with rustfmt and clippy (required for merge)
  - VFS integration tests for cloud services (optional)
  - Smart test gating with final CI success gate
  - Aggressive caching for fast feedback (15-20 min with parallelization)
  - Artifact uploads: CLI and GUI binaries (7-day retention)
- **Code Coverage Pipeline** - Automated coverage tracking with Codecov
  - Uses cargo-tarpaulin for accurate Rust coverage
  - Generates XML (Codecov) and HTML (human-readable) reports
  - Excludes test files and examples
  - Archives HTML reports as artifacts (30-day retention)
- **Security Audit Pipeline** - Comprehensive security scanning
  - **cargo-audit**: Daily vulnerability scanning (RustSec Advisory Database)
  - **cargo-deny**: License and dependency policy enforcement
  - **cargo-outdated**: Dependency update tracking (weekly)
  - Configuration in `deny.toml` with strict security policies
- **Scheduled Builds** - Weekly builds to catch issues early
  - Multi-platform: Linux, Windows, macOS
  - Multi-version: stable, beta Rust
  - MSRV validation (Rust 1.70)
  - Full test suite and documentation checks
  - Runs every Monday at 02:00 UTC
- **Release Automation** - Modern release workflow with GitHub Actions
  - Multi-platform builds: Linux, Windows, macOS (x86_64)
  - Automatic release creation on version tags (v*.*.*)
  - Individual binaries and combined archives
  - Enhanced release notes with installation instructions
  - Uses modern `softprops/action-gh-release@v1` action
- **PR Labeler** - Automatic PR labeling based on changed files
  - Labels: core, cli, gui, common, documentation, ci, tests, dependencies
  - Configuration in `.github/labeler.yml`
- **Dependabot** - Automated dependency updates
  - Cargo dependencies: Weekly (Mondays)
  - GitHub Actions: Weekly (Mondays)
  - Groups minor/patch updates
  - Conventional commit messages

#### GitHub Templates & Configuration
- **Pull Request Template** - Structured PR template with comprehensive checklist
  - Type of change selection
  - Testing checklist
  - Code quality checklist
  - Screenshots section
  - Related PRs/issues
- **Issue Templates** - Bug reports and feature requests
  - Bug Report: Structured with reproduction steps, environment details
  - Feature Request: Motivation, use case, priority levels
  - Configuration: Links to docs and discussions
- **Code Owners** - Automatic review assignment
  - CI/CD workflows (`.github/`)
  - Core library (`rcompare_core/`)
  - Documentation (`docs/`, `*.md`)
  - Security files (`deny.toml`, `Cargo.lock`)
- **Security Policy** - cargo-deny configuration (`deny.toml`)
  - Allowed licenses: MIT, Apache-2.0, BSD, ISC, Zlib
  - Blocks: Known vulnerabilities, yanked crates
  - Warns: Unmaintained crates, copyleft licenses
  - Enforces: crates.io only (no git dependencies)
- **Scanner Tests** - Added 6 comprehensive tests for directory scanning
  - Gitignore-style pattern matching tests
  - Root-relative pattern tests (`/config.toml`)
  - Directory-only pattern tests (`build/`)
  - Root entry exclusion verification
- **SFTP VFS Tests** - Added 18 comprehensive tests for SFTP VFS implementation
  - 5 unit tests for configuration and authentication variants
  - 13 integration tests for file operations (require SFTP server)
  - Support for password, key file, and SSH agent authentication
  - Tests for read/write, copy, delete, metadata operations
  - Large file and nested directory tests
- **CI Documentation** - Comprehensive guide for CI setup and usage
  - Branch protection configuration
  - Local testing instructions
  - Troubleshooting guide
  - Performance optimization details
- **Pattern Improvements Documentation** - Detailed report of all improvements made

### Changed

#### GUI Improvements
- **Tree View Layout** - Fixed tree view name column display issue
  - Applied Krokiet (Czkawka) best practices for Slint layouts
  - Added `min-width: 200px` to Name column in all three panels (base, left, right)
  - Increased Type column width to 50px for better display
  - File and folder names now visible correctly

#### Documentation
- **WinMerge Parity Documentation** - Consolidated Phase 1 documentation
  - Merged WINMERGE_PARITY_PHASE1_SUMMARY.md and WINMERGE_PARITY_USER_REQUESTS_STATUS.md
  - Created comprehensive WINMERGE_PARITY_PHASE1.md (22K)
  - Reduced redundancy by ~5K
  - Single source of truth for Phase 1 work
- **CI/CD Documentation** - Comprehensive workflow documentation
  - Updated `.github/workflows/README.md` with all new workflows
  - Added documentation for coverage, security, scheduled builds
  - Updated branch protection and testing instructions

#### CI/CD Workflows
- **Release Workflow** - Modernized from deprecated GitHub Actions
  - Replaced deprecated `actions/create-release@v1` with `softprops/action-gh-release@v1`
  - Replaced deprecated `actions/upload-release-asset@v1` with modern alternative
  - Simplified from two-job to single-job workflow
  - Parallel execution across all platforms
  - 40% fewer upload steps
  - Enhanced release notes with features and installation

- **Scanner Pattern Matching** - Replaced custom glob implementation with `ignore` crate
  - Now uses gitignore-compatible pattern matching
  - Patterns like `build/` properly exclude entire directory trees
  - Root-relative patterns (`/file.txt`) work correctly
  - Directory-only patterns (`temp/`) distinguish files from directories
  - Added parent directory checking to ensure proper exclusion
- **Test Coverage** - Increased from 180 to 198 tests (+18 SFTP tests)
  - 153 unit tests passing (100% pass rate) - up from 148
  - 45 integration tests (marked as ignored, require external services: S3, WebDAV, SFTP) - up from 32
  - Total: 198 tests (153 passing + 45 integration)
- **Documentation Updates**
  - Updated TEST_COVERAGE_REPORT.md with scanner tests and CI information
  - Updated README.md with CI badges and testing section
  - Added CI and Pattern Improvements documentation
  - Reorganized documentation into Architecture, User Guides, and Testing sections

### Fixed
- **Release Workflow** - Fixed use of deprecated GitHub Actions
  - Replaced sunset `actions/create-release@v1` and `actions/upload-release-asset@v1`
  - Now uses actively maintained `softprops/action-gh-release@v1`
  - Improved reliability and compatibility with current GitHub API
- **GUI Tree View** - Fixed missing file/folder names in tree view
  - Names now display correctly in all three panels
  - Applied proper min-width constraints
  - Based on Krokiet (Czkawka) best practices
- **Ignore Pattern Semantics** - Fixed custom ignore patterns to match gitignore behavior
  - Patterns now properly exclude parent directories and all contents
  - Cross-platform path normalization working correctly
  - Pattern precedence and priority handled correctly
- **Scanner Accuracy** - Verified root entry exclusion and accurate counting
  - Root directory never included in results
  - File counts are accurate across all scan types
  - Entry counting properly tested and documented
- **Directory Hash Protection** - Fixed "Is a directory (os error 21)" error during comparison
  - Fixed scanner to use consistent directory detection (always use `metadata.is_dir()`)
  - Previously used `file_type().is_dir()` for filtering but `metadata.is_dir()` for FileEntry, causing symlink mismatches
  - Added directory check at the start of `compare_files()` as first line of defense
  - Added explicit directory checks in `hash_file()` and `partial_hash_file()` as secondary protection
  - Comparison now gracefully handles directory entries by marking them as Different rather than erroring

### Testing
- **Scanner Tests (6 tests)**
  - `test_scanner_basic` - Basic scanning with accurate entry counts
  - `test_scanner_ignore_patterns` - Simple glob patterns
  - `test_scanner_gitignore_style_patterns` - Complex gitignore-style patterns
  - `test_scanner_root_relative_patterns` - Root-only matching
  - `test_scanner_directory_only_patterns` - Directory-only exclusion
  - `test_scanner_no_root_entry` - Explicit root exclusion verification

- **SFTP VFS Tests (18 tests)**
  - **Unit Tests (5 tests)** - Configuration and authentication
    - `test_sftp_config_default` - Default configuration validation
    - `test_sftp_auth_variants` - Password, KeyFile, Agent auth types
    - `test_sftp_config_clone` - Configuration cloning
    - `test_sftp_config_with_custom_port` - Non-standard SSH ports
    - `test_sftp_config_with_root_path` - Root path mapping
  - **Integration Tests (13 tests)** - Require SFTP server (marked as ignored)
    - `test_sftp_vfs_creation` - Connection establishment
    - `test_sftp_vfs_list_directory` - Directory listing
    - `test_sftp_vfs_read_write` - File read/write operations
    - `test_sftp_vfs_metadata` - Metadata retrieval
    - `test_sftp_vfs_create_directory` - Directory creation
    - `test_sftp_vfs_copy_file` - File copy operations
    - `test_sftp_vfs_remove_file` - File deletion
    - `test_sftp_vfs_with_key_auth` - SSH key file authentication
    - `test_sftp_vfs_with_agent_auth` - SSH agent authentication
    - `test_sftp_vfs_nested_directories` - Nested directory structures
    - `test_sftp_vfs_large_file` - Large file operations (1MB)
    - `test_sftp_vfs_metadata_not_found` - Error handling
    - `test_sftp_vfs_open_file_not_found` - Error handling

### Deferred to Phase 7

Three WinMerge parity features were thoroughly researched and strategically deferred due to complexity:

- **Grammar-Aware Text Comparison** (4-6 weeks estimated)
  - Requires tree-sitter integration for AST parsing
  - Need language-specific grammars (Rust, Python, JS, etc.)
  - Research identified diffsitter and difftastic as existing tools
  - Alternative: Integrate difftastic as external tool via CLI wrapper
  - Deferred in favor of simpler preprocessing options (whitespace, case, regex)

- **Editable Hex Mode** (2-3 weeks estimated)
  - Complex GUI/UX work with custom Slint widgets
  - Safety concerns require robust backup and validation
  - Research identified hex-patch, rex, hexdino as options
  - Alternative: Add "Open in External Hex Editor" button
  - Current read-only hex view sufficient for comparison use case

- **Structure Viewer for Binary Files** (2-3 weeks estimated)
  - Specialized feature for ELF, PE, Mach-O analysis
  - Requires goblin crate integration and tree view GUI
  - Complex GUI requirements with side-by-side comparison
  - Alternative: Export to JSON for use with external tools
  - Primarily useful for developers comparing compiled binaries

**Documentation**: Comprehensive research findings in `docs/WINMERGE_PARITY_PHASE1.md`

### Summary Statistics

**Branch**: `feature/winmerge-parity` (16 commits ahead of main)
**Changes**: 59 files changed, 10,274 insertions, 4,731 deletions
**Time Investment**: ~7 days for implemented features, ~10-14 weeks deferred to Phase 7

**Completion Rates**:
- Text Comparison: 3/4 features (75%)
- Binary/Hex Comparison: 0/2 features (0% - deferred)
- Image Comparison: 2/2 features (100%)
- Overall WinMerge Parity: 5/8 features (62.5%)

**Key Commits**:
- da9ebe0: Add security scanning, scheduled builds, and GitHub templates
- 212e0f0: Modernize release workflow and add comprehensive CI/CD automation
- 6c03145: Consolidate WinMerge parity Phase 1 documentation
- 6fef726: Enhance CI/CD with GUI tests, artifacts, and automated releases
- 34419a5: Add --text-diff flag and complete CLI text comparison integration
- b048910: Apply Krokiet best practices to fix tree view name column display

**Documentation**:
- `docs/WINMERGE_PARITY_PHASE1.md` - Phase 1 completion summary (22K)
- `docs/WINMERGE_PARITY.md` - Main roadmap (all phases) (22K)
- `.github/workflows/README.md` - CI/CD documentation
- `deny.toml` - Security policy configuration

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
