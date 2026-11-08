"""Saved-run recovery controls in the synchronization dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox
from teczka.dialogs.sync_dialog import SyncDialog
from teczka.utils.cli_bridge import (
    DiffEntry,
    DiffStatus,
    FileSide,
    ScanReport,
    ScanSummary,
)


def _checkpoint(**overrides):
    checkpoint = {
        "id": "sync-123-456",
        "left": "/left",
        "right": "/right",
        "status": "cancelled",
        "completed_actions": 2,
        "remaining_actions": 3,
        "direction": "left_to_right",
        "delete_mode": "trash",
        "conflict_policy": "newest",
        "ignore_patterns": [],
        "follow_symlinks": False,
        "verify_hashes": False,
        "no_verify_hashes": False,
    }
    checkpoint.update(overrides)
    return checkpoint


def _sync_report():
    return ScanReport(
        left="/left",
        right="/right",
        summary=ScanSummary(
            total=3, same=0, different=1, orphan_left=1, orphan_right=1, unchecked=0
        ),
        entries=[
            DiffEntry(
                "left-only.txt",
                DiffStatus.ORPHAN_LEFT,
                FileSide(size=4, modified_unix=10, is_dir=False),
                None,
            ),
            DiffEntry(
                "right-only.txt",
                DiffStatus.ORPHAN_RIGHT,
                None,
                FileSide(size=5, modified_unix=11, is_dir=False),
            ),
            DiffEntry(
                "changed.txt",
                DiffStatus.DIFFERENT,
                FileSide(size=6, modified_unix=20, is_dir=False),
                FileSide(size=7, modified_unix=15, is_dir=False),
            ),
        ],
    )


def test_recovery_list_is_limited_to_the_current_folder_pair(qtbot):
    dialog = SyncDialog()
    qtbot.addWidget(dialog)

    dialog.set_recovery_checkpoints(
        [
            _checkpoint(),
            _checkpoint(id="sync-other", right="/other"),
            _checkpoint(id="sync-complete", status="completed"),
        ],
        "/left",
        "/right",
    )

    assert dialog._recovery_list.count() == 2
    assert dialog._resume_button.isEnabled()
    assert dialog._discard_button.isEnabled()
    assert "Resume rescans both folders" in dialog._recovery_status.text()

    dialog._recovery_list.setCurrentRow(1)
    assert not dialog._resume_button.isEnabled()
    assert dialog._discard_button.isEnabled()


def test_resume_emits_saved_options_and_closes_dialog(qtbot, monkeypatch):
    dialog = SyncDialog()
    qtbot.addWidget(dialog)
    checkpoint = _checkpoint()
    dialog.set_recovery_checkpoints([checkpoint], "/left", "/right")
    dialog.show()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )

    with qtbot.waitSignal(dialog.resume_requested, timeout=1000) as emitted:
        qtbot.mouseClick(dialog._resume_button, Qt.MouseButton.LeftButton)

    assert emitted.args == [checkpoint]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_discard_requires_confirmation_and_emits_checkpoint_id(qtbot, monkeypatch):
    dialog = SyncDialog()
    qtbot.addWidget(dialog)
    dialog.set_recovery_checkpoints([_checkpoint()], "/left", "/right")
    questions = []

    def confirm(*args):
        questions.append(args[2])
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)

    with qtbot.waitSignal(dialog.discard_requested, timeout=1000) as emitted:
        dialog._discard_selected()

    assert emitted.args == ["sync-123-456"]
    assert "partial destination files will remain" in questions[0].lower()


def test_update_and_mirror_previews_apply_distinct_orphan_policies(qtbot):
    dialog = SyncDialog()
    qtbot.addWidget(dialog)
    dialog.set_preview_source(_sync_report(), "/left", "/right")
    assert not dialog._trash_check.isEnabled()

    def actions_for(mode):
        index = dialog._mode_combo.findData(mode)
        assert index >= 0
        dialog._mode_combo.setCurrentIndex(index)
        return {(action.path, action.code) for action in dialog._plan_actions()}

    assert actions_for("update_right") == {
        ("left-only.txt", "COPY L->R"),
        ("changed.txt", "UPDATE R"),
    }
    assert actions_for("mirror_right") == {
        ("left-only.txt", "COPY L->R"),
        ("right-only.txt", "DELETE R"),
        ("changed.txt", "UPDATE R"),
    }
    assert dialog._trash_check.isEnabled()
    assert actions_for("update_left") == {
        ("right-only.txt", "COPY R->L"),
        ("changed.txt", "UPDATE L"),
    }
    assert actions_for("mirror_left") == {
        ("left-only.txt", "DELETE L"),
        ("right-only.txt", "COPY R->L"),
        ("changed.txt", "UPDATE L"),
    }
    assert actions_for("update_both") == {
        ("left-only.txt", "COPY L->R"),
        ("right-only.txt", "COPY R->L"),
        ("changed.txt", "COPY L->R"),
    }


def test_mirror_execution_requires_confirmation_when_deletes_are_planned(
    qtbot, monkeypatch
):
    dialog = SyncDialog()
    qtbot.addWidget(dialog)
    dialog.set_preview_source(_sync_report(), "/left", "/right")
    dialog._mode_combo.setCurrentIndex(dialog._mode_combo.findData("mirror_right"))
    dialog._dry_run_check.setChecked(False)
    dialog._trash_check.setChecked(False)
    answers = iter(
        [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes]
    )
    questions = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: (questions.append(_args[2]), next(answers))[1],
    )
    emitted = []
    dialog.sync_requested.connect(lambda *args: emitted.append(args))

    dialog._on_execute()
    assert emitted == []
    assert "permanently deletes" in questions[0].lower()

    dialog._on_execute()
    assert emitted == [("mirror_right", False, False)]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_mirror_without_previewed_deletes_still_warns_about_rescan(
    qtbot, monkeypatch
):
    dialog = SyncDialog()
    qtbot.addWidget(dialog)
    report = _sync_report()
    report.entries = [report.entries[0]]
    dialog.set_preview_source(report, "/left", "/right")
    dialog._mode_combo.setCurrentIndex(dialog._mode_combo.findData("mirror_right"))
    dialog._dry_run_check.setChecked(False)
    questions = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: (questions.append(args[2]), QMessageBox.StandardButton.No)[1],
    )

    dialog._on_execute()

    assert "new target-only items may be removed" in questions[0].lower()
    assert dialog.result() == QDialog.DialogCode.Rejected
