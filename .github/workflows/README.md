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

5. **ci-success** - Final Gate
   - Runs after all required jobs
   - Blocks merge if any required job fails
   - Enforces that core tests, CLI tests, FFI tests, and quality checks all pass

> **Note:** The Rust `rcompare_gui` (Slint) crate has been removed. The desktop GUI is now
> `teczka`, a PySide6/Qt6 application under `teczka/`, tested and packaged separately
> (see `uv sync && uv run pytest` and the GUI release job in `release.yml`).

### Code Coverage Pipeline (`coverage.yml`)

Measures code coverage and uploads reports to Codecov.

#### Triggers
- Push to `main` or `develop` branches
- Pull requests targeting `main` or `develop`

#### Features
- Uses `cargo-tarpaulin` for accurate Rust code coverage
- Generates both XML (Codecov) and HTML (human-readable) reports
- Excludes test files and examples from coverage calculation
- Uploads reports to Codecov for tracking over time
- Archives HTML reports as artifacts (30-day retention)

#### Local Coverage Testing
```bash
# Install tarpaulin
cargo install cargo-tarpaulin

# Run coverage locally
cargo tarpaulin --workspace --out Html --out Xml

# Open HTML report
firefox tarpaulin-report.html
```

### PR Labeler (`labeler.yml`)

Automatically labels pull requests based on changed files.

#### Labels Applied
- **core**: Changes to `rcompare_core/`
- **cli**: Changes to `rcompare_cli/`
- **gui**: Changes to `teczka/`
- **common**: Changes to `rcompare_common/`
- **documentation**: Changes to `.md` files or `docs/`
- **ci**: Changes to `.github/workflows/`
- **tests**: Changes to test files
- **dependencies**: Changes to `Cargo.toml` or `Cargo.lock`

#### Configuration
Labels are defined in [.github/labeler.yml](../labeler.yml)

### Dependabot (`dependabot.yml`)

Automated dependency updates for Rust crates and GitHub Actions.

#### Update Schedule
- **Cargo dependencies**: Weekly (Mondays)
- **GitHub Actions**: Weekly (Mondays)

#### Features
- Groups minor and patch updates together
- Limits open PRs (10 for Cargo, 5 for Actions)
- Automatic labeling (dependencies, rust, github-actions)
- Conventional commit messages (chore: for deps, ci: for actions)

#### Configuration
Dependabot settings in [.github/dependabot.yml](../dependabot.yml)

### Security Audit Pipeline (`security.yml`)

Comprehensive security scanning for dependencies and licenses.

#### Triggers
- Push to `main` or `develop` (when Cargo files change)
- Pull requests (when Cargo files change)
- Daily schedule (00:00 UTC)
- Manual workflow dispatch

#### Jobs

**1. cargo-audit** - Security Vulnerability Scanner
- Scans dependencies for known security vulnerabilities
- Uses RustSec Advisory Database
- Denies builds with known vulnerabilities
- Runs daily to catch new advisories

**2. cargo-deny** - License and Dependency Policy
- Enforces license compliance (MIT, Apache-2.0, BSD, etc.)
- Detects multiple versions of same crate
- Blocks dependencies from untrusted sources
- Warns about copyleft licenses
- Configuration in [deny.toml](../../deny.toml)

**3. cargo-outdated** - Dependency Update Check (scheduled only)
- Identifies outdated dependencies
- Only runs on scheduled builds (not PRs)
- Issues warnings but doesn't fail build

#### Configuration

**deny.toml** configures cargo-deny policies:
```toml
[advisories]
vulnerability = "deny"    # Block known vulnerabilities
yanked = "deny"          # Block yanked crates

[licenses]
allow = ["MIT", "Apache-2.0", "BSD-2-Clause", ...]
copyleft = "warn"        # Warn about GPL-like licenses

[bans]
multiple-versions = "warn"  # Warn about duplicate deps
```

#### Local Security Testing
```bash
# Install tools
cargo install cargo-audit cargo-deny cargo-outdated

# Run security checks
cargo audit
cargo deny check
cargo outdated
```

### Scheduled Builds (`scheduled.yml`)

Weekly builds to catch issues with dependencies and newer Rust versions.

#### Schedule
- Every Monday at 02:00 UTC

#### Jobs

**1. scheduled-build** - Multi-platform/Rust Version Build
- Tests on: Linux, Windows, macOS
- Rust versions: stable, beta
- Runs full test suite with all features
- Checks documentation generation
- Helps catch issues before they affect development

**2. minimum-rust-version** - MSRV Check
- Tests compilation with Rust 1.70 (MSRV)
- Ensures project stays compatible with declared MSRV
- Non-blocking (informational)

#### Purpose
- Catch breaking changes in dependencies early
- Test compatibility with upcoming Rust releases (beta)
- Verify MSRV remains valid
- Ensure documentation builds correctly

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

**build-release** - Builds and Releases the CLI binary (parallel across platforms)
- Compiles `rcompare_cli` in `dist` profile (LTO + single codegen unit) for all platforms
- Strips binaries (Unix) for smaller size
- Packages as `tar.gz` (Unix) or `zip` (Windows)
- Creates GitHub release (if it doesn't exist)
- Uploads standalone binary and archive, named with the Rust target triple
- Uses modern `softprops/action-gh-release` action (v1)

**build-gui-release** - Builds and Releases the teczka GUI (parallel across platforms)
- Packages the PySide6/Qt6 `teczka` app with PyInstaller into a standalone app per platform
- Packages as `tar.gz` (Unix) or `zip` (Windows)
- Uploads to the same GitHub release

**checksums** - Publishes `SHA256SUMS` and the release notes after all builds finish

#### Artifacts

Each release includes:
- CLI binary: `rcompare_cli-{version}-{target-triple}[.exe]` and matching `.tar.gz`/`.zip`
- GUI bundle: `teczka-{version}-{platform}-{arch}.{tar.gz|zip}`
- `SHA256SUMS` covering all of the above

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
   - `Code Quality`
   - `CI Success Gate`

## Running Tests Locally

Before pushing, you can run the same checks locally:

```bash
# Core library tests
cargo test --package rcompare_core --lib

# CLI tests
cargo test --package rcompare_cli

# GUI (teczka) tests
cd teczka && uv sync && uv run pytest

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

#### Artifacts

The CI pipeline uploads build artifacts with 7-day retention:
- **CLI binaries**: `rcompare_cli-{Linux|Windows|macOS}`

These artifacts are useful for testing PR builds without running the full build locally.

## Troubleshooting

### Tests Failing Locally But Passing in CI (or vice versa)

- Ensure you're using the same Rust version (check `rust-toolchain.toml` if present)
- Run `cargo clean` to clear local build artifacts
- Check for platform-specific code that might behave differently

### VFS Integration Tests Failing

This is expected if you don't have S3/WebDAV services configured. These tests are marked with `#[ignore]` and only run with `--include-ignored` flag. They're not required for CI to pass.

### teczka (GUI) Build Failing

PyInstaller builds may fail due to missing Qt6 runtime dependencies:

**Linux:**
```bash
sudo apt-get install libxcb-cursor0 libxcb-render0 libxcb-shape0 libxcb-xfixes0 \
                     libxkbcommon0 libgl1 libegl1
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
