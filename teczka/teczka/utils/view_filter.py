"""Shared status and newer-side predicates for folder rows and navigation."""

from __future__ import annotations

from .cli_bridge import DiffStatus


def status_is_enabled(
    status: DiffStatus,
    *,
    show_identical: bool,
    show_different: bool,
    show_left_only: bool,
    show_right_only: bool,
) -> bool:
    """Return whether the status pills allow *status*."""
    if status == DiffStatus.SAME:
        return show_identical
    if status == DiffStatus.DIFFERENT:
        return show_different
    if status == DiffStatus.ORPHAN_LEFT:
        return show_left_only
    if status == DiffStatus.ORPHAN_RIGHT:
        return show_right_only
    return True


def diff_mode_matches(
    status: DiffStatus,
    left_modified: int | None,
    right_modified: int | None,
    mode: str,
) -> bool:
    """Return whether a status and timestamp pair match a Diff Options mode."""
    selected_mode = (mode or "show_differences").strip().lower()
    if selected_mode == "show_differences":
        # Status pills decide which statuses are visible in the default mode.
        return True
    if selected_mode == "show_no_orphans":
        return status not in {DiffStatus.ORPHAN_LEFT, DiffStatus.ORPHAN_RIGHT}
    if selected_mode == "show_differences_no_orphans":
        return status in {DiffStatus.DIFFERENT, DiffStatus.UNCHECKED}
    if selected_mode == "show_orphans":
        return status in {DiffStatus.ORPHAN_LEFT, DiffStatus.ORPHAN_RIGHT}
    if selected_mode == "show_left_orphans":
        return status == DiffStatus.ORPHAN_LEFT
    if selected_mode == "show_right_orphans":
        return status == DiffStatus.ORPHAN_RIGHT

    both_modified = left_modified is not None and right_modified is not None
    left_newer = both_modified and left_modified > right_modified
    right_newer = both_modified and right_modified > left_modified
    if selected_mode == "show_left_newer":
        return left_newer
    if selected_mode == "show_right_newer":
        return right_newer
    if selected_mode == "show_left_newer_left_orphans":
        return left_newer or status == DiffStatus.ORPHAN_LEFT
    if selected_mode == "show_right_newer_right_orphans":
        return right_newer or status == DiffStatus.ORPHAN_RIGHT
    return True
