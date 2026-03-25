# teczka GitHub Milestone Plan

Last updated: 2026-02-13

This document converts the `teczka` roadmap into a concrete GitHub execution plan with:
- Milestones with target dates
- Epics and issue-sized tasks
- Labels, priorities, and dependencies
- Definition of Done and release gates

## Progress Snapshot (Implemented)

Completed in current codebase:
1. Multi-selection and context-menu command handling in folder view.
2. "Files only" filter mode and persistence of last-used settings/options per user.
3. Multi-tab session workspace with per-tab state capture/restore.
4. Richer KDE-style Help/About, Session Profiles, and Options dialog improvements.
5. Sync preview implemented and Sync execution wired (CLI-first with local fallback).
6. Profile auto-save on close (`Last Session (Auto)` snapshot behavior).
7. Folder column width persistence and restore behavior.
8. CLI bridge integration expanded with `sync`, `copy`, `diff-file`, and `read` command wrappers.

Remaining milestone work is primarily around broader QA automation, performance/scale hardening, and cross-platform release packaging.

## 1) Milestones

| Milestone | Target Window | Goal |
|---|---|---|
| M1 - Stabilize Core UX | 2026-02-16 to 2026-02-27 | Remove regressions and lock down current feature set |
| M2 - Sync Engine Execution | 2026-03-02 to 2026-03-20 | Move from sync preview to reliable executable sync |
| M3 - Folder UX Productivity | 2026-03-23 to 2026-04-03 | Make high-frequency workflows faster and safer |
| M4 - Viewer Improvements | 2026-04-06 to 2026-04-17 | Improve text/hex/image compare usability |
| M5 - Performance and Scale | 2026-04-20 to 2026-05-01 | Keep UI responsive on very large comparisons |
| M6 - Release Readiness | 2026-05-04 to 2026-05-15 | Ship with CI quality gates and release artifacts |

## 2) Label Set

Create and apply these labels:
- `area:pyside`
- `area:sync`
- `area:folder-view`
- `area:profiles`
- `area:settings`
- `area:viewer-text`
- `area:viewer-hex`
- `area:viewer-image`
- `area:performance`
- `area:qa`
- `type:epic`
- `type:feature`
- `type:bug`
- `type:test`
- `type:docs`
- `priority:P0`
- `priority:P1`
- `priority:P2`
- `size:S`
- `size:M`
- `size:L`
- `blocked`

## 3) Epic and Issue Backlog

Issue IDs below are suggested for tracking consistency.

### M1 - Stabilize Core UX

#### EPIC RPY-M1-E1: Regression hardening for recent UI features
- Labels: `type:epic`, `area:pyside`, `priority:P0`
- Milestone: `M1 - Stabilize Core UX`
- Acceptance criteria:
  - No crash in compare, sync-preview, tabs, profile load/save, and options flows
  - Core regressions tracked and closed

Issues:
1. `RPY-M1-01` Add smoke test matrix for tabs/profiles/options/sync-preview
   - Labels: `type:test`, `area:qa`, `priority:P0`, `size:M`
   - Depends on: none
2. `RPY-M1-02` Fix profile dialog load/save contract mismatches
   - Labels: `type:bug`, `area:profiles`, `priority:P0`, `size:S`
   - Depends on: `RPY-M1-01`
3. `RPY-M1-03` Ensure session switching cancels running comparison safely
   - Labels: `type:bug`, `area:pyside`, `priority:P0`, `size:S`
   - Depends on: `RPY-M1-01`
4. `RPY-M1-04` Add end-user error messages for invalid path/config states
   - Labels: `type:feature`, `area:settings`, `priority:P1`, `size:S`
   - Depends on: none
5. `RPY-M1-05` Add QA checklist doc for manual pre-release verification
   - Labels: `type:docs`, `area:qa`, `priority:P1`, `size:S`
   - Depends on: `RPY-M1-01`

### M2 - Sync Engine Execution

