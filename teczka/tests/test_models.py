"""Tests for teczka data models."""

from __future__ import annotations

from teczka.state import AppState, CompareState, ActiveView
from teczka.models.undo_stack import OperationHistory, Operation
from teczka.models.comparison import TreeNode
from teczka.models.tree_model import (
    COL_EXTENSION,
    COL_PATH,
    COL_TYPE,
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


def test_tree_model_exposes_derived_file_columns(qapp):
    root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
    root.add_child(
        TreeNode(
            name="archive.tar.gz",
            path="exports/archive.tar.gz",
            status=DiffStatus.DIFFERENT,
            is_dir=False,
        )
    )

    model = ComparisonTreeModel()
    model.set_tree(root)

    assert model.index(0, COL_EXTENSION).data() == "gz"
    assert model.index(0, COL_TYPE).data() == "GZ file"
    assert model.index(0, COL_PATH).data() == "exports/archive.tar.gz"
