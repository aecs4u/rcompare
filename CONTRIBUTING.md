# Contributing to RCompare

Thank you for your interest in contributing to RCompare! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Architecture](#project-architecture)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Documentation](#documentation)
- [Getting Help](#getting-help)

## Code of Conduct

This project follows the [Rust Code of Conduct](https://www.rust-lang.org/policies/code-of-conduct). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Getting Started

### Prerequisites

- **Rust**: Install via [rustup](https://rustup.rs/) (MSRV: 1.70+)
- **Git**: Version control
- **Platform-specific dependencies**:
  - Linux: `libssl-dev`, `pkg-config`
  - macOS: Xcode Command Line Tools
  - Windows: Visual Studio Build Tools

### Areas for Contribution

We welcome contributions in the following areas:

- **Bug fixes**: Check the [issue tracker](https://github.com/aecs4u/rcompare/issues)
- **New features**: Specialized file comparisons, VFS providers, UI improvements
- **Documentation**: User guides, API documentation, examples
- **Testing**: Unit tests, integration tests, performance benchmarks
- **Performance**: Optimization, profiling, benchmarking

## Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/rcompare.git
cd rcompare

# Add upstream remote
git remote add upstream https://github.com/aecs4u/rcompare.git
```

### 2. Build the Project

```bash
# Build all workspace members
cargo build

# Build release version
cargo build --release

# Build specific component
cargo build --package rcompare_cli
cargo build --package rcompare_gui
```

### 3. Run Tests

```bash
# Run all tests
cargo test

# Run tests for a specific package
cargo test --package rcompare_core

# Run tests with output
cargo test -- --nocapture

# Run specific test
cargo test test_name
```

### 4. Run Linters and Formatters

```bash
# Format code (required before committing)
cargo fmt --all

# Check formatting without changes
cargo fmt --all -- --check

# Run Clippy (required before committing)
cargo clippy --all-targets --all-features -- -D warnings

# Run security audit
cargo audit

# Run cargo-deny checks
cargo deny check
```

## Project Architecture

RCompare follows the architectural patterns of [Czkawka](https://github.com/qarmin/czkawka) with strict separation of concerns:

### Workspace Structure

```
rcompare/
├── rcompare_common/     # Shared types and utilities
├── rcompare_core/       # Core business logic (NO UI dependencies)
├── rcompare_cli/        # Command-line interface
├── rcompare_gui/        # Slint-based graphical interface
├── rcompare_ffi/        # C FFI layer for external integrations
└── examples/            # Usage examples
```

### Key Principles

1. **Core Library Purity**: `rcompare_core` must remain UI-agnostic
2. **Memory Safety**: Minimize `unsafe` code; document all unsafe blocks with `# Safety` comments
3. **Concurrency**: Use `rayon` for parallel operations
4. **Cross-Platform**: All features must work on Linux, Windows, and macOS
5. **Privacy-First**: No telemetry or external network calls without explicit user consent

For detailed architecture information, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Development Workflow

### Creating a Feature Branch

```bash
# Update your fork
git fetch upstream
git checkout main
git merge upstream/main

# Create a feature branch
git checkout -b feature/your-feature-name
# or for bug fixes
git checkout -b fix/issue-number-description
```

### Making Changes

1. **Write code** following our [coding standards](#coding-standards)
2. **Add tests** for new functionality (see [Testing Guidelines](#testing-guidelines))
3. **Update documentation** if adding/changing public APIs
4. **Run tests and linters** before committing

```bash
# Quick validation before commit
cargo fmt --all && cargo clippy --all-targets -- -D warnings && cargo test
```

### Keeping Your Branch Updated

```bash
# Regularly sync with upstream
git fetch upstream
git rebase upstream/main
```

## Coding Standards

### Rust Style Guide

- Follow the [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/)
- Use `rustfmt` with default settings (enforced by CI)
- Maximum line length: 100 characters (rustfmt default)

### Code Organization

- One module per file when practical
- Group related functionality in modules
- Keep functions focused and small (<100 lines when possible)
- Use descriptive names; avoid abbreviations unless widely understood

### Error Handling

```rust
// ✅ Good: Use Result with descriptive errors
pub fn parse_file(path: &Path) -> Result<Data, RCompareError> {
    let content = std::fs::read_to_string(path)
        .map_err(|e| RCompareError::Io { path: path.to_path_buf(), source: e })?;
    // ... parse content
    Ok(data)
}

// ❌ Bad: Using unwrap() in library code
pub fn parse_file(path: &Path) -> Data {
    let content = std::fs::read_to_string(path).unwrap(); // DON'T DO THIS
    // ...
}
```

- **Library code** (`rcompare_core`, `rcompare_common`): Never use `unwrap()` or `expect()`
- **Application code** (`rcompare_cli`, `rcompare_gui`): Use `expect()` with descriptive messages when failure is truly unrecoverable
- **Test code**: `unwrap()` is acceptable

### Documentation

```rust
/// Brief one-line summary of the function.
///
/// More detailed explanation if needed. Describe what the function does,
/// not how it does it.
///
/// # Arguments
///
/// * `path` - The file path to process
/// * `options` - Configuration options for processing
///
/// # Returns
///
/// Returns `Ok(Data)` on success, or an error if the file cannot be read
/// or parsed.
///
/// # Errors
///
/// This function will return an error if:
/// - The file does not exist
/// - The file cannot be read due to permissions
/// - The file content is malformed
///
/// # Examples
///
/// ```
/// use rcompare_core::parse_file;
/// use std::path::Path;
///
/// let data = parse_file(Path::new("config.json"))?;
/// ```
pub fn parse_file(path: &Path, options: &Options) -> Result<Data, RCompareError> {
    // Implementation
}
```

### Safety Documentation

All `unsafe` code must include a `# Safety` section:

```rust
/// # Safety
///
/// This function is unsafe because it dereferences a raw pointer.
/// The caller must ensure that:
/// - `ptr` is non-null
/// - `ptr` points to a valid, properly aligned `PatchSetHandle`
/// - The handle has not been freed
unsafe fn get_handle<'a>(ptr: *const PatchSetHandle) -> &'a PatchSetHandle {
    &*ptr
}
```

## Testing Guidelines

### Test Coverage Requirements

- **New features**: Must include tests (unit and/or integration)
- **Bug fixes**: Must include a regression test
- **Public APIs**: Must have documentation examples (doctests)
- **Target coverage**: Aim for >70% code coverage

### Test Structure

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_feature_happy_path() {
        // Arrange
        let input = create_test_data();

        // Act
        let result = function_under_test(input);

        // Assert
        assert_eq!(result, expected_value);
    }

    #[test]
    fn test_feature_error_handling() {
        // Test error conditions
        let result = function_under_test(invalid_input);
        assert!(result.is_err());
    }

    #[test]
    fn test_feature_edge_case() {
        // Test boundary conditions, empty inputs, etc.
    }
}
```

### Integration Tests

Place integration tests in `<package>/tests/`:

```rust
// rcompare_core/tests/integration_test.rs
use rcompare_core::{Scanner, ScanOptions};
use std::path::Path;

#[test]
fn test_full_scan_workflow() {
    let scanner = Scanner::new();
    let results = scanner.scan(Path::new("fixtures/test_data")).unwrap();
    assert!(results.files.len() > 0);
}
```

### Test Data

- Keep test fixtures in `fixtures/` or `testdata/` directories
- Use `tempfile` crate for temporary test files
- Clean up test data in test teardown or use RAII patterns

## Pull Request Process

### Before Submitting

Ensure your changes:

1. ✅ Pass all tests: `cargo test`
2. ✅ Pass formatting check: `cargo fmt --all -- --check`
3. ✅ Pass Clippy: `cargo clippy --all-targets -- -D warnings`
4. ✅ Include tests for new functionality
5. ✅ Update documentation for API changes
6. ✅ Have descriptive commit messages

### PR Submission

1. **Push your branch** to your fork
2. **Open a Pull Request** against `main` branch
3. **Fill out the PR template** with:
   - Description of changes
   - Related issue number (if applicable)
   - Testing performed
   - Screenshots/output (if UI changes)

### PR Template

```markdown
## Description
Brief description of what this PR does.

## Related Issue
Fixes #123

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe the tests you ran and how to reproduce them.

## Checklist
- [ ] My code follows the project's coding standards
- [ ] I have performed a self-review of my code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have added tests that prove my fix/feature works
- [ ] New and existing tests pass locally
- [ ] I have updated the documentation accordingly
```

### Review Process

- Maintainers will review your PR within a few days
- Address feedback by pushing new commits to your branch
- Once approved, a maintainer will merge your PR
- Your contribution will be acknowledged in release notes

## Commit Message Guidelines

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks, dependency updates

### Examples

```
feat(core): add support for YAML file comparison

Implements structural comparison for YAML files with path-based
diffing and type checking.

Closes #45
```

```
fix(cli): correct exit code for scan errors

Previously returned 0 even when scan failed. Now returns 1 on error.

Fixes #78
```

```
docs: add examples for archive comparison

Added example code demonstrating ZIP and TAR archive comparison
workflows.
```

## Documentation

### Types of Documentation

1. **Code Documentation**: Rustdoc comments on public APIs
2. **User Documentation**: Usage guides, tutorials in `docs/`
3. **Architecture Documentation**: Design decisions in `ARCHITECTURE.md`
4. **Examples**: Runnable examples in `examples/`

### Building Documentation

```bash
# Build and open API documentation
cargo doc --no-deps --open

# Build documentation for all dependencies
cargo doc --open
```

### Writing Good Documentation

- Start with a one-line summary
- Explain the "why," not just the "what"
- Include examples for complex APIs
- Document error conditions
- Link to related functions/types using `[`Type`]` syntax

## Getting Help

### Resources

- **Documentation**: [docs/](docs/) directory
- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Issue Tracker**: [GitHub Issues](https://github.com/aecs4u/rcompare/issues)
- **Discussions**: [GitHub Discussions](https://github.com/aecs4u/rcompare/discussions)

### Asking Questions

- **General questions**: Open a GitHub Discussion
- **Bug reports**: Open a GitHub Issue with reproduction steps
- **Feature requests**: Open a GitHub Issue with use case description

### Issue Template

When reporting bugs, include:

1. **RCompare version**: `rcompare_cli --version`
2. **Operating system**: Linux/Windows/macOS + version
3. **Rust version**: `rustc --version`
4. **Steps to reproduce**
5. **Expected behavior**
6. **Actual behavior**
7. **Minimal reproduction case** (if possible)

## Development Tips

### Useful Commands

```bash
# Watch mode (install cargo-watch first)
cargo watch -x test

# Run specific test pattern
cargo test --package rcompare_core -- comparison

# Check without building
cargo check

# Build with verbose output
cargo build -vv

# Clean build artifacts
cargo clean
```

### IDE Setup

#### VS Code

Recommended extensions:
- `rust-analyzer`: Rust language support
- `CodeLLDB`: Debugging
- `Even Better TOML`: Cargo.toml support

#### IntelliJ IDEA / CLion

- Install the Rust plugin from JetBrains Marketplace

### Performance Profiling

```bash
# Install profiling tools
cargo install cargo-flamegraph

# Generate flamegraph (Linux only)
cargo flamegraph --bin rcompare_cli -- scan /large/dir /other/dir

# Use criterion for benchmarks
cargo bench
```

---

## License

By contributing to RCompare, you agree that your contributions will be licensed under the same dual MIT OR Apache-2.0 license that covers the project.

## Thank You!

Your contributions help make RCompare better for everyone. We appreciate your time and effort! 🦀
