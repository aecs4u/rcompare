"""Select-identical and bulk-delete actions for the folder view (LHS)."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QFile, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from .dialogs.delete_dialog import DeleteDialog
from .dialogs.identical_select_dialog import IdenticalSelectDialog
from .dialogs.select_dialog import SelectDialog
from .utils.bulk_select import (
    collapse_to_top_level,
    find_by_criteria,
    find_identical,
)


def _folders_blocked_reason(window) -> str:
    session = window._current_session()
    if session.file_filter.strip() or session.settings.ignore_patterns:
        return (
            "Folder selection is disabled while file filters or ignore patterns are active: "
            "those files are not part of the comparison, so a folder that looks identical "
            "may still contain other files."
        )
    return ""


def select_identical_lhs(window) -> None:
    report = window._current_report
    if report is None:
        window.statusBar().showMessage("Run a comparison first.", 4000)
        return
    dialog = IdenticalSelectDialog(report, _folders_blocked_reason(window), window)
    if not dialog.exec():
        return
    selection = find_identical(report, dialog.include_folders())
    if not selection.paths:
        window.statusBar().showMessage("No identical items to select.", 4000)
        return
    # Identical rows must be visible to be selectable.
    if window._filter_bar.diff_option_mode != "show_differences":
        window._apply_newer_mode("show_differences")
    if not window._filter_bar.show_identical:
        window._act_show_identical.setChecked(True)
        window._on_view_filter_toggled()
    window._folder_view.set_selection_mode("left")  # keep the selection on the LHS only
    shown = window._folder_view.select_paths(selection.paths, side="left")
    window.statusBar().showMessage(
        f"Selected {shown:,} identical item(s) on the left. Use Edit → Delete Selected (LHS) to remove them.",
        8000,
    )


def _apply_smart_selection(
    window, paths: list[str], operation: str, side: str = "left"
) -> int:
    side = side if side in {"left", "right", "both"} else "left"
    window._folder_view.set_selection_mode(side)
    selection_side = "right" if side == "right" else "left"
    return window._folder_view.select_paths(
        paths, side=selection_side, operation=operation
    )


def quick_select_lhs(window, command: str, side: str = "left") -> None:
    """Apply All/None/Invert to visible rows on the selected panel(s)."""
    folder_view = window._folder_view
    side = side if side in {"left", "right", "both"} else "left"
    folder_view.set_selection_mode(side)
    visible_paths = {node.path for node in folder_view.visible_nodes() if node.path}
    selection_side = "right" if side == "right" else "left"
    selected_paths = set(folder_view.selected_paths(selection_side))
    if command == "all":
        paths = sorted(visible_paths)
    elif command == "none":
        paths = []
    elif command == "invert":
        paths = sorted(visible_paths - selected_paths)
    else:
        return

    selected = _apply_smart_selection(window, paths, "replace", side)
    panel = {"left": "LHS", "right": "RHS", "both": "both panels"}[side]
    window.statusBar().showMessage(
        f"Selected {selected:,} visible item(s) on the {panel}.", 5000
    )


def select_by_criteria_lhs(window) -> None:
    """Select or deselect visible rows by status, newer side, pattern, and size."""
    if window._current_report is None:
        window.statusBar().showMessage("Run a comparison first.", 4000)
        return

    dialog = SelectDialog(window)
    dialog.quick_select.connect(
        lambda command: quick_select_lhs(window, command, dialog.criteria["side"])
    )
    if not dialog.exec():
        return

    criteria = dialog.criteria
    paths = find_by_criteria(window._folder_view.visible_nodes(), criteria)
    if not paths:
        window.statusBar().showMessage("No visible items match those criteria.", 5000)
        return

    operation = "replace" if criteria["mode"] == "select" else "remove"
    side = criteria.get("side", "left")
    matched = _apply_smart_selection(window, paths, operation, side)
    verb = "Selected" if operation == "replace" else "Deselected"
    panel = {"left": "LHS", "right": "RHS", "both": "both panels"}.get(side, "LHS")
    window.statusBar().showMessage(
        f"{verb} {matched:,} matching item(s) on the {panel}.", 6000
    )


def delete_selected_lhs(window) -> None:
    report = window._current_report
    if report is None:
        window.statusBar().showMessage("Run a comparison first.", 4000)
        return
    paths = collapse_to_top_level(window._folder_view.selected_paths("left"))
    # Delete relative to the folder that was actually scanned, not whatever the
    # path bar shows now (it may have been edited since the comparison).
    root = Path(report.left).expanduser()
    targets = [(p, root / p) for p in paths if (root / p).exists()]
    if not targets:
        window.statusBar().showMessage(
            "Nothing selected on the left panel to delete.", 4000
        )
        return

    sel = find_identical(report, include_folders=True)
    identical = set(sel.paths) | set(find_identical(report, False).files)
    not_identical = [p for p, _ in targets if p not in identical]
    warning = ""
    if not_identical:
        warning = (
            f"{len(not_identical):,} of the selected item(s) are NOT identical to the right side "
            "(different, left-only, or folders with other content)."
        )

    dialog = DeleteDialog(
        [p for p, _ in targets], window, warning=warning, dry_run_default=True
    )
    dialog.setWindowTitle("Delete Selected (LHS)")
    dialog.exec()
    if not dialog.confirmed:
        return
    if dialog.dry_run:
        window.statusBar().showMessage(
            f"Dry run: {len(targets):,} item(s) on the left would be deleted. Nothing was changed.",
            8000,
        )
        return
    if not dialog.use_trash:
        answer = QMessageBox.warning(
            window,
            "Permanent delete",
            f"Permanently delete {len(targets):,} item(s) from the left folder?\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

    progress = QProgressDialog("Deleting…", "Cancel", 0, len(targets), window)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    done, failed = 0, []
    for i, (rel, path) in enumerate(targets):
        progress.setValue(i)
        QApplication.processEvents()
        if progress.wasCanceled():
            break
        try:
            if dialog.use_trash:
                if not QFile.moveToTrash(str(path)):
                    raise OSError("could not move to trash")
            elif path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
            done += 1
        except OSError as exc:
            failed.append((rel, str(exc)))
    progress.setValue(len(targets))

    where = "to the trash" if dialog.use_trash else "permanently"
    msg = f"Deleted {done:,} item(s) {where}."
    if failed:
        msg += f" {len(failed):,} failed (first: {failed[0][0]}: {failed[0][1]})."
    if progress.wasCanceled():
        msg += " Cancelled before finishing."
    window.statusBar().showMessage(msg, 12000)
    window._on_refresh()
