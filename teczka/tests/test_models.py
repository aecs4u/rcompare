"""Tests for teczka data models."""

from __future__ import annotations

from PySide6.QtCore import Qt

from teczka.state import AppState, CompareState, ActiveView
from teczka.models.undo_stack import OperationHistory, Operation
from teczka.models.comparison import TreeNode
from teczka.models.tree_model import (
    COL_LEFT_DATE,
    COL_LEFT_SIZE,
    COL_RIGHT_DATE,
    COL_RIGHT_SIZE,
    ComparisonTreeModel,
)
from teczka.utils.cli_bridge import DiffStatus


class TestAppState:
    def test_initial_state(self, qapp):
        state = AppState()
        assert state.compare_state == CompareState.IDLE
        assert state.active_view == ActiveView.HOME
        assert not state.comparing

    def test_compare_lifecycle(self, qapp):
        state = AppState()
        state.set_comparing(True)
        assert state.comparing
        assert state.compare_state == CompareState.COMPARING
        state.request_stop()
        assert state.stop_requested
        state.set_comparing(False)
        assert state.compare_state == CompareState.IDLE

    def test_path_management(self, qapp):
        state = AppState()
        state.left_path = "/tmp/left"
        state.right_path = "/tmp/right"
        assert state.left_path == "/tmp/left"
        assert state.right_path == "/tmp/right"

    def test_view_change(self, qapp):
        state = AppState()
        received = []
        state.view_changed.connect(lambda v: received.append(v))
        state.set_active_view(ActiveView.FOLDER)
        assert received == [ActiveView.FOLDER]

    def test_bookmarks(self, qapp):
        state = AppState()
        state.add_bookmark("test", "/left", "/right")
        assert len(state.config.bookmarks) >= 1


class TestOperationHistory:
    def test_push_and_undo(self):
        history = OperationHistory()
        op = Operation(op_type="copy", source_path="/a", dest_path="/b")
        history.push(op)
        assert history.can_undo
        undone = history.undo()
        assert undone == op
        assert not history.can_undo

    def test_redo(self):
        history = OperationHistory()
        op = Operation(op_type="copy", source_path="/a", dest_path="/b")
        history.push(op)
        history.undo()
        assert history.can_redo
        redone = history.redo()
        assert redone == op

    def test_max_history(self):
        history = OperationHistory()
        for i in range(60):
            history.push(Operation(op_type="copy", source_path=f"/{i}", dest_path=f"/{i}b"))
        assert len(history._operations) <= 50


def test_tree_model_tracks_large_node_count(qapp):
    root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
    for index in range(10_000):
        root.add_child(
            TreeNode(
                name=f"file-{index}.txt",
                path=f"file-{index}.txt",
                status=DiffStatus.DIFFERENT,
                is_dir=False,
            )
        )

    model = ComparisonTreeModel()
    model.set_tree(root)
    assert model.node_count == 10_001
    assert model.rowCount() == 10_000


def test_orphan_metadata_cells_explain_the_missing_side(qapp):
    root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
    right_only = TreeNode(
        name="right.txt",
        path="right.txt",
        status=DiffStatus.ORPHAN_RIGHT,
        is_dir=False,
        right_size=8,
        right_modified=1_700_000_000,
        parent=root,
    )
    left_only = TreeNode(
        name="left.txt",
        path="left.txt",
        status=DiffStatus.ORPHAN_LEFT,
        is_dir=False,
        left_size=4,
        left_modified=1_700_000_001,
        parent=root,
    )
    root.add_child(right_only)
    root.add_child(left_only)

    model = ComparisonTreeModel()
    model.set_tree(root)
    right_row = model.index(0, 0)
    left_row = model.index(1, 0)

    for col in (COL_LEFT_SIZE, COL_LEFT_DATE):
        cell = model.index(right_row.row(), col)
        assert model.data(cell, Qt.DisplayRole) == "—"
        assert model.data(cell, Qt.ToolTipRole) == "Not present on the left side."
        assert model.data(cell, Qt.ForegroundRole).isValid()
    for col in (COL_RIGHT_SIZE, COL_RIGHT_DATE):
        cell = model.index(left_row.row(), col)
        assert model.data(cell, Qt.DisplayRole) == "—"
        assert model.data(cell, Qt.ToolTipRole) == "Not present on the right side."

    assert model.data(model.index(right_row.row(), COL_RIGHT_SIZE), Qt.DisplayRole) == "8 B"
    assert model.data(model.index(left_row.row(), COL_LEFT_SIZE), Qt.DisplayRole) == "4 B"
