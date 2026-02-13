# KDE Compliance Checklist

Last updated: 2026-02-13
Status: **Baseline** (pre-compliance work)

This checklist provides objective pass/fail criteria for KDE/Plasma application compliance.

## Scoring

- **Pass**: ✅ Meets KDE standard
- **Partial**: ⚠️ Partially compliant, needs work
- **Fail**: ❌ Does not meet KDE standard
- **N/A**: — Not applicable

**Target Score**: ≥90% pass rate

---

## WS1: KDE UX and Information Architecture

### Menu Structure

| Criteria | Status | Notes |
|----------|--------|-------|
| Top-level menus follow KDE order: File, Edit, View, Tools, Settings, Help | ❌ | Current: File, Edit, View, Session, Tools, Help (missing Settings, extra Session) |
| File menu contains: New, Open, Recent, Quit | ⚠️ | Has New, Refresh, missing Open/Recent, has Quit |
| Edit menu contains standard editing actions | ❌ | Currently empty/minimal |
| View menu contains: Refresh, view mode toggles, toolbars/status bar toggles | ⚠️ | Has Folder/Text/Hex/Image, missing Refresh, toolbar toggles |
| Settings menu contains: Configure Shortcuts, Configure Toolbars, Preferences | ❌ | Settings in Tools→Options instead |
| Help menu contains: Handbook, About App, About KDE | ⚠️ | Has About, missing Handbook, About KDE |
| No duplicate actions across menus | ⚠️ | Need to verify after restructure |

**Score: 1/7 Pass, 4/7 Partial, 2/7 Fail**

### Action Naming

| Criteria | Status | Notes |
|----------|--------|-------|
| Standard action names used (New, Open, Save, Quit, not New Comparison, Exit) | ❌ | Uses "New Comparison", "Options" instead of "Preferences" |
| Consistent terminology (not Compare in menu, Scan in toolbar) | ❌ | Need audit |
| Actions use KDE standard icons (document-new, document-open, etc.) | ❌ | Uses custom icons, not QIcon.fromTheme |
| Menu items have keyboard mnemonics (&File, &Edit) | ❌ | Not implemented |
| All actions accessible via menu OR toolbar OR keyboard | ⚠️ | Most accessible, need comprehensive check |

**Score: 0/5 Pass, 2/5 Partial, 3/5 Fail**

### Navigation

| Criteria | Status | Notes |
|----------|--------|-------|
| Common workflows reachable in ≤2 navigation steps | ⚠️ | Need to measure |
| Help text reflects final action names | ❌ | No help text/handbook |
| Consistent terminology across UI and documentation | ⚠️ | Limited docs currently |

**Score: 0/3 Pass, 2/3 Partial, 1/3 Fail**

**WS1 Total: 1/15 (7%) Pass, 8/15 (53%) Partial, 6/15 (40%) Fail**

---

## WS2: Theming and Visual Compliance

### Color and Palette

| Criteria | Status | Notes |
|----------|--------|-------|
| No hardcoded colors in main_window.py | ❌ | Uses hardcoded QSS in themes.py |
| No hardcoded colors in dialogs | ❌ | settings_dialog, sync_dialog have hardcoded styles |
| No hardcoded colors in widgets | ❌ | diff_text_edit, filter_bar have literal color values |
| Uses QPalette for foreground/background/highlight | ❌ | Direct QColor("#rrggbb") usage throughout |
| App follows active Plasma theme without restart | ❌ | Hardcoded light/dark themes |
| No unreadable foreground/background combinations | ✅ | Current hardcoded themes are readable |

**Score: 1/6 Pass, 0/6 Partial, 5/6 Fail**

### Icons

| Criteria | Status | Notes |
|----------|--------|-------|
| Uses QIcon.fromTheme() for standard actions | ❌ | Uses QStyle.standardIcon() or text labels |
| Fallback icons defined for missing theme icons | ❌ | No fallback table |
| Icon set coherent across Breeze/Breeze Dark | ⚠️ | Standard icons would work, custom ones untested |
| Application icon in multiple sizes (16-256px) | ❌ | No icon assets packaged |

**Score: 0/4 Pass, 1/4 Partial, 3/4 Fail**

### High-DPI

| Criteria | Status | Notes |
|----------|--------|-------|
| Correct rendering at 1.5x scaling | ⚠️ | Not tested |
| Correct rendering at 2x scaling | ⚠️ | Not tested |
| Icons scale correctly | ⚠️ | Not tested |
| Fonts scale correctly | ⚠️ | Not tested |

**Score: 0/4 Pass, 4/4 Partial, 0/4 Fail**

**WS2 Total: 1/14 (7%) Pass, 5/14 (36%) Partial, 8/14 (57%) Fail**

---

## WS3: Shortcuts and Keyboard Standards

### Standard Shortcuts

