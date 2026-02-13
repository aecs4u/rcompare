# KDE Keyboard Shortcut Audit

Last updated: 2026-02-13

This document audits all keyboard shortcuts and identifies conflicts with KDE standards.

## Current Shortcut Map

| Shortcut | Action | Location | KDE Standard | Conflict? |
|----------|--------|----------|--------------|-----------|
| **Ctrl+Q** | Exit | Session menu | Quit | ✅ Match |
| **Ctrl+N** | New Session | Session menu | New | ⚠️ Partial (should be New Tab) |
| **Ctrl+H** | Home | Session menu | - | ⚠️ Can conflict with Find/Replace |
| **F5** | Compare Now | Actions menu | Refresh/Reload | ⚠️ Semantic mismatch |
| **Shift+F5** | Refresh Now | Actions menu | - | ⚠️ Non-standard |
| **Ctrl+W** | Swap L/R Sides | Actions menu | Close Window/Tab | ❌ **CONFLICT** |
| **F7** | Copy L→R | Actions/Edit menus | - | ✅ OK (app-specific) |
| **F8** | Copy R→L | Actions/Edit menus | - | ✅ OK (app-specific) |
| **Ctrl+F** | Focus Search | Search menu | Find | ✅ Match |
| **Ctrl+Shift+F** | Clear Search | Search menu | - | ⚠️ Non-standard |

## Missing KDE Standard Shortcuts

| Shortcut | Expected Action | Priority |
|----------|----------------|----------|
| **F1** | Help / Handbook | P0 |
| **F3** | Find Next | P1 |
| **Shift+F3** | Find Previous | P1 |
| **Ctrl+,** | Preferences | P0 |
| **Ctrl+Shift+,** | Configure Shortcuts | P1 |
| **Ctrl+T** | New Tab | P1 |
| **Ctrl+W** | Close Tab | P0 (currently conflicts!) |
| **Ctrl+Tab** | Next Tab | P1 |
| **Ctrl+Shift+Tab** | Previous Tab | P1 |
| **Ctrl+[1-9]** | Switch to Tab N | P2 |
| **Esc** | Cancel / Clear | P1 |
| **Ctrl+Z** | Undo | P2 (if applicable) |
| **Ctrl+Y** | Redo | P2 (if applicable) |

## Shortcut Collision Analysis

### P0 Conflicts (Must Fix)

1. **Ctrl+W: Swap Sides vs Close Tab**
   - Current: Swap L/R Sides
   - KDE Standard: Close Window/Tab
   - Resolution: Remove Ctrl+W from Swap, reassign to Close Tab
   - Alternative for Swap: Ctrl+Shift+W or unassigned (menu-only)

### P1 Semantic Mismatches

2. **F5: Compare Now vs Refresh**
   - Current: "Compare Now" (initiates comparison)
   - KDE Standard: Refresh/Reload (refresh current view)
   - Resolution:
     - Rename "Compare Now" to "Refresh" or "Reload"
     - Use Shift+F5 or Ctrl+R for full re-scan if needed
   - Impact: Medium (users expect F5 = refresh)

3. **Ctrl+H: Home vs Find/Replace**
   - Current: "Home" (unclear function)
   - Potential KDE Conflict: Some apps use Ctrl+H for Find/Replace
   - Resolution: Remove Ctrl+H, use Alt+Home or no shortcut

### P2 Non-Standard Shortcuts

4. **Shift+F5: Refresh Now**
   - Current: "Refresh Now" (function unclear vs F5)
   - Resolution: Clarify distinction or consolidate with F5

5. **Ctrl+Shift+F: Clear Search**
   - Current: Clear search field
   - Better: Use Esc to clear search (standard pattern)
   - Resolution: Keep Ctrl+Shift+F as secondary, add Esc

## Recommended Shortcut Map (KDE Compliant)

| Shortcut | Action | Menu | Notes |
|----------|--------|------|-------|
| **Ctrl+Q** | Quit | File | Standard |
| **Ctrl+T** | New Tab | File | Standard |
| **Ctrl+W** | Close Tab | File | Standard (currently conflicts!) |
| **F7** | Copy Left to Right | Edit | App-specific, acceptable |
| **F8** | Copy Right to Left | Edit | App-specific, acceptable |
| **Ctrl+F** | Find... | Edit | Standard |
| **F3** | Find Next | Edit | Standard |
| **Shift+F3** | Find Previous | Edit | Standard |
| **Esc** | Clear Search | Edit | Standard pattern |
| **F5** | Refresh | View | Standard |
| **Ctrl+R** | Full Re-scan | Tools | Alternative to Shift+F5 |
| **Ctrl+Y** | Synchronize | Tools | Uncommon but reasonable |
| **Ctrl+P** | Profiles | Tools | Common shortcut |
| **Ctrl+,** | Configure rcompare | Settings | Standard (macOS-style, widely adopted) |
| **Ctrl+Shift+,** | Configure Shortcuts | Settings | Standard |
| **F1** | rcompare Handbook | Help | Standard |

## Shortcut Grouping by Function

### File Management
- Ctrl+T - New Tab
- Ctrl+W - Close Tab
- Ctrl+Q - Quit

