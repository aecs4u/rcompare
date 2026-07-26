# Beyond Compare vs teczka: GUI Configuration Comparison

Last updated: 2026-07-26

Compares the **configuration surface** of Beyond Compare 5.2.4 (build 32425, Linux/Qt)
against teczka (PySide6/Qt6 GUI in this repo). Feature-level parity is tracked in
[FEATURE_COMPARISON.md](../FEATURE_COMPARISON.md) and remaining work in
[PLAN.md](PLAN.md); this document is narrower — it asks *what can a user configure,
where does that setting live, and does it persist*.

## Method

Beyond Compare was inspected live on this machine (X11 `:1`, `bcompare` PID under
Xwayland). Every menu was opened and every Options page and Session Settings tab was
visited and screenshotted via XTEST automation; the tables below are transcribed from
those captures, not from vendor documentation. teczka's side is read from the working
tree ([main_window.py](../teczka/teczka/main_window.py),
[settings_dialog.py](../teczka/teczka/dialogs/settings_dialog.py),
[config.py](../teczka/teczka/utils/config.py),
[settings.py](../teczka/teczka/models/settings.py)).

Beyond Compare was running in 30-day evaluation mode; nothing observed here is
edition-gated in a way that affects the configuration surface.

**Evidence:** the 62 captures backing the Beyond Compare columns are in
[`.playwright-mcp/bcompare/`](../.playwright-mcp/bcompare/) — all 11 Options pages
(`options_*`), the Folder Compare menus, submenus and Session Settings (`fc_*`), the Text
Compare set (`tc_*`), the Table Compare set (`tbc_*`), the Home menus (`home_*`) and the
File Formats dialog (`tools_file_formats*`). Every Beyond Compare claim below can be
checked against them. The teczka columns cite source files directly.

Not captured: Session Settings for Folder Merge, Folder Sync, Text Merge, Hex, Media and
Picture Compare (they reuse the Folder and Text Compare tab structures), and the contents
of Table Compare's Sheets/Columns/Rows tabs.

**Moving-target caveat:** teczka is under active change. §6 records defect state as of
2026-07-26 and calls out which items the working tree has since fixed; re-verify against
`main` before acting on it.

---

## 1. Configuration architecture

The single biggest structural difference: **Beyond Compare lets the user choose the scope
at which a settings change applies. teczka has per-session state internally, but no way
for the user to target it.**

