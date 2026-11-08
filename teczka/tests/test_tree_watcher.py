"""Coverage for recursive watch setup, polling fallback, and auto-refresh state."""

from __future__ import annotations

import time

from teczka.dialogs.settings_dialog import SettingsDialog
from teczka.main_window import MainWindow, SessionState
from teczka.models.settings import ComparisonSettings
from teczka.models.comparison import TreeNode
from teczka.utils.cli_bridge import DiffStatus
from teczka.utils.config import AppConfig
from teczka.views.folder_view import FolderView
from teczka.workers.tree_watcher import RecursivePathWatcher


def _wait(qapp, predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_recursive_watcher_detects_nested_file_edits(qapp, tmp_path):
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    file_path = nested / "item.txt"
    file_path.write_text("before")
    watcher = RecursivePathWatcher(max_watched_paths=32)
    changes: list[str] = []
    coverage: list[str] = []
    watcher.changed.connect(changes.append)
    watcher.coverage_changed.connect(coverage.append)

    watcher.start([str(root)])
    assert _wait(qapp, lambda: any("Watching" in text for text in coverage))
    file_path.write_text("after edit")
    assert _wait(qapp, lambda: str(file_path) in changes)
    assert watcher.fallback_count == 0
    watcher.close()
    qapp.processEvents()


def test_recursive_watcher_polls_paths_the_platform_cannot_watch(qapp, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "item.txt"
    file_path.write_text("before")
    watcher = RecursivePathWatcher(max_watched_paths=0, poll_interval_ms=250)
    changes: list[str] = []
    coverage: list[str] = []
    watcher.changed.connect(changes.append)
    watcher.coverage_changed.connect(coverage.append)

    watcher.start([str(root)])
    assert _wait(qapp, lambda: any("polling" in text for text in coverage))
    assert watcher.fallback_count == 2  # root directory and its file
    file_path.write_text("after edit")
    assert _wait(qapp, lambda: str(file_path) in changes)
    watcher.close()
    qapp.processEvents()


def test_auto_refresh_is_opt_in_and_stale_state_offers_refresh(qapp, monkeypatch):
    window = MainWindow(AppConfig(cli_path="/missing/rcompare_cli"))
    session = window._current_session()
    session.report = object()
    session.settings.auto_refresh = True
    window._settings.auto_refresh = True
    window._sync_config_from_runtime()
    assert window._config.comparison_settings["auto_refresh"] is True
    called: list[bool] = []
    monkeypatch.setattr(window, "_on_refresh", lambda: called.append(True))
    window._auto_refresh_timer.setInterval(20)

    window._on_tree_changed("/tmp/changed.txt")
    assert session.stale
    assert "Refresh" in window._act_refresh.text()
    assert _wait(qapp, lambda: bool(called))
    window._tree_watcher.close()


def test_closing_active_session_stops_its_watcher(qapp, tmp_path):
    root = tmp_path / "watched"
    root.mkdir()
    window = MainWindow(AppConfig(cli_path="/missing/rcompare_cli"))
    window._sessions.append(SessionState(name="Session 2"))
    window._session_tab_bar.add_session("Session 2")
    window._session_tab_bar._tab_bar.setCurrentIndex(0)
    window._tree_watcher.start([str(root)])
    assert _wait(qapp, lambda: window._tree_watcher.candidate_count == 1)

    window._on_close_tab()
    assert len(window._sessions) == 1
    assert window._active_session_index == 0
    assert window._tree_watcher.candidate_count == 0
    window._tree_watcher.close()
    qapp.processEvents()


def test_folder_view_preserves_selection_and_scroll_after_tree_reset(qapp):
    root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
    for index in range(80):
        node = TreeNode(
            name=f"{index:03}.txt",
            path=f"{index:03}.txt",
            status=DiffStatus.DIFFERENT,
            is_dir=False,
            parent=root,
        )
        root.add_child(node)

    view = FolderView()
    view.resize(1000, 500)
    view.set_tree(root)
    view.show()
    view.expand_all()
    qapp.processEvents()
    view.select_path("050.txt")
    view.left_tree.verticalScrollBar().setValue(20)
    view.right_tree.verticalScrollBar().setValue(18)
    state = view.capture_view_state()

    view.left_tree.verticalScrollBar().setValue(0)
    view.right_tree.verticalScrollBar().setValue(0)
    view.restore_view_state(state)
    assert "050.txt" in view.selected_paths()
    assert view.left_tree.verticalScrollBar().value() == state["left_scroll"]
    assert view.right_tree.verticalScrollBar().value() == state["right_scroll"]
    view.close()


def test_settings_dialog_persists_auto_refresh_choice(qapp):
    settings = ComparisonSettings(auto_refresh=True)
    dialog = SettingsDialog(AppConfig(cli_path="/missing/rcompare_cli"), settings)
    assert dialog._auto_refresh_check.isChecked()
    dialog._auto_refresh_check.setChecked(False)
    assert not dialog.get_settings().auto_refresh
