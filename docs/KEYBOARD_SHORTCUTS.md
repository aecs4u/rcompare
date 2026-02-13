# RCompare Keyboard Shortcuts

This document lists all keyboard shortcuts available in RCompare PySide6 GUI.

## File Menu

| Shortcut | Action | Description |
|----------|--------|-------------|
| **Ctrl+T** | New Tab | Create a new comparison tab |
| **Ctrl+W** | Close Tab | Close the current tab |
| **Ctrl+Q** | Quit | Exit the application |

## Edit Menu

| Shortcut | Action | Description |
|----------|--------|-------------|
| **F7** | Copy Left to Right | Copy selected files from left to right |
| **F8** | Copy Right to Left | Copy selected files from right to left |
| - | Swap Sides | Swap left and right panels (no shortcut) |
| **Ctrl+F** | Find... | Focus the search/filter field |
| **F3** | Find Next | Find next occurrence (placeholder) |
| **Shift+F3** | Find Previous | Find previous occurrence (placeholder) |

## View Menu

| Shortcut | Action | Description |
|----------|--------|-------------|
| **F5** | Refresh | Refresh the current comparison |
| - | Compare Mode | Switch between Folder/Text/Hex/Image views |
| - | Filter | Toggle All/Differences/Same filter |
| - | Show/Hide | Toggle visibility of file types |
| - | Folder Options | Configure folder comparison mode |
| - | Expand All | Expand all folders in tree |
| - | Collapse All | Collapse all folders in tree |

## Tools Menu

| Shortcut | Action | Description |
|----------|--------|-------------|
| **Shift+F5** | Compare Now | Start a new comparison scan |
| **Ctrl+Y** | Synchronize... | Open sync dialog with preview |
| **Ctrl+P** | Profiles... | Open profile management dialog |

## Settings Menu

| Shortcut | Action | Description |
|----------|--------|-------------|
| **Ctrl+Shift+,** | Configure Shortcuts... | Configure keyboard shortcuts (placeholder) |
| - | Configure Toolbars... | Configure toolbar layout (placeholder) |
| **Ctrl+,** | Configure rcompare... | Open preferences/settings dialog |

## Help Menu

| Shortcut | Action | Description |
|----------|--------|-------------|
| **F1** | rcompare Handbook | Open online handbook/wiki |
| - | Report Bug... | Open GitHub issues page |
| - | About rcompare | Show about dialog |
| - | About KDE | Show About KDE information |

## Context Menu (Folder View)

| Shortcut | Action | Description |
|----------|--------|-------------|
| **Enter** | Open/View File | Open selected file in appropriate viewer |
| **Delete** | Delete | Delete selected files (requires confirmation) |
| - | Copy Path | Copy file path to clipboard |
| - | Reveal in File Manager | Open containing folder in system file manager |

## General Navigation

| Shortcut | Action | Description |
|----------|--------|-------------|
| **Ctrl+Tab** | Next Tab | Switch to next tab (placeholder) |
| **Ctrl+Shift+Tab** | Previous Tab | Switch to previous tab (placeholder) |
| **Ctrl+1-9** | Go to Tab N | Jump to specific tab number (placeholder) |
| **Esc** | Cancel/Clear | Cancel operation or clear search |
| **Alt+F** | Open File Menu | Access File menu via keyboard |
| **Alt+E** | Open Edit Menu | Access Edit menu via keyboard |
| **Alt+V** | Open View Menu | Access View menu via keyboard |
| **Alt+T** | Open Tools Menu | Access Tools menu via keyboard |
| **Alt+S** | Open Settings Menu | Access Settings menu via keyboard |
| **Alt+H** | Open Help Menu | Access Help menu via keyboard |

## Notes

### Placeholders
Some shortcuts marked as "(placeholder)" are reserved but not yet fully implemented:
- **Find Next/Previous** - Will enable incremental search navigation
- **Configure Shortcuts** - Will open shortcut customization dialog
- **Configure Toolbars** - Will allow toolbar layout customization
- **Ctrl+Tab navigation** - Will enable keyboard tab switching

### KDE Standard Shortcuts
RCompare follows KDE/Qt standard key sequences where applicable:
- `Ctrl+Q` (Quit) - QKeySequence.StandardKey.Quit
- `Ctrl+T` (New Tab) - QKeySequence.StandardKey.AddTab
- `Ctrl+W` (Close) - QKeySequence.StandardKey.Close
- `Ctrl+F` (Find) - QKeySequence.StandardKey.Find
- `F1` (Help) - QKeySequence.StandardKey.HelpContents
- `F3` (Find Next) - QKeySequence.StandardKey.FindNext
- `Shift+F3` (Find Previous) - QKeySequence.StandardKey.FindPrevious
- `F5` (Refresh) - QKeySequence.StandardKey.Refresh

### Custom Shortcuts
Application-specific shortcuts designed for file comparison workflows:
- `F7` / `F8` - Quick copy left/right (traditional diff tool convention)
- `Shift+F5` - Trigger comparison scan (distinct from refresh)
- `Ctrl+Y` - Synchronize (uncommon but mnemonic)
- `Ctrl+P` - Profiles (common shortcut for profiles/preferences)

### Removed/Changed Shortcuts
The following shortcuts were removed or changed for KDE compliance:
- ❌ `Ctrl+W` - Was "Swap Sides", now "Close Tab" (KDE standard)
- ❌ `Ctrl+H` - Was "Home", removed (potential conflict)
- ❌ `Ctrl+N` - Was "New Session", now `Ctrl+T` "New Tab"
- ❌ `Ctrl+Shift+F` - Was "Clear Filter", now uses `Esc`

### Accessibility
All menu items can be accessed via keyboard using mnemonics:
- Press `Alt` to activate the menu bar
- Press the underlined letter to open a menu (e.g., `Alt+F` for File)
- Use arrow keys to navigate within menus
- Press `Enter` to activate the selected item
- Press `Esc` to close menus

## Customization

Future versions will support shortcut customization through:
- **Settings → Configure Shortcuts** (`Ctrl+Shift+,`)
- Standard KDE shortcut configuration dialog
- Import/export shortcut schemes
- Reset to defaults option

For now, shortcuts are hardcoded to ensure KDE compliance and consistency.

## Related Documentation

- [KDE Menu Audit](KDE_MENU_AUDIT.md) - Menu structure and organization
- [KDE Shortcut Audit](KDE_SHORTCUT_AUDIT.md) - Detailed shortcut analysis
- [KDE Compliance Checklist](KDE_COMPLIANCE_CHECKLIST.md) - Overall compliance status
