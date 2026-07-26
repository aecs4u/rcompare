"""Regression coverage for filesystem, persistence, and mutation safety."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from teczka.main_window import MainWindow
from teczka.models.settings import ProfileManager, SessionProfile
from teczka.utils.config import AppConfig
from teczka.utils.safe_paths import (
    UnsafePathError,
    resolve_safe_relative,
    validate_child_name,
)


@pytest.fixture
def window(qapp, tmp_path):
    config = AppConfig()
    config._config_file = str(tmp_path / "pyside.json")
    win = MainWindow(config)
    yield win
    win.close()
    win.deleteLater()


def test_safe_relative_path_stays_below_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    assert resolve_safe_relative(root, "folder/file.txt") == (
        root / "folder" / "file.txt"
    )


@pytest.mark.parametrize(
    "value", ["../outside", "folder/../../outside", "/tmp/outside"]
)
def test_safe_relative_path_rejects_root_escape(tmp_path, value):
    with pytest.raises(UnsafePathError):
        resolve_safe_relative(tmp_path, value)


def test_safe_relative_path_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafePathError):
        resolve_safe_relative(root, "link/file.txt")


@pytest.mark.parametrize("value", ["", ".", "..", "../name", "dir/name", "dir\\name"])
def test_child_name_must_be_one_safe_component(value):
    with pytest.raises(UnsafePathError):
        validate_child_name(value)


def test_profile_mutation_rolls_back_when_atomic_save_fails(tmp_path, monkeypatch):
    manager = ProfileManager(tmp_path / "profiles.json")
    profile = SessionProfile(name="Work")
    monkeypatch.setattr(
        "teczka.models.settings.atomic_write_json", lambda *_args: False
    )

    assert manager.add(profile) is False
    assert manager.profiles == []
    assert manager.last_save_error is not None


def test_saved_filter_contract_is_restored(qapp, tmp_path):
    config = AppConfig(
        filter_options={
            "show_identical": False,
            "show_different": True,
            "show_left_only": False,
            "show_right_only": True,
            "show_files_only": True,
            "search_text": "report",
            "diff_option_mode": "show_orphans",
        }
    )
    config._config_file = str(tmp_path / "pyside.json")
    win = MainWindow(config)
    try:
        state = win._filter_state
        assert state.show_identical is False
        assert state.show_different is True
        assert state.show_left_only is False
        assert state.show_right_only is True
        assert state.show_files_only is True
        assert state.search_text == "report"
        assert state.diff_option_mode == "show_orphans"
    finally:
        win.close()
        win.deleteLater()


def test_binary_pattern_forces_hex_view(window):
    window._file_options["binary_patterns"] = ["*.dat", "firmware.*"]

    assert window._determine_file_compare_mode("nested/payload.dat") == "hex"
    assert window._determine_file_compare_mode("firmware.txt") == "hex"
    assert window._determine_file_compare_mode("notes.txt") == "text"


def test_failed_copy_is_not_replayed_locally(window, monkeypatch):
    refreshed: list[bool] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(window, "_on_refresh", lambda: refreshed.append(True))
    monkeypatch.setattr(
        window,
        "_copy_paths_local_fallback",
        lambda *_args, **_kwargs: pytest.fail("failed mutation was replayed"),
    )

    window._on_copy_error("partial failure", rel_paths=["a"], left_to_right=True)

    assert refreshed == [True]


def test_failed_sync_is_not_replayed_locally(window, monkeypatch):
    refreshed: list[bool] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(window, "_on_refresh", lambda: refreshed.append(True))
    monkeypatch.setattr(
        window,
        "_sync_local_fallback",
        lambda *_args, **_kwargs: pytest.fail("failed mutation was replayed"),
    )

    window._on_sync_error(
        "partial failure",
        direction="left_to_right",
        dry_run=False,
        use_trash=True,
    )

    assert refreshed == [True]


def test_profiles_follow_an_explicit_config_location(qapp, tmp_path):
    config_path = tmp_path / "isolated" / "pyside.json"
    config = AppConfig()
    config._config_file = str(config_path)
    win = MainWindow(config)
    try:
        assert Path(win._profile_manager._path) == config_path.with_name(
            "profiles.json"
        )
    finally:
        win.close()
        win.deleteLater()
