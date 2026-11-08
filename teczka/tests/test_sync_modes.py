"""Sync modes preserve unrelated target data and require matching scan settings."""

from __future__ import annotations

import pytest
from teczka.dialogs.sync_dialog import SyncDialog
from teczka.main_window import MainWindow
from teczka.utils.cli_bridge import ScanReport, ScanSummary
from teczka.utils.config import AppConfig
from teczka.utils.criteria import CompareCriteria


@pytest.mark.parametrize("option", ["file_filter", "criteria", "rules", "stale"])
def test_sync_requires_fresh_report_with_cli_supported_options(
    qapp, tmp_path, monkeypatch, option
):
    window = MainWindow(AppConfig(_config_file=str(tmp_path / "teczka.json")))
    session = window._current_session()
    window._left_path = "/left"
    window._right_path = "/right"
    window._current_report = ScanReport(
        left="/left",
        right="/right",
        summary=ScanSummary(
            total=0, same=0, different=0, orphan_left=0, orphan_right=0, unchecked=0
        ),
        entries=[],
    )
    if option == "file_filter":
        session.file_filter = "*.py"
    elif option == "criteria":
        session.criteria = CompareCriteria(mode="size")
    elif option == "rules":
        session.unimportant_text_rules = [
            {"pattern": "generated", "replacement": "", "description": ""}
        ]
    else:
        session.stale = True

    dialogs = []
    monkeypatch.setattr(
        window,
        "_load_sync_checkpoints",
        lambda dialog: dialog.set_recovery_checkpoints(
            [
                {
                    "id": "sync-123-456",
                    "left": "/left",
                    "right": "/right",
                    "status": "cancelled",
                    "completed_actions": 1,
                    "remaining_actions": 2,
                }
            ],
            "/left",
            "/right",
        ),
    )
    monkeypatch.setattr(SyncDialog, "exec", lambda dialog: dialogs.append(dialog) or 0)

    window._on_sync()

    assert len(dialogs) == 1
    assert not dialogs[0]._execute_btn.isEnabled()
    assert dialogs[0]._resume_button.isEnabled()
    if option == "stale":
        assert "out of date" in dialogs[0]._preview_edit.toPlainText().lower()
    else:
        assert "cannot apply" in dialogs[0]._preview_edit.toPlainText().lower()
    window.close()
    qapp.processEvents()