| Criteria | Status | Notes |
|----------|--------|-------|
| Ctrl+Q = Quit | ✅ | Implemented |
| Ctrl+N = New | ❌ | Not implemented |
| Ctrl+O = Open | ❌ | Not applicable (no file opening) |
| Ctrl+W = Close tab/window | ❌ | Not implemented |
| F1 = Help | ❌ | Not implemented |
| F5 = Refresh | ❌ | Not implemented |
| Ctrl+, = Preferences | ❌ | Not implemented |
| Ctrl+Shift+, = Configure Shortcuts | ❌ | Not implemented |

**Score: 1/8 Pass, 0/8 Partial, 7/8 Fail**

### Collision-Free

| Criteria | Status | Notes |
|----------|--------|-------|
| No duplicate shortcut assignments | ⚠️ | Need comprehensive audit |
| Global actions take priority over context actions | ⚠️ | Need audit |
| Shortcut list available in Help menu | ❌ | Not implemented |

**Score: 0/3 Pass, 2/3 Partial, 1/3 Fail**

### Keyboard Navigation

| Criteria | Status | Notes |
|----------|--------|-------|
| All dialogs have logical tab order | ⚠️ | Need to verify each dialog |
| Folder tree navigable with arrow keys | ✅ | QTreeView default behavior |
| Context menus accessible via keyboard | ⚠️ | Need to verify |
| Mnemonics work in menus | ❌ | Not implemented |

**Score: 1/4 Pass, 2/4 Partial, 1/4 Fail**

**WS3 Total: 2/15 (13%) Pass, 4/15 (27%) Partial, 9/15 (60%) Fail**

---

## WS4: Dialog and Workflow Consistency

### Button Order

| Criteria | Status | Notes |
|----------|--------|-------|
| Settings dialog uses KDE button order | ❌ | Need to check QDialogButtonBox |
| Sync dialog uses KDE button order | ❌ | Need to check |
| Profiles dialog uses KDE button order | ❌ | Need to check |
| About dialog uses KDE button order | ❌ | Custom layout |
| Default button is action button (OK/Apply) | ⚠️ | Need to verify |

**Score: 0/5 Pass, 1/5 Partial, 4/5 Fail**

### Confirmations

| Criteria | Status | Notes |
|----------|--------|-------|
| Destructive sync operations require confirmation | ❌ | Sync not implemented yet |
| Confirmation dialogs show target paths | ❌ | Not implemented |
| Delete actions have "Move to Trash" vs "Permanent Delete" options | ❌ | Not implemented |

**Score: 0/3 Pass, 0/3 Partial, 3/3 Fail**

### Progress and Errors

| Criteria | Status | Notes |
|----------|--------|-------|
| Long operations show non-blocking progress | ⚠️ | ComparisonWorker has progress, but blocks with modal |
| Progress dialogs have Cancel button | ⚠️ | Cancel exists, need to verify non-blocking |
| Error messages include cause + next step | ❌ | Generic error messages |
| Error dialogs actionable, not just "Error" | ❌ | Need improvement |

**Score: 0/4 Pass, 2/4 Partial, 2/4 Fail**

**WS4 Total: 0/12 (0%) Pass, 3/12 (25%) Partial, 9/12 (75%) Fail**

---

## WS5: Desktop Integration (Plasma/Linux)

### Desktop File

| Criteria | Status | Notes |
|----------|--------|-------|
| .desktop file exists | ❌ | Not created |
| Name, Comment, Icon, Exec, Categories fields present | ❌ | N/A |
| Categories include Utility, Qt, KDE | ❌ | N/A |
| Validates with desktop-file-validate | ❌ | N/A |
| Actions defined for launcher integration | ❌ | N/A |

**Score: 0/5 Pass, 0/5 Partial, 5/5 Fail**

### AppStream

| Criteria | Status | Notes |
|----------|--------|-------|
| AppStream metainfo.xml exists | ❌ | Not created |
| Contains name, summary, description | ❌ | N/A |
| Contains screenshots | ❌ | N/A |
| Contains release information | ❌ | N/A |
| Validates with appstreamcli validate | ❌ | N/A |

**Score: 0/5 Pass, 0/5 Partial, 5/5 Fail**

### Icons and Resources

| Criteria | Status | Notes |
|----------|--------|-------|
| SVG icon exists | ❌ | Not packaged |
| PNG icons in sizes 16, 22, 32, 48, 64, 128, 256 | ❌ | Not packaged |
| Icons installed in hicolor theme | ❌ | Not packaged |
| XDG directory structure compliance | ❌ | Not packaged |

**Score: 0/4 Pass, 0/4 Partial, 4/4 Fail**

### Launcher Integration

| Criteria | Status | Notes |
|----------|--------|-------|
| App appears in Plasma launcher | ❌ | No .desktop file |
| App appears in Discover | ❌ | No AppStream metadata |
| Correct category placement | ❌ | N/A |

