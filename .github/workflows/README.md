# RCompare CI/CD Configuration

This directory contains GitHub Actions workflows for continuous integration and testing.

## Workflows

### CI Pipeline (`ci.yml`)

The main CI pipeline runs on every push to `main` or `develop` branches and on all pull requests.

#### Jobs

1. **test-core** - Core Library Tests
   - Runs on: Linux, Windows, macOS
   - Tests: `rcompare_core` and `rcompare_common` library tests
   - **Required for merge** ✅
   - Fast execution (< 1 minute typically)

2. **test-cli** - CLI Integration Tests
   - Runs on: Linux, Windows, macOS
   - Tests: `rcompare_cli` tests and binary builds
   - **Required for merge** ✅
   - Validates CLI functionality across platforms

3. **quality** - Code Quality Checks
   - Runs on: Linux only
   - Checks:
     - `cargo fmt --check` - Code formatting
     - `cargo clippy` - Linting with warnings as errors
   - **Required for merge** ✅

4. **test-vfs-integration** - VFS Integration Tests
   - Runs on: Linux only
   - Tests: S3, WebDAV, and other cloud VFS implementations
   - **Not required for merge** ⚠️
   - Requires external services (S3, WebDAV servers)
   - Allowed to fail without blocking PR merges

5. **build-gui** - GUI Build Verification
   - Runs on: Linux, Windows, macOS
   - Tests: GUI builds successfully across platforms
   - **Not required for merge** ⚠️
   - May have platform-specific dependencies

6. **ci-success** - Final Gate
   - Runs after all required jobs
   - Blocks merge if any required job fails
   - Enforces that core tests, CLI tests, and quality checks all pass

## Branch Protection

To enable CI gating on GitHub:

1. Go to repository **Settings** → **Branches**
2. Add a branch protection rule for `main` (and optionally `develop`)
3. Enable "Require status checks to pass before merging"
4. Select the following required checks:
   - `Core Tests (ubuntu-latest)`
   - `Core Tests (windows-latest)`
   - `Core Tests (macos-latest)`
   - `CLI Tests (ubuntu-latest)`
   - `CLI Tests (windows-latest)`
   - `CLI Tests (macos-latest)`
   - `Code Quality`
   - `CI Success Gate`

## Running Tests Locally

Before pushing, you can run the same checks locally:

```bash
# Core library tests
cargo test --package rcompare_core --lib

# CLI tests
cargo test --package rcompare_cli

# Formatting check
cargo fmt --all -- --check

# Linting
cargo clippy --all-targets --all-features -- -D warnings

# VFS integration tests (requires S3/WebDAV services)
cargo test --package rcompare_core --lib vfs::tests_cloud -- --include-ignored
```

## Performance

The CI pipeline uses aggressive caching to minimize build times:

- **Cargo registry cache** - Downloaded crate metadata
- **Cargo git cache** - Git-based dependencies
- **Target directory cache** - Compiled artifacts

Typical execution times:
- Core tests: ~2-3 minutes per platform
- CLI tests: ~3-4 minutes per platform
- Quality checks: ~2-3 minutes
- Total pipeline: ~10-15 minutes (with parallelization)

## Troubleshooting

### Tests Failing Locally But Passing in CI (or vice versa)

- Ensure you're using the same Rust version (check `rust-toolchain.toml` if present)
- Run `cargo clean` to clear local build artifacts
- Check for platform-specific code that might behave differently

### VFS Integration Tests Failing

This is expected if you don't have S3/WebDAV services configured. These tests are marked with `#[ignore]` and only run with `--include-ignored` flag. They're not required for CI to pass.

### GUI Build Failing

GUI builds may fail due to missing system dependencies:

**Linux:**
```bash
sudo apt-get install libxcb-render0-dev libxcb-shape0-dev libxcb-xfixes0-dev \
                     libxkbcommon-dev libssl-dev libfontconfig1-dev
```

**Windows/macOS:**
Usually works out of the box, but may require Visual Studio Build Tools (Windows) or Xcode (macOS).

## Adding New Tests

When adding new test files or test modules:

1. **Unit tests** in `rcompare_core` - automatically included in `test-core` job
2. **Integration tests** in `rcompare_cli` - automatically included in `test-cli` job
3. **Cloud/VFS tests** requiring external services - mark with `#[ignore]` attribute

Example of marking a test that requires external services:

```rust
#[test]
#[ignore]  // Requires S3 service
fn test_s3_connection() {
    // Test code here
}
```

## Modifying CI Configuration

To modify the CI workflow:

1. Edit `.github/workflows/ci.yml`
2. Test changes in a feature branch
3. Review CI results before merging to main
4. Update this README if you change job structure or requirements
