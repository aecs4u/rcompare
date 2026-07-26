# RCompare Documentation Hub

This file is the consolidated entrypoint for all Markdown documentation in this repository.

## Start Here

- [Project README](../README.md): Product overview, features, install/build instructions.
- [Quick Start](../QUICKSTART.md): End-to-end usage examples for CLI and GUI.
- [Changelog](../CHANGELOG.md): Versioned change history.

## By Module

One doc per workspace crate/component, each source-verified and cross-linked:

- [rcompare_common](modules/rcompare_common.md): Shared types, traits, errors.
- [rcompare_core](modules/rcompare_core.md): Comparison engine, VFS/archive/cloud backends, merge engine, patch system.
- [rcompare_cli](modules/rcompare_cli.md): Command-line interface reference.
- [rcompare_ffi](modules/rcompare_ffi.md): Pointer to [rcompare_ffi/README.md](../rcompare_ffi/README.md), the C FFI API.
- [teczka](modules/teczka.md): PySide6/Qt6 desktop GUI feature inventory.

## Status and Roadmap

- [Project Status](status.md): Current state, test counts, known weak spots.
- [Roadmap](roadmap.md): **Source-verified**, prioritized list of remaining work for parity with Beyond Compare/WinMerge/Meld/KDiff3. The maintained source of truth — keep this current instead of adding new standalone roadmap docs.
- [Development Plan](development-plan.md): Execution plan — how the roadmap's remaining work is sequenced into phases and shippable work items, with acceptance criteria. Scope lives in `roadmap.md`; sequencing lives here.
- [Feature Comparison](../FEATURE_COMPARISON.md): Comparison with competing tools.
- [Beyond Compare GUI Config Comparison](BCOMPARE_GUI_CONFIG_COMPARISON.md): teczka's configuration surface (menus, Options, per-session settings) against Beyond Compare 5.2.4, transcribed from a live inspection on 2026-07-26.
- [Architecture](../ARCHITECTURE.md): Original design handbook (largely historical — see the notice at its top; current module boundaries are documented in `docs/modules/` instead).

## Cloud and Storage Docs

- [Cloud Storage Guide](CLOUD_STORAGE.md): Cloud backend capabilities and usage (core-API-only — see wiring status note at top of that doc).
- [Cloud Quick Start](QUICK_START_CLOUD.md): Focused cloud onboarding.

## KDE/Plasma Compliance

- [KDE Compliance](KDE_COMPLIANCE.md): Audits, checklist, shortcuts, implementation plan for teczka's KDE/Plasma UX compliance (~35% of target as of this doc's last update).

## History (dated, point-in-time — not maintained, not rewritten to match current state)

- [PR Summary](history/PR_SUMMARY.md): Historical PR-level implementation summary.
- [Review Report](history/REVIEW_REPORT.md): Dated automated code review (2026-02-13).
- [WinMerge Parity Plan](history/WINMERGE_PARITY.md) / [Phase 1](history/WINMERGE_PARITY_PHASE1.md): Phase implementation write-ups.
- [CI and Pattern Improvements](history/CI_AND_PATTERN_IMPROVEMENTS.md): Dated CI/ignore-pattern change summary (2026-01-26).
- [Test Coverage Report](history/TEST_COVERAGE_REPORT.md): Dated test-count snapshot (2026-01-26) — see [status.md](status.md) for current counts.
- [teczka Design Review](history/TECZKA_DESIGN_REVIEW.md): Dated architecture/UX review of the GUI (2026-07-25), runtime-verified against a live session and benchmarked against Beyond Compare.

## Contributor Docs

- [Contributing Guide](../CONTRIBUTING.md): Contribution workflow and quality gates.
- [Claude Instructions](../CLAUDE.md): Repository-specific coding-agent instructions.

## Consolidation Rules

- Keep **high-level docs** in repository root: `README.md`, `QUICKSTART.md`,
  `ARCHITECTURE.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `FEATURE_COMPARISON.md`.
- Keep **per-module docs** in `docs/modules/` — one file per workspace crate
  (`rcompare_common`/`rcompare_core`/`rcompare_cli`/`rcompare_ffi`) plus `teczka`.
- Keep **status/roadmap** in `docs/status.md` and `docs/roadmap.md` — these are
  the living, source-verified documents. Don't create a new standalone
  roadmap/gaps doc; add to `docs/roadmap.md` instead.
- Keep **deep-dive guides** (cloud, KDE compliance) in `docs/`.
- Keep **dated, point-in-time reports** (PR summaries, phase reports, past
  reviews) in `docs/history/` — never rewrite these to match later reality;
  add a new doc instead if something needs re-reporting.
- Every status claim in `docs/modules/`, `docs/status.md`, and `docs/roadmap.md`
  should trace to something checked against actual source, not carried forward
  from an older doc — this repo has a history of docs drifting from source in
  both directions (claiming things are missing that are actually done, and
  vice versa).
- When adding a new Markdown file, add it to this hub under the correct section.