### Navigation
- Ctrl+Tab - Next Tab
- Ctrl+Shift+Tab - Previous Tab
- Ctrl+1 through Ctrl+9 - Go to Tab N

### Search/Find
- Ctrl+F - Open Find
- F3 - Find Next
- Shift+F3 - Find Previous
- Esc - Clear/Cancel Search

### View/Refresh
- F5 - Refresh Current View
- Ctrl+R - Full Re-scan (if needed)

### Comparison Actions
- F7 - Copy Left to Right
- F8 - Copy Right to Left
- (No shortcut) - Swap Sides

### Tools
- Ctrl+Y - Synchronize
- Ctrl+P - Profiles

### Settings
- Ctrl+, - Preferences
- Ctrl+Shift+, - Configure Shortcuts

### Help
- F1 - Handbook

## Implementation Plan

### Phase 1: Fix Critical Conflicts (KDE-M1-05)
1. Remove Ctrl+W from "Swap Sides"
2. Assign Ctrl+W to "Close Tab"
3. Add Ctrl+T for "New Tab"

### Phase 2: Implement Standard Shortcuts (KDE-M1-06)
1. F1 → Help Handbook
2. F3 → Find Next
3. Shift+F3 → Find Previous
4. Ctrl+, → Preferences
5. Ctrl+Shift+, → Configure Shortcuts
6. Esc → Clear Search

### Phase 3: Semantic Fixes (KDE-M1-06)
1. Rename "Compare Now" to "Refresh"
2. Keep F5 as primary refresh shortcut
3. Optionally add Ctrl+R for full re-scan
4. Remove Ctrl+H from Home (or reassign)

### Phase 4: Tab Navigation (Lower Priority)
1. Ctrl+Tab → Next Tab
2. Ctrl+Shift+Tab → Previous Tab
3. Ctrl+[1-9] → Switch to Tab N

## Testing Matrix

| Test Case | Steps | Expected Result |
|-----------|-------|----------------|
| **Quit** | Press Ctrl+Q | App quits (with save prompt if needed) |
| **New Tab** | Press Ctrl+T | New comparison tab created |
| **Close Tab** | Press Ctrl+W | Current tab closes |
| **Find** | Press Ctrl+F | Search field focused |
| **Find Next** | Press F3 | Jump to next match |
| **Find Previous** | Press Shift+F3 | Jump to previous match |
| **Clear Search** | Press Esc | Search cleared, filter reset |
| **Refresh** | Press F5 | Current comparison refreshed |
| **Help** | Press F1 | Handbook opens |
| **Preferences** | Press Ctrl+, | Settings dialog opens |
| **Shortcuts** | Press Ctrl+Shift+, | Configure Shortcuts dialog opens |

## Accessibility Considerations

1. **Discoverability**: All shortcuts must be visible in menu labels
2. **Consistency**: Same action = same shortcut everywhere
3. **Conflicts**: No two active actions with same shortcut
4. **Standards**: Follow KDE conventions for muscle memory
5. **Documentation**: Shortcuts listed in Help menu and handbook

## Code Changes Required

### main_window.py Updates

```python
# Fix conflicts
self._act_close_tab = QAction("&Close Tab", self)
self._act_close_tab.setShortcut(QKeySequence.StandardKey.Close)  # Ctrl+W

self._act_swap_sides = QAction("S&wap Sides", self)
# Remove shortcut - menu only

# Add missing standards
self._act_new_tab = QAction("&New Tab", self)
self._act_new_tab.setShortcut(QKeySequence.StandardKey.AddTab)  # Ctrl+T

self._act_find_next = QAction("Find &Next", self)
self._act_find_next.setShortcut(QKeySequence.StandardKey.FindNext)  # F3

self._act_find_prev = QAction("Find &Previous", self)
self._act_find_prev.setShortcut(QKeySequence.StandardKey.FindPrevious)  # Shift+F3

self._act_preferences = QAction("Configure &rcompare...", self)
self._act_preferences.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_Comma))

self._act_configure_shortcuts = QAction("Configure &Shortcuts...", self)
self._act_configure_shortcuts.setShortcut(QKeySequence(
    Qt.CTRL | Qt.SHIFT | Qt.Key_Comma
))

self._act_handbook = QAction("rcompare &Handbook", self)
self._act_handbook.setShortcut(QKeySequence.StandardKey.HelpContents)  # F1

# Semantic rename
self._act_refresh = QAction("&Refresh", self)  # was "Compare Now"
self._act_refresh.setShortcut(QKeySequence.StandardKey.Refresh)  # F5
```

## Shortcut Reference Document

After implementation, generate a shortcut reference:
- Format: Markdown table
- Location: docs/KEYBOARD_SHORTCUTS.md
- Linked from: Help menu → Keyboard Shortcuts

## Acceptance Criteria

- [ ] No shortcut collisions (Ctrl+W fixed)
- [ ] All KDE P0 shortcuts implemented
- [ ] All actions show shortcuts in menu labels
- [ ] Shortcut reference doc created and linked
- [ ] All shortcuts tested and working
- [ ] QKeySequence.StandardKey used where available
- [ ] Semantic action names match shortcut expectations (F5 = Refresh)
