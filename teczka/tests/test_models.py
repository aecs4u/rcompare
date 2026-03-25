"""Tests for teczka data models."""

from __future__ import annotations

from teczka.state import AppState, CompareState, ActiveView
from teczka.models.undo_stack import OperationHistory, Operation


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
