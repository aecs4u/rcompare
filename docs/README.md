# RCompare Documentation Hub

This file is the consolidated entrypoint for all Markdown documentation in this repository.

## Start Here

- [Project README](../README.md): Product overview, features, install/build instructions.
- [Quick Start](../QUICKSTART.md): End-to-end usage examples for CLI and GUI.
- [Changelog](../CHANGELOG.md): Versioned change history.

## Core Engineering Docs

- [Architecture](../ARCHITECTURE.md): Core architecture and implementation handbook.
- [Development Status](../DEVELOPMENT_STATUS.md): Current state of implemented components.
- [Known Gaps](../GAPS.md): Limitations and incomplete areas.
- [Feature Comparison](../FEATURE_COMPARISON.md): Comparison with competing tools.
- [Compliance Matrix](../COMPLIANCE_MATRIX.md): Requirement/feature compliance tracking.

## Roadmaps and Plans

- [Main Roadmap](../ROADMAP.md): Product roadmap.
- [VFS & Archive Roadmap](../ROADMAP_VFS.md): Storage/archive-focused roadmap.
- [CLI Feature Roadmap](RCOMPARE_CLI_FEATURE_ROADMAP.md): Planned CLI milestones.
- [PySide GitHub Plan](RCOMPARE_PYSIDE_GITHUB_PLAN.md): PySide release/milestone planning.
- [PySide KDE Compliance Plan](RCOMPARE_PYSIDE_KDE_COMPLIANCE_PLAN.md): KDE-focused UX, integration, and QA plan.
- [WinMerge Parity Plan](WINMERGE_PARITY.md): Detailed parity plan.
- [WinMerge Parity Phase 1](WINMERGE_PARITY_PHASE1.md): Phase completion report.

## Cloud and Storage Docs

- [Cloud Storage Guide](CLOUD_STORAGE.md): Cloud backend capabilities and usage.
- [Cloud Quick Start](QUICK_START_CLOUD.md): Focused cloud onboarding.
- [Cloud Features Summary](../CLOUD_FEATURES_SUMMARY.md): Implemented cloud scope summary.

## Quality, CI, and Reviews

- [Test Coverage Report](TEST_COVERAGE_REPORT.md): Test scope and coverage details.
- [CI and Pattern Improvements](CI_AND_PATTERN_IMPROVEMENTS.md): CI and ignore-pattern enhancements.
- [Review Report](../REVIEW_REPORT.md): Comprehensive review findings.
- [PR Summary](PR_SUMMARY.md): Historical PR-level implementation summary.

## API / Integration Docs

- [FFI API Guide](../rcompare_ffi/README.md): C/C++ API usage and reference.

## Contributor Docs

- [Contributing Guide](../CONTRIBUTING.md): Contribution workflow and quality gates.
- [Claude Instructions](../CLAUDE.md): Repository-specific coding-agent instructions.

## Consolidation Rules

- Keep **high-level docs** in repository root:
  - `README.md`, `QUICKSTART.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `CHANGELOG.md`, `CONTRIBUTING.md`.
- Keep **deep-dive and report docs** in `docs/`.
- When adding a new Markdown file, add it to this hub under the correct section.
