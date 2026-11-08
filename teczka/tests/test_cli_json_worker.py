"""Tests for structured results from asynchronous CLI mutations."""

from __future__ import annotations

import json
import sys

from teczka.workers.comparison_worker import CliJsonWorker


def test_cli_json_worker_parses_a_cancelled_sync_report(qtbot):
    report = {
        "schema_version": "2.0.0",
        "command": "sync",
        "status": "cancelled",
        "summary": {
            "total_actions": 2,
            "completed": 1,
            "remaining": 1,
            "cancelled": True,
            "copied": 1,
            "updated": 0,
            "deleted": 0,
            "skipped": 0,
            "failed": 0,
        },
        "data": {"actions": []},
        "warnings": [],
    }
    payload = json.dumps(report)
    script = (
        "import json,sys; "
        f"print(json.dumps(json.loads({payload!r}))); "
        "sys.exit(130)"
    )
    worker = CliJsonWorker()
    received = []
    worker.finished.connect(received.append)

    worker.start(
        [sys.executable, "-c", script],
        accepted_exit_codes=(0, 1, 130),
    )
    qtbot.waitUntil(lambda: bool(received), timeout=5000)

    assert received[0]["status"] == "cancelled"
    assert received[0]["summary"]["completed"] == 1
    assert received[0]["summary"]["remaining"] == 1
    assert received[0]["summary"]["cancelled"] is True
