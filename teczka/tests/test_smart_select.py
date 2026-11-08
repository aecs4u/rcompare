"""Tests for the folder view's criteria-based bulk selection."""

from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from teczka.bulk_actions import quick_select_lhs
from teczka.dialogs.select_dialog import SelectDialog
from teczka.main_window import MainWindow
from teczka.models.comparison import build_tree_with_options
from teczka.utils.cli_bridge import (
    DiffEntry,
    DiffStatus,
    FileSide,
    ScanReport,
    ScanSummary,
)
from teczka.utils.config import AppConfig


def _report(tmp_path):
    return ScanReport(
        left=str(tmp_path / "lhs"),
        right=str(tmp_path / "rhs"),
        summary=ScanSummary(4, 1, 1, 1, 1, 0),
        entries=[
            DiffEntry(
                "same.txt",
                DiffStatus.SAME,
                FileSide(10, 100, False),
                FileSide(10, 100, False),
            ),
            DiffEntry(
                "different.txt",
                DiffStatus.DIFFERENT,
                FileSide(11, 100, False),
                FileSide(12, 100, False),
            ),
            DiffEntry(
                "left-only.txt",
                DiffStatus.ORPHAN_LEFT,
                FileSide(13, 100, False),
                None,
            ),
            DiffEntry(
                "right-only.txt",
                DiffStatus.ORPHAN_RIGHT,
                None,
                FileSide(14, 100, False),
            ),
        ],
    )


def test_smart_select_dialog_collects_criteria_and_quick_actions(qtbot):
    dialog = SelectDialog()
    qtbot.addWidget(dialog)
    scope = dialog.findChild(QLabel, "selectionScope")
    assert scope is not None
    assert "collapsed folders" in scope.text()
    dialog._status_identical.setChecked(False)
    dialog._status_different.setChecked(False)
    dialog._status_left_only.setChecked(True)
    dialog._status_right_only.setChecked(False)
    dialog._left_newer.setChecked(True)
    dialog._side_combo.setCurrentIndex(dialog._side_combo.findData("both"))
    dialog._pattern_edit.setText("*.txt")
    dialog._min_size_spin.setValue(2)
    dialog._max_size_spin.setValue(8)
    dialog._radio_deselect.setChecked(True)

    assert dialog.criteria == {
        "statuses": ["left_only"],
        "newer_sides": ["left"],
        "pattern": "*.txt",
        "min_size": 2,
        "max_size": 8,
        "mode": "deselect",
        "side": "both",
    }

    received = []
    dialog.quick_select.connect(received.append)
    button = dialog.findChild(QPushButton, "invertVisibleSelection")
    assert button is not None
    button.click()
    assert received == ["invert"]


