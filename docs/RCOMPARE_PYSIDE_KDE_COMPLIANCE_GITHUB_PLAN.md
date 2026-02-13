# rcompare_pyside KDE Compliance GitHub Milestone Plan

Last updated: 2026-02-13

This document converts the KDE Compliance Plan into a concrete GitHub execution plan with:
- Milestones with target dates
- Epics and issue-sized tasks
- Labels, priorities, and dependencies
- Definition of Done and release gates

## 1) Milestones

| Milestone | Target Window | Goal |
|---|---|---|
| KDE-M0 - Baseline Audit | 2026-02-17 to 2026-02-21 | Document current gaps and create compliance checklist |
| KDE-M1 - UX & Shortcuts | 2026-02-24 to 2026-03-07 | Align menus, actions, and keyboard behavior with KDE |
| KDE-M2 - Theme & Dialog | 2026-03-10 to 2026-03-21 | Remove style conflicts, respect Plasma theming |
| KDE-M3 - Desktop Integration | 2026-03-24 to 2026-04-04 | Add .desktop, AppStream, icons, and XDG compliance |
| KDE-M4 - QA Hardening | 2026-04-07 to 2026-04-18 | Compliance testing on Wayland/X11, light/dark themes |
| KDE-M5 - Release Candidate | 2026-04-21 to 2026-04-25 | Final compliance verification and release gate |

## 2) Label Set

Add these labels to the existing PySide label set:
- `area:kde-compliance`
- `area:theming`
- `area:shortcuts`
- `area:desktop-integration`
- `area:accessibility`
- `area:i18n`

## 3) Epic and Issue Backlog

Issue IDs use prefix `KDE` to distinguish from core PySide work.

### KDE-M0 - Baseline Audit

#### EPIC KDE-M0-E1: KDE Compliance Assessment and Planning
- Labels: `type:epic`, `area:kde-compliance`, `priority:P0`
- Milestone: `KDE-M0 - Baseline Audit`
- Acceptance criteria:
  - Compliance checklist created with measurable pass/fail criteria
  - All gaps documented with severity ratings
  - Issue backlog prioritized and assigned to milestones

Issues:
1. `KDE-M0-01` Create KDE compliance checklist (menu, shortcuts, theme, dialogs, desktop)
   - Labels: `type:docs`, `area:kde-compliance`, `priority:P0`, `size:S`
   - Depends on: none
   - Description: Build a comprehensive checklist covering WS1-WS7 with objective pass/fail criteria

2. `KDE-M0-02` Audit current menu structure against KDE conventions
   - Labels: `type:docs`, `area:kde-compliance`, `priority:P0`, `size:S`
   - Depends on: `KDE-M0-01`
   - Description: Document menu taxonomy gaps, action naming inconsistencies, and missing standard items

3. `KDE-M0-03` Audit keyboard shortcuts and identify collisions
   - Labels: `type:docs`, `area:shortcuts`, `priority:P0`, `size:M`
   - Depends on: `KDE-M0-01`
   - Description: Create complete shortcut map, identify duplicates, and compare against KDE standards

4. `KDE-M0-04` Audit hardcoded styles and theme conflicts
   - Labels: `type:docs`, `area:theming`, `priority:P0`, `size:S`
   - Depends on: `KDE-M0-01`
   - Description: Identify all hardcoded QSS, color values, and palette overrides that break KDE theme inheritance

5. `KDE-M0-05` Capture baseline screenshots (Breeze Light/Dark, Wayland/X11)
   - Labels: `type:docs`, `area:kde-compliance`, `priority:P1`, `size:S`
   - Depends on: none
   - Description: Baseline visual regression reference for comparison after changes

### KDE-M1 - UX & Shortcuts

#### EPIC KDE-M1-E1: Menu and Action Normalization
- Labels: `type:epic`, `area:kde-compliance`, `priority:P0`
- Milestone: `KDE-M1 - UX & Shortcuts`
- Acceptance criteria:
  - Top-level menus follow KDE standard order: File, Edit, View, Tools, Settings, Help
  - All actions have unique, KDE-aligned names
  - Terminology consistent across menu/toolbar/context menus

Issues:
1. `KDE-M1-01` Restructure main menu to KDE taxonomy
   - Labels: `type:feature`, `area:kde-compliance`, `priority:P0`, `size:M`
   - Depends on: `KDE-M0-02`
   - Description: Move actions to correct menus (File/Edit/View/Tools/Settings/Help), remove duplicates

2. `KDE-M1-02` Rename non-standard actions to KDE conventions
   - Labels: `type:feature`, `area:kde-compliance`, `priority:P0`, `size:M`
   - Depends on: `KDE-M0-02`
   - Description: Align action names: "New Comparison" → "New", "Options" → "Configure rcompare", etc.

