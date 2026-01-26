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
