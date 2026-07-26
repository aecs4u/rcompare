# Module: teczka

Last verified against source: 2026-07-25 (`teczka/teczka/{main_window.py,
views/*, widgets/*, dialogs/*}` read directly).

The desktop GUI — PySide6/Qt6, Python, under `teczka/teczka/`. Shells out to
`rcompare_cli` for every comparison (`utils/cli_bridge.py`; the binary is
located via `shutil.which("rcompare_cli")` or a configured path, see
`utils/config.py::_find_cli`). Packaged for release with PyInstaller —
see [.github/workflows/release.yml](../../.github/workflows/release.yml). The
Rust/Slint `rcompare_gui` crate that used to be teczka's sibling GUI was
removed 2026-07-25; teczka is now the only GUI in this repo.

## Structure

- `views/`: `folder_view.py`, `text_view.py`, `hex_view.py`, `image_view.py`,
  `table_view.py` (CSV/Excel/Parquet), `merge_view.py` (3-way merge),
  `home_view.py`, `path_bar.py`.
- `widgets/`: `session_tab_bar.py`, `sidebar.py`, `diff_overview_bar.py`
  (gutter map), `diff_text_edit.py`, `filter_bar.py`, `breadcrumb_bar.py`,
  `compact_path_bar.py`, `color_legend.py`, `progress_widget.py`,
  `integrated_status_bar.py`.
- `dialogs/`: `settings_dialog.py`, `profiles_dialog.py`, `sync_dialog.py`,
  `export_dialog.py`, `align_dialog.py`, `delete_dialog.py`, `move_dialog.py`,
  `rename_dialog.py`, `select_dialog.py`, `shortcuts_dialog.py`,
  `stats_dialog.py`, `about_dialog.py`, `splash_dialog.py`.
- `workers/`: `comparison_worker.py`, `function_worker.py` (background threads
  for scan/compare so the UI stays responsive).
- `models/settings.py`: `SessionProfile`, `ProfileManager`.

## Feature inventory (source-verified — several of these were marked
"planned"/"missing" in docs this pass replaces; that was wrong)

| Feature | Status | Evidence |
|---|---|---|
| Multi-tab sessions | **Done, load-bearing** | `main_window.py`: `SessionState`, `_capture_session_state`/`_apply_session_state`, `_on_session_changed` actually snapshot/restore per-tab left/right/base paths, settings, and 3-way-mode flag on tab switch — not decorative. |
| Session profiles (save/load/auto-save) | **Done** | `models/settings.py` (`ProfileManager`, `SessionProfile`), `dialogs/profiles_dialog.py`, wired to Tools→Profiles (Ctrl+P); auto-saves a "Last Session (Auto)" profile on close. |
| Sync preview dialog | **Done** | `dialogs/sync_dialog.py`. |
| Three-way merge UI | **Done** | `views/merge_view.py` (596 lines) — independent line-level diff via Python `difflib.SequenceMatcher` comparing base/left/right (not just a display of the core `MergeEngine`'s tree-level plan — see [docs/modules/rcompare_core.md](rcompare_core.md#merge-engine-merge_enginers-681-lines)). Reachable via a 3-Way toggle action (`_on_three_way_toggled`), not orphaned. |
| Drag-and-drop | **Done, with a bug** | `main_window.py` `dragEnterEvent`/`dropEvent` accept any `file://` URL (files or directories). **Bug**: if more than 2 paths are dropped, only the first two are used — the rest are silently discarded, no warning. |
| Synced scrolling + gutter diff map | **Done** | `text_view.py` mirrors scrollbar position by ratio between left/right editors; `widgets/diff_overview_bar.py` renders the gutter/overview map. |
| Hex viewer | **Done** | `views/hex_view.py`, instantiated at startup. |
| CSV/JSON export of comparison results | **Done (GUI-only)** | `dialogs/export_dialog.py` — no CLI equivalent, no HTML/JUnit export anywhere (see [docs/modules/rcompare_cli.md](rcompare_cli.md)). |
| Archive-write / cloud (S3/SFTP/WebDAV) sources | **Not wired** | Core APIs exist in `rcompare_core` but nothing in teczka constructs them — see [docs/modules/rcompare_core.md](rcompare_core.md). |

## KDE/Plasma compliance

Tracked in detail in [docs/KDE_COMPLIANCE.md](../KDE_COMPLIANCE.md) (self-reported,
appears accurate on spot-check — e.g. `QIcon.fromTheme()` usage and an "About
KDE" action are both present as claimed). Baseline was a **5% pass rate**;
after one work session of menu restructuring, shortcut fixes, and partial
theming it moved to **~35%**. Target is **≥90%**. This is the single largest
open GUI-quality gap — see [docs/PLAN.md](../PLAN.md).

## Testing

`teczka/tests/`: 4 files (`test_config.py`, `test_models.py`, `test_utils.py`,
`test_widgets.py`), ~250 lines total, using `pytest-qt` (a real declared
dependency, not just unittest mocks). Thin relative to the size of `views/`
and `widgets/` — most GUI surface area (merge view, sync/export/profiles
dialogs, drag-and-drop) has no automated coverage. No dedicated CI job runs
these yet; they're only exercised manually or incidentally at PyInstaller
release-build time — see [.github/workflows/ci.yml](../../.github/workflows/ci.yml).
