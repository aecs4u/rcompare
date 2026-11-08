"""CLI report compatibility tests for the scan JSON contract."""

from __future__ import annotations

import json

import pytest
from teczka.utils.cli_bridge import CliBridge, DiffStatus


@pytest.mark.parametrize("enveloped", [False, True])
def test_scan_parser_accepts_legacy_and_v2_reports(enveloped):
    report = {
        "schema_version": "1.1.0",
        "left": "/left",
        "right": "/right",
        "summary": {
            "total": 1,
            "same": 0,
            "different": 0,
            "orphan_left": 1,
            "orphan_right": 0,
            "unchecked": 0,
        },
        "warnings": [],
        "entries": [
            {
                "path": "only-left.txt",
                "status": "OrphanLeft",
                "left": {"size": 4, "modified_unix": 12, "is_dir": False},
                "right": None,
            }
        ],
    }
    if enveloped:
        report = {
            "schema_version": "2.0.0",
            "command": "scan",
            "status": "completed",
            "summary": report.pop("summary"),
            "data": report,
            "warnings": [],
        }

    parsed = CliBridge("rcompare_cli").parse_scan_report(json.dumps(report))

    assert parsed.left == "/left"
    assert parsed.right == "/right"
    assert parsed.summary.total == 1
    assert parsed.entries[0].path == "only-left.txt"
    assert parsed.entries[0].status is DiffStatus.ORPHAN_LEFT
    assert parsed.entries[0].left.size == 4
    assert parsed.entries[0].right is None


def test_sync_args_include_persistent_checkpoint_directory():
    args = CliBridge("rcompare_cli").build_sync_args(
        left="/left",
        right="/right",
        direction="left_to_right",
        dry_run=False,
        use_trash=True,
        checkpoint_dir="/data/app/sync-checkpoints",
    )

    assert args[0] == "sync"
    assert args[args.index("--checkpoint-dir") + 1] == "/data/app/sync-checkpoints"


def test_sync_args_include_resume_checkpoint_id():
    args = CliBridge("rcompare_cli").build_sync_args(
        left="/left",
        right="/right",
        direction="right_to_left",
        dry_run=False,
        use_trash=False,
        checkpoint_dir="/data/app/sync-checkpoints",
        resume_checkpoint="sync-123-456",
    )

    assert args[args.index("--resume-checkpoint") + 1] == "sync-123-456"


def test_sync_args_pass_mirror_mode_to_cli():
    args = CliBridge("rcompare_cli").build_sync_args(
        left="/left",
        right="/right",
        direction="mirror_right",
        dry_run=True,
        use_trash=True,
    )

    assert args[args.index("--direction") + 1] == "mirror_right"
    assert "--dry-run" in args


def test_sync_checkpoint_commands_are_built_with_the_app_storage_path():
    bridge = CliBridge("rcompare_cli")

    assert bridge.build_sync_checkpoints_args("/data/app/sync-checkpoints") == [
        "sync-checkpoints",
        "/data/app/sync-checkpoints",
    ]
    assert bridge.build_sync_discard_args("/data/app/sync-checkpoints", "sync-123-456") == [
        "sync-discard",
        "/data/app/sync-checkpoints",
        "sync-123-456",
    ]