3. `KDE-M1-03` Add missing standard menu items (Quit, Preferences, About KDE, etc.)
   - Labels: `type:feature`, `area:kde-compliance`, `priority:P1`, `size:S`
   - Depends on: `KDE-M1-01`
   - Description: Ensure presence of File→Quit, Settings→Configure Shortcuts, Help→About KDE

4. `KDE-M1-04` Unify action labels across menu/toolbar/context menu
   - Labels: `type:feature`, `area:kde-compliance`, `priority:P0`, `size:S`
   - Depends on: `KDE-M1-02`
   - Description: Same action should have same label everywhere (no "Compare" in menu, "Scan" in toolbar)

#### EPIC KDE-M1-E2: Keyboard Shortcut Compliance
- Labels: `type:epic`, `area:shortcuts`, `priority:P0`
- Milestone: `KDE-M1 - UX & Shortcuts`
- Acceptance criteria:
  - No duplicate active shortcut collisions
  - Standard KDE shortcuts respected (Ctrl+Q quit, F1 help, Ctrl+, preferences)
  - Core workflows keyboard-accessible

Issues:
1. `KDE-M1-05` Fix shortcut collisions identified in audit
   - Labels: `type:bug`, `area:shortcuts`, `priority:P0`, `size:M`
   - Depends on: `KDE-M0-03`
   - Description: Resolve all duplicate/conflicting shortcuts, prioritize global actions

2. `KDE-M1-06` Implement standard KDE shortcuts
   - Labels: `type:feature`, `area:shortcuts`, `priority:P0`, `size:M`
   - Depends on: `KDE-M1-05`
   - Description: Ctrl+Q quit, Ctrl+N new, Ctrl+O open, F1 help, Ctrl+, preferences, F5 refresh, etc.

3. `KDE-M1-07` Add keyboard navigation to dialogs and folder trees
   - Labels: `type:feature`, `area:shortcuts`, `priority:P1`, `size:M`
   - Depends on: none
   - Description: Tab order, focus policy, mnemonic accelerators, arrow key navigation

4. `KDE-M1-08` Create shortcut reference doc and surface in Help menu
   - Labels: `type:docs`, `area:shortcuts`, `priority:P1`, `size:S`
   - Depends on: `KDE-M1-06`
   - Description: Generate markdown table of all shortcuts, add Help→Keyboard Shortcuts entry

### KDE-M2 - Theme & Dialog

#### EPIC KDE-M2-E1: Theming and Visual Compliance
- Labels: `type:epic`, `area:theming`, `priority:P0`
- Milestone: `KDE-M2 - Theme & Dialog`
- Acceptance criteria:
  - App respects active Plasma light/dark theme
  - No hardcoded colors that override system palette
  - Icons use `QIcon.fromTheme()` with fallbacks

Issues:
1. `KDE-M2-01` Remove hardcoded QSS from main_window.py
   - Labels: `type:feature`, `area:theming`, `priority:P0`, `size:M`
   - Depends on: `KDE-M0-04`
   - Description: Replace hardcoded stylesheets with QPalette-driven styling

2. `KDE-M2-02` Remove hardcoded QSS from all dialogs
   - Labels: `type:feature`, `area:theming`, `priority:P0`, `size:M`
   - Depends on: `KDE-M0-04`
   - Description: settings_dialog, sync_dialog, profiles_dialog, about_dialog

3. `KDE-M2-03` Remove hardcoded QSS from widgets (diff_text_edit, filter_bar)
   - Labels: `type:feature`, `area:theming`, `priority:P0`, `size:M`
   - Depends on: `KDE-M0-04`
   - Description: Use palette colors instead of literal hex values

4. `KDE-M2-04` Migrate icons to QIcon.fromTheme() with fallback table
   - Labels: `type:feature`, `area:theming`, `priority:P0`, `size:L`
   - Depends on: none
   - Description: Replace hardcoded icons with theme icons (document-new, document-open, etc.)

5. `KDE-M2-05` Test theme switching without restart (Breeze Light ↔ Dark)
   - Labels: `type:test`, `area:theming`, `priority:P0`, `size:S`
   - Depends on: `KDE-M2-01`, `KDE-M2-02`, `KDE-M2-03`
   - Description: Verify app reacts to runtime theme changes via QPalette signals

6. `KDE-M2-06` Verify high-DPI behavior on 1.5x, 2x scaling
   - Labels: `type:test`, `area:theming`, `priority:P1`, `size:S`
   - Depends on: `KDE-M2-04`
   - Description: Icons, fonts, layout margins scale correctly

