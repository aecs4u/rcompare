"""Tests for selecting and launching external applications."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QDialog, QLabel
from teczka.dialogs.open_with_dialog import OpenWithDialog
from teczka.main_window import MainWindow
from teczka.utils.config import AppConfig
from teczka.utils.external_app import application_argv, handler_key


def test_application_argv_handles_spaces_and_file_placeholder(tmp_path):
    target = tmp_path / "folder with spaces" / "report file.txt"
    argv = application_argv('"editor app" --wait "{file}"', target)

    assert argv == ["editor app", "--wait", str(target)]


def test_application_argv_appends_path_without_running_a_shell(tmp_path):
    target = tmp_path / "report.txt"
    argv = application_argv("editor ; echo unsafe", target)

    assert argv == ["editor", ";", "echo", "unsafe", str(target)]


def test_application_argv_rejects_empty_and_malformed_commands(tmp_path):
    target = tmp_path / "report.txt"

    for command in ("", "   ", '""', '"unfinished'):
        try:
            application_argv(command, target)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected invalid command to fail: {command!r}")


def test_open_with_dialog_accepts_valid_command_and_remember_choice(qtbot, tmp_path):
    target = tmp_path / "report.txt"
    target.write_text("data", encoding="utf-8")
    dialog = OpenWithDialog(target)
    qtbot.addWidget(dialog)
    dialog._command_edit.setText('"editor app" --wait {file}')

    dialog._accept_command()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.command == '"editor app" --wait {file}'
    assert dialog.remember
    assert handler_key(target) == ".txt"


def test_open_with_dialog_keeps_invalid_command_open(qtbot, tmp_path):
    dialog = OpenWithDialog(tmp_path / "report.txt")
    qtbot.addWidget(dialog)
    dialog._command_edit.setText('"unfinished')

    dialog._accept_command()

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.findChild(QLabel, "openWithError").text()


def test_saved_handler_is_used_and_picker_persists_selection(
    qapp: QApplication, monkeypatch, tmp_path
):
    left_root = tmp_path / "lhs"
    right_root = tmp_path / "rhs"
    left_root.mkdir()
    right_root.mkdir()
    target = left_root / "report.txt"
    target.write_text("data", encoding="utf-8")

    config = AppConfig(_config_file=str(tmp_path / "teczka-test-config.json"))
    window = MainWindow(config)
    window._left_path = str(left_root)
    window._right_path = str(right_root)

    class DialogStub:
        DialogCode = QDialog.DialogCode

        def __init__(self, *_args, **_kwargs):
            self.command = '"editor app" --wait {file}'
            self.remember = True

        def exec(self):
            return QDialog.DialogCode.Accepted

    launched = []
    system_default_opens = []

    class DesktopServicesStub:
        @staticmethod
        def openUrl(url):
            system_default_opens.append(url.toLocalFile())
            return True

    monkeypatch.setattr("teczka.main_window.OpenWithDialog", DialogStub)
    monkeypatch.setattr("teczka.main_window.QDesktopServices", DesktopServicesStub)
    monkeypatch.setattr(
        "teczka.main_window.subprocess.Popen",
        lambda argv, **kwargs: launched.append((argv, kwargs)),
    )

    window._on_folder_context_command("open_with_picker", "report.txt", "left")
    window._on_folder_context_command("open_ext", "report.txt", "left")
    window._on_folder_context_command("open_saved", "report.txt", "left")

    expected = ["editor app", "--wait", str(target)]
    assert [argv for argv, _kwargs in launched] == [expected, expected]
    assert system_default_opens == [str(target)]
    assert all(kwargs["cwd"] == str(left_root) for _argv, kwargs in launched)
    assert config.open_with_handlers == {".txt": '"editor app" --wait {file}'}

    config.save()
    monkeypatch.setattr(
        "teczka.utils.config._default_config_path",
        lambda: tmp_path / "teczka-test-config.json",
    )
    loaded = AppConfig.load()
    assert loaded.open_with_handlers == config.open_with_handlers

    window.close()
    qapp.processEvents()
