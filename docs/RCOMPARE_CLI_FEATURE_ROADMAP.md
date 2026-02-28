# rcompare_cli Feature Roadmap

Last updated: 2026-02-13

This roadmap focuses on `rcompare_cli` feature evolution required to:
1. Fully support `rcompare_pyside` workflows.
2. Improve standalone CLI automation quality.
3. Keep API and JSON output stable and versioned.

## Progress Snapshot (Implemented)

Completed in current codebase:
1. `RCLI-C1-01` `capabilities --json` command.
2. `RCLI-C1-02` `sync` command with shared option parser.
3. `RCLI-C1-03` `copy` command with selected-path input.
4. `RCLI-C1-04` `diff-file` command (functional modes including `text` and `binary`, plus specialized mode support).
5. `RCLI-C1-05` `read` command for side/path export to stdout or `--out`.
6. `RCLI-C2-01` + `RCLI-C2-02` sync planner/executor with dry-run parity.
7. `RCLI-C2-03` delete mode support (`trash|permanent`).
8. `RCLI-C2-04` conflict policy support (`newest|left|right|skip|error`).
9. `RCLI-C2-05` copy executor (`--path` / `--paths-file`).

Remaining high-priority roadmap items from this plan include progress streaming (`RCLI-C4-02+`), schema v2 formalization, and reliability/transaction features.

## 1) Current Gap Summary

`rcompare_cli` currently exposes a `scan` command with rich comparison flags, JSON output, and specialized diff reports.  
To fully back `rcompare_pyside`, CLI still needs command-level support for sync execution, selected-path copy operations, on-demand file-level diffs, and structured progress/events.

## 2) Milestones

| Milestone | Target Window | Outcome |
|---|---|---|
| C1 - Command Surface Expansion | 2026-02-17 to 2026-02-28 | New subcommands and capability discovery |
| C2 - Sync and Copy Execution | 2026-03-02 to 2026-03-20 | Reliable operation engine for sync/copy |
| C3 - Viewer Backend APIs | 2026-03-23 to 2026-04-10 | File-level and content APIs for GUI views |
| C4 - JSON Schema and Streaming | 2026-04-13 to 2026-04-24 | Stable schema v2 + progress/NDJSON streams |
| C5 - Reliability and Performance | 2026-04-27 to 2026-05-08 | Transaction safety, retries, scale performance |
| C6 - Release and Adoption | 2026-05-11 to 2026-05-22 | Documentation, migration guides, GA readiness |

## 3) Feature Epics

### EPIC RCLI-C1-E1: Expand command surface

Goal: evolve from scan-only to operation-oriented CLI.

Work items:
1. `RCLI-C1-01` Add `capabilities --json` command.
2. `RCLI-C1-02` Add `sync` command skeleton with shared option parser.
3. `RCLI-C1-03` Add `copy` command skeleton with selected-path input.
4. `RCLI-C1-04` Add `diff-file` command skeleton for on-demand per-file diff.
5. `RCLI-C1-05` Add `read` command skeleton for file content export.

Acceptance criteria:
1. New commands parse consistently with clap.
2. `--help` pages include clear examples and exit code semantics.
3. No regression to existing `scan` behavior.

### EPIC RCLI-C2-E1: Implement sync and copy execution

Goal: provide deterministic, auditable operations used by GUI and automation.

Work items:
1. `RCLI-C2-01` Implement sync planner (`left_to_right`, `right_to_left`, `bidirectional`).
2. `RCLI-C2-02` Implement sync executor with `--dry-run`.
3. `RCLI-C2-03` Add delete mode: `--delete-mode trash|permanent`.
4. `RCLI-C2-04` Add conflict policy: `--conflict newest|left|right|skip|error`.
5. `RCLI-C2-05` Implement `copy` operation with `--paths-file` and `--direction`.
6. `RCLI-C2-06` Add per-item operation report JSON with retryable errors.

Acceptance criteria:
1. Planner output equals executor actions in dry-run mode.
2. Operation reports include per-path status and error code.
3. Sync/copy works for local and VFS-backed paths where supported.

### EPIC RCLI-C3-E1: Viewer backend APIs

Goal: enable pyside text/hex/image views without local-only assumptions.

