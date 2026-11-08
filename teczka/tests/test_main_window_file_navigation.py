"""Tests that difference navigation and counters operate on file entries."""

from __future__ import annotations

from PySide6.QtCore import QEvent
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


def test_navigation_and_file_count_exclude_directories_on_either_side(qapp, tmp_path):
    report = ScanReport(
        left=str(tmp_path / "lhs"),
        right=str(tmp_path / "rhs"),
        summary=ScanSummary(
            total=6,
            same=1,
            different=1,
            orphan_left=2,
            orphan_right=2,
            unchecked=0,
        ),
        entries=[
            DiffEntry(
                "left-folder",
                DiffStatus.ORPHAN_LEFT,
                FileSide(size=0, modified_unix=1, is_dir=True),
                None,
            ),
            DiffEntry(
                "left-folder/file.txt",
                DiffStatus.ORPHAN_LEFT,
                FileSide(size=4, modified_unix=1, is_dir=False),
                None,
            ),
            DiffEntry(
                "right-folder",
                DiffStatus.ORPHAN_RIGHT,
                None,
                FileSide(size=0, modified_unix=1, is_dir=True),
            ),
            DiffEntry(
                "right-folder/file.txt",
                DiffStatus.ORPHAN_RIGHT,
                None,
                FileSide(size=5, modified_unix=1, is_dir=False),
            ),
            DiffEntry(
                "type-conflict",
                DiffStatus.DIFFERENT,
                FileSide(size=8, modified_unix=1, is_dir=False),
                FileSide(size=0, modified_unix=1, is_dir=True),
            ),
            DiffEntry(
                "same.txt",
                DiffStatus.SAME,
                FileSide(size=4, modified_unix=1, is_dir=False),
                FileSide(size=4, modified_unix=1, is_dir=False),
            ),
        ],
    )
    window = MainWindow(
        AppConfig(
            cli_path="/bin/true",
            _config_file=str(tmp_path / "app-config.json"),
        )
    )
    window._profile_manager._path = tmp_path / "profiles.json"
    window._current_report = report
    window._current_session().report = report
    window._folder_view.set_tree(build_tree_with_options(report))

    files = window._get_all_file_entries()
    differences = window._get_diff_entries()
    visible_files = [
        node for node in window._folder_view.visible_nodes() if not node.is_dir
    ]

    assert {entry.path for entry in files} == {
        "left-folder/file.txt",
        "right-folder/file.txt",
        "same.txt",
    }
    assert {entry.path for entry in differences} == {
        "left-folder/file.txt",
        "right-folder/file.txt",
    }
    assert {node.path for node in visible_files} == {entry.path for entry in files}

    window._update_visible_status_summary()
    assert "visible folder rows" in window._integrated_status._status_label.toolTip()
    window._integrated_status.set_diff_position(0, len(differences))
    assert (
        "Folder entries are excluded"
        in window._integrated_status._diff_pos_label.toolTip()
    )

    window.close()
    window.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_navigation_and_folder_proxy_share_status_and_diff_mode_rules(qapp, tmp_path):
    entries = [
        DiffEntry(
            "same.txt",
            DiffStatus.SAME,
            FileSide(size=4, modified_unix=200, is_dir=False),
            FileSide(size=4, modified_unix=100, is_dir=False),
        ),
        DiffEntry(
            "left-newer.txt",
            DiffStatus.DIFFERENT,
            FileSide(size=4, modified_unix=200, is_dir=False),
            FileSide(size=4, modified_unix=100, is_dir=False),
        ),
        DiffEntry(
            "right-newer.txt",
            DiffStatus.DIFFERENT,
            FileSide(size=4, modified_unix=100, is_dir=False),
            FileSide(size=4, modified_unix=200, is_dir=False),
        ),
        DiffEntry(
            "left-only.txt",
            DiffStatus.ORPHAN_LEFT,
            FileSide(size=4, modified_unix=300, is_dir=False),
            None,
        ),
        DiffEntry(
            "right-only.txt",
            DiffStatus.ORPHAN_RIGHT,
            None,
            FileSide(size=4, modified_unix=300, is_dir=False),
        ),
        DiffEntry(
            "unchecked.txt",
            DiffStatus.UNCHECKED,
            FileSide(size=4, modified_unix=100, is_dir=False),
            FileSide(size=4, modified_unix=100, is_dir=False),
        ),
    ]
    report = ScanReport(
        left=str(tmp_path / "lhs"),
        right=str(tmp_path / "rhs"),
        summary=ScanSummary(
            total=len(entries),
            same=1,
            different=2,
            orphan_left=1,
            orphan_right=1,
            unchecked=1,
        ),
        entries=entries,
    )
    window = MainWindow(
        AppConfig(
            cli_path="/bin/true",
            _config_file=str(tmp_path / "app-config.json"),
        )
    )
    window._profile_manager._path = tmp_path / "profiles.json"
    window._current_report = report
    window._current_session().report = report
    window._folder_view.set_tree(build_tree_with_options(report))

    modes = (
        "show_differences",
        "show_no_orphans",
        "show_differences_no_orphans",
        "show_orphans",
        "show_left_newer",
        "show_right_newer",
        "show_left_newer_left_orphans",
        "show_right_newer_right_orphans",
        "show_left_orphans",
        "show_right_orphans",
    )
    pill_states = (
        (True, True, True, True),
        (False, True, False, True),
        (True, False, True, False),
    )
    for flags in pill_states:
        for mode in modes:
            window._filter_bar.diff_option_mode = mode
            window._on_filters_changed(*flags, False, "")
            tree_differences = {
                node.path
                for node in window._folder_view.visible_nodes()
                if not node.is_dir and node.status != DiffStatus.SAME
            }
            navigation_differences = {
                entry.path for entry in window._get_diff_entries()
            }
            assert navigation_differences == tree_differences, (flags, mode)

    window.close()
    window.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
