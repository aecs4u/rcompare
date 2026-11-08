"""Remote source validation, capability gating, and preview tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import teczka.main_window as main_window_module
from PySide6.QtWidgets import QMessageBox
from teczka.dialogs.file_pair_dialog import FilePairDialog
from teczka.main_window import MainWindow
from teczka.utils.cli_bridge import CliBridge
from teczka.utils.config import AppConfig
from teczka.utils.source_paths import (
    is_remote_source,
    local_source_paths,
    source_log_label,
    source_scheme,
    validate_remote_source,
)
from teczka.views.folder_view import _read_preview_pair
from teczka.views.hex_view import HexView
from teczka.views.image_view import ImageView
from teczka.views.table_view import TableView
from teczka.widgets.breadcrumb_bar import BreadcrumbBar
from teczka.workers.comparison_worker import ComparisonWorker
from teczka.workers.remote_file_pair_worker import RemoteFilePairWorker


@pytest.mark.parametrize(
    ("source", "scheme"),
    [
        ("s3://archive-bucket/outputs", "s3"),
        ("sftp://files.example.test/data", "sftp"),
        ("dav://files.example.test/remote", "dav"),
        ("davs://files.example.test/remote", "davs"),
    ],
)
def test_remote_source_urls_are_validated_without_local_filesystem_checks(
    source, scheme
):
    assert is_remote_source(source)
    assert source_scheme(source) == scheme
    assert validate_remote_source(source) is None
    assert local_source_paths([source, "/tmp/local-root"]) == ("/tmp/local-root",)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("sftp://user:password@files.example.test/data", "credentials"),
        ("https://files.example.test/data?token=secret", "query string"),
        ("https://files.example.test/data#secret", "fragment"),
        ("s3:///missing-host", "scheme and host"),
    ],
)
def test_remote_source_rejects_inline_auth_material_and_malformed_urls(source, message):
    error = validate_remote_source(source)
    assert error is not None
    assert message in error
    assert "secret" not in error
    assert "password" not in error


def test_remote_source_log_label_hides_path_and_credentials():
    label = source_log_label("sftp://user:password@files.example.test/private/token")
    assert label == "sftp://files.example.test/…"
    assert "user" not in label
    assert "password" not in label
    assert "private" not in label
    assert "token" not in label


def test_breadcrumb_bar_preserves_remote_url_and_hides_credentials(qapp):
    bar = BreadcrumbBar()
    bar.path = "sftp://user:password@files.example.test/share"
    assert bar.path == "sftp://user:password@files.example.test/share"
    assert BreadcrumbBar._split_path(bar.path)[0] == (
        "sftp://files.example.test",
        "sftp://files.example.test",
    )


def _write_fake_cli(tmp_path, *, schemes: list[str]):
    script = tmp_path / "fake-rcompare-cli"
    report = {
        "left": "s3://bucket/left",
        "right": "/tmp/right",
        "summary": {
            "total": 1,
            "same": 1,
            "different": 0,
            "orphan_left": 0,
            "orphan_right": 0,
            "unchecked": 0,
        },
        "entries": [
            {
                "path": "same.txt",
                "status": "Same",
                "left": {"size": 5, "modified_unix": 0, "is_dir": False},
                "right": {"size": 5, "modified_unix": 0, "is_dir": False},
            }
        ],
    }
    script.write_text(
        "#!" + sys.executable + "\n"
        "import json, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "if args[0] == 'capabilities':\n"
        f"    print(json.dumps({{'source_schemes': {schemes!r}}}))\n"
        "elif args[0] == 'scan':\n"
        f"    print(json.dumps({report!r}))\n"
        "elif args[0] == 'read':\n"
        "    side = args[args.index('--side') + 1]\n"
        "    output = pathlib.Path(args[args.index('--out') + 1])\n"
        "    output.parent.mkdir(parents=True, exist_ok=True)\n"
        "    output.write_bytes((side + ' remote sample').encode())\n"
    )
    script.chmod(0o755)
    return script


def test_remote_scan_requires_advertised_scheme_before_running_scan(qtbot, tmp_path):
    executable = _write_fake_cli(tmp_path, schemes=["s3"])
    worker = ComparisonWorker(CliBridge(str(executable)))
    with qtbot.waitSignal(worker.finished, timeout=5_000) as completed:
        worker.start_scan("s3://bucket/left", "/tmp/right")
    result = completed.args[0]
    assert result.report.left == "s3://bucket/left"
    assert result.report.summary.total == 1


def test_main_window_scans_remote_roots_and_disables_local_mutations(
    qapp, qtbot, tmp_path, monkeypatch
):
    executable = _write_fake_cli(tmp_path, schemes=["s3"])
    window = MainWindow(AppConfig(cli_path=str(executable)))
    window._profile_manager._path = tmp_path / "profiles.json"
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, title, message: messages.append((title, message)),
    )
    window._path_bar.left_path = "s3://bucket/left"
    window._path_bar.right_path = "s3://other-bucket/right"

    window._on_compare()
    qtbot.waitUntil(
        lambda: window._current_report is not None or bool(messages), timeout=5_000
    )
    assert not messages, messages

    assert window._current_report.left == "s3://bucket/left"
    assert window._tree_watcher._roots == ()
    assert not window._act_copy_lr.isEnabled()
    assert not window._act_sync.isEnabled()
    assert not window._folder_view._local_operations_enabled
    window.close()


def test_remote_scan_fails_clearly_when_cli_is_stale(qtbot, tmp_path):
    executable = _write_fake_cli(tmp_path, schemes=[])
    worker = ComparisonWorker(CliBridge(str(executable)))
    with qtbot.waitSignal(worker.error, timeout=5_000) as failed:
        worker.start_scan("s3://bucket/left", "/tmp/right")
    assert "does not support remote scheme(s): s3" in failed.args[0]


def test_remote_folder_preview_uses_cli_read_adapter_and_size_limit(tmp_path):
    executable = tmp_path / "fake-read-cli"
    executable.write_text(
        "#!" + sys.executable + "\n"
        "import pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "pathlib.Path(args[args.index('--out') + 1]).write_bytes(b'remote text')\n"
    )
    executable.chmod(0o755)

    left, right = _read_preview_pair(
        "s3://bucket/left",
        "/path/that/does/not/exist",
        "sample.txt",
        str(executable),
        11,
        None,
    )
    assert left == "remote text"
    assert right == "(not present on this side)"

    skipped, _ = _read_preview_pair(
        "s3://bucket/left",
        "/path/that/does/not/exist",
        "large.txt",
        str(executable),
        65_537,
        None,
    )
    assert "preview skipped" in skipped


def test_remote_file_activation_opens_staged_text_pair(qtbot, tmp_path):
    executable = _write_fake_cli(tmp_path, schemes=["s3"])
    window = MainWindow(AppConfig(cli_path=str(executable)))
    window._profile_manager._path = tmp_path / "profiles.json"
    window._left_path = "s3://left-bucket/private/left"
    window._right_path = "s3://right-bucket/private/right"

    window._on_file_activated("folder/sample.txt", False)

    qtbot.waitUntil(lambda: bool(window._file_compare_tabs), timeout=5_000)
    pair_key, index = next(iter(window._file_compare_tabs.items()))
    view = window._view_stack.widget(index)
    qtbot.waitUntil(
        lambda: view._has_comparison_data
        and not Path(view._left_path).exists()
        and not Path(view._right_path).exists(),
        timeout=5_000,
    )

    assert pair_key.startswith("remote|")
    assert "left remote sample" in view._left_editor.toPlainText()
    assert "right remote sample" in view._right_editor.toPlainText()
    assert view._left_path_label.text() == "s3://left-bucket/…/sample.txt"
    assert view._right_path_label.text() == "s3://right-bucket/…/sample.txt"
    assert "teczka-remote-pair" not in view._left_path_label.text()
    window.close()


@pytest.mark.parametrize(
    ("left_remote", "right_remote"),
    [(True, True), (True, False), (False, True)],
)
def test_standalone_file_pair_stages_remote_or_mixed_sources_with_different_names(
    qtbot, tmp_path, monkeypatch, left_remote, right_remote
):
    executable = tmp_path / "remote-file-pair-cli"
    executable.write_text(
        "#!" + sys.executable + "\n"
        "import json, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "if args[0] == 'capabilities':\n"
        "    print(json.dumps({'schema_version': '2.0.0', 'data': "
        "{'source_schemes': ['s3']}}))\n"
        "else:\n"
        "    side = args[args.index('--side') + 1]\n"
        "    rel = args[args.index('--path') + 1]\n"
        "    output = pathlib.Path(args[args.index('--out') + 1])\n"
        "    output.parent.mkdir(parents=True, exist_ok=True)\n"
        "    output.write_text(side + ':' + rel)\n"
    )
    executable.chmod(0o755)
    window = MainWindow(AppConfig(cli_path=str(executable)))
    window._profile_manager._path = tmp_path / "profiles.json"
    left_local = tmp_path / "local-left" / "old-name.txt"
    right_local = tmp_path / "local-right" / "new-name.md"
    if not left_remote:
        left_local.parent.mkdir()
        left_local.write_text("local left")
    if not right_remote:
        right_local.parent.mkdir()
        right_local.write_text("local right")
    left_source = (
        "s3://left-bucket/private/old-name.txt"
        if left_remote
        else str(left_local)
    )
    right_source = (
        "s3://right-bucket/archive/new-name.md"
        if right_remote
        else str(right_local)
    )

    class AcceptedPairDialog:
        DialogCode = FilePairDialog.DialogCode

        def __init__(self, _parent):
            pass

        def exec(self):
            return self.DialogCode.Accepted

        def selected_files(self):
            return left_source, right_source

    monkeypatch.setattr(main_window_module, "FilePairDialog", AcceptedPairDialog)

    window._act_compare_files.trigger()
    qtbot.waitUntil(lambda: bool(window._file_compare_tabs), timeout=5_000)
    pair_key, index = next(iter(window._file_compare_tabs.items()))
    view = window._view_stack.widget(index)
    qtbot.waitUntil(
        lambda: view._has_comparison_data
        and not Path(view._left_path).exists()
        and not Path(view._right_path).exists(),
        timeout=5_000,
    )

    assert pair_key.startswith("remote|")
    assert "left:old-name.txt" in view._left_editor.toPlainText()
    assert "right:new-name.md" in view._right_editor.toPlainText()
    assert view._left_path_label.text() == (
        "s3://left-bucket/…/old-name.txt" if left_remote else left_source
    )
    assert view._right_path_label.text() == (
        "s3://right-bucket/…/new-name.md" if right_remote else right_source
    )
    window.close()


def test_remote_file_worker_rejects_unsafe_relative_paths(qapp, tmp_path):
    with pytest.raises(ValueError, match="safe relative file path"):
        RemoteFilePairWorker(
            str(tmp_path / "unused-cli"),
            "s3://bucket/private",
            "/tmp/right",
            "../outside.txt",
        )


def test_remote_file_worker_redacts_source_paths_from_cli_errors(qtbot, tmp_path):
    executable = tmp_path / "failing-read-cli"
    executable.write_text(
        "#!" + sys.executable + "\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if args[0] == 'capabilities':\n"
        "    print(json.dumps({'source_schemes': ['s3']}))\n"
        "else:\n"
        "    print(args[5], file=sys.stderr)\n"
        "    sys.exit(7)\n"
    )
    executable.chmod(0o755)
    worker = RemoteFilePairWorker(
        str(executable),
        "s3://bucket/private/location",
        "/tmp/right",
        "sample.txt",
    )
    errors = []
    finished = []
    worker.error.connect(errors.append)
    worker.finished.connect(lambda: finished.append(True))

    worker.start()
    qtbot.waitUntil(lambda: bool(errors) and bool(finished), timeout=5_000)

    assert "s3://bucket/…" in errors[0]
    assert "private/location" not in errors[0]
    assert not Path(worker._temporary_directory.name).exists()


def test_remote_file_worker_rejects_unadvertised_scheme(qtbot, tmp_path):
    executable = tmp_path / "stale-remote-cli"
    executable.write_text(
        "#!" + sys.executable + "\n"
        "import json\n"
        "print(json.dumps({'source_schemes': []}))\n"
    )
    executable.chmod(0o755)
    worker = RemoteFilePairWorker(
        str(executable),
        "s3://bucket/left",
        "s3://bucket/right",
        ("old.txt", "new.txt"),
    )

    with qtbot.waitSignal(worker.error, timeout=5_000) as failed:
        worker.start()

    assert "does not support remote scheme(s): s3" in failed.args[0]


@pytest.mark.parametrize(
    ("file_name", "view_type"),
    [
        ("data.csv", TableView),
        ("photo.png", ImageView),
        ("payload.bin", HexView),
    ],
)
def test_remote_file_activation_routes_each_format_to_its_view(
    qtbot, tmp_path, file_name, view_type
):
    executable = _write_fake_cli(tmp_path, schemes=["s3"])
    window = MainWindow(AppConfig(cli_path=str(executable)))
    window._profile_manager._path = tmp_path / "profiles.json"
    window._left_path = "s3://left-bucket/data"
    window._right_path = "s3://right-bucket/data"

    window._on_file_activated(file_name, False)
    qtbot.waitUntil(lambda: bool(window._file_compare_tabs), timeout=5_000)
    index = next(iter(window._file_compare_tabs.values()))
    view = window._view_stack.widget(index)
    assert isinstance(view, view_type)

    if isinstance(view, TableView):
        qtbot.waitUntil(
            lambda: view._summary_label.text() != "Loading...", timeout=5_000
        )
    elif isinstance(view, ImageView):
        qtbot.waitUntil(lambda: view._image_worker is None, timeout=5_000)
    qtbot.waitUntil(
        lambda: not Path(view._remote_temporary_directory.name).exists(),
        timeout=5_000,
    )

    window.close()