Work items:
1. `RCLI-C3-01` Implement `diff-file text` output mode (line-level JSON).
2. `RCLI-C3-02` Implement `diff-file binary` output mode (summary + mismatch ranges).
3. `RCLI-C3-03` Implement `diff-file image` output mode (dimensions, diff stats, optional EXIF).
4. `RCLI-C3-04` Implement `read --side left|right --path` with stdout and `--out`.
5. `RCLI-C3-05` Add guardrails for large-file read/export with explicit limits.

Acceptance criteria:
1. GUI can request file-level diffs without scanning entire tree.
2. Non-local sources are accessible through `read` abstraction.
3. JSON for each mode is stable and schema-versioned.

### EPIC RCLI-C4-E1: JSON schema v2 and streaming events

Goal: formalize machine-friendly outputs for UI and CI integrations.

Work items:
1. `RCLI-C4-01` Define JSON schema v2 for scan/sync/copy/diff-file/read.
2. `RCLI-C4-02` Add `--progress-json` event stream (stderr).
3. `RCLI-C4-03` Add `--ndjson` for incremental result delivery.
4. `RCLI-C4-04` Add stable error catalog with structured codes.
5. `RCLI-C4-05` Add compatibility contract and deprecation policy docs.

Acceptance criteria:
1. Old schema remains available for compatibility window.
2. Progress events contain phase/current/total/percent/path fields.
3. Consumers can opt into either final JSON or NDJSON streams.

### EPIC RCLI-C5-E1: Reliability and scale hardening

Goal: production-grade behavior under large and failure-prone workloads.

Work items:
1. `RCLI-C5-01` Add transaction log for sync/copy operations.
2. `RCLI-C5-02` Add resumable sync/copy checkpoints.
3. `RCLI-C5-03` Add cancellation checkpoints and clean interruption behavior.
4. `RCLI-C5-04` Add benchmarks for 10k/50k/100k entry operations.
5. `RCLI-C5-05` Add operation integrity verification mode.

Acceptance criteria:
1. Interrupted operations can be resumed safely.
2. Partial failures are reported without losing successful item records.
3. Benchmarks are reproducible and documented.

### EPIC RCLI-C6-E1: Release and migration

Goal: make adoption safe for both pyside and external users.

Work items:
1. `RCLI-C6-01` Publish migration guide from scan-only automation to multi-command workflows.
2. `RCLI-C6-02` Add command cookbook for sync/copy/diff-file/read/capabilities.
3. `RCLI-C6-03` Add end-to-end integration tests with `rcompare_pyside` bridge expectations.
4. `RCLI-C6-04` Expand CI matrix for Linux/macOS/Windows command parity.
5. `RCLI-C6-05` Tag GA release with schema and command compatibility table.

Acceptance criteria:
1. Docs contain copy-paste-ready examples for all new commands.
2. Integration tests validate expected JSON payload shapes.
3. Release notes include compatibility and known limitations.

## 4) Proposed Command Additions

Proposed top-level commands:
1. `rcompare sync`
2. `rcompare copy`
3. `rcompare diff-file`
4. `rcompare read`
5. `rcompare capabilities`

Example forms:
1. `rcompare sync LEFT RIGHT --direction left_to_right --dry-run --json`
2. `rcompare copy LEFT RIGHT --paths-file selected.txt --direction right_to_left --json`
3. `rcompare diff-file LEFT RIGHT --path src/main.rs --mode text --json`
4. `rcompare read LEFT RIGHT --side left --path assets/logo.png --out /tmp/logo.png`
5. `rcompare capabilities --json`

## 5) Priority Order for Immediate Implementation

Recommended first 8 tasks:
1. `RCLI-C1-01` capabilities command.
2. `RCLI-C1-02` sync command skeleton.
3. `RCLI-C2-01` sync planner.
4. `RCLI-C2-02` sync executor dry-run parity.
5. `RCLI-C2-03` delete-mode behavior.
6. `RCLI-C1-03` copy command skeleton.
7. `RCLI-C2-05` copy executor for selected paths.
8. `RCLI-C4-02` structured progress stream.

This sequence unlocks the largest `rcompare_pyside` backend parity gains first.

## 6) Definition of Done

A roadmap task is done only when:
1. Unit and integration tests cover success and failure paths.
2. JSON output is validated against schema fixtures.
3. CLI help and docs include examples and exit-code behavior.
4. No regression to existing `scan` command and schema v1.1 output mode.
