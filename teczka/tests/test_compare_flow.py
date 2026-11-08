"""Small GUI checks for folder selection and comparison feedback."""

from __future__ import annotations

import json
import os
import sys

import pytest
from teczka.main_window import MainWindow
from teczka.utils.config import AppConfig


def _window(tmp_path, cli_path=None):
    return MainWindow(
        AppConfig(
            cli_path=cli_path,
            _config_file=str(tmp_path / "teczka-flow-config.json"),
        )
    )


@pytest.mark.parametrize(
    ("side", "button_name"),
    (("left", "_left_browse_button"), ("right", "_right_browse_button")),
)
def test_browse_replaces_folder(qapp, tmp_path, monkeypatch, side, button_name):
    from teczka.widgets import compact_path_bar

    selected = str(tmp_path / "replacement")
    monkeypatch.setattr(
        compact_path_bar.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: selected,
    )
    window = _window(tmp_path)

    getattr(window._path_bar, button_name).click()

    assert getattr(window._path_bar, f"{side}_path") == selected
    assert getattr(window, f"_{side}_path") == selected
    window.close()


def test_invalid_folder_path_is_reported_before_scan(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, message: messages.append((title, message)),
    )
    window = _window(tmp_path)
    missing = str(tmp_path / "missing-folder")
    window._path_bar.left_path = missing
    window._path_bar.right_path = str(tmp_path)

    window._on_compare()

    assert messages and messages[0][0] == "Path Not Found"
    assert missing in messages[0][1]
    assert window._worker is None
    assert not window._integrated_status.progress_bar.isVisible()
    window.close()


def test_file_path_is_rejected_for_folder_comparison(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, message: messages.append((title, message)),
    )
    file_path = tmp_path / "input.txt"
    file_path.write_text("content", encoding="utf-8")
    window = _window(tmp_path)
    window._path_bar.left_path = str(file_path)
    window._path_bar.right_path = str(tmp_path)

    window._on_compare()

    assert messages and messages[0][0] == "Invalid Folder"
    assert str(file_path) in messages[0][1]
    assert window._worker is None
    assert not window._integrated_status.progress_bar.isVisible()
    window.close()


def test_cancel_stops_worker_and_hides_progress(qapp, tmp_path):
    class Worker:
        cancelled = False

        def cancel(self):
            self.cancelled = True

    window = _window(tmp_path)
    worker = Worker()
    window._worker = worker
    window._tb_cancel.setEnabled(True)
    window._tb_compare.setEnabled(False)
    window._integrated_status.show_progress(True)

    window._on_cancel()

    assert worker.cancelled
    assert not window._tb_cancel.isEnabled()
    assert window._tb_compare.isEnabled()
    assert window._integrated_status._status_label.text() == "Cancelled"
    assert not window._integrated_status.progress_bar.isVisible()
    window.close()


@pytest.mark.skipif(os.name == "nt", reason="uses an executable Python shebang")
def test_cancel_requests_graceful_cli_stop(qapp, qtbot, tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    fake_cli = tmp_path / "slow-cli"
    marker = tmp_path / "terminated"
    ready = tmp_path / "ready"
    fake_cli.write_text(
        f"#!{sys.executable}\n"
        "import signal\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n"
        "def stop(*_):\n"
        f"    Path({str(marker)!r}).write_text('terminated')\n"
        "    print('PROGRESS:{\"stage\":\"cancelled\",\"stage_index\":6,\"stage_count\":7,\"entries_done\":0,\"entries_total\":0,\"status\":\"cancelled\"}', file=sys.stderr, flush=True)\n"
        "    raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        f"Path({str(ready)!r}).write_text('ready')\n"
        "while True:\n"
        "    time.sleep(1)\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)
    window = _window(tmp_path, cli_path=str(fake_cli))
    qtbot.addWidget(window)
    window._path_bar.left_path = str(left)
    window._path_bar.right_path = str(right)

    window._on_compare()
    qtbot.waitUntil(lambda: window._worker.is_running(), timeout=3000)
    qtbot.waitUntil(ready.exists, timeout=3000)
    worker = window._worker
    window._on_cancel()
    qtbot.waitUntil(lambda: not worker.is_running(), timeout=3000)

    assert window._current_report is None
    assert window._status_summary.text() == "Cancelled"
    assert not window._integrated_status.progress_bar.isVisible()
    assert window._tb_compare.isEnabled()
    assert marker.read_text(encoding="utf-8") == "terminated"
    assert window._status_summary.text() == "Cancelled"
    assert window._integrated_status._status_label.text() == "Cancelled"
    assert window._integrated_status.progress_bar.isHidden()


@pytest.mark.skipif(os.name == "nt", reason="uses an executable Python shebang")
def test_copy_consumes_partial_json_report_on_nonzero_exit(
    qapp, qtbot, tmp_path
):
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    report = {
        "schema_version": "1.0.0",
        "summary": {
            "total_paths": 2,
            "copied": 1,
            "missing": 1,
            "skipped": 0,
            "failed": 0,
        },
        "items": [],
    }
    fake_cli = tmp_path / "partial-copy-cli"
    fake_cli.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"print({json.dumps(report)!r})\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)
    window = _window(tmp_path, cli_path=str(fake_cli))
    qtbot.addWidget(window)
    window._path_bar.left_path = str(left)
    window._path_bar.right_path = str(right)
    fallback_calls = []
    reports = []
    window._copy_paths_local_fallback = lambda *args, **kwargs: fallback_calls.append(
        (args, kwargs)
    )
    window._on_refresh = lambda: None

    window._copy_paths(["copied.txt", "missing.txt"], left_to_right=True)
    window._copy_worker.finished.connect(reports.append)
    qtbot.waitUntil(
        lambda: window.statusBar().currentMessage().startswith("Copied "),
        timeout=3000,
    )

    assert reports and reports[0]["summary"] == report["summary"]
    assert "1 missing" in window.statusBar().currentMessage()
    assert not fallback_calls


def test_copy_and_sync_cli_errors_do_not_retry_local_mutations(qapp, tmp_path):
    window = _window(tmp_path)
    copy_calls = []
    sync_calls = []
    window._copy_paths_local_fallback = lambda *args, **kwargs: copy_calls.append(
        (args, kwargs)
    )
    window._sync_local_fallback = lambda *args, **kwargs: sync_calls.append(
        (args, kwargs)
    )

    window._on_copy_error("invalid CLI report")
    assert window.statusBar().currentMessage().startswith("Copy failed:")
    window._on_sync_error("invalid CLI report")
    assert window.statusBar().currentMessage().startswith("Sync failed:")

    assert not copy_calls
    assert not sync_calls
    window.close()