def test_edit_action_selects_and_deselects_a_status_group(
    qapp: QApplication, monkeypatch, tmp_path
):
    report = _report(tmp_path)
    window = MainWindow(
        AppConfig(cli_path="/bin/true", _config_file=str(tmp_path / "config.json"))
    )
    window._current_report = report
    window._current_session().report = report
    window._folder_view.set_tree(build_tree_with_options(report))
    window._folder_view.set_filters(True, True, True, True)

    class QuickSignal:
        def connect(self, _callback):
            pass

    class DialogStub:
        criteria = {
            "statuses": ["left_only"],
            "newer_sides": [],
            "pattern": "*.txt",
            "min_size": 0,
            "max_size": 0,
            "mode": "select",
            "side": "left",
        }
        quick_select = QuickSignal()
        next_mode = "select"

        def __init__(self, _parent):
            self.criteria = {**self.criteria, "mode": self.next_mode}

        def exec(self):
            return True

    monkeypatch.setattr("teczka.bulk_actions.SelectDialog", DialogStub)

    window._act_smart_select_lhs.trigger()
    assert window._folder_view.selection_mode == "left"
    assert window._folder_view.selected_paths("left") == ["left-only.txt"]

    DialogStub.next_mode = "deselect"
    window._act_smart_select_lhs.trigger()
    assert window._folder_view.selected_paths("left") == []

    window.close()
    window.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_quick_select_all_invert_and_none_use_visible_rows(qapp, tmp_path):
    report = _report(tmp_path)
    window = MainWindow(
        AppConfig(cli_path="/bin/true", _config_file=str(tmp_path / "config.json"))
    )
    window._current_report = report
    window._current_session().report = report
    window._folder_view.set_tree(build_tree_with_options(report))
    window._folder_view.set_filters(True, True, True, True)
    expected = sorted(entry.path for entry in report.entries)

    quick_select_lhs(window, "all")
    assert window._folder_view.selected_paths("left") == expected

    quick_select_lhs(window, "all", side="both")
    assert window._folder_view.selection_mode == "both"
    assert window._folder_view.selected_paths("left") == expected
    assert window._folder_view.selected_paths("right") == expected

    quick_select_lhs(window, "all", side="right")
    quick_select_lhs(window, "invert", side="right")
    assert window._folder_view.selection_mode == "right"
    assert window._folder_view.selected_paths("right") == []

    quick_select_lhs(window, "all")
    quick_select_lhs(window, "invert")
    assert window._folder_view.selected_paths("left") == []

    quick_select_lhs(window, "all")
    quick_select_lhs(window, "none")
    assert window._folder_view.selected_paths("left") == []

    window.close()
    window.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_smart_select_can_select_newer_items_on_the_rhs(qapp, monkeypatch, tmp_path):
    report = _report(tmp_path)
    report.entries.extend(
        [
            DiffEntry(
                "left-newer.txt",
                DiffStatus.DIFFERENT,
                FileSide(4, 200, False),
                FileSide(4, 100, False),
            ),
            DiffEntry(
                "right-newer.txt",
                DiffStatus.DIFFERENT,
                FileSide(4, 100, False),
                FileSide(4, 200, False),
            ),
        ]
    )
    window = MainWindow(
        AppConfig(cli_path="/bin/true", _config_file=str(tmp_path / "config.json"))
    )
    window._current_report = report
    window._current_session().report = report
    window._folder_view.set_tree(build_tree_with_options(report))
    window._folder_view.set_filters(True, True, True, True)

    class QuickSignal:
        def connect(self, _callback):
            pass

    class DialogStub:
        criteria = {
            "statuses": ["different"],
            "newer_sides": ["left"],
            "pattern": "",
            "min_size": 0,
            "max_size": 0,
            "mode": "select",
            "side": "right",
        }
        quick_select = QuickSignal()

        def __init__(self, _parent):
            pass

        def exec(self):
            return True

    monkeypatch.setattr("teczka.bulk_actions.SelectDialog", DialogStub)
    window._act_smart_select_lhs.trigger()

    assert window._folder_view.selection_mode == "right"
    assert window._folder_view.selected_paths("right") == ["left-newer.txt"]
    assert window._folder_view.selected_paths("left") == []

    window.close()
    window.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_smart_select_can_select_orphans_on_both_panels(qapp, monkeypatch, tmp_path):
    report = _report(tmp_path)
    window = MainWindow(
        AppConfig(cli_path="/bin/true", _config_file=str(tmp_path / "config.json"))
    )
    window._current_report = report
    window._current_session().report = report
    window._folder_view.set_tree(build_tree_with_options(report))
    window._folder_view.set_filters(True, True, True, True)

    class QuickSignal:
        def connect(self, _callback):
            pass

    class DialogStub:
        criteria = {
            "statuses": ["right_only"],
            "newer_sides": [],
            "pattern": "",
            "min_size": 0,
            "max_size": 0,
            "mode": "select",
            "side": "both",
        }
        quick_select = QuickSignal()

        def __init__(self, _parent):
            pass

        def exec(self):
            return True

    monkeypatch.setattr("teczka.bulk_actions.SelectDialog", DialogStub)
    window._act_smart_select_lhs.trigger()

    assert window._folder_view.selection_mode == "both"
    assert window._folder_view.selected_paths("left") == ["right-only.txt"]
    assert window._folder_view.selected_paths("right") == ["right-only.txt"]

    window.close()
    window.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
