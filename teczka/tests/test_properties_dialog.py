"""Tests for the side-by-side filesystem properties dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QDialog, QGroupBox, QPushButton
from teczka.dialogs.properties_dialog import PropertiesDialog
from teczka.main_window import MainWindow
from teczka.utils.config import AppConfig


def test_properties_dialog_shows_both_sides_and_copies_path(qtbot, tmp_path):
    left = tmp_path / "left" / "report.txt"
    left.parent.mkdir()
    left.write_text("left data", encoding="utf-8")
    right = tmp_path / "right" / "report.txt"
    right.parent.mkdir()

    dialog = PropertiesDialog("report.txt", left, right, selected_side="right")
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Properties — report.txt"
    assert dialog._value_labels["left.availability"].text() == "Present"
    assert dialog._value_labels["left.type"].text() == "File"
    assert dialog._value_labels["left.size"].text() == "9 bytes"
    assert (
        dialog._value_labels["right.availability"].text()
        == "Missing on this side"
    )
    groups = dialog.findChildren(QGroupBox)
    assert [group.title() for group in groups] == ["LHS", "RHS (selected)"]

    copy_button = dialog.findChild(QPushButton, "propertiesCopyPath_left")
    assert copy_button is not None
    copy_button.click()
    assert QApplication.clipboard().text() == str(left)


def test_properties_dialog_reports_symlink_without_following_it(qtbot, tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("target", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target.name)

    dialog = PropertiesDialog("link.txt", link, tmp_path / "missing")
    qtbot.addWidget(dialog)

    assert dialog._value_labels["left.type"].text() == "Symbolic link"
    assert dialog._value_labels["left.link_target"].text() == target.name
    assert dialog._value_labels["left.size"].text() == f"{len(target.name)} bytes"


def test_main_window_properties_action_passes_both_roots(
    qapp: QApplication, monkeypatch, tmp_path
):
    left_root = tmp_path / "lhs"
    right_root = tmp_path / "rhs"
    left_root.mkdir()
    right_root.mkdir()
    (left_root / "nested").mkdir()
    (left_root / "nested" / "item.txt").write_text("lhs", encoding="utf-8")
    (right_root / "nested").mkdir()

    captured = {}

    class DialogStub:
        def __init__(
            self, relative_path, left_path, right_path, parent, *, selected_side
        ):
            captured.update(
                relative_path=relative_path,
                left_path=left_path,
                right_path=right_path,
                parent=parent,
                selected_side=selected_side,
            )

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("teczka.main_window.PropertiesDialog", DialogStub)
    window = MainWindow(
        AppConfig(_config_file=str(tmp_path / "teczka-test-config.json"))
    )
    window._left_path = str(left_root)
    window._right_path = str(right_root)

    window._show_item_attributes("nested/item.txt", "right")

    assert captured == {
        "relative_path": "nested/item.txt",
        "left_path": left_root / "nested" / "item.txt",
        "right_path": right_root / "nested" / "item.txt",
        "parent": window,
        "selected_side": "right",
    }
    window.close()
    qapp.processEvents()