#### EPIC KDE-M2-E2: Dialog and Workflow Consistency
- Labels: `type:epic`, `area:kde-compliance`, `priority:P0`
- Milestone: `KDE-M2 - Theme & Dialog`
- Acceptance criteria:
  - Destructive operations require explicit confirmation
  - Dialog button order matches KDE standards
  - Long operations provide non-blocking progress and cancel

Issues:
1. `KDE-M2-07` Standardize dialog button order (KDE: Help - Action - Apply - Cancel - OK)
   - Labels: `type:feature`, `area:kde-compliance`, `priority:P0`, `size:S`
   - Depends on: none
   - Description: Use QDialogButtonBox with KDE button order and roles

2. `KDE-M2-08` Add confirmation dialogs for destructive sync operations
   - Labels: `type:feature`, `area:kde-compliance`, `priority:P0`, `size:M`
   - Depends on: none
   - Description: Delete, overwrite actions show target paths and require explicit confirmation

3. `KDE-M2-09` Improve error messages with cause + next step
   - Labels: `type:feature`, `area:kde-compliance`, `priority:P1`, `size:M`
   - Depends on: none
   - Description: Replace generic "Error" dialogs with actionable remediation text

4. `KDE-M2-10` Add non-blocking progress for long-running operations
   - Labels: `type:feature`, `area:kde-compliance`, `priority:P1`, `size:L`
   - Depends on: none
   - Description: Progress dialogs with cancel button, don't block main window

### KDE-M3 - Desktop Integration

#### EPIC KDE-M3-E1: Linux Desktop Integration
- Labels: `type:epic`, `area:desktop-integration`, `priority:P0`
- Milestone: `KDE-M3 - Desktop Integration`
- Acceptance criteria:
  - App appears correctly in Plasma launcher and Discover
  - Desktop file validates via `desktop-file-validate`
  - AppStream validates via `appstreamcli validate`

Issues:
1. `KDE-M3-01` Create rcompare-pyside.desktop file with categories and actions
   - Labels: `type:feature`, `area:desktop-integration`, `priority:P0`, `size:M`
   - Depends on: none
   - Description: Desktop entry with Name, Comment, Icon, Exec, Categories (Utility;FileManager;Qt;KDE)

2. `KDE-M3-02` Create AppStream metainfo file (org.aecs4u.rcompare_pyside.metainfo.xml)
   - Labels: `type:feature`, `area:desktop-integration`, `priority:P0`, `size:M`
   - Depends on: none
   - Description: AppStream metadata with description, screenshots, releases, OARS rating

3. `KDE-M3-03` Package application icons in XDG-compliant locations
   - Labels: `type:feature`, `area:desktop-integration`, `priority:P0`, `size:M`
   - Depends on: none
   - Description: SVG + PNG icons in hicolor theme at multiple sizes (16, 22, 32, 48, 64, 128, 256)

4. `KDE-M3-04` Add desktop file validation to CI
   - Labels: `type:test`, `area:desktop-integration`, `priority:P0`, `size:S`
   - Depends on: `KDE-M3-01`
   - Description: Run `desktop-file-validate` in CI, fail on errors

5. `KDE-M3-05` Add AppStream validation to CI
   - Labels: `type:test`, `area:desktop-integration`, `priority:P0`, `size:S`
   - Depends on: `KDE-M3-02`
   - Description: Run `appstreamcli validate` in CI, fail on errors

6. `KDE-M3-06` Add file associations for compare actions (optional)
   - Labels: `type:feature`, `area:desktop-integration`, `priority:P2`, `size:M`
   - Depends on: `KDE-M3-01`
   - Description: Desktop actions for "Compare with..." in Dolphin context menu

#### EPIC KDE-M3-E2: Accessibility and Internationalization
- Labels: `type:epic`, `area:accessibility`, `priority:P1`
- Milestone: `KDE-M3 - Desktop Integration`
- Acceptance criteria:
  - Key controls have accessible names/tooltips
  - Focus order and tab chain are deterministic
  - Strings externalized for translation

Issues:
1. `KDE-M3-07` Add accessible names and tooltips to main window controls
   - Labels: `type:feature`, `area:accessibility`, `priority:P1`, `size:M`
   - Depends on: none
   - Description: setAccessibleName/Description for toolbar buttons, path inputs, view switcher

2. `KDE-M3-08` Verify and fix tab order in all dialogs
   - Labels: `type:feature`, `area:accessibility`, `priority:P1`, `size:S`
   - Depends on: none
   - Description: Logical tab chain: top to bottom, left to right