#### EPIC RPY-M2-E1: Implement executable folder synchronization
- Labels: `type:epic`, `area:sync`, `priority:P0`
- Milestone: `M2 - Sync Engine Execution`
- Acceptance criteria:
  - Execute sync supports `left_to_right`, `right_to_left`, `bidirectional`
  - Dry-run output matches execution planner
  - Delete policy supports trash and permanent delete

Issues:
1. `RPY-M2-01` Implement sync planner service from `ScanReport` + options
   - Labels: `type:feature`, `area:sync`, `priority:P0`, `size:M`
   - Depends on: none
2. `RPY-M2-02` Implement sync executor for copy/update actions
   - Labels: `type:feature`, `area:sync`, `priority:P0`, `size:L`
   - Depends on: `RPY-M2-01`
3. `RPY-M2-03` Implement delete strategy abstraction (trash/permanent)
   - Labels: `type:feature`, `area:sync`, `priority:P0`, `size:M`
   - Depends on: `RPY-M2-01`
4. `RPY-M2-04` Conflict handling policy UI for bidirectional mode
   - Labels: `type:feature`, `area:sync`, `priority:P1`, `size:M`
   - Depends on: `RPY-M2-01`
5. `RPY-M2-05` Wire SyncDialog Execute to planner+executor with progress/cancel
   - Labels: `type:feature`, `area:sync`, `priority:P0`, `size:L`
   - Depends on: `RPY-M2-02`, `RPY-M2-03`
6. `RPY-M2-06` Add sync unit tests for all `DiffStatus` combinations
   - Labels: `type:test`, `area:qa`, `priority:P0`, `size:M`
   - Depends on: `RPY-M2-02`, `RPY-M2-03`
7. `RPY-M2-07` Add sync integration tests validating preview vs execution parity
   - Labels: `type:test`, `area:qa`, `priority:P0`, `size:M`
   - Depends on: `RPY-M2-05`

### M3 - Folder UX Productivity

#### EPIC RPY-M3-E1: High-frequency folder operations usability
- Labels: `type:epic`, `area:folder-view`, `priority:P1`
- Milestone: `M3 - Folder UX Productivity`
- Acceptance criteria:
  - Most common workflows complete via keyboard/context menu
  - Column/selection behavior is predictable and persistent

Issues:
1. `RPY-M3-01` Persist LH/RH column widths per user
   - Labels: `type:feature`, `area:folder-view`, `priority:P1`, `size:M`
   - Depends on: none
2. `RPY-M3-02` Add keyboard shortcuts for expand/collapse/copy/open actions
   - Labels: `type:feature`, `area:folder-view`, `priority:P1`, `size:S`
   - Depends on: none
3. `RPY-M3-03` Add context menu actions: reveal in file manager, copy path
   - Labels: `type:feature`, `area:folder-view`, `priority:P1`, `size:S`
   - Depends on: none
4. `RPY-M3-04` Add non-blocking progress UI for long copy operations
   - Labels: `type:feature`, `area:folder-view`, `priority:P1`, `size:M`
   - Depends on: none
5. `RPY-M3-05` Add undo-friendly safeguards for destructive actions
   - Labels: `type:feature`, `area:folder-view`, `priority:P1`, `size:M`
   - Depends on: `RPY-M3-04`

### M4 - Viewer Improvements

#### EPIC RPY-M4-E1: Improve compare viewers for text, hex, image
- Labels: `type:epic`, `area:pyside`, `priority:P1`
- Milestone: `M4 - Viewer Improvements`
- Acceptance criteria:
  - User can navigate differences quickly in all viewers
  - Viewer interactions remain synced and responsive

Issues:
1. `RPY-M4-01` Text view: add next/previous diff navigation and markers
   - Labels: `type:feature`, `area:viewer-text`, `priority:P1`, `size:M`
2. `RPY-M4-02` Text view: improve synced scrolling and cursor lock options
   - Labels: `type:feature`, `area:viewer-text`, `priority:P1`, `size:S`
3. `RPY-M4-03` Hex view: jump to first mismatch and mismatch count
   - Labels: `type:feature`, `area:viewer-hex`, `priority:P1`, `size:M`
4. `RPY-M4-04` Image view: add fit/original/linked zoom modes
   - Labels: `type:feature`, `area:viewer-image`, `priority:P1`, `size:M`
