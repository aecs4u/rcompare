"""WI-5.9 — one filter contract, driven from every input surface.

The verified contradictions this replaces:

* the proxy defaulted to ``show_differences`` while all four status pills
  showed as enabled, so "Identical" read *on* while identical rows were hidden;
* View-menu toggles only wrote to a hidden ``FilterBar`` whose signals were
  never connected;
* clicking a visible status pill passed ``show_files_only=True``, silently
  hiding every folder row;
* session capture later read the stale hidden values;
* ``Ctrl+F`` focused the hidden search field.

The state-matrix test below drives each input surface and asserts the proxy,
the menu, the footer and the persisted session all agree.
"""

from __future__ import annotations

import pytest

from teczka.main_window import MainWindow
from teczka.models.filter_state import (
    DEFAULT_DIFF_OPTION_MODE,
    FolderFilterState,
    PRESET_ALL,
    PRESET_CUSTOM,
    PRESET_DIFFS,
    PRESET_SAME,
)
from teczka.utils.config import AppConfig


@pytest.fixture
def window(qapp, tmp_path):
    config = AppConfig()
    config._config_file = str(tmp_path / "pyside.json")
    win = MainWindow(config)
    yield win
    win.close()
    win.deleteLater()


# ---------------------------------------------------------------------------
# The value object
# ---------------------------------------------------------------------------


def test_default_shows_every_status():
    """The default must not contradict the controls that display it."""
    state = FolderFilterState()
    assert state.show_identical and state.show_different
    assert state.show_left_only and state.show_right_only
    assert state.preset == PRESET_ALL
    # "show_differences" here is precisely what hid identical rows while the
    # Identical pill claimed to be on.
    assert state.diff_option_mode == DEFAULT_DIFF_OPTION_MODE == "show_all"


def test_status_toggle_does_not_touch_files_only():
    """Clicking a status pill used to force files-only mode on."""
    state = FolderFilterState().with_files_only(False)
    updated = state.with_statuses(True, True, False, False)
    assert updated.show_files_only is False


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        (PRESET_ALL, (True, True, True, True)),
        (PRESET_DIFFS, (False, True, True, True)),
        (PRESET_SAME, (True, False, False, False)),
    ],
)
def test_presets_round_trip(preset, expected):
    state = FolderFilterState().with_preset(preset)
    flags = (
        state.show_identical,
        state.show_different,
        state.show_left_only,
        state.show_right_only,
    )
    assert flags == expected
    assert state.preset == preset


def test_preset_preserves_unrelated_filters():
    state = (
        FolderFilterState().with_files_only(True).with_search("readme")
    ).with_preset(PRESET_DIFFS)
    assert state.show_files_only is True
    assert state.search_text == "readme"


def test_arbitrary_combination_reports_custom():
    state = FolderFilterState().with_statuses(False, False, True, False)
    assert state.preset == PRESET_CUSTOM


def test_serialisation_round_trip():
    state = (
        FolderFilterState()
        .with_statuses(False, True, True, False)
        .with_files_only(True)
        .with_search("log")
        .with_diff_option_mode("show_orphans")
    )
    assert FolderFilterState.from_dict(state.to_dict()) == state


def test_unknown_diff_mode_falls_back_to_the_default():
    assert (
        FolderFilterState().with_diff_option_mode("nonsense").diff_option_mode
        == DEFAULT_DIFF_OPTION_MODE
    )
    assert FolderFilterState.from_dict({"diff_option_mode": 7}).diff_option_mode == (
        DEFAULT_DIFF_OPTION_MODE
    )


# ---------------------------------------------------------------------------
# The state matrix: every surface agrees
# ---------------------------------------------------------------------------


