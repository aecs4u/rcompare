"""Tests for collapsing unchanged text-diff context."""

from __future__ import annotations

from PySide6.QtGui import QColor
from teczka.views.text_view import TextView, _compute_file_diff, _with_context


def _write_pair(tmp_path):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("before-1\nbefore-2\nbefore-3\nold\nafter-1\nafter-2\nafter-3\n")
    right.write_text("before-1\nbefore-2\nbefore-3\nnew\nafter-1\nafter-2\nafter-3\n")
    return left, right


def test_context_collapses_unchanged_runs_and_keeps_source_line_numbers(tmp_path):
    left, right = _write_pair(tmp_path)
    result = _compute_file_diff(str(left), str(right), QColor("white"))

    visible = _with_context(result, 1)

    assert visible.display_left == [
        "… 2 unchanged lines hidden …",
        "before-3",
        "old",
        "after-1",
        "… 2 unchanged lines hidden …",
    ]
    assert visible.display_right == [
        "… 2 unchanged lines hidden …",
        "before-3",
        "new",
        "after-1",
        "… 2 unchanged lines hidden …",
    ]
    assert visible.nums_left == ["", "3", "4", "5", ""]
    assert visible.nums_right == ["", "3", "4", "5", ""]


def test_zero_context_shows_only_changes_with_collapsed_markers(tmp_path):
    left, right = _write_pair(tmp_path)
    result = _compute_file_diff(str(left), str(right), QColor("white"))

    visible = _with_context(result, 0)

    assert visible.display_left == [
        "… 3 unchanged lines hidden …",
        "old",
        "… 3 unchanged lines hidden …",
    ]
    assert visible.display_right == [
        "… 3 unchanged lines hidden …",
        "new",
        "… 3 unchanged lines hidden …",
    ]
    assert visible.nums_left == ["", "4", ""]
    assert visible.nums_right == ["", "4", ""]


def test_text_view_context_toggle_renders_cached_diff_without_recomputing(
    qapp, qtbot, tmp_path
):
    left, right = _write_pair(tmp_path)
    view = TextView()
    qtbot.addWidget(view)

    view.compare_files(str(left), str(right))
    qtbot.waitUntil(lambda: view.has_comparison_data, timeout=5_000)
    qtbot.waitUntil(lambda: view._diff_worker is None, timeout=5_000)
    full_lines = view._left_editor.get_lines()

    assert view.set_context_lines(1)
    assert len(view._left_editor.get_lines()) == 5
    assert view._left_editor.get_lines()[0] == "… 2 unchanged lines hidden …"
    assert not view._edit_toggle.isEnabled()

    assert view.set_context_lines(None)
    assert view._left_editor.get_lines() == full_lines
    assert view._edit_toggle.isEnabled()
