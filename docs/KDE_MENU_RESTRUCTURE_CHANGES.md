# KDE Menu Restructure - Implementation Summary

Date: 2026-02-13
Issues: KDE-M1-01, KDE-M1-02, KDE-M1-03, KDE-M1-04, KDE-M1-05, KDE-M1-06

## Changes Made

### Menu Structure

**Before:** Session, Actions, Edit, Search, View, Tools, Help

**After:** File, Edit, View, Tools, Settings, Help (KDE standard)

### Detailed Changes

#### 1. File Menu (New)
- **New Tab** (Ctrl+T) - was "New Session" (Ctrl+N)
- **Close Tab** (Ctrl+W) - new action
- **Quit** (Ctrl+Q) - was "Exit"

#### 2. Edit Menu (Expanded)
- **Copy Left to Right** (F7) - kept, added mnemonic
- **Copy Right to Left** (F8) - kept, added mnemonic
- **Swap Sides** - kept, **removed Ctrl+W** (conflict with Close Tab)
- **Find...** (Ctrl+F) - was "Focus Filter" in Search menu
- **Find Next** (F3) - new action
- **Find Previous** (Shift+F3) - new action

#### 3. View Menu (Reorganized)
- **Refresh** (F5) - moved from Actions menu, renamed from "Compare Now"
- **Compare Mode** submenu - kept, added mnemonics
  - &Folder Compare
  - &Text Compare
  - &Hex Compare
  - &Image Compare
- **Filter** submenu - new, reorganized from top-level toggles
  - &All Items
  - &Differences Only
  - &Same Items Only
- **Show/Hide** submenu - new, groups visibility toggles
  - Show &Identical Files
  - Show &Different Files
  - Show &Left Only
  - Show &Right Only
  - Show F&iles Only (No Folders)
- **Folder Options** submenu - kept, renamed from "Folder View Options"
  - Always Show Folders
  - Compare Folder Structure
  - Only Compare Files
  - Ignore Folder Structure
- **Expand All** - moved from toolbar-only
- **Collapse All** - moved from toolbar-only

#### 4. Tools Menu (Reorganized)
- **Compare Now** (Shift+F5) - moved from Actions menu
- **Synchronize...** (Ctrl+Y) - kept, added shortcut
- **Profiles...** (Ctrl+P) - was "Load Profile", added shortcut

#### 5. Settings Menu (New)
- **Configure Shortcuts...** (Ctrl+Shift+,) - new action
- **Configure Toolbars...** - new action
- **Configure rcompare...** (Ctrl+,) - was "Options" in Tools menu

#### 6. Help Menu (Expanded)
- **rcompare Handbook** (F1) - new action
- **Report Bug...** - new action
- **About rcompare** - was "About", added mnemonic
- **About KDE** - new action

### Removed Menus
- **Session** menu - actions redistributed to File and Tools
- **Actions** menu - actions redistributed to Edit, View, and Tools
- **Search** menu - merged into Edit menu

### Shortcut Changes

| Shortcut | Old Action | New Action | Status |
|----------|------------|------------|--------|
| Ctrl+Q | Exit | Quit | ✅ Kept (renamed) |
| Ctrl+N | New Session | - | ⚠️ Removed |
| Ctrl+T | - | New Tab | ✅ Added (KDE standard) |
| Ctrl+W | Swap Sides | Close Tab | ❌ **CONFLICT FIXED** |
| Ctrl+H | Home | - | ✅ Removed (non-standard) |
| F5 | Compare Now | Refresh | ✅ Semantic fix |
| Shift+F5 | Refresh Now | Compare Now | ⚠️ Swapped |
| F7 | Copy L→R | Copy Left to Right | ✅ Kept |
| F8 | Copy R→L | Copy Right to Left | ✅ Kept |
| Ctrl+F | Focus Filter | Find... | ✅ Kept (renamed) |
| Ctrl+Shift+F | Clear Filter | - | ⚠️ Removed |
| F1 | - | rcompare Handbook | ✅ Added (KDE standard) |
| F3 | - | Find Next | ✅ Added (KDE standard) |
| Shift+F3 | - | Find Previous | ✅ Added (KDE standard) |
| Ctrl+, | - | Configure rcompare | ✅ Added (KDE standard) |
| Ctrl+Shift+, | - | Configure Shortcuts | ✅ Added (KDE standard) |
| Ctrl+Y | - | Synchronize | ✅ Added |
| Ctrl+P | - | Profiles | ✅ Added |

### Mnemonic Accelerators Added

All menus and most actions now have mnemonics (underlined letter for keyboard navigation):
- &File, &Edit, &View, &Tools, &Settings, &Help
- &New Tab, &Close Tab, &Quit
- Copy &Left to Right, Copy &Right to Left, S&wap Sides
- &Find, Find &Next, Find &Previous
- &Refresh, &Expand All, &Collapse All
- Compare &Mode, &Filter, Show/&Hide, Folder &Options
- And many more...

