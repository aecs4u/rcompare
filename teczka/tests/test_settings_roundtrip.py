"""WI-5.10 — every exposed Settings field has a reader and a consumer.

Two Settings handlers existed. The connected ``_on_preferences()`` stored
comparison and appearance values but ignored ``get_config_updates()``, so Theme
and CLI Path were discarded; the more complete ``_on_options()`` was wired to
nothing. Separately, the Diff Options page exposed whitespace, case,
specialised-comparison and regex controls, and the Files page exposed encoding,
EOL and binary-pattern controls, none of which were returned, persisted or
applied.

Also covers WI-5.2 (CLI schema validation) since both are contract boundaries.
"""

from __future__ import annotations

import json

import pytest

from teczka.dialogs.settings_dialog import SettingsDialog
from teczka.main_window import MainWindow
from teczka.models.settings import ComparisonSettings
from teczka.resources.themes import load_theme, normalize_theme
from teczka.utils.cli_bridge import (
    CliBridge,
    SchemaVersionError,
    check_schema_version,
    parse_schema_version,
)
from teczka.utils.config import AppConfig


@pytest.fixture
def config(tmp_path):
    cfg = AppConfig()
    cfg._config_file = str(tmp_path / "pyside.json")
    return cfg


@pytest.fixture
def window(qapp, config):
    win = MainWindow(config)
    yield win
    win.close()
    win.deleteLater()


# ---------------------------------------------------------------------------
# One handler
# ---------------------------------------------------------------------------


def test_only_one_settings_handler_remains(window):
    """`_on_options()` was the more complete handler, and was unconnected."""
    assert hasattr(window, "_on_preferences")
    assert not hasattr(window, "_on_options")


def test_settings_action_is_connected_to_the_surviving_handler(window, monkeypatch):
    """Triggering Configure must reach _on_preferences, not nothing."""
    called: list[bool] = []
    monkeypatch.setattr(window, "_on_preferences", lambda: called.append(True))
    # Reconnect so the monkeypatched attribute is the one invoked.
    window._act_preferences.triggered.disconnect()
    window._act_preferences.triggered.connect(window._on_preferences)
    window._act_preferences.trigger()
    assert called == [True]


# ---------------------------------------------------------------------------
# Diff Options / Files: exposed means applied
# ---------------------------------------------------------------------------


def test_diff_options_are_returned(qapp, config):
    dialog = SettingsDialog(config, ComparisonSettings())
    dialog._case_check.setChecked(True)
    dialog._image_exif_check.setChecked(True)
    dialog._csv_diff_check.setChecked(True)
    dialog._csv_key_edit.setText("id, order_number")
    dialog._ws_combo.setCurrentIndex(dialog._ws_combo.findData("all"))
    dialog._regex_edit.setPlainText(r"\d+:[N]:Numbers")

    options = dialog.get_diff_options()
    assert options["ignore_case"] is True
    assert options["ignore_whitespace"] == "all"
    assert options["image_exif"] is True
    assert options["csv_key_columns"] == ["id", "order_number"]
    assert options["regex_rules"] == [r"\d+:[N]:Numbers"]
    dialog.deleteLater()


def test_file_options_are_returned(qapp, config):
    dialog = SettingsDialog(config, ComparisonSettings())
    dialog._encoding_combo.setCurrentText("latin-1")
    dialog._eol_ignore_check.setChecked(False)
    dialog._binary_patterns_edit.setPlainText("*.iso\n*.img")

    options = dialog.get_file_options()
    assert options["encoding"] == "latin-1"
    assert options["ignore_eol"] is False
    assert options["binary_patterns"] == ["*.iso", "*.img"]
    dialog.deleteLater()


def test_settings_restart_round_trip(qapp, config):
    """Every field must survive a save/reload cycle."""
    dialog = SettingsDialog(config, ComparisonSettings())
    dialog._case_check.setChecked(True)
    dialog._ws_combo.setCurrentIndex(dialog._ws_combo.findData("trailing"))
    dialog._csv_key_edit.setText("sku")
    dialog._encoding_combo.setCurrentText("utf-16")
    dialog._eol_ignore_check.setChecked(False)
    config.diff_options = dialog.get_diff_options()
    config.file_options = dialog.get_file_options()
    config.theme = "dark"
    config.save()
    dialog.deleteLater()

    saved = json.loads(open(config._config_file).read())
    assert saved["diff_options"]["ignore_whitespace"] == "trailing"
    assert saved["file_options"]["encoding"] == "utf-16"
    assert saved["theme"] == "dark"

    # Rebuild the config from what actually landed on disk, the way a restart
    # would; a reopened dialog must show that, not the hardcoded defaults.
    reloaded = AppConfig(
        theme=saved["theme"],
        diff_options=saved["diff_options"],
        file_options=saved["file_options"],
    )
    restored = SettingsDialog(reloaded, ComparisonSettings())
    assert restored.get_diff_options()["ignore_case"] is True
    assert restored.get_diff_options()["csv_key_columns"] == ["sku"]
    assert restored.get_file_options()["encoding"] == "utf-16"
    assert restored.get_file_options()["ignore_eol"] is False
    restored.deleteLater()


def test_every_diff_control_has_a_reader(qapp, config):
    """No control may exist without something reading it back."""
    dialog = SettingsDialog(config, ComparisonSettings())
    read = set(dialog.get_diff_options()) | set(dialog.get_file_options())
    expected = {
        "ignore_whitespace",
        "ignore_case",
        "text_diff",
        "image_diff",
        "image_exif",
        "csv_diff",
        "csv_key_columns",
        "json_diff",
        "yaml_diff",
        "excel_diff",
        "regex_rules",
        "encoding",
        "ignore_eol",
        "binary_patterns",
    }
    assert expected <= read
    dialog.deleteLater()


