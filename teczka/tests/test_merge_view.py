"""Three-way merge behavior and widget integration tests."""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog
from teczka.views.merge_view import (
    COLOR_CONFLICT,
    ConflictType,
    MergeView,
    _MergeComputation,
)


def test_disjoint_and_identical_changes_merge_automatically():
    conflicts, output, _colors = MergeView._merge_lines(
        ["head", "one", "base-two", "tail"],
        ["head", "base-one", "base-two", "tail"],
        ["head", "base-one", "two", "tail"],
    )
    assert output == ["head", "one", "two", "tail"]
    assert conflicts and all(conflict.resolved for conflict in conflicts)

    conflicts, output, _colors = MergeView._merge_lines(
        ["head", "same", "tail"],
        ["head", "base", "tail"],
        ["head", "same", "tail"],
    )
    assert output == ["head", "same", "tail"]
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type is ConflictType.BOTH_DIFFER
    assert conflicts[0].resolved


def test_overlapping_edits_are_one_unresolved_conflict():
    conflicts, output, colors = MergeView._merge_lines(
        ["head", "left replacement", "tail"],
        ["head", "base one", "base two", "base three", "tail"],
        ["head", "base one", "right replacement", "tail"],
    )

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.conflict_type is ConflictType.BOTH_DIFFER
    assert not conflict.resolved
    assert conflict.left_lines == ["left replacement"]
    assert conflict.right_lines == ["base one", "right replacement"]
    assert conflict.base_lines == ["base one", "base two", "base three"]
    assert output[conflict.start_line] == "<<<< CONFLICT >>>>"
    assert all(color == COLOR_CONFLICT for color in colors[conflict.start_line : conflict.end_line])


def test_same_point_insertions_are_resolved_or_conflicted_as_a_region():
    base = ["head", "tail"]
    conflicts, output, _colors = MergeView._merge_lines(
        ["head", "left insert", "tail"],
        base,
        ["head", "right insert", "tail"],
    )
    assert len(conflicts) == 1
    assert not conflicts[0].resolved
    assert conflicts[0].left_lines == ["left insert"]
    assert conflicts[0].right_lines == ["right insert"]

    conflicts, output, _colors = MergeView._merge_lines(
        ["head", "same insert", "tail"],
        base,
        ["head", "same insert", "tail"],
    )
    assert output == ["head", "same insert", "tail"]
    assert len(conflicts) == 1
    assert conflicts[0].resolved


def test_resolving_conflicts_updates_following_line_offsets(qapp):
    left = ["head", "left one", "between", "left two", "tail"]
    base = ["head", "base one", "between", "base two", "tail"]
    right = ["head", "right one", "between", "right two", "tail"]
    conflicts, output, colors = MergeView._merge_lines(left, base, right)
    view = MergeView()
    view._pending_merge_paths = ("left", "base", "right")
    view._on_merge_computed(
        ("left", "base", "right"),
        _MergeComputation(left, base, right, conflicts, output, colors),
    )

    view._take_left()
    assert view._output_editor.toPlainText().splitlines() == [
        "head",
        "left one",
        "between",
        "<<<< CONFLICT >>>>",
        "left two",
        "====",
        "right two",
        "<<<< END >>>>",
        "tail",
    ]

    second_conflict = view._conflicts[1]
    assert second_conflict.start_line == 3
    view._go_next_conflict()
    view._take_right()
    assert view._output_editor.toPlainText().splitlines() == [
        "head",
        "left one",
        "between",
        "right two",
        "tail",
    ]
    assert view._conflict_label.text() == "Conflict 2 of 2 (0 unresolved)"


def test_load_merge_reads_sources_off_the_gui_thread(qapp, qtbot, tmp_path):
    left = tmp_path / "left.txt"
    base = tmp_path / "base.txt"
    right = tmp_path / "right.txt"
    left.write_text("before\nleft\n", encoding="utf-8")
    base.write_text("before\nbase\n", encoding="utf-8")
    right.write_text("before\nbase\n", encoding="utf-8")
    view = MergeView()
    qtbot.addWidget(view)

    view.load_merge(str(left), str(base), str(right))
    worker = view._merge_worker
    worker_finished = []
    worker.finished.connect(lambda: worker_finished.append(True))
    qtbot.waitUntil(
        lambda: view._output_editor.toPlainText() != ""
        and (bool(worker_finished) or worker.isFinished()),
        timeout=3000,
    )

    assert view._left_editor.toPlainText().splitlines() == ["before", "left"]
    assert view._base_editor.toPlainText().splitlines() == ["before", "base"]
    assert view._right_editor.toPlainText().splitlines() == ["before", "base"]
    assert view._output_editor.toPlainText().splitlines() == ["before", "left"]
    assert view._conflict_label.text() == "Conflict 1 of 1 (0 unresolved)"


def test_stale_merge_result_does_not_replace_a_newer_request(qapp):
    view = MergeView()
    current_paths = ("current-left", "current-base", "current-right")
    view._pending_merge_paths = current_paths
    view._output_editor.setPlainText("current output")

    view._on_merge_computed(
        ("stale-left", "stale-base", "stale-right"),
        _MergeComputation(
            ["stale"],
            ["base"],
            ["stale"],
            [],
            ["stale output"],
            [],
        ),
    )

    assert view._output_editor.toPlainText() == "current output"


def test_load_merge_reports_file_read_errors(qapp, qtbot, tmp_path):
    left = tmp_path / "missing-left.txt"
    base = tmp_path / "base.txt"
    right = tmp_path / "right.txt"
    base.write_text("base", encoding="utf-8")
    right.write_text("right", encoding="utf-8")
    view = MergeView()
    qtbot.addWidget(view)

    view.load_merge(str(left), str(base), str(right))
    worker = view._merge_worker
    worker_finished = []
    worker.finished.connect(lambda: worker_finished.append(True))
    qtbot.waitUntil(
        lambda: view._output_editor.toPlainText().startswith("Error reading files:")
        and (bool(worker_finished) or worker.isFinished()),
        timeout=3000,
    )

    assert "missing-left.txt" in view._output_editor.toPlainText()


def test_save_merged_writes_output_and_emits_saved_path(qapp, tmp_path, monkeypatch):
    view = MergeView()
    view._output_editor.setPlainText("merged\ncontent\n")
    destination = tmp_path / "merged.txt"
    saved = []
    view.merge_saved.connect(saved.append)
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(destination), "All Files (*)"),
    )

    view._save_merged()

    assert destination.read_text(encoding="utf-8") == "merged\ncontent\n"
    assert saved == [str(destination)]