3. `KDE-M3-09` Add screen reader testing checklist
   - Labels: `type:test`, `area:accessibility`, `priority:P1`, `size:S`
   - Depends on: `KDE-M3-07`
   - Description: Verify Orca/NVDA can navigate main workflows

4. `KDE-M3-10` Extract strings for i18n (Qt Linguist .ts workflow)
   - Labels: `type:feature`, `area:i18n`, `priority:P1`, `size:L`
   - Depends on: none
   - Description: Wrap user-visible strings in tr(), generate .ts files, add translation CI

5. `KDE-M3-11` Add RTL layout testing (Arabic/Hebrew locale)
   - Labels: `type:test`, `area:i18n`, `priority:P2`, `size:S`
   - Depends on: `KDE-M3-10`
   - Description: Verify UI mirrors correctly in RTL mode

### KDE-M4 - QA Hardening

#### EPIC KDE-M4-E1: KDE Compliance Testing
- Labels: `type:epic`, `area:qa`, `priority:P0`
- Milestone: `KDE-M4 - QA Hardening`
- Acceptance criteria:
  - KDE compliance checklist >= 90% pass
  - All P0 compliance issues resolved
  - Verified on Plasma Wayland and X11

Issues:
1. `KDE-M4-01` Create automated KDE compliance test suite
   - Labels: `type:test`, `area:qa`, `priority:P0`, `size:L`
   - Depends on: `KDE-M0-01`
   - Description: pytest-qt tests for menu structure, shortcuts, theme response, dialog behavior

2. `KDE-M4-02` Execute compliance checklist on Plasma Wayland
   - Labels: `type:test`, `area:qa`, `priority:P0`, `size:M`
   - Depends on: `KDE-M4-01`
   - Description: Manual verification pass on Plasma 6 Wayland session

3. `KDE-M4-03` Execute compliance checklist on Plasma X11
   - Labels: `type:test`, `area:qa`, `priority:P0`, `size:M`
   - Depends on: `KDE-M4-01`
   - Description: Manual verification pass on Plasma 6 X11 session

4. `KDE-M4-04` Test Breeze Light theme compliance
   - Labels: `type:test`, `area:theming`, `priority:P0`, `size:S`
   - Depends on: `KDE-M4-02`, `KDE-M4-03`
   - Description: Verify no unreadable text, correct palette usage, icon coherence

5. `KDE-M4-05` Test Breeze Dark theme compliance
   - Labels: `type:test`, `area:theming`, `priority:P0`, `size:S`
   - Depends on: `KDE-M4-02`, `KDE-M4-03`
   - Description: Verify no unreadable text, correct palette usage, icon coherence

6. `KDE-M4-06` Smoke tests: startup, compare, sync, profile, options, help
   - Labels: `type:test`, `area:qa`, `priority:P0`, `size:M`
   - Depends on: none
   - Description: Automated smoke tests covering critical user paths

7. `KDE-M4-07` Regression testing: ensure core PySide features still work
   - Labels: `type:test`, `area:qa`, `priority:P0`, `size:M`
   - Depends on: `KDE-M4-06`
   - Description: Verify tabs, filters, multi-selection, profiles, session restore unchanged

8. `KDE-M4-08` Performance regression testing
   - Labels: `type:test`, `area:performance`, `priority:P1`, `size:S`
   - Depends on: none
   - Description: Verify no slowdown from palette/theme changes on large trees

### KDE-M5 - Release Candidate

#### EPIC KDE-M5-E1: Release Gate and Documentation
- Labels: `type:epic`, `area:kde-compliance`, `priority:P0`
- Milestone: `KDE-M5 - Release Candidate`
- Acceptance criteria:
  - All KDE-M1 through KDE-M4 P0 issues closed
  - No open P0/P1 accessibility issues
  - Desktop and AppStream validation pass in CI
  - Manual verification on Plasma Wayland and X11 complete

Issues:
1. `KDE-M5-01` Close all P0 KDE compliance issues
   - Labels: `type:epic`, `area:kde-compliance`, `priority:P0`, `size:L`
   - Depends on: all prior P0 issues
   - Description: Gate for release: no open P0 issues in KDE milestones

2. `KDE-M5-02` Close or defer all P1 KDE compliance issues
   - Labels: `type:epic`, `area:kde-compliance`, `priority:P1`, `size:M`
   - Depends on: `KDE-M5-01`
   - Description: P1 issues either closed or explicitly deferred with rationale

3. `KDE-M5-03` Final compliance checklist verification
   - Labels: `type:test`, `area:kde-compliance`, `priority:P0`, `size:M`
   - Depends on: `KDE-M5-01`, `KDE-M5-02`
   - Description: Run full checklist, verify >= 90% pass rate

