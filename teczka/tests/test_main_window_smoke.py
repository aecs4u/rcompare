"""End-to-end smoke test: MainWindow -> rcompare_cli -> status bar."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from teczka.main_window import MainWindow
from teczka.utils.config import AppConfig
from teczka.workers.comparison_worker import ProgressInfo

pytestmark = pytest.mark.skipif(
    shutil.which("rcompare_cli") is None, reason="rcompare_cli not installed"
)


def _wait(app: QApplication, cond, timeout: float = 20.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_compare_updates_visible_status(qapp, sample_dirs, tmp_path):
    left, right = sample_dirs
    window = MainWindow(AppConfig())
    window._settings.cache_dir = str(tmp_path / "hash-cache")
    window._path_bar.left_path = str(left)
    window._path_bar.right_path = str(right)
    window._on_compare()

    status = window._integrated_status
    assert _wait(qapp, lambda: "identical" in status._status_label.text())
    assert "Comparing" not in status._status_label.text()
    # 3 differing entries: diff.txt, only_left.txt, only_right.txt
    assert status._diff_pos_label.text() == "0/3"

    window._on_next_diff()
    assert status._diff_pos_label.text() == "1/3"


def test_unknown_progress_total_keeps_busy_indicator(qapp):
    window = MainWindow(AppConfig())
    bar = window._integrated_status.progress_bar

    window._on_progress_update(
        ProgressInfo(
            stage="scanning_left",
            stage_label="Scanning left source...",
            stage_index=0,
            stage_count=6,
            entries_done=0,
            entries_total=0,
            percent=0,
        )
    )
    assert bar.minimum() == 0
    assert bar.maximum() == 0
    assert bar.format() == "Scanning…"

    window._on_progress_update(
        ProgressInfo(
            stage="comparing",
            stage_label="Comparing files...",
            stage_index=2,
            stage_count=6,
            entries_done=5,
            entries_total=10,
            percent=50,
        )
    )
    assert bar.minimum() == 0
    assert bar.maximum() == 100
    assert bar.value() == 50

    window.close()
    qapp.processEvents()


def test_word_wrap_is_retained_per_session(qapp, tmp_path):
    from PySide6.QtWidgets import QPlainTextEdit

    window = MainWindow(
        AppConfig(_config_file=str(tmp_path / "teczka-test-config.json"))
    )
    left = window._text_view._left_editor
    right = window._text_view._right_editor

    window._act_word_wrap.setChecked(True)
    assert window._current_session().wrap_text
    assert left.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    assert right.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth

    window._on_new_session()
    assert window._current_session().wrap_text is False
    assert not window._act_word_wrap.isChecked()
    assert left.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap

    window._session_tabs.setCurrentIndex(0)
    qapp.processEvents()
    assert window._current_session().wrap_text
    assert window._act_word_wrap.isChecked()
    assert left.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    window._sync_config_from_runtime()
    assert window._config.filter_options["wrap_text"] is True

    window.close()
    qapp.processEvents()


def test_text_context_is_retained_per_session_and_config(qapp, tmp_path):
    config_path = tmp_path / "context-config.json"
    config = AppConfig(_config_file=str(config_path))
    window = MainWindow(config)

    window._text_context_actions[3].trigger()
    assert window._current_session().context_lines == 3
    assert window._text_view._context_lines == 3

    window._text_context_actions[None].trigger()
    assert window._current_session().context_lines is None
    assert window._text_view._context_lines is None

    window._text_context_actions[3].trigger()
    assert window._current_session().context_lines == 3

    window._on_new_session()
    assert window._current_session().context_lines is None
    assert window._text_context_actions[None].isChecked()
    assert window._text_view._context_lines is None

    window._session_tabs.setCurrentIndex(0)
    qapp.processEvents()
    assert window._current_session().context_lines == 3
    assert window._text_context_actions[3].isChecked()
    assert window._text_view._context_lines == 3

    window._sync_config_from_runtime()
    assert config.filter_options["context_lines"] == 3

    window.close()
    qapp.processEvents()
    saved_config = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved_config["filter_options"]["context_lines"] == 3


def test_text_context_cannot_be_hidden_while_editing(qapp, tmp_path):
    window = MainWindow(
        AppConfig(_config_file=str(tmp_path / "context-edit-config.json"))
    )
    window._text_view._edit_toggle.setChecked(True)

    window._text_context_actions[3].trigger()

    assert window._current_session().context_lines is None
    assert window._text_context_actions[None].isChecked()
    assert "Exit text editing" in window._integrated_status._status_label.text()

    window.close()
    qapp.processEvents()


def test_diff_counter_respects_filters_and_nav_wraps(qapp, sample_dirs, tmp_path):
    left, right = sample_dirs
    window = MainWindow(AppConfig())
    window._settings.cache_dir = str(tmp_path / "hash-cache")
    window._path_bar.left_path = str(left)
    window._path_bar.right_path = str(right)
    window._on_compare()
    status = window._integrated_status
    assert _wait(qapp, lambda: "identical" in status._status_label.text())

    # Only "Different" visible -> counter drops from 3 to 1.
    window._filter_bar.set_filters(False, True, False, False) if hasattr(
        window._filter_bar, "set_filters"
    ) else None
    window._on_filters_changed(False, True, False, False, False, "")
    qapp.processEvents()
    assert status._diff_pos_label.text().endswith("/1")

    # Previous from nothing selected wraps to the last entry without error.
    window._on_prev_diff()
    assert status._diff_pos_label.text() == "1/1"


def test_status_summary_tracks_active_folder_filters(qapp, sample_dirs, tmp_path):
    left, right = sample_dirs
    config = AppConfig(_config_file=str(tmp_path / "status-config.json"))
    window = MainWindow(config)
    window._settings.cache_dir = str(tmp_path / "hash-cache")
    window._path_bar.left_path = str(left)
    window._path_bar.right_path = str(right)
    window._on_compare()
    assert _wait(qapp, lambda: "identical" in window._status_summary.text())
    assert (
        window._status_summary.text()
        == "1 identical, 1 different, 1 left only, 1 right only"
    )

    window._on_filters_changed(False, True, False, False, False, "")
    assert (
        window._status_summary.text()
        == "0 identical, 1 different, 0 left only, 0 right only"
    )
    assert (
        window._integrated_status._status_label.text() == window._status_summary.text()
    )

    window.close()
    qapp.processEvents()


def test_wildcard_and_regex_search_filter_navigation_and_persist(qapp, sample_dirs):
    left, right = sample_dirs
    window, status = _compare(qapp, left, right)

    status.set_search_text("diff.*")
    status.set_search_mode("wildcard", emit=True)
    qapp.processEvents()
    assert status._diff_pos_label.text() == "0/1"
    assert [node.path for node in window._folder_view.visible_nodes()] == ["diff.txt"]

    status.set_search_text(r"^only_(left|right)\.txt$")
    status.set_search_mode("regex", emit=True)
    qapp.processEvents()
    assert status._diff_pos_label.text() == "0/2"
    assert {node.path for node in window._folder_view.visible_nodes()} == {
        "only_left.txt",
        "only_right.txt",
    }

    status.set_search_text("[")
    window._on_search_changed("[")
    assert window._folder_view.search_error
    assert status._diff_pos_label.text() == "0/0"
    assert status._search_edit.property("searchError") is True

    window._capture_session_state(window._active_session_index)
    assert window._current_session().search_text == "["
    assert window._current_session().search_mode == "regex"
    window._sync_config_from_runtime()
    assert window._config.filter_options["search_mode"] == "regex"

    window._on_new_session()
    assert status.search_mode == "contains"
    window._session_tabs.setCurrentIndex(0)
    qapp.processEvents()
    assert status.search_text == "["
    assert status.search_mode == "regex"
    assert window._folder_view.search_error

    window.close()
    qapp.processEvents()


def test_expand_folders_with_differences_in_comparison_window(qapp, tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    (left / "changed" / "deep").mkdir(parents=True)
    (right / "changed" / "deep").mkdir(parents=True)
    (left / "unchanged").mkdir()
    (right / "unchanged").mkdir()
    (left / "changed" / "deep" / "diff.txt").write_text("left")
    (right / "changed" / "deep" / "diff.txt").write_text("right")
    (left / "unchanged" / "same.txt").write_text("same")
    (right / "unchanged" / "same.txt").write_text("same")

    window, _status = _compare(qapp, left, right)
    view = window._folder_view
    tree = view._left_tree
    changed = view._proxy_model.mapFromSource(
        view._source_model.index_for_path("changed")
    )
    view.expand_folders_with_differences(tree, changed)

    deep = view._proxy_model.mapFromSource(
        view._source_model.index_for_path("changed/deep")
    )
    unchanged = view._proxy_model.mapFromSource(
        view._source_model.index_for_path("unchanged")
    )
    assert tree.isExpanded(changed)
    assert tree.isExpanded(deep)
    assert not tree.isExpanded(unchanged)

    window.close()
    qapp.processEvents()


def test_search_mode_restores_from_app_config(qapp, tmp_path):
    config = AppConfig(
        filter_options={"search_text": "*.py", "search_mode": "wildcard"},
        _config_file=str(tmp_path / "search-config.json"),
    )
    window = MainWindow(config)

    assert window._integrated_status.search_text == "*.py"
    assert window._integrated_status.search_mode == "wildcard"
    assert window._current_session().search_mode == "wildcard"

    window.close()
    qapp.processEvents()


def test_unimportant_text_rules_change_folder_summary_and_file_status(qapp, tmp_path):
    left, right = tmp_path / "lhs", tmp_path / "rhs"
    left.mkdir()
    right.mkdir()
    (left / "generated.txt").write_text("Build-ID=abc\nvalue=1\n")
    (right / "generated.txt").write_text("Build-ID=xyz\nvalue=1\n")
    config = AppConfig(_config_file=str(tmp_path / "rules-config.json"))
    window = MainWindow(config)
    window._current_session().unimportant_text_rules = [
        {
            "pattern": r"^Build-ID=.*$",
            "replacement": "Build-ID=<ignored>",
            "description": "Generated build identifier",
        }
    ]
    window._path_bar.left_path = str(left)
    window._path_bar.right_path = str(right)
    window._settings.cache_dir = str(tmp_path / "hash-cache")
    window._on_compare()

    assert _wait(qapp, lambda: window._current_report is not None)
    assert window._current_report.summary.same == 1
    assert window._current_report.summary.different == 0
    assert window._current_report.entries[0].status.value == "Same"
    assert (
        window._status_summary.text()
        == "1 identical, 0 different, 0 left only, 0 right only"
    )

    window.close()
    qapp.processEvents()


def test_unimportant_text_rules_are_restored_per_session(qapp, tmp_path):
    rule = {
        "pattern": r"^Build-ID=.*$",
        "replacement": "Build-ID=<ignored>",
        "description": "Generated build identifier",
    }
    config = AppConfig(
        filter_options={"unimportant_text_rules": [rule]},
        _config_file=str(tmp_path / "rules-config.json"),
    )
    window = MainWindow(config)
    assert window._current_session().unimportant_text_rules == [rule]
    assert window._act_unimportant_text_rules.text().endswith("(1)")

    window._on_new_session()
    assert window._current_session().unimportant_text_rules == []
    assert window._act_unimportant_text_rules.text().endswith("(0)")
    window._session_tabs.setCurrentIndex(0)
    qapp.processEvents()
    assert window._current_session().unimportant_text_rules == [rule]
    assert window._act_unimportant_text_rules.text().endswith("(1)")

    window._sync_config_from_runtime()
    assert window._config.filter_options["unimportant_text_rules"] == [rule]
    window.close()
    qapp.processEvents()


def _compare(qapp, left, right):
    window = MainWindow(AppConfig())
    window._settings.cache_dir = str(Path(left).parent / "hash-cache")
    window._path_bar.left_path = str(left)
    window._path_bar.right_path = str(right)
    window._on_compare()
    status = window._integrated_status
    assert _wait(qapp, lambda: "identical" in status._status_label.text())
    return window, status


def test_newer_files_filter(qapp, tmp_path):
    import os

    left, right = tmp_path / "l", tmp_path / "r"
    left.mkdir()
    right.mkdir()
    for name, (lt, rt) in {"a.txt": (2000, 1000), "b.txt": (1000, 2000)}.items():
        (left / name).write_text("left " + name)
        (right / name).write_text("right " + name)
        os.utime(left / name, (lt, lt))
        os.utime(right / name, (rt, rt))
    (left / "only_l.txt").write_text("x")

    window, status = _compare(qapp, left, right)
    assert status._diff_pos_label.text() == "0/3"

    window._newer_actions["show_left_newer"].trigger()
    qapp.processEvents()
    assert status._diff_pos_label.text() == "0/1"
    # The tree itself must be filtered, not just the counter.
    assert window._folder_view._proxy_model.rowCount() == 1
    window._on_next_diff()
    assert window._folder_view.selected_paths() == ["a.txt"]

    window._newer_actions["show_right_newer"].trigger()
    qapp.processEvents()
    window._on_next_diff()
    assert window._folder_view.selected_paths() == ["b.txt"]

    window._newer_actions["show_left_newer_left_orphans"].trigger()
    qapp.processEvents()
    assert status._diff_pos_label.text() == "0/2"

    window._newer_actions["show_differences"].trigger()
    qapp.processEvents()
    assert status._diff_pos_label.text() == "0/3"


def test_newer_status_bar_pills(qapp, tmp_path):
    import os

    left, right = tmp_path / "l", tmp_path / "r"
    left.mkdir()
    right.mkdir()
    for name, (lt, rt) in {"a.txt": (2000, 1000), "b.txt": (1000, 2000)}.items():
        (left / name).write_text("L" + name)
        (right / name).write_text("R" + name)
        os.utime(left / name, (lt, lt))
        os.utime(right / name, (rt, rt))

    window, status = _compare(qapp, left, right)
    status._pill_left_newer.setChecked(True)
    qapp.processEvents()
    assert status._diff_pos_label.text() == "0/1"
    assert window._newer_actions["show_left_newer"].isChecked()

    # Exclusive: checking the right pill releases the left one.
    status._pill_right_newer.setChecked(True)
    qapp.processEvents()
    assert not status._pill_left_newer.isChecked()
    assert window._folder_view._proxy_model.rowCount() == 1
    window._on_next_diff()
    assert window._folder_view.selected_paths() == ["b.txt"]

    status._pill_right_newer.setChecked(False)
    qapp.processEvents()
    assert status._diff_pos_label.text() == "0/2"

    # Menu choice is mirrored back onto the pills.
    window._newer_actions["show_left_newer"].trigger()
    assert status._pill_left_newer.isChecked()


def test_file_filter_applies_to_scan(qapp, tmp_path):
    left, right = tmp_path / "l", tmp_path / "r"
    for side in (left, right):
        (side / "build").mkdir(parents=True)
    (left / "a.py").write_text("1")
    (right / "a.py").write_text("2")
    (left / "b.tmp").write_text("x")
    (left / "build" / "x.o").write_text("x")

    window = MainWindow(AppConfig())
    window._current_session().file_filter = "*.py"
    window._settings.cache_dir = str(tmp_path / "hash-cache")
    window._sync_file_filter_ui()
    assert window._integrated_status._pill_file_filter.isChecked()
    window._path_bar.left_path = str(left)
    window._path_bar.right_path = str(right)
    window._on_compare()
    status = window._integrated_status
    assert _wait(qapp, lambda: "identical" in status._status_label.text())
    assert [e.path for e in window._current_report.entries] == ["a.py"]
    assert status._diff_pos_label.text() == "0/1"


def test_time_criteria_changes_scan_result(qapp, tmp_path):
    import os

    left, right = tmp_path / "l", tmp_path / "r"
    left.mkdir()
    right.mkdir()
    (left / "a.txt").write_text("AAAA")
    (right / "a.txt").write_text("BBBB")  # same size, different content
    os.utime(left / "a.txt", (1000, 1000))
    os.utime(right / "a.txt", (1001, 1001))

    from teczka.utils.criteria import CompareCriteria

    window = MainWindow(AppConfig())
    window._current_session().criteria = CompareCriteria("size_time", 2)
    window._settings.cache_dir = str(tmp_path / "hash-cache")
    window._path_bar.left_path = str(left)
    window._path_bar.right_path = str(right)
    window._on_compare()
    status = window._integrated_status
    assert _wait(qapp, lambda: "identical" in status._status_label.text())
    assert window._current_report.summary.same == 1
    assert window._current_report.summary.different == 0


def test_leaving_newer_mode_restores_filters(qapp, tmp_path):
    import os

    left, right = tmp_path / "l", tmp_path / "r"
    left.mkdir()
    right.mkdir()
    (left / "s.txt").write_text("same")
    (right / "s.txt").write_text("same")
    (left / "a.txt").write_text("L")
    (right / "a.txt").write_text("RR")
    os.utime(left / "a.txt", (2000, 2000))
    os.utime(right / "a.txt", (1000, 1000))

    window, status = _compare(qapp, left, right)
    fb = window._filter_bar
    assert fb.show_identical

    window._newer_actions["show_left_newer"].trigger()
    qapp.processEvents()
    assert not fb.show_identical
    # Switching between newer modes must not overwrite the remembered state.
    window._newer_actions["show_right_newer"].trigger()
    qapp.processEvents()

    window._newer_actions["show_differences"].trigger()
    qapp.processEvents()
    assert fb.show_identical and fb.show_different
    assert status._pill_identical.isChecked()
    assert window._folder_view._proxy_model.rowCount() == 2


def test_identical_pill_controls_identical_rows_by_default(qapp, tmp_path):
    left, right = tmp_path / "l", tmp_path / "r"
    left.mkdir()
    right.mkdir()
    (left / "s.txt").write_text("same")
    (right / "s.txt").write_text("same")
    (left / "d.txt").write_text("L")
    (right / "d.txt").write_text("RR")

    window, status = _compare(qapp, left, right)
    proxy = window._folder_view._proxy_model
    assert proxy.rowCount() == 2  # identical pill is ticked, so identical files show
    status._pill_identical.setChecked(False)
    qapp.processEvents()
    assert proxy.rowCount() == 1
    status._pill_identical.setChecked(True)
    qapp.processEvents()
    assert proxy.rowCount() == 2


class _StubSelect:
    folders = False

    def __init__(self, report, reason="", parent=None):
        self.reason = reason

    def exec(self):
        return True

    def include_folders(self):
        return _StubSelect.folders


class _StubDelete:
    dry = False

    def __init__(self, items, parent=None, **kw):
        _StubDelete.items = list(items)
        _StubDelete.warning = kw.get("warning", "")

    def setWindowTitle(self, _):
        pass

    def exec(self):
        return 1

    confirmed = True
    use_trash = False

    @property
    def dry_run(self):
        return _StubDelete.dry


def _bulk_fixture(tmp_path):
    left, right = tmp_path / "l", tmp_path / "r"
    for side in (left, right):
        (side / "same_dir").mkdir(parents=True)
        (side / "mixed").mkdir()
        (side / "same_dir" / "a.txt").write_text("a")
        (side / "mixed" / "ok.txt").write_text("ok")
        (side / "top.txt").write_text("top")
    (left / "mixed" / "diff.txt").write_text("L")
    (right / "mixed" / "diff.txt").write_text("RR")
    (left / "only_left.txt").write_text("x")
    return left, right


def _run_bulk(qapp, monkeypatch, left, right, *, folders, dry=False):
    from teczka import bulk_actions

    monkeypatch.setattr(bulk_actions, "IdenticalSelectDialog", _StubSelect)
    monkeypatch.setattr(bulk_actions, "DeleteDialog", _StubDelete)
    monkeypatch.setattr(
        bulk_actions.QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: bulk_actions.QMessageBox.StandardButton.Yes),
    )
    _StubSelect.folders = folders
    _StubDelete.dry = dry
    window, status = _compare(qapp, left, right)
    bulk_actions.select_identical_lhs(window)
    selected = window._folder_view.selected_paths("left")
    bulk_actions.delete_selected_lhs(window)
    _wait(qapp, lambda: False, timeout=0.5)
    return window, selected


def test_select_identical_and_delete_files_only(qapp, tmp_path, monkeypatch):
    left, right = _bulk_fixture(tmp_path)
    window, selected = _run_bulk(qapp, monkeypatch, left, right, folders=False)
    assert set(selected) == {"same_dir/a.txt", "mixed/ok.txt", "top.txt"}
    # identical files removed from LHS only; everything else untouched
    assert (
        not (left / "top.txt").exists() and not (left / "same_dir" / "a.txt").exists()
    )
    assert (left / "same_dir").is_dir()  # folder stays when only files are chosen
    assert (left / "mixed" / "diff.txt").exists() and (left / "only_left.txt").exists()
    assert (right / "top.txt").exists() and (right / "same_dir" / "a.txt").exists()
    assert _StubDelete.warning == ""


def test_select_identical_and_delete_with_folders(qapp, tmp_path, monkeypatch):
    left, right = _bulk_fixture(tmp_path)
    window, selected = _run_bulk(qapp, monkeypatch, left, right, folders=True)
    assert set(selected) == {"same_dir", "mixed/ok.txt", "top.txt"}
    assert not (left / "same_dir").exists()  # whole identical folder removed
    assert (left / "mixed" / "diff.txt").exists() and (left / "mixed").is_dir()
    assert (right / "same_dir" / "a.txt").exists()


def test_bulk_delete_dry_run_changes_nothing(qapp, tmp_path, monkeypatch):
    left, right = _bulk_fixture(tmp_path)
    _run_bulk(qapp, monkeypatch, left, right, folders=True, dry=True)
    assert (left / "same_dir" / "a.txt").exists() and (left / "top.txt").exists()


def test_folder_option_blocked_when_filter_active(qapp, tmp_path):
    from teczka.bulk_actions import _folders_blocked_reason

    window = MainWindow(AppConfig())
    assert _folders_blocked_reason(window) == ""
    window._current_session().file_filter = "*.txt"
    assert "disabled" in _folders_blocked_reason(window)


def test_columns_fit_contents_and_respect_manual_resize(qapp, tmp_path):
    left, right = tmp_path / "l", tmp_path / "r"
    left.mkdir()
    right.mkdir()
    long_name = (
        "a_really_quite_long_file_name_to_force_a_wide_name_column_0123456789.txt"
    )
    (left / long_name).write_text("L")
    (right / long_name).write_text("RR")
    (left / "x.txt").write_text("1")
    (right / "x.txt").write_text("22")

    window, status = _compare(qapp, left, right)
    window.resize(1400, 700)
    window.show()
    fv = window._folder_view
    _wait(qapp, lambda: False, timeout=0.4)  # let the debounced fit run
    lt = fv._left_tree
    from teczka.views.folder_view import COL_LEFT_DATE, COL_LEFT_SIZE, COL_NAME

    # Name column is wider than the old 240 px floor to fit the long name,
    # and Size/Date are wide enough for their text (not the 36 px minimum).
    assert lt.columnWidth(COL_NAME) > 240
    assert lt.columnWidth(COL_LEFT_SIZE) >= lt.fontMetrics().horizontalAdvance("1 B")
    assert lt.columnWidth(COL_LEFT_DATE) >= lt.fontMetrics().horizontalAdvance(
        "2026-11-08 12:00:00"
    )

    # A manual drag stops auto-fitting until "Fit Columns" is used.
    lt.header().resizeSection(COL_NAME, 300)
    manual = lt.columnWidth(COL_NAME)
    fv.set_filters(True, True, True, True)
    _wait(qapp, lambda: False, timeout=0.4)
    assert lt.columnWidth(COL_NAME) == manual
    fv.fit_columns_to_contents()
    assert lt.columnWidth(COL_NAME) != manual


def test_header_columns_show_file_attributes(qapp, tmp_path):
    import os
    import stat

    left, right = tmp_path / "l", tmp_path / "r"
    (left / "sub").mkdir(parents=True)
    (right / "sub").mkdir(parents=True)
    (left / "sub" / "script.PY").write_text("L")
    (right / "sub" / "script.PY").write_text("RR")
    os.chmod(left / "sub" / "script.PY", 0o640)
    os.chmod(right / "sub" / "script.PY", 0o600)
    (left / "only_left.txt").write_text("x")

    from teczka.models.tree_model import attr_column

    window, status = _compare(qapp, left, right)
    fv = window._folder_view
    model = fv._source_model
    lt, rt = fv._left_tree, fv._right_tree

    # Optional attribute columns are hidden until chosen.
    assert lt.isColumnHidden(attr_column("perms", "left"))
    fv._toggle_column_key("perms", True)
    fv._toggle_column_key("ext", True)
    fv._toggle_column_key("owner", True)
    assert not lt.isColumnHidden(attr_column("perms", "left"))
    assert lt.isColumnHidden(
        attr_column("perms", "right")
    )  # LHS tree shows LHS values only
    assert not rt.isColumnHidden(attr_column("perms", "right"))

    def text(path, key, side):
        idx = model.index_for_path(path)
        return model.index(idx.row(), attr_column(key, side), idx.parent()).data()

    assert text("sub/script.PY", "perms", "left") == stat.filemode(0o100640)
    assert text("sub/script.PY", "perms", "right") == stat.filemode(0o100600)
    assert text("sub/script.PY", "ext", "left") == "py"
    assert text("sub", "ext", "left") == "Folder"
    assert text("sub/script.PY", "owner", "left") == model._owner_name(
        "user", os.getuid()
    )
    # Missing side shows a dash, not another file's data.
    assert text("only_left.txt", "perms", "right") == "—"

    # Choice persists and can be restored / reset.
    saved = fv.column_widths()
    assert set(saved["visible"]) == {"size", "date", "perms", "ext", "owner"}
    fv.reset_columns()
    assert lt.isColumnHidden(attr_column("perms", "left"))
    fv.set_column_widths(saved)
    assert not lt.isColumnHidden(attr_column("owner", "left"))


def test_selection_mirrors_and_can_be_limited_to_one_panel(qapp, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    left, right = tmp_path / "l", tmp_path / "r"
    left.mkdir()
    right.mkdir()
    for name in ("a.txt", "b.txt"):
        (left / name).write_text("L" + name)
        (right / name).write_text("RR" + name)

    window, status = _compare(qapp, left, right)
    fv = window._folder_view
    lt, rt = fv._left_tree, fv._right_tree
    proxy = fv._proxy_model

    def rows(tree):
        return sorted(i.row() for i in tree.selectionModel().selectedRows())

    # Default: selecting on one panel selects on both.
    assert fv.selection_mode == "both"
    lt.selectionModel().select(
        proxy.index(0, 0),
        lt.selectionModel().SelectionFlag.ClearAndSelect
        | lt.selectionModel().SelectionFlag.Rows,
    )
    assert rows(lt) == [0] and rows(rt) == [0]
    rt.selectionModel().select(
        proxy.index(1, 0),
        rt.selectionModel().SelectionFlag.ClearAndSelect
        | rt.selectionModel().SelectionFlag.Rows,
    )
    assert rows(lt) == [1] and rows(rt) == [1]

    # Alt+Left limits to LHS: RHS cleared, later selections stay on the LHS.
    fv.toggle_selection_limit("left")
    assert fv.selection_mode == "left" and rows(rt) == [] and rows(lt) == [1]
    lt.selectionModel().select(
        proxy.index(0, 0),
        lt.selectionModel().SelectionFlag.ClearAndSelect
        | lt.selectionModel().SelectionFlag.Rows,
    )
    assert rows(lt) == [0] and rows(rt) == []
    rt.selectionModel().select(  # the other panel can't hold a selection now
        proxy.index(1, 0),
        rt.selectionModel().SelectionFlag.ClearAndSelect
        | rt.selectionModel().SelectionFlag.Rows,
    )
    assert rows(rt) == [] and rows(lt) == [0]
    assert fv.selected_paths() == ["a.txt"]

    # Switching to RHS-only, then repeating the key returns to both and re-mirrors.
    fv.toggle_selection_limit("right")
    assert fv.selection_mode == "right" and rows(lt) == []
    rt.selectionModel().select(
        proxy.index(1, 0),
        rt.selectionModel().SelectionFlag.ClearAndSelect
        | rt.selectionModel().SelectionFlag.Rows,
    )
    fv.toggle_selection_limit("right")
    assert fv.selection_mode == "both" and rows(lt) == [1] and rows(rt) == [1]

    # The keyboard shortcuts drive the same toggle.
    window.show()
    window.activateWindow()
    window._switch_view(1) if hasattr(window, "_switch_view") else None
    lt.setFocus()
    _wait(qapp, lambda: lt.hasFocus() and window.isActiveWindow(), timeout=2.0)
    if window.isActiveWindow():  # shortcut dispatch needs an active window
        QTest.keyClick(lt, Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)
        assert fv.selection_mode == "left"
        QTest.keyClick(lt, Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)
        assert fv.selection_mode == "both"
    else:  # offscreen platforms never activate: check the shortcuts are registered
        from PySide6.QtGui import QShortcut

        keys = {sc.key().toString() for sc in fv.findChildren(QShortcut)}
        assert {"Alt+Left", "Alt+Right"} <= keys
