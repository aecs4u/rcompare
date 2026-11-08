"""Standalone file-pair comparison workflow tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import teczka.main_window as main_window_module
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QDialog
from teczka.dialogs.file_pair_dialog import FilePairDialog
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
from teczka.utils.criteria import CompareCriteria
from teczka.utils.source_paths import split_source_file
from teczka.views.text_view import TextView


def _wait(app: QApplication, condition, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_file_pair_dialog_validates_both_files(qapp, tmp_path):
    left = tmp_path / "original.txt"
    right = tmp_path / "renamed.md"
    left.write_text("left")
    right.write_text("right")

    dialog = FilePairDialog()
    assert not dialog._ok_button.isEnabled()
    dialog._left_path.setText(str(left))
    assert not dialog._ok_button.isEnabled()
    dialog._right_path.setText(str(right))
    assert dialog._ok_button.isEnabled()
    assert dialog.selected_files() == (left, right)

    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    qapp.processEvents()


def test_file_pair_dialog_accepts_supported_remote_file_urls(qapp):
    dialog = FilePairDialog()
    left = "s3://left-bucket/reports/old.txt"
    right = "sftp://files.example.test/archive/new.md"

    dialog._left_path.setText(left)
    dialog._right_path.setText(right)

    assert dialog._ok_button.isEnabled()
    assert dialog.selected_files() == (left, right)
    dialog._left_path.setText("s3://user:secret@left-bucket/reports/old.txt")
    assert not dialog._ok_button.isEnabled()
    dialog.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize(
    ("source", "root", "relative"),
    [
        ("s3://bucket/folder/report.csv", "s3://bucket/folder", "report.csv"),
        ("sftp://host/a/b/image.png", "sftp://host/a/b", "image.png"),
        ("davs://host/file.bin", "davs://host", "file.bin"),
    ],
)
def test_split_source_file_separates_remote_root_and_name(source, root, relative):
    assert split_source_file(source) == (root, relative)


def test_split_source_file_rejects_remote_folders_and_unsafe_urls():
    for source in (
        "s3://bucket/folder/",
        "s3://user:secret@bucket/file.txt",
        "https://host/file.txt",
        "s3://bucket/file.txt?token=secret",
    ):
        with pytest.raises(ValueError):
            split_source_file(source)


def test_file_only_comparison_opens_and_reuses_text_tab(qapp, tmp_path, monkeypatch):
    left = tmp_path / "left" / "old-name.txt"
    right = tmp_path / "right" / "new-name.md"
    left.parent.mkdir()
    right.parent.mkdir()
    left.write_text("first line\nleft value\n")
    right.write_text("first line\nright value\n")

    window = MainWindow(AppConfig())

    class AcceptedPairDialog:
        DialogCode = FilePairDialog.DialogCode

        def __init__(self, _parent):
            pass

        def exec(self):
            return self.DialogCode.Accepted

        def selected_files(self):
            return left, right

    monkeypatch.setattr(main_window_module, "FilePairDialog", AcceptedPairDialog)
    window._act_compare_files.trigger()
    view = window._view_stack.currentWidget()
    assert isinstance(view, TextView)
    assert view._left_path == str(left)
    assert view._right_path == str(right)
    assert "old-name.txt" in view._left_path_label.text()
    assert "new-name.md" in view._right_path_label.text()
    assert window._current_report is None
    assert window._path_bar.left_path == ""
    assert window._path_bar.right_path == ""
    assert _wait(qapp, lambda: view._has_comparison_data)
    assert "left value" in view._left_editor.toPlainText()
    assert "right value" in view._right_editor.toPlainText()

    count = window._view_stack.count()
    assert window._open_file_pair(left, right)
    assert window._view_stack.count() == count
    window.close()
    qapp.processEvents()


def test_dropping_two_files_starts_file_only_comparison(qapp, tmp_path, monkeypatch):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("left")
    right.write_text("right")

    window = MainWindow(AppConfig())
    opened: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        window,
        "_open_file_pair",
        lambda lhs, rhs, **kwargs: opened.append((Path(lhs), Path(rhs))) or True,
    )
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(left)), QUrl.fromLocalFile(str(right))])
    event = QDropEvent(
        QPointF(0, 0),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    window.dropEvent(event)

    assert event.isAccepted()
    assert opened == [(left, right)]
    assert window._path_bar.left_path == ""
    assert window._path_bar.right_path == ""
    window.close()
    qapp.processEvents()


def test_file_only_comparison_rejects_missing_or_unreadable_files(
    qapp, tmp_path, monkeypatch
):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("left")
    right.write_text("right")
    missing = tmp_path / "missing.txt"

    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "information",
        lambda _parent, title, message: messages.append((title, message)),
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        lambda _parent, title, message: messages.append((title, message)),
    )
    window = MainWindow(AppConfig())

    assert not window._open_file_pair(left, missing)
    assert messages[-1][0] == "File Compare Not Available"

    original_open = Path.open

    def deny_right_file(path: Path, *args, **kwargs):
        if path == right:
            raise PermissionError("access denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_right_file)
    assert not window._open_file_pair(left, right)
    assert messages[-1][0] == "File Cannot Be Read"
    assert "access denied" in messages[-1][1]
    assert window._view_stack.count() == 6

    window.close()
    qapp.processEvents()


@pytest.mark.parametrize(
    ("left_contents", "right_contents", "initial", "expected"),
    [
        (b"same-size-left", b"same-size-rght", DiffStatus.SAME, DiffStatus.DIFFERENT),
        (b"same content", b"same content", DiffStatus.DIFFERENT, DiffStatus.SAME),
    ],
)
def test_opening_file_recompares_content_and_updates_folder_status(
    qapp, qtbot, tmp_path, monkeypatch, left_contents, right_contents, initial, expected
):
    left_root = tmp_path / "left"
    right_root = tmp_path / "right"
    left_root.mkdir()
    right_root.mkdir()
    left_file = left_root / "nested" / "sample.txt"
    right_file = right_root / "nested" / "sample.txt"
    left_file.parent.mkdir()
    right_file.parent.mkdir()
    left_file.write_bytes(left_contents)
    right_file.write_bytes(right_contents)

    entry = DiffEntry(
        path="nested/sample.txt",
        status=initial,
        left=FileSide(len(left_contents), 1_700_000_000, False),
        right=FileSide(len(right_contents), 1_700_000_000, False),
    )
    directory = DiffEntry(
        path="nested",
        status=DiffStatus.SAME,
        left=FileSide(0, 1_700_000_000, True),
        right=FileSide(0, 1_700_000_000, True),
    )
    report = ScanReport(
        left=str(left_root),
        right=str(right_root),
        summary=ScanSummary(
            total=2,
            same=int(initial == DiffStatus.SAME) + 1,
            different=int(initial == DiffStatus.DIFFERENT),
            orphan_left=0,
            orphan_right=0,
            unchecked=0,
        ),
        entries=[directory, entry],
    )
    window = MainWindow(AppConfig())
    qtbot.addWidget(window)
    session = window._current_session()
    session.left_path = str(left_root)
    session.right_path = str(right_root)
    session.criteria = CompareCriteria(mode="size_time")
    session.report = report
    window._left_path = str(left_root)
    window._right_path = str(right_root)
    window._current_report = report
    window._folder_view.set_tree(build_tree_with_options(report))

    status_changes = []
    window._folder_view.source_model.dataChanged.connect(
        lambda start, _end, _roles: status_changes.append(start.data(Qt.UserRole))
    )
    assert (
        window._folder_view.source_model.update_entry_status(
            "nested/sample.txt", initial
        )
        == initial
    )

    assert window._open_file_pair(
        left_file, right_file, relative_path="nested/sample.txt"
    )
    qtbot.waitUntil(lambda: entry.status == expected, timeout=3000)

    model = window._folder_view.source_model
    file_index = model.index_for_path("nested/sample.txt")
    folder_index = model.index_for_path("nested")
    assert model.data(file_index, Qt.UserRole) == expected
    assert model.data(folder_index, Qt.UserRole) == expected
    assert entry.status == expected
    assert report.summary.same == (1 if expected == DiffStatus.DIFFERENT else 2)
    assert report.summary.different == (1 if expected == DiffStatus.DIFFERENT else 0)
    assert status_changes

    window.close()
    qapp.processEvents()
