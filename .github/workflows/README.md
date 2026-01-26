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

5. **test-gui** - GUI Tests & Build
   - Runs on: Linux, Windows, macOS
   - Tests: GUI compile tests (`ui_compile`)
   - Builds: Both debug and release GUI binaries
   - Artifacts: Uploads binaries with 7-day retention
   - **Required for merge** ✅
   - May have platform-specific dependencies (see Troubleshooting section)

6. **ci-success** - Final Gate
   - Runs after all required jobs
   - Blocks merge if any required job fails
   - Enforces that core tests, CLI tests, GUI tests, and quality checks all pass

### Release Pipeline (`release.yml`)

The release pipeline automates building and publishing release binaries for all platforms.

#### Triggers

- **Tag push**: Automatically triggered when a version tag is pushed (e.g., `v0.1.0`, `v1.2.3`)
- **Manual dispatch**: Can be manually triggered from GitHub Actions tab with a custom tag

#### Build Matrix

Builds for three platforms:
- **Linux**: `x86_64-unknown-linux-gnu` (Ubuntu latest)
- **Windows**: `x86_64-pc-windows-msvc` (Windows latest)
- **macOS**: `x86_64-apple-darwin` (macOS latest)

#### Build Process

1. **create-release** - Creates GitHub Release
   - Extracts version from tag
   - Creates release with changelog template
   - Provides upload URL for build artifacts

2. **build-release** - Builds Binaries
   - Compiles CLI and GUI in release mode
   - Strips binaries (Unix) for smaller size
   - Packages as `tar.gz` (Unix) or `zip` (Windows)
   - Uploads individual binaries and archives to release

#### Artifacts

Each release includes:
- Individual binaries: `rcompare_cli-{platform}-x86_64[.exe]`
- Individual binaries: `rcompare_gui-{platform}-x86_64[.exe]`
- Combined archives: `rcompare-{version}-{platform}-x86_64.{tar.gz|zip}`

#### Creating a Release

```bash
# Tag the release
git tag v0.1.0
git push origin v0.1.0

# Or use GitHub CLI
gh release create v0.1.0 --generate-notes

# The workflow will automatically:
# 1. Build binaries for all platforms
# 2. Create GitHub release
# 3. Upload all artifacts
```

#### Manual Release

To manually trigger a release:
1. Go to **Actions** → **Release** workflow
2. Click **Run workflow**
3. Enter the tag name (e.g., `v0.1.0`)
4. Click **Run workflow**

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
   - `GUI Tests & Build (ubuntu-latest)`
   - `GUI Tests & Build (windows-latest)`
   - `GUI Tests & Build (macos-latest)`
   - `Code Quality`
   - `CI Success Gate`

## Running Tests Locally

Before pushing, you can run the same checks locally:

```bash
# Core library tests
cargo test --package rcompare_core --lib

# CLI tests
cargo test --package rcompare_cli

# GUI compile tests
cargo test --package rcompare_gui --test ui_compile

# Build GUI binary
cargo build --package rcompare_gui --release

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
- GUI tests: ~4-5 minutes per platform (includes debug and release builds)
- Quality checks: ~2-3 minutes
- Total pipeline: ~15-20 minutes (with parallelization)

#### Artifacts

The CI pipeline uploads build artifacts with 7-day retention:
- **CLI binaries**: `rcompare_cli-{Linux|Windows|macOS}`
- **GUI binaries**: `rcompare_gui-{Linux|Windows|macOS}`

These artifacts are useful for testing PR builds without running the full build locally.

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