5. `RPY-M4-05` Viewer QA tests and keyboard shortcut consistency pass
   - Labels: `type:test`, `area:qa`, `priority:P1`, `size:S`

### M5 - Performance and Scale

#### EPIC RPY-M5-E1: Handle large trees with responsive UI
- Labels: `type:epic`, `area:performance`, `priority:P1`
- Milestone: `M5 - Performance and Scale`
- Acceptance criteria:
  - UI remains responsive during filtering and large tree operations
  - Baseline benchmark results documented

Issues:
1. `RPY-M5-01` Add benchmark harness for 10k/50k/100k entry trees
   - Labels: `type:test`, `area:performance`, `priority:P1`, `size:M`
2. `RPY-M5-02` Optimize filter/search path for large datasets
   - Labels: `type:feature`, `area:performance`, `priority:P1`, `size:L`
   - Depends on: `RPY-M5-01`
3. `RPY-M5-03` Lazy node expansion and deferred population strategy
   - Labels: `type:feature`, `area:performance`, `priority:P1`, `size:L`
4. `RPY-M5-04` Add cancellation checkpoints in expensive UI operations
   - Labels: `type:feature`, `area:performance`, `priority:P1`, `size:M`
5. `RPY-M5-05` Publish performance report in docs
   - Labels: `type:docs`, `area:performance`, `priority:P2`, `size:S`
   - Depends on: `RPY-M5-02`, `RPY-M5-03`

### M6 - Release Readiness

#### EPIC RPY-M6-E1: Ship-quality release process
- Labels: `type:epic`, `area:qa`, `priority:P0`
- Milestone: `M6 - Release Readiness`
- Acceptance criteria:
  - CI passes with test/lint/type checks
  - Packaging process reproducible on supported platforms
  - Release checklist completed

Issues:
1. `RPY-M6-01` Add/expand CI jobs for `teczka` test gates
   - Labels: `type:feature`, `area:qa`, `priority:P0`, `size:M`
2. `RPY-M6-02` Add UI smoke tests for startup/compare/sync/profile/options
   - Labels: `type:test`, `area:qa`, `priority:P0`, `size:M`
3. `RPY-M6-03` Add packaging scripts and artifact naming conventions
   - Labels: `type:feature`, `area:qa`, `priority:P1`, `size:M`
4. `RPY-M6-04` Create release checklist and changelog workflow doc
   - Labels: `type:docs`, `area:qa`, `priority:P1`, `size:S`
5. `RPY-M6-05` Release candidate bug bash and closure criteria
   - Labels: `type:test`, `area:qa`, `priority:P0`, `size:S`

## 4) Definition of Done (DoD)

Every issue is Done only when:
1. Implementation merged with tests or explicit rationale for no tests.
2. No regressions in compare, filters, tabs, profiles, options, and sync flows.
3. User-visible change documented in `CHANGELOG.md` (or release notes draft).
4. QA checklist item marked complete.

## 5) Release Gates

Before closing milestone `M6`:
1. P0 and P1 issues are closed or formally deferred.
2. CI green on all required workflows.
3. Manual smoke pass on Linux, Windows, and macOS (or tracked exceptions).
4. Release notes include known limitations and migration notes.

## 6) Suggested GitHub Project Setup

Board columns:
1. Backlog
2. Ready
3. In Progress
4. In Review
5. Done

Custom fields:
- Milestone
- Priority (`P0/P1/P2`)
- Size (`S/M/L`)
- Area
- Risk (`Low/Med/High`)

Automation suggestions:
1. Move issue to `In Progress` when assigned.
2. Move issue to `In Review` when linked PR is opened.
3. Move issue to `Done` when linked PR is merged.

## 7) First Sprint Cut (Recommended)

Start with these 8 issues:
1. `RPY-M1-01`
2. `RPY-M1-02`
3. `RPY-M1-03`
4. `RPY-M1-04`
5. `RPY-M2-01`
6. `RPY-M2-03`
7. `RPY-M2-06`
8. `RPY-M3-01`

This gives a stable base and unlocks full sync execution with low integration risk.