teczka does keep settings per tab: `SessionState` holds its own `ComparisonSettings` and
`FolderFilterState` ([main_window.py:134](../teczka/teczka/main_window.py#L134)), and
switching tabs captures and reapplies them. What is missing is the *user-facing* half —
a scope selector, and any way to promote a change to "the default for new sessions".
Editing Settings writes the active session and the global config together, so there is no
way to tighten a filter for one comparison only.

| Tier | Beyond Compare | teczka |
|------|----------------|--------|
| Global preferences | `Tools > Options` — 11 pages | `Settings > Configure RCompare...` — 5 tabs |
| Per-comparison settings | `Session > Session Settings...` — 6 tabs, with a **scope selector** ("Use for this view only" / session / defaults) | ⚠️ per-tab state exists in `SessionState`, but no dialog and no scope selector |
| Reusable named config | Profiles, File Formats, Name-Filter presets, Workspaces | `SessionProfile` (paths + 3 flags) via `Tools > Profiles...` |
| On-disk form | `~/.config/bcompare/*.xml` (`BCPreferences`, `BCSessions`, `BCState`, `BCProfiles`, `menu.ini`) | `pyside.json` under `QStandardPaths.AppConfigLocation`; `profiles.json` |
| Portability | `Tools > Export Settings...` / `Import Settings...` / `Restore Factory Defaults...` | ❌ none (a per-dialog "Defaults" button only) |

The scope selector is the mechanism teczka lacks. In BC, tightening a filter or turning on
content comparison can be scoped to the current view, saved into the session, or promoted
to the default for all new sessions of that type. teczka has the storage for the first two
but exposes neither, and has no notion of the third.

---

## 2. Menu bar

Beyond Compare's Folder Compare view carries 7 menus; teczka carries 8.

| Beyond Compare | teczka | Notes |
|----------------|--------|-------|
| **Session** (23 items) | **File** (9 items) | BC's Session menu is session-lifecycle oriented: New Session ▸ (9 types), New Tab/Window, Open Session, Load/Save Workspace, Save Session (As), Session Settings, Locked, Clear Session, Swap Sides, Back/Forward, Browse for Folder ▸, Up One Level ▸, Folder Compare Report, Folder Compare Info, Merge/Sync Base Folders, Compare Parent Folders. teczka's File menu is document oriented (New Tab, Open/Save Diff, Print, Print Preview, Close Tab, Quit). |
| **Actions** (15 items) | *(context menus + Tools)* | Compare Contents, Copy/Move to Side, Copy/Move to Folder, Delete, Rename, Attributes, Touch, Exclude, New Folder, Copy Filename, Ignored, Refresh Selection, Synchronize ▸. teczka exposes most of these via `context_menus.py` rather than a menu bar entry. |
| **Edit** (9 items) | **Edit** (8 items) | BC's Edit is *selection* (Expand/Collapse All, Select All, Select All Files, Select Newer ▸, Select Orphans ▸, Invert Selection, Refresh, Full Refresh). teczka's Edit is *editing* (Undo, Redo, Copy L→R, Copy R→L, Swap Sides, Find, Find Next/Prev). Same name, disjoint content. |
| **Search** (5 items) | *(folded into Edit)* | Next/Previous Difference, Find Filename, Find Next/Previous Filename. |
| **View** (~24 items) | **View** (9 entries + 5 submenus) | The closest match — see §4. |
| **Tools** (9 items) | **Tools** (3) + **Settings** (2) | BC: Options, File Formats, Profiles, Export/Import Settings, Restore Factory Defaults, Save Snapshot, Edit Text File, View Patch. teczka: Compare Now, Synchronize, Profiles / Configure Shortcuts, Configure RCompare. |
| **Help** (7 items) | **Help** (3–4 items) | BC adds Context Sensitive Help (F1), Check for Updates, Support, Enter Key. |
| — | **Difference** (9 items) | teczka-only: Previous/Next File, Previous/Next Difference, Apply/Unapply Difference, Apply/Unapply All, Statistics. BC scatters these across Search and Actions. |
| — | **Bookmarks** (2 + dynamic) | teczka-only. BC's nearest equivalent is saved sessions/workspaces. |

---

## 3. Global preferences: `Tools > Options` vs `Configure RCompare`

Beyond Compare's 11 pages against teczka's 5 tabs:

| Beyond Compare page | Contents | teczka equivalent |
|---------------------|----------|-------------------|
| **Startup** | Load workspace on start, save workspace on exit, quick compare dialog (binary vs rules-based), open view automatically if different; File Manager Integration (context-menu commands + locations) | ❌ none. `show_splash` exists in config but has no dialog control |
| **Tabs** | Open sessions in new window/tab, child sessions in new window/tab, open next to active tab, closing last tab closes window, warn on closing multiple tabs/windows, hide tab bar if single tab | ❌ none |
| **Appearance** | Theme (Follow OS / Light / Dark) + live **Preview** checkbox; per-view color trees for **Folder Views / File Views / Picture Compare** (Default text, Log panel, Selection, Filtered out, Compare colors: Unknown/Same/Orphan/Older/Newer/Different, Merge colors); use system font; color folders to reflect content; gradient background | ⚠️ **Appearance** tab: Light/Dark combo (restart required), 4 diff colors (added/removed/changed/applied), font family/size/tab width |
| **Text Editing** | Auto indent, backspace unindents, initialize "Text to find" to current word, show filtered line counts, number of context lines | ❌ none |
| **Next Difference** | Go to first difference on load, go to next difference after copy, limit to current folder, wrap around, show message panel | ❌ none |
| **Backups** | Back up before copy / before save, 7 backup naming schemes, backup folder | ❌ none |
| **File Operations** | 10 confirmation toggles (copy, move, read-only, system files, overwrite newer, replace during move, content compare, delete, explicit side selection, merge), synchronize confirmations (Prompt/Yes to All/No to All), include hidden filtered items by default | ⚠️ partial — teczka has confirmation dialogs (`delete_dialog`, `move_dialog`, `sync_dialog`) but **no page to configure which ones appear** |
| **Archive Types** | ~40 archive formats with editable name/mask table | ❌ none in GUI (core has archive backends) |
| **Commands** | Per-view (Home/Folder Compare/…) command table with **Menu / Toolbar / Shortcut** columns, searchable; assign or clear shortcuts; large-buttons-with-text-labels toggle | ⚠️ **Configure Shortcuts** dialog — rebinding works in-session but see §6.2 |
| **Open With** | User-defined external applications with command line + shortcut | ❌ none |
| **Tweaks** | Check for updates every N days; Editor Display (syntax highlighting on diff lines, crosshatching past EOF, right-side gutter, orphan color, extra line spacing, column line, dim inactive pane %, merge-pane font); File Operations (beep after long operations) | ❌ none |
| — | — | ✅ **General** tab (teczka-only page): follow symlinks, hash verification, cache directory, ignore-pattern glob list |
| — | — | ✅ **CLI** tab (teczka-only): `rcompare_cli` binary path, auto-detect, validation status — a consequence of the split core/CLI/GUI architecture BC does not have |
| — | — | ⚠️ **Diff Options** tab: whitespace mode, ignore case, line-by-line diff, image/CSV/JSON/Excel comparison, regex normalization rules — **see §6.1, none of these are read** |
| — | — | ⚠️ **Files** tab: default encoding, ignore LF/CRLF, binary-file glob patterns — **see §6.1, none of these are read** |

**Score:** of BC's 11 preference pages, teczka has a real equivalent for 2 (Appearance,
partially Commands), a partial for 1 (File Operations), and nothing for 8. teczka adds 2
pages BC has no need for (General, CLI).

---

## 4. View menu / display filtering

This is teczka's strongest area of parity — the diff-option modes are a direct port.

| Beyond Compare (12 modes) | teczka `DIFF_OPTION_MODES` |
|---------------------------|----------------------------|
| Show All | `show_all` ✅ |
| Show Differences | `show_differences` ✅ |
| **Show Same** | ❌ **absent from the mode list** (a "Same Items Only" preset exists under View > Filter, which is not the same control) |
| Show No Orphans | `show_no_orphans` ✅ |
| Show Differences but No Orphans | `show_differences_no_orphans` ✅ |
| Show Orphans | `show_orphans` ✅ |
| Show Left Newer | `show_left_newer` ✅ |
| Show Right Newer | `show_right_newer` ✅ |
| Show Left Newer and Left Orphans | `show_left_newer_left_orphans` ✅ |
| Show Right Newer and Right Orphans | `show_right_newer_right_orphans` ✅ |
| Show Left Orphans | `show_left_orphans` ✅ |
| Show Right Orphans | `show_right_orphans` ✅ |

Folder-structure modes match 4/4: Always Show Folders, Compare Files and Folder Structure
(teczka: "Compare Folder Structure"), Only Compare Files, Ignore Folder Structure.

Remaining View-menu gaps in teczka: **Ignore Unimportant Differences**, **Suppress
Filters**, **Columns ▸** (BC lets the user choose which columns are shown; teczka's
`folder_columns` config persists widths only), **Legend** (Ctrl+Alt+L — a `color_legend.py`
widget exists but no menu entry), **Log** panel toggle, **Toolbar** toggle (teczka's
toolbar was removed).

---

## 5. Per-session settings

Beyond Compare's `Session > Session Settings...` has six tabs. teczka has no equivalent
dialog; the nearest thing is `ComparisonSettings` (4 fields) and `SessionProfile`
(paths + 3 flags).

| BC tab | Controls | teczka |
|--------|----------|--------|
| **Specs** | Left/right folder, per-side "Disable editing", session description | ⚠️ paths only, via path bar / `SessionProfile`; no read-only side, no description |
| **Comparison** | **Quick tests:** compare file size, compare timestamps + **N-second tolerance**, ignore DST (1 hour), ignore timezone differences, compare filename case, align filenames with different extensions, align different Unicode normalization forms. **Unix metadata:** compare permissions / owner / group. **Requires opening files:** compare contents (CRC / binary / rules-based), skip if quick tests indicate same, override quick test results | ⚠️ only `use_hash_verification`. **No timestamp tolerance, no DST/timezone handling, no filename-case option, no Unicode-normalization alignment, no permission/owner/group comparison, no CRC-vs-binary-vs-rules choice** |
| **Handling** | Auto-scan subfolders in background, auto-scan top-level orphan subfolders, expand subfolders when loading, only expand with differences, **archive handling** (e.g. "As folders once opened"), touch local files when copying to FTP, **follow symbolic links**, **automatic refresh** every N minutes | ⚠️ only `follow_symlinks`. No archive policy, no auto-refresh, no expansion policy |
| **Name Filters** | Include files / Exclude files / Include folders / Exclude folders (4 independent mask lists) + **Add To Presets** | ⚠️ a single flat `ignore_patterns` glob list — no include/exclude split, no file/folder split, no presets |
| **Other Filters** | Rule list (size, date, attribute filters) with add/remove/configure/share | ❌ none |
| **Misc** | **Alignment overrides** (left↔right name mapping table), **Enabled file formats** table (Bash, C/C++/C#/ObjC, COBOL, CSV, Delphi, HTML, Java, JavaScript, …) with per-format enable | ⚠️ `align_dialog.py` exists for text alignment; no folder-level alignment overrides, no file-format table |

teczka's per-session model covers roughly **4 of BC's ~40 session-level settings**.

---

## 6. Verified defects on teczka's side

These are not gaps in scope — they are controls that exist in the UI and do nothing.

### 6.1 Eleven settings controls are never read

Every widget on the **Diff Options** and **Files** tabs of
[settings_dialog.py](../teczka/teczka/dialogs/settings_dialog.py) is constructed, shown,
and then never consulted. `get_settings()` returns only `ignore_patterns`,
`follow_symlinks`, `use_hash_verification` and `cache_dir`;
`get_appearance_settings()` returns colors/font/tab width; `get_config_updates()` returns
theme and CLI path. Grepping the whole package for each control name outside the dialog
returns zero hits:

`_ws_combo`, `_case_check`, `_text_diff_check`, `_image_diff_check`, `_csv_diff_check`,
`_json_diff_check`, `_excel_diff_check`, `_regex_edit`, `_encoding_combo`,
`_eol_ignore_check`, `_binary_patterns_edit`

They are also not initialised from config — the encoding combo hardcodes `utf-8` and the
binary-pattern box hardcodes a 9-line list on every open. So a user who sets "Ignore
whitespace: All" sees it accepted, sees it reset next time, and never sees it affect a
comparison. Two of teczka's five preference tabs are inert.

### 6.2 Shortcut rebinding does not survive restart

`ShortcutsDialog._apply_shortcut()` calls `action.setShortcut(...)` on the live action, but
`AppConfig` has no shortcuts field and nothing writes the rebinding to disk. BC persists
its equivalent in `BCState.xml`/`menu.ini`.

### 6.3 Theme changes require a restart

The Appearance tab tells the user "Change takes effect after restart." BC applies the
theme immediately and offers a **Preview** checkbox to try one before committing.

---

## 7. Where teczka is ahead

| Capability | teczka | Beyond Compare |
|------------|--------|----------------|
| Undo/redo of file operations | ✅ `OperationHistory` + Edit > Undo/Redo | ❌ no undo for copy/move/delete |
| Bookmarks | ✅ dedicated menu, persisted in config | ❌ (sessions/workspaces only) |
| Configurable comparison backend | ✅ CLI tab — the GUI is a front end over `rcompare_cli` | ❌ monolithic |
| Print / Print Preview | ✅ File menu | ⚠️ reports instead |
| 3-way merge exposed as a compare mode | ✅ View > Compare Mode | ⚠️ separate session types |
| Ignore patterns as first-class globs | ✅ (with `.gitignore` handling in core) | ⚠️ mask-based filters |
| Shortcut collision detection | ✅ `find_collisions()`, test-enforced | ❌ not surfaced |

---

## 8. Recommended priorities

Ordered by user-visible impact per unit of work:

1. **Fix or remove the inert controls (§6.1).** A preference that silently does nothing is
   worse than an absent one. Either wire the 11 controls through to
   `ComparisonSettings`/the CLI, or delete the two tabs until the backend supports them.
2. **Persist shortcut rebindings (§6.2)** — add a `shortcuts` dict to `AppConfig` and
   reapply on startup. Small, self-contained.
3. **Add a per-session settings dialog with a scope selector.** This is the structural gap.
   Even a two-tab version (Comparison + Name Filters) scoped to "this view / this session /
   default" would close most of §5.
4. **Timestamp tolerance and metadata comparison.** `N-second tolerance`, ignore DST,
   ignore timezone, and compare permissions/owner/group are the settings most likely to be
   missed by someone moving from BC, especially across filesystems.
5. **Split name filters into include/exclude × files/folders** rather than one flat
   ignore list.
6. **Export/Import Settings.** Cheap to build on the existing JSON config, and it is how
   users migrate between machines.
7. **Restore View menu leftovers:** Columns selection, Legend entry (the widget already
   exists), Suppress Filters.

Items 1 and 2 are defect fixes and should not wait on the roadmap.
