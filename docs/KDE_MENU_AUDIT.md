# KDE Menu Structure Audit

Last updated: 2026-02-13

This document audits the current menu structure and maps it to KDE-compliant organization.

## Current Menu Structure

```
&Session
├── Home (Ctrl+H)
├── New Session (Ctrl+N)
├── ───────────
├── Save Profile...
├── Load Profile...
├── ───────────
└── Exit (Ctrl+Q)

&Actions
├── Compare Now (F5)
├── Refresh Now (Shift+F5)
├── Swap L/R Sides (Ctrl+W)
├── ───────────
├── Copy L→R (F7)
├── Copy R→L (F8)
└── Synchronize...

&Edit
├── Copy L→R (F7)
└── Copy R→L (F8)

&Search
├── Focus Search (Ctrl+F)
└── Clear Search (Ctrl+Shift+F)

&View
├── Compare Mode ▸
│   ├── ◉ Folder Compare
│   ├── ○ Text Compare
│   ├── ○ Hex Compare
│   └── ○ Image Compare
├── ───────────
├── ☑ Show Identical
├── ☑ Show Different
├── ☑ Show Left Only
├── ☑ Show Right Only
├── ☐ Show Files Only
├── ───────────
├── Folder View Options ▸
│   ├── ☑ Always Show Folders
│   ├── ◉ Compare Folder Structure
│   ├── ○ Only Compare Files
│   └── ○ Ignore Folder Structure
├── ───────────
├── ◉ All
├── ○ Diffs
└── ○ Same

&Tools
├── ───────────
└── Options

&Help
└── About
```

## Issues Identified

### 1. Non-Standard Top-Level Menus
- ❌ **Session**: Not a KDE standard menu, should be split into File/View
- ❌ **Actions**: Should be split into File/Edit/Tools
- ❌ **Search**: Too small to be top-level, should merge into Edit
- ⚠️ **Edit**: Currently minimal, needs expansion
- ✅ **View**: Correct, but overstuffed
- ✅ **Tools**: Correct, but too empty
- ✅ **Help**: Correct, but incomplete

### 2. Missing KDE Standard Menus
- ❌ **Settings**: Should contain Configure Shortcuts, Configure Toolbars, Preferences

### 3. Action Naming Issues

| Current Name | KDE Standard Name | Severity |
|--------------|-------------------|----------|
| New Session | New | P0 |
| Exit | Quit | P1 |
| Options | Configure rcompare... | P0 |
| Compare Now | (Keep as-is, app-specific) | P2 |
| Refresh Now | Refresh | P1 |
| Synchronize... | (Keep as-is, app-specific) | P2 |

### 4. Shortcut Conflicts

| Shortcut | Current Action | Potential Conflict |
|----------|----------------|-------------------|
| Ctrl+W | Swap L/R Sides | KDE standard: Close Window/Tab |
| Ctrl+H | Home | Some apps: Find and Replace |
| Shift+F5 | Refresh Now | Uncommon, but acceptable |
| F7/F8 | Copy L→R / R→L | Acceptable for app-specific actions |

### 5. Duplicate Actions
- ❌ Copy L→R appears in both Actions and Edit menus
- ❌ Copy R→L appears in both Actions and Edit menus

### 6. Missing Standard Items
- ❌ File menu missing entirely
- ❌ Help→Handbook (F1)
- ❌ Help→About KDE
- ❌ Help→Report Bug
- ❌ Settings→Configure Shortcuts (Ctrl+Shift+,)
- ❌ Settings→Configure Toolbars
- ❌ View→Refresh (F5) - currently in Actions
- ❌ Mnemonics (underlined letters) for keyboard navigation

## KDE-Compliant Menu Structure (Target)

```
&File
├── &New Tab (Ctrl+T)
├── &Close Tab (Ctrl+W)
├── ───────────
├── &Quit (Ctrl+Q)

&Edit
├── Copy &Left to Right (F7)
├── Copy &Right to Left (F8)
├── ───────────
├── S&wap Sides
├── ───────────
├── &Find... (Ctrl+F)
├── Find &Next (F3)
├── Find &Previous (Shift+F3)
├── Clear Search (Esc)

&View
├── &Refresh (F5)
├── ───────────
├── Compare &Mode ▸
│   ├── ◉ &Folder Compare
│   ├── ○ &Text Compare
│   ├── ○ &Hex Compare
│   └── ○ &Image Compare
├── ───────────
├── &Filter ▸
│   ├── ◉ &All Items
│   ├── ○ &Differences Only
│   └── ○ &Same Items Only
├── ───────────
├── Show/Hide ▸
│   ├── ☑ Show &Identical Files
│   ├── ☑ Show &Different Files
│   ├── ☑ Show &Left Only
│   ├── ☑ Show &Right Only
│   └── ☐ Show F&iles Only (No Folders)
├── ───────────
├── Folder Options ▸
│   ├── ☑ Always Show Folders
│   ├── ◉ Compare Folder Structure
│   ├── ○ Only Compare Files
│   └── ○ Ignore Folder Structure
├── ───────────
├── &Expand All
├── &Collapse All

&Tools
├── &Compare Now (Shift+F5)
├── &Synchronize... (Ctrl+Y)
├── ───────────
├── &Profiles... (Ctrl+P)

&Settings
├── Configure &Shortcuts...
├── Configure Tool&bars...
├── ───────────
├── Configure &rcompare... (Ctrl+Shift+,)

&Help
├── rcompare &Handbook (F1)
├── ───────────
├── &Report Bug...
├── &About rcompare
├── About &KDE
```