4. `KDE-M5-04` Update documentation with KDE compliance status
   - Labels: `type:docs`, `area:kde-compliance`, `priority:P0`, `size:S`
   - Depends on: `KDE-M5-03`
   - Description: Add "KDE Compliance" section to README and release notes

5. `KDE-M5-05` Create KDE-focused release notes
   - Labels: `type:docs`, `area:kde-compliance`, `priority:P0`, `size:S`
   - Depends on: `KDE-M5-04`
   - Description: Highlight KDE integration features, theme support, desktop integration

6. `KDE-M5-06` Update CHANGELOG with KDE compliance work
   - Labels: `type:docs`, `area:kde-compliance`, `priority:P1`, `size:S`
   - Depends on: `KDE-M5-05`
   - Description: Comprehensive changelog entry for KDE compliance milestone

## 4) Definition of Done (DoD)

Every KDE compliance issue is Done only when:
1. Implementation merged with tests or explicit rationale for no tests
2. Behavior matches KDE compliance checklist entry
3. No regressions in existing PySide features (tabs, filters, profiles, sync)
4. User-facing docs/help text updated where relevant
5. No new shortcut/theme regressions introduced

## 5) Release Gates

Before claiming "KDE Compliant" in release notes:
1. All KDE-M1 through KDE-M4 P0 issues closed
2. No open P0/P1 accessibility issues
3. Desktop file and AppStream validation pass in CI
4. Manual verification completed on:
   - Plasma 6 Wayland session
   - Plasma 6 X11 session
   - Breeze Light theme
   - Breeze Dark theme
5. KDE compliance checklist >= 90% pass
6. No P0 compliance regressions from baseline screenshots

## 6) Suggested GitHub Project Setup

Extend existing PySide project with KDE-specific views:

Board columns (same as PySide):
1. Backlog
2. Ready
3. In Progress
4. In Review
5. Done

Custom fields (add):
- KDE Compliance Phase (`M0/M1/M2/M3/M4/M5`)
- Workstream (`WS1-UX / WS2-Theme / WS3-Shortcuts / WS4-Dialog / WS5-Desktop / WS6-A11y / WS7-QA`)

Filters:
- View: KDE Compliance (`area:kde-compliance`)
- View: Theme Work (`area:theming`)
- View: Accessibility (`area:accessibility`)

## 7) First Sprint Cut (Recommended)

Start with baseline audit and quick wins (8 issues):
1. `KDE-M0-01` - Create compliance checklist
2. `KDE-M0-02` - Audit menu structure
3. `KDE-M0-03` - Audit shortcuts
4. `KDE-M0-04` - Audit hardcoded styles
5. `KDE-M1-01` - Restructure main menu
6. `KDE-M1-05` - Fix shortcut collisions
7. `KDE-M2-01` - Remove hardcoded QSS from main_window
8. `KDE-M3-01` - Create .desktop file

This gives rapid visibility into gaps and starts fixing the most visible non-compliance issues.

## 8) Integration with Core PySide Roadmap

KDE compliance work runs in parallel with core PySide milestones:

| PySide Milestone | KDE Milestone | Integration Point |
|---|---|---|
| M1 - Stabilize Core UX | KDE-M0 - Baseline Audit | Audit includes regression testing |
| M2 - Sync Engine | KDE-M1 - UX & Shortcuts | Sync dialogs get KDE button order |
| M3 - Folder UX | KDE-M2 - Theme & Dialog | Context menus get theme icons |
| M4 - Viewer Improvements | KDE-M2 - Theme & Dialog | Viewers respect palette |
| M5 - Performance | KDE-M4 - QA Hardening | Performance tests include theme switching |
| M6 - Release Readiness | KDE-M5 - Release Candidate | Combined release gate |

## 9) Risk Mitigation

High-risk areas:
1. **Theme removal breaking layout**: Mitigation = incremental removal with visual regression screenshots
2. **Shortcut collisions causing broken workflows**: Mitigation = comprehensive test coverage before changes
3. **Desktop integration validation failures**: Mitigation = early CI integration for `desktop-file-validate` and `appstreamcli`
4. **Performance regression from palette updates**: Mitigation = benchmark before/after, rollback plan

## 10) Success Metrics

KDE compliance milestone is successful when:
- Compliance checklist score: **>= 90%**
- P0 issues closed: **100%**
- P1 issues closed or deferred: **>= 80%**
- Desktop validation CI: **Green**
- Manual QA pass rate: **>= 95%**
- User-reported theme/integration issues: **<= 2 per month** (post-release)