def _assert_surfaces_agree(window) -> None:
    """The proxy, the menu, the footer and the session must match the state."""
    window.flush_pending_filters()
    state = window.filter_state
    proxy = window._folder_view._proxy_model

    assert proxy._show_identical == state.show_identical
    assert proxy._show_different == state.show_different
    assert proxy._show_left_only == state.show_left_only
    assert proxy._show_right_only == state.show_right_only
    assert proxy._show_files_only == state.show_files_only
    assert proxy._search_text == state.search_text.strip().lower()
    assert proxy._diff_option_mode == state.diff_option_mode

    assert window._act_show_identical.isChecked() == state.show_identical
    assert window._act_show_different.isChecked() == state.show_different
    assert window._act_show_left_only.isChecked() == state.show_left_only
    assert window._act_show_right_only.isChecked() == state.show_right_only
    assert window._act_show_files_only.isChecked() == state.show_files_only

    footer = window._integrated_status
    assert footer._pill_identical.isChecked() == state.show_identical
    assert footer._pill_different.isChecked() == state.show_different
    assert footer._pill_left_only.isChecked() == state.show_left_only
    assert footer._pill_right_only.isChecked() == state.show_right_only

    assert window._current_session().filters == state


def test_initial_state_is_consistent(window):
    _assert_surfaces_agree(window)


def test_status_pill_click_propagates(window):
    """Driving the footer must move the proxy, the menu and the session."""
    window._integrated_status._pill_identical.setChecked(False)
    _assert_surfaces_agree(window)
    assert window.filter_state.show_identical is False


def test_status_pill_click_does_not_enable_files_only(window):
    """The exact regression: a pill click passed show_files_only=True."""
    assert window.filter_state.show_files_only is False
    window._integrated_status._pill_different.setChecked(False)
    window.flush_pending_filters()
    assert window.filter_state.show_files_only is False
    assert window._folder_view._proxy_model._show_files_only is False


def test_view_menu_toggle_propagates(window):
    """The menu wrote into a hidden widget with unconnected signals."""
    window._act_show_left_only.setChecked(False)
    _assert_surfaces_agree(window)
    assert window._folder_view._proxy_model._show_left_only is False


def test_quick_filter_preset_propagates(window):
    window._apply_quick_filter_preset(PRESET_DIFFS)
    _assert_surfaces_agree(window)
    assert window._act_filter_diffs.isChecked()
    assert window.filter_state.show_identical is False


def test_search_text_propagates(window):
    window._on_search_changed("readme")
    _assert_surfaces_agree(window)
    assert window._folder_view._proxy_model._search_text == "readme"


def test_diff_option_mode_propagates(window):
    window._on_diff_option_changed("show_orphans")
    _assert_surfaces_agree(window)
    assert window._diff_option_actions["show_orphans"].isChecked()


def test_session_capture_reads_live_state(window):
    """Capture used to read stale values off the hidden FilterBar."""
    window._act_show_right_only.setChecked(False)
    window._on_search_changed("build")
    window.flush_pending_filters()
    window._capture_session_state(window._active_session_index)
    captured = window._sessions[window._active_session_index].filters
    assert captured.show_right_only is False
    assert captured.search_text == "build"


def test_filter_state_survives_a_session_round_trip(window):
    window._apply_quick_filter_preset(PRESET_SAME)
    window.flush_pending_filters()
    expected = window.filter_state

    window._on_new_session()
    assert window.filter_state == FolderFilterState()

    window._session_tab_bar.current_index = 0
    window.flush_pending_filters()
    assert window.filter_state == expected
    _assert_surfaces_agree(window)


def test_ctrl_f_focuses_the_visible_search_field(window, qapp):
    """Ctrl+F focused a hidden QLineEdit, so typing went nowhere.

    A widget only takes focus once its window is shown, hence the show() here
    even under the offscreen platform.
    """
    window.show()
    qapp.processEvents()
    window._switch_view(1)  # Folder Compare
    window._on_find()
    focused = window._integrated_status._search_edit
    assert focused.hasFocus()
    assert focused.isVisibleTo(window)


def test_switching_views_never_changes_files_only(window):
    """A view change must not silently alter what the folder filter shows."""
    before = window.filter_state
    for index in range(window._view_stack.count()):
        window._switch_view(index)
        window.flush_pending_filters()
        assert window.filter_state == before