## Migration Strategy

### Phase 1: Restructure Menus (KDE-M1-01)
1. Remove "Session" menu
2. Remove "Actions" menu
3. Create "File" menu
4. Expand "Edit" menu
5. Reorganize "View" menu
6. Populate "Tools" menu
7. Create "Settings" menu
8. Expand "Help" menu

### Phase 2: Rename Actions (KDE-M1-02)
1. "New Session" → "New Tab"
2. "Exit" → "Quit"
3. "Options" → "Configure rcompare..."
4. "Refresh Now" → "Refresh"
5. "Focus Search" → "Find..."
6. "Clear Search" → maintain but add Esc shortcut

### Phase 3: Add Missing Items (KDE-M1-03)
1. File→New Tab
2. File→Close Tab
3. Help→rcompare Handbook
4. Help→Report Bug
5. Help→About KDE
6. Settings→Configure Shortcuts
7. Settings→Configure Toolbars

### Phase 4: Fix Duplicates (KDE-M1-04)
1. Remove Copy L→R / R→L from Actions menu (keep in Edit)
2. Ensure toolbar and menu actions use same QAction instances

### Phase 5: Add Mnemonics (KDE-M1-04)
1. Add & before accelerator letter in all menu/action names
2. Ensure no duplicate mnemonics within same menu

### Phase 6: Fix Shortcut Conflicts (KDE-M1-05)
1. Change Swap L/R from Ctrl+W to unassigned (or Ctrl+Shift+W)
2. Change Home from Ctrl+H to Ctrl+Home (or Alt+Home)
3. Add standard Find shortcuts (F3/Shift+F3)
4. Add Esc to clear search

## Code Changes Required

### main_window.py _build_menu_bar()

```python
def _build_menu_bar(self) -> None:
    menu_bar: QMenuBar = self.menuBar()

    # -- File -------------------------------------------------------
    file_menu = menu_bar.addMenu("&File")

    self._act_new_tab = QAction("&New Tab", self)
    self._act_new_tab.setShortcut(QKeySequence.StandardKey.NewTab)
    file_menu.addAction(self._act_new_tab)

    self._act_close_tab = QAction("&Close Tab", self)
    self._act_close_tab.setShortcut(QKeySequence.StandardKey.Close)
    file_menu.addAction(self._act_close_tab)

    file_menu.addSeparator()

    self._act_quit = QAction("&Quit", self)
    self._act_quit.setShortcut(QKeySequence.StandardKey.Quit)
    file_menu.addAction(self._act_quit)

    # -- Edit -------------------------------------------------------
    edit_menu = menu_bar.addMenu("&Edit")

    self._act_copy_lr = QAction("Copy &Left to Right", self)
    self._act_copy_lr.setShortcut(QKeySequence(Qt.Key.Key_F7))
    edit_menu.addAction(self._act_copy_lr)

    self._act_copy_rl = QAction("Copy &Right to Left", self)
    self._act_copy_rl.setShortcut(QKeySequence(Qt.Key.Key_F8))
    edit_menu.addAction(self._act_copy_rl)

    edit_menu.addSeparator()

    self._act_swap_sides = QAction("S&wap Sides", self)
    # Removed Ctrl+W conflict
    edit_menu.addAction(self._act_swap_sides)

    edit_menu.addSeparator()

    self._act_find = QAction("&Find...", self)
    self._act_find.setShortcut(QKeySequence.StandardKey.Find)
    edit_menu.addAction(self._act_find)

    # etc...
```

## Test Plan

1. **Visual Verification**: Compare menu structure against target
2. **Keyboard Navigation**: Verify mnemonics work (Alt+F, Alt+E, etc.)
3. **Shortcut Testing**: Verify all shortcuts work without conflicts
4. **Consistency Check**: Same action has same label in menu/toolbar/context
5. **Screenshot Comparison**: Before/after shots for documentation

## Acceptance Criteria

- [ ] Menu structure matches KDE standard order: File, Edit, View, Tools, Settings, Help
- [ ] No custom menus (Session, Actions removed)
- [ ] All actions have mnemonics
- [ ] No duplicate actions across menus
- [ ] Standard shortcuts implemented (Ctrl+Q, F1, Ctrl+F, etc.)
- [ ] Ctrl+W conflict resolved
- [ ] Help menu includes Handbook, About KDE, Report Bug
- [ ] Settings menu includes Configure Shortcuts, Configure Toolbars, Preferences