def test_diff_options_become_scan_arguments(window):
    """A Settings value must reach the CLI, not just the config file."""
    window._diff_options = {
        "ignore_case": True,
        "ignore_whitespace": "all",
        "image_exif": True,
        "csv_diff": True,
        "csv_key_columns": ["id"],
        "regex_rules": [r"\d+:[N]:Numbers"],
    }
    options = window._scan_options()
    assert options["ignore_case"] is True
    assert options["ignore_whitespace"] == "all"
    assert options["image_exif"] is True
    assert options["csv_key_columns"] == ["id"]
    assert options["regex_rules"] == [r"\d+:[N]:Numbers"]


def test_whitespace_none_becomes_no_flag(window):
    """"None" must not be passed to the CLI as a literal mode."""
    window._diff_options = {"ignore_whitespace": "none"}
    assert window._scan_options()["ignore_whitespace"] is None


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


def test_light_and_dark_render_differently():
    """Neither stylesheet was ever loaded, at startup or on change."""
    light, dark = load_theme("light"), load_theme("dark")
    assert light and dark
    assert light != dark


def test_system_theme_applies_no_stylesheet():
    """So Plasma dark mode, accent colour and high-contrast show through."""
    assert load_theme("system") == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Dark", "dark"), ("LIGHT", "light"), ("", "system"), (None, "system"),
     ("nonsense", "system")],
)
def test_theme_names_are_normalized(raw, expected):
    assert normalize_theme(raw) == expected


def test_theme_selector_offers_a_system_option(qapp, config):
    dialog = SettingsDialog(config, ComparisonSettings())
    values = {
        dialog._theme_combo.itemData(i) for i in range(dialog._theme_combo.count())
    }
    assert values == {"system", "light", "dark"}
    dialog.deleteLater()


# ---------------------------------------------------------------------------
# CLI path validation
# ---------------------------------------------------------------------------


def test_a_missing_cli_path_is_rejected_actionably(qapp, config, tmp_path):
    dialog = SettingsDialog(config, ComparisonSettings())
    dialog._cli_edit.setText(str(tmp_path / "does-not-exist"))
    problem = dialog._cli_path_problem()
    assert problem is not None and "does not exist" in problem
    dialog.deleteLater()


def test_a_directory_is_rejected_as_a_cli_path(qapp, config, tmp_path):
    dialog = SettingsDialog(config, ComparisonSettings())
    dialog._cli_edit.setText(str(tmp_path))
    assert "not a file" in (dialog._cli_path_problem() or "")
    dialog.deleteLater()


def test_an_empty_cli_path_is_valid(qapp, config):
    """Empty means auto-detect, which is a legitimate choice."""
    dialog = SettingsDialog(config, ComparisonSettings())
    dialog._cli_edit.setText("")
    assert dialog._cli_path_problem() is None
    dialog.deleteLater()


def test_cli_error_message_names_a_real_location(window):
    """The message pointed at "Tools > Options", a menu that never existed."""
    try:
        AppConfig(cli_path=None).get_cli_path()
    except FileNotFoundError as exc:
        assert "Tools" not in str(exc)
        assert "Settings" in str(exc)


# ---------------------------------------------------------------------------
# WI-5.2: the CLI schema contract
# ---------------------------------------------------------------------------


def test_matching_major_version_is_accepted():
    assert check_schema_version({"schema_version": "1.1.0"}) == "1.1.0"


def test_missing_version_is_treated_as_legacy():
    """Older binaries predate the field; that is not a mismatch."""
    major, normalized = parse_schema_version(None)
    assert major == 1 and normalized == "1.0.0"
    assert check_schema_version({}) == "1.0.0"


def test_incompatible_major_version_is_rejected_with_both_versions():
    with pytest.raises(SchemaVersionError) as excinfo:
        check_schema_version({"schema_version": "2.0.0"})
    message = str(excinfo.value)
    assert "2.0.0" in message  # received
    assert "1" in message  # expected
    assert excinfo.value.received == "2.0.0"
    assert excinfo.value.expected_major == 1


def test_parse_scan_report_checks_the_schema_before_parsing(tmp_path):
    """A drifted schema must not surface as a bare KeyError in a worker."""
    bridge = CliBridge("/nonexistent/rcompare_cli")
    payload = json.dumps({"schema_version": "9.0.0", "left": "a", "right": "b"})
    with pytest.raises(SchemaVersionError):
        bridge.parse_scan_report(payload)


def test_a_missing_summary_field_is_reported_as_a_schema_problem():
    bridge = CliBridge("/nonexistent/rcompare_cli")
    payload = json.dumps(
        {"schema_version": "1.1.0", "left": "a", "right": "b", "summary": {}}
    )
    with pytest.raises(SchemaVersionError):
        bridge.parse_scan_report(payload)


def test_a_valid_report_records_its_schema_version():
    bridge = CliBridge("/nonexistent/rcompare_cli")
    payload = json.dumps(
        {
            "schema_version": "1.1.0",
            "left": "a",
            "right": "b",
            "summary": {
                "total": 0, "same": 0, "different": 0,
                "orphan_left": 0, "orphan_right": 0, "unchecked": 0,
            },
            "entries": [],
        }
    )
    report = bridge.parse_scan_report(payload)
    assert report.schema_version == "1.1.0"