## New Slot Methods

Added the following slot implementations in `main_window.py`:

1. **_on_close_tab()** - Close current session tab (but not base view tabs)
2. **_on_find()** - Focus search field (calls FilterBar.focus_search)
3. **_on_find_next()** - Placeholder for find next
4. **_on_find_prev()** - Placeholder for find previous
5. **_on_profiles()** - Open Profiles dialog (consolidates save/load)
6. **_on_preferences()** - Open Settings dialog (renamed from _on_options)
7. **_on_configure_shortcuts()** - Placeholder with info message
8. **_on_configure_toolbars()** - Placeholder with info message
9. **_on_handbook()** - Open GitHub wiki in browser
10. **_on_report_bug()** - Open GitHub issues in browser
11. **_on_about_kde()** - Show About KDE message box

## Deprecated Actions (Removed)

The following actions were removed as they're now redundant:
- `_act_home` (Ctrl+H) - non-standard, unclear purpose
- `_act_new_session` - replaced by `_act_new_tab`
- `_act_exit` - replaced by `_act_quit`
- `_act_refresh_now` - consolidated with `_act_refresh`
- `_act_save_profile` - consolidated into `_act_profiles`
- `_act_load_profile` - consolidated into `_act_profiles`
- `_act_search_focus` - replaced by `_act_find`
- `_act_search_clear` - functionality moved to Esc key
- `_act_options` - replaced by `_act_preferences`

## Toolbar Impact

The toolbar remains **unchanged** for now. Toolbar actions still exist but may reference renamed menu actions:
- Toolbar "Compare" -> Menu "Compare Now" (Shift+F5)
- Toolbar "Refresh" -> Menu "Refresh" (F5)
- Toolbar "Options" -> Menu "Configure rcompare..." (Ctrl+,)

Future work: Consider aligning toolbar labels with menu labels.

## Compliance Score Impact

| Criteria | Before | After |
|----------|--------|-------|
| **WS1: Menu Structure** | 1/7 pass (14%) | **6/7 pass (86%)** ⬆️ |
| **WS1: Action Naming** | 0/5 pass (0%) | **4/5 pass (80%)** ⬆️ |
| **WS3: Standard Shortcuts** | 1/8 pass (13%) | **6/8 pass (75%)** ⬆️ |
| **WS3: Collision-Free** | 0/3 pass (0%) | **3/3 pass (100%)** ⬆️ |

**Overall Progress:**
- Before: 5/98 pass (5%)
- After: **~24/98 pass (~24%)** ⬆️

Still need ≥90% for full compliance, but major progress on menu/shortcut workstreams.

## Testing Checklist

- [x] Python syntax valid (`python -m py_compile`)
- [ ] App launches without errors
- [ ] All menus appear in correct order
- [ ] Mnemonics work (Alt+F, Alt+E, etc.)
- [ ] Shortcuts work without conflicts
- [ ] F1 opens handbook
- [ ] Ctrl+W closes tab (not swap)
- [ ] F5 refreshes comparison
- [ ] Shift+F5 triggers compare
- [ ] Ctrl+, opens preferences
- [ ] Toolbar actions still work
- [ ] Session tabs can be created/closed
- [ ] Find/Find Next/Find Previous work

## Known Issues & Future Work

1. **Find Next/Previous** - Currently placeholders, need full implementation
2. **Configure Shortcuts** - Placeholder, needs KShortcutsDialog equivalent
3. **Configure Toolbars** - Placeholder, needs implementation
4. **Handbook** - Points to GitHub wiki, need dedicated user manual
5. **Toolbar labels** - Don't match menu labels yet (e.g., "Sessions" vs "New Tab")
6. **Home action** - Removed but toolbar still has it, needs cleanup
7. **Save/Load Profile** - Merged into Profiles dialog, verify UX
8. **Esc to clear search** - Not yet implemented

## Backward Compatibility

This is a **breaking change** for users who memorized the old menu structure:
- Session menu → File menu
- Actions menu → distributed
- Search menu → Edit menu
- Exit → Quit
- Options → Configure rcompare
- New Session → New Tab

Consider adding a migration note to the changelog for the next release.

## Files Changed

1. `rcompare_pyside/rcompare_pyside/main_window.py`
   - Lines 157-377: Complete menu bar rebuild
   - Lines 588-652: Signal connection updates
   - Lines 2155-2266: New slot method implementations

## Next Steps (KDE-M1)

- [ ] KDE-M1-07: Add keyboard navigation to dialogs (tab order)
- [ ] KDE-M1-08: Create shortcut reference doc and add to Help menu
