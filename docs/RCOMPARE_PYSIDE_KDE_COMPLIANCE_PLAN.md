# rcompare_pyside KDE Compliance Development Plan

Last updated: 2026-02-13

This plan defines the work required to make `rcompare_pyside` behave like a first-class KDE/Plasma application (UI conventions, desktop integration, accessibility, packaging, and QA).

## 1) Scope and Target

Target quality bar:
- Follows KDE/Plasma UX conventions for menus, shortcuts, dialogs, and visual behavior.
- Integrates with KDE desktop services and theming without hardcoded conflicting styles.
- Ships Linux artifacts with proper desktop metadata (`.desktop`, AppStream, icons).
- Passes KDE-focused QA on both Wayland and X11.

Non-goals (for this plan):
- Rewriting the app in Qt/C++ or KDE Frameworks.
- Implementing every optional KDE feature (focus is practical compliance, not framework parity).

## 2) Current Gaps (High-Level)

1. Hardcoded widget/dialog styles in several places conflict with KDE theme inheritance.
2. Menu taxonomy is custom and only partially aligned with KDE patterns.
3. Shortcut schema is inconsistent (some collisions and non-standard mappings).
4. Context actions and dialogs need stronger consistency for destructive operations and confirmations.
5. Desktop packaging metadata for KDE discoverability is not fully defined.
6. No explicit KDE-focused acceptance test matrix.

## 3) Workstreams

### WS1: KDE UX and Information Architecture
Goal: Align primary interaction model with KDE expectations.

Deliverables:
- Menu normalization to KDE-like structure:
  - `File`, `Edit`, `View`, `Tools`, `Settings`, `Help`.
- Action naming consistency across menu/toolbar/context menus.
- Unified terminology for comparison/sync/profile operations.

Acceptance criteria:
- No duplicate/conflicting action labels.
- Common workflows reachable in <= 2 navigation steps.
- Help text reflects final action names.

### WS2: Theming and Visual Compliance
Goal: Respect KDE color/font/icon themes by default.

Deliverables:
- Reduce hardcoded stylesheet usage in dialogs/widgets.
- Prefer palette-driven styling and `QIcon.fromTheme`.
- Fallback icon mapping table for missing theme icons.
- High-DPI behavior verification.

Acceptance criteria:
- App correctly follows active Plasma light/dark theme.
- Icon set remains coherent across Breeze/Breeze Dark.
- No unreadable foreground/background combinations.

### WS3: Shortcuts and Keyboard Standards
Goal: Align shortcuts with KDE conventions and remove collisions.

Deliverables:
- Shortcut audit and canonical mapping table.
- Collision fixes (global vs context actions).
- Keyboard navigation support in dialogs and folder trees.

Acceptance criteria:
- No duplicate active shortcut collisions in default profile.
- Core workflows usable keyboard-only.
- Shortcut list documented and surfaced in Help.

### WS4: Dialog and Workflow Consistency
Goal: KDE-style behavior for options, profiles, sync, and confirmations.

Deliverables:
- Consistent dialog button order and default button semantics.
- Destructive action confirmations with clear target/path context.
- Non-blocking progress feedback for long operations.
- Improved error messages with actionable remediation.

Acceptance criteria:
- Destructive operations always require explicit confirmation.
- Long-running operations provide progress and cancel path.
- Error dialogs include cause + next step.

### WS5: Desktop Integration (Plasma/Linux)
Goal: Make the app install and behave like a KDE desktop app.

Deliverables:
- `rcompare-pyside.desktop` entry with categories and actions.
- AppStream metainfo file (`org.aecs4u.rcompare_pyside.metainfo.xml`).
- Icon assets and install locations compliant with XDG.
- URL/file association definitions for compare actions (where practical).

Acceptance criteria:
- App appears correctly in Plasma launcher and Discover metadata checks.
- Desktop file validates via `desktop-file-validate`.
- AppStream validates via `appstreamcli validate`.

### WS6: Accessibility and Internationalization
Goal: Meet baseline accessibility and localization readiness.

Deliverables:
- Accessible names/tooltips for key controls.
- Focus order and tab chain pass.
- Initial i18n extraction strategy (Qt Linguist `.ts` workflow).

Acceptance criteria:
- Keyboard focus indicators and order are deterministic.
- Screen reader exposed names exist for main actions.
- Strings externalized for translation.

### WS7: Quality and Compliance Testing
Goal: Add objective gates for KDE compliance.

Deliverables:
- KDE QA checklist (manual + automated subset).
- Smoke tests for startup/compare/sync/profile/options/help.
- Linux test matrix:
  - Plasma Wayland
  - Plasma X11
  - Light/Dark themes

Acceptance criteria:
- Compliance checklist >= 90% pass.
- Release candidate blocked if any P0 compliance issue fails.

## 4) Phased Timeline (10 Weeks)

## Phase 0 (Week 1): Baseline and Audit
- Build a KDE compliance checklist.
- Capture baseline screenshots and shortcut map.
- Open issues and label by workstream.

## Phase 1 (Weeks 2-3): UX + Shortcut Core
- Execute WS1 and WS3.
- Fix menu/action naming and shortcut collisions.

## Phase 2 (Weeks 4-5): Theming + Dialog Consistency
- Execute WS2 and WS4.
- Remove hardcoded style conflicts.

## Phase 3 (Weeks 6-7): Desktop Integration + i18n/a11y
- Execute WS5 and WS6.
- Add desktop metadata and validation scripts.

## Phase 4 (Weeks 8-9): QA Hardening
- Execute WS7.
- Close P0/P1 compliance defects.

## Phase 5 (Week 10): Release Candidate
- Freeze scope.
- Run full KDE compliance checklist.
- Publish release notes section: "KDE compliance status".

## 5) Issue Backlog Template

Use this issue structure:

- Title: `KDE-WSx-YY: <concise task>`
- Labels:
  - `area:pyside`
  - `area:kde-compliance`
  - one of `type:feature|type:bug|type:test|type:docs`
  - one of `priority:P0|P1|P2`
  - one of `size:S|M|L`
- Required fields:
  - User-visible behavior
  - Technical approach
  - Test plan
  - Acceptance criteria

## 6) Definition of Done (KDE Compliance)

An item is done only if:
1. Behavior matches KDE compliance checklist entry.
2. Tests/checklist entries are updated and passing.
3. User-facing docs/help text are updated.
4. No new shortcut/theme regressions introduced.

## 7) Release Gate for "KDE Compliant" Claim

Before claiming KDE compliance in release notes:
1. All WS1-WS5 P0 issues closed.
2. No open P0/P1 accessibility issues.
3. Desktop and AppStream validation pass in CI.
4. Manual verification completed on Plasma Wayland and X11.

## 8) Immediate Next Sprint (Recommended)

1. Create `area:kde-compliance` labels and project board lane.
2. Implement shortcut collision audit/fix.
3. Remove hardcoded dialog stylesheet blocks that override KDE palette.
4. Normalize top-level menus to KDE convention.
5. Add draft `.desktop` and AppStream files with validation scripts.
