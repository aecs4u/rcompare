"""MainWindow wiring for explicit sync resume."""

from __future__ import annotations

from teczka.main_window import MainWindow
from teczka.utils.cli_bridge import CliBridge
from teczka.utils.config import AppConfig


def test_resume_uses_the_saved_sync_roots_and_options(qapp, tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    window = MainWindow(AppConfig())
    window._left_path = str(left)
    window._right_path = str(right)
    window._cli_bridge = CliBridge("rcompare_cli")
    started = []
    window._start_cli_sync = lambda args, *, dry_run: started.append((args, dry_run))

    window._on_sync_resume_requested(
        {
            "id": "sync-123-456",
            "left": str(left),
            "right": str(right),
            "direction": "right_to_left",
            "delete_mode": "permanent",
            "conflict_policy": "left",
            "ignore_patterns": ["*.tmp"],
            "follow_symlinks": True,
            "verify_hashes": True,
            "no_verify_hashes": False,
            "strict": True,
        }
    )

    assert len(started) == 1
    args, dry_run = started[0]
    assert dry_run is False
    assert args[args.index("--direction") + 1] == "right_to_left"
    assert args[args.index("--delete-mode") + 1] == "permanent"
    assert args[args.index("--conflict") + 1] == "left"
    assert args[args.index("--ignore") + 1] == "*.tmp"
    assert "--follow-symlinks" in args
    assert "--verify-hashes" in args
    assert "--strict" in args
    assert args[args.index("--resume-checkpoint") + 1] == "sync-123-456"

    window.close()
    qapp.processEvents()