**Score: 0/3 Pass, 0/3 Partial, 3/3 Fail**

**WS5 Total: 0/17 (0%) Pass, 0/17 (0%) Partial, 17/17 (100%) Fail**

---

## WS6: Accessibility and Internationalization

### Accessible Names

| Criteria | Status | Notes |
|----------|--------|-------|
| Main toolbar buttons have accessible names | ❌ | setAccessibleName not used |
| Path input fields have accessible names | ❌ | Not set |
| View switcher has accessible name | ❌ | Not set |
| Dialog controls have accessible names | ❌ | Not set |

**Score: 0/4 Pass, 0/4 Partial, 4/4 Fail**

### Focus and Tab Order

| Criteria | Status | Notes |
|----------|--------|-------|
| Settings dialog tab order is logical | ⚠️ | Need to verify |
| Sync dialog tab order is logical | ⚠️ | Need to verify |
| Profiles dialog tab order is logical | ⚠️ | Need to verify |
| Focus indicators visible | ✅ | Qt default behavior |

**Score: 1/4 Pass, 3/4 Partial, 0/4 Fail**

### Internationalization

| Criteria | Status | Notes |
|----------|--------|-------|
| Strings wrapped in tr() | ❌ | Mostly hardcoded strings |
| .ts files generated | ❌ | Not implemented |
| Translation workflow documented | ❌ | Not implemented |
| RTL layout tested | ❌ | Not implemented |

**Score: 0/4 Pass, 0/4 Partial, 4/4 Fail**

**WS6 Total: 1/12 (8%) Pass, 3/12 (25%) Partial, 8/12 (67%) Fail**

---

## WS7: Quality and Compliance Testing

### Test Coverage

| Criteria | Status | Notes |
|----------|--------|-------|
| Automated compliance test suite exists | ❌ | Not implemented |
| Menu structure tests | ❌ | Not implemented |
| Shortcut collision tests | ❌ | Not implemented |
| Theme switching tests | ❌ | Not implemented |
| Dialog behavior tests | ❌ | Not implemented |

**Score: 0/5 Pass, 0/5 Partial, 5/5 Fail**

### Manual Verification

| Criteria | Status | Notes |
|----------|--------|-------|
| Tested on Plasma Wayland | ❌ | Not tested |
| Tested on Plasma X11 | ❌ | Not tested |
| Tested on Breeze Light | ❌ | Not tested |
| Tested on Breeze Dark | ❌ | Not tested |
| Smoke tests pass | ⚠️ | Manual testing only, no automation |

**Score: 0/5 Pass, 1/5 Partial, 4/5 Fail**

### CI Integration

| Criteria | Status | Notes |
|----------|--------|-------|
| desktop-file-validate runs in CI | ❌ | No .desktop file yet |
| appstreamcli validate runs in CI | ❌ | No AppStream file yet |
| pytest-qt tests run in CI | ❌ | No tests yet |

**Score: 0/3 Pass, 0/3 Partial, 3/3 Fail**

**WS7 Total: 0/13 (0%) Pass, 1/13 (8%) Partial, 12/13 (92%) Fail**

---

## Overall Compliance Score

| Workstream | Pass | Partial | Fail | Pass % |
|------------|------|---------|------|--------|
| WS1: UX and IA | 1/15 | 8/15 | 6/15 | 7% |
| WS2: Theming | 1/14 | 5/14 | 8/14 | 7% |
| WS3: Shortcuts | 2/15 | 4/15 | 9/15 | 13% |
| WS4: Dialogs | 0/12 | 3/12 | 9/12 | 0% |
| WS5: Desktop | 0/17 | 0/17 | 17/17 | 0% |
| WS6: A11y/i18n | 1/12 | 3/12 | 8/12 | 8% |
| WS7: QA | 0/13 | 1/13 | 12/13 | 0% |
| **TOTAL** | **5/98** | **24/98** | **69/98** | **5%** |

**Baseline Score: 5% Pass** (Target: ≥90%)

---

## Priority Gaps (P0)

These must be addressed before claiming KDE compliance:

1. **Menu restructuring** - Non-standard menu organization
2. **Hardcoded styles** - Breaks KDE theme integration
3. **Missing standard shortcuts** - F1, F5, Ctrl+N, Ctrl+,
4. **No .desktop file** - App not discoverable in Plasma
5. **No AppStream metadata** - App not in Discover
6. **No icon assets** - No application icon
7. **Destructive action confirmations** - Safety gap
8. **Accessible names missing** - Screen reader incompatible

---

## Next Steps

1. Execute KDE-M0 issues (audit completion)
2. Begin KDE-M1 issues (menu restructure, shortcut fixes)
3. Re-run checklist after each milestone
4. Target ≥90% pass by KDE-M5
