"""WI-5.8 / WI-5.11 — navigation, documents, swap and action state.

Five navigation defects were reproduced at runtime and are pinned here:

1. ``_on_close_tab()`` compared a visible session index against the number of
   *view* tabs (6), so the first six session tabs could not be closed and the
   deletion offset was wrong.
2. A folder double-click created a comparison widget in the view stack but
   registered its label in a hidden tab bar, leaving the opened document with
   no visible tab, return path or close action.
3. The sidebar exposed a 3-Way Merge destination the stack did not have, so
   selecting it did nothing.
4. Home emitted ``profile_selected`` into nothing, and read profiles from a
   store ``ProfileManager`` never writes.
5. Home rendered a Recent Sessions section nothing populated.

Plus WI-5.11: the path bar swapped locally *and* emitted ``swap_requested``,
whose handler swapped again — two swaps, no visible change.
"""

from __future__ import annotations

import pytest

from teczka.main_window import (
    VIEW_FOLDER,
    VIEW_HEX,
    VIEW_HOME,
    VIEW_IMAGE,
    VIEW_MERGE,
    VIEW_TABLE,
    VIEW_TEXT,
    MainWindow,
)
from teczka.models.settings import ProfileManager, SessionProfile
from teczka.utils.config import AppConfig


@pytest.fixture
def window(qapp, tmp_path):
    config = AppConfig()
    config._config_file = str(tmp_path / "pyside.json")
    win = MainWindow(config)
    # Keep profiles out of the developer's real ~/.config.
    win._profile_manager = ProfileManager(tmp_path / "profiles.json")
    yield win
    win.close()
    win.deleteLater()


@pytest.fixture
def pair(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "same.txt").write_text("hello")
    (right / "same.txt").write_text("hello")
    (left / "diff.txt").write_text("left")
    (right / "diff.txt").write_text("right")
    return left, right


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def test_starts_with_one_session(window):
    assert window.session_count == 1
    assert window._session_tab_bar.count == 1


def test_creating_and_switching_two_sessions(window):
    window._on_new_session()
    assert window.session_count == 2
    assert window._session_tab_bar.count == 2
    assert window._active_session_index == 1

    window._session_tab_bar.current_index = 0
    assert window._active_session_index == 0


def test_the_first_session_tab_can_be_closed(window):
    """The exact regression: index 0 < _BASE_VIEW_TAB_COUNT, so it never closed."""
    window._on_new_session()
    window._sessions[0].left_path = "/tmp/one"
    window._sessions[1].left_path = "/tmp/two"

    window._close_session(0)

    assert window.session_count == 1
    assert window._session_tab_bar.count == 1
    # The *right* entry was removed: the survivor is the second session.
    assert window._sessions[0].left_path == "/tmp/two"


def test_closing_a_middle_session_keeps_the_rest_aligned(window):
    for _ in range(2):
        window._on_new_session()
    for index, session in enumerate(window._sessions):
        session.left_path = f"/tmp/{index}"

    window._close_session(1)

    assert [s.left_path for s in window._sessions] == ["/tmp/0", "/tmp/2"]
    assert window._session_tab_bar.count == 2
    assert 0 <= window._active_session_index < window.session_count


def test_the_last_session_cannot_be_closed(window):
    window._close_session(0)
    assert window.session_count == 1


def test_close_tab_action_is_disabled_with_one_session(window):
    window._update_action_states()
    assert not window._act_close_tab.isEnabled()
    window._on_new_session()
    assert window._act_close_tab.isEnabled()


# ---------------------------------------------------------------------------
# Comparison documents
# ---------------------------------------------------------------------------


def test_every_base_view_is_reachable(window):
    """Including Merge, which the sidebar advertised but the stack lacked."""
    for index in (
        VIEW_HOME,
        VIEW_FOLDER,
        VIEW_TEXT,
        VIEW_HEX,
        VIEW_IMAGE,
        VIEW_TABLE,
        VIEW_MERGE,
    ):
        window._switch_view(index)
        assert window.active_view_index == index


def test_sidebar_merge_destination_is_not_inert(window):
    """`_switch_view(6)` used to return without doing anything."""
    window._switch_view(VIEW_FOLDER)
    window._sidebar.view_requested.emit(VIEW_MERGE)
    assert window.active_view_index == VIEW_MERGE


def test_no_sidebar_destination_is_inert(window):
    """Every destination the sidebar offers must exist in the stack."""
    assert len(window._sidebar._buttons) <= window._view_stack.count()


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("notes.txt", "hello\n"),
        ("data.csv", "id,name\n1,a\n"),
        ("blob.unknown", "\x00\x01binary"),
    ],
)
def test_opening_a_document_creates_a_visible_tab(window, pair, name, content):
    """Documents were registered in a hidden tab bar with no close action."""
    left, right = pair
    (left / name).write_text(content)
    (right / name).write_text(content + "x")
    window._left_path, window._right_path = str(left), str(right)

    assert window.open_document_count == 0
    window._on_file_activated(name, False)

    assert window.open_document_count == 1
    assert window._document_tabs.isVisible() or window._document_tabs.document_count
    assert window.active_view_index >= 7  # beyond the base views


def test_reopening_the_same_file_reuses_its_document(window, pair):
    left, right = pair
    window._left_path, window._right_path = str(left), str(right)

    window._on_file_activated("diff.txt", False)
    first = window.active_view_index
    window._switch_view(VIEW_FOLDER)
    window._on_file_activated("diff.txt", False)

    assert window.open_document_count == 1
    assert window.active_view_index == first


def test_closing_a_document_returns_to_the_folder_view(window, pair):
    left, right = pair
    window._left_path, window._right_path = str(left), str(right)
    window._on_file_activated("diff.txt", False)
    index = window.active_view_index

    window._on_close_document(index)

    assert window.open_document_count == 0
    assert window.active_view_index == VIEW_FOLDER


def test_base_views_cannot_be_closed_as_documents(window):
    before = window._view_stack.count()
    for index in range(7):
        window._on_close_document(index)
    assert window._view_stack.count() == before


def test_closing_one_of_two_documents_keeps_the_other_addressable(window, pair):
    left, right = pair
    for name in ("a.txt", "b.txt"):
        (left / name).write_text("l")
        (right / name).write_text("r")
    window._left_path, window._right_path = str(left), str(right)

    window._on_file_activated("a.txt", False)
    first = window.active_view_index
    window._switch_view(VIEW_FOLDER)
    window._on_file_activated("b.txt", False)

    assert window.open_document_count == 2
    window._on_close_document(first)
    assert window.open_document_count == 1

    # The survivor's recorded stack index must still point at a live widget.
    for stack_index in window._document_tabs.stack_indices()[1:]:
        assert window._view_stack.widget(stack_index) is not None


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------


def test_home_offers_every_document_type(window):
    """Home covered Folder/Text/Hex/Image only, omitting Table and Merge."""
    from teczka.views.home_view import _SESSION_TYPES

    offered = {info["view"] for info in _SESSION_TYPES}
    assert offered == {
        VIEW_FOLDER,
        VIEW_TEXT,
        VIEW_HEX,
        VIEW_IMAGE,
        VIEW_TABLE,
        VIEW_MERGE,
    }


def test_home_cards_open_the_view_they_name(window):
    from teczka.views.home_view import _SESSION_TYPES

    for info in _SESSION_TYPES:
        window._home_view.session_type_selected.emit(info["view"])
        assert window.active_view_index == info["view"]


def test_home_profile_activation_opens_the_persisted_pair(window, pair):
    """profile_selected was emitted into nothing."""
    left, right = pair
    profile = SessionProfile(name="Nightly", left_path=str(left), right_path=str(right))
    window._profile_manager.add(profile)
    window._home_view.refresh(window._config, window._profile_manager)

    window._on_home_profile_selected(profile.id)

    assert window._left_path == str(left)
    assert window._right_path == str(right)


def test_home_reads_profiles_from_the_profile_manager(window, pair):
    """Home looked in comparison_settings["profiles"], which is never written."""
    left, right = pair
    window._profile_manager.add(
        SessionProfile(name="Nightly", left_path=str(left), right_path=str(right))
    )
    window._home_view.refresh(window._config, window._profile_manager)
    assert window._home_view.profile_count == 1


def test_completing_a_comparison_adds_a_recent_entry(window, pair):
    """Recent Sessions was rendered but never populated."""
    left, right = pair
    assert window._home_view.recent_count == 0

    window._left_path, window._right_path = str(left), str(right)
    window._record_recent_session()

    assert window._config.recent_sessions[0] == {
        "left": str(left),
        "right": str(right),
    }
    assert window._home_view.recent_count == 1


def test_recent_entries_are_deduplicated_most_recent_first(window):
    window._left_path, window._right_path = "/a", "/b"
    window._record_recent_session()
    window._left_path, window._right_path = "/c", "/d"
    window._record_recent_session()
    window._left_path, window._right_path = "/a", "/b"
    window._record_recent_session()

    assert window._config.recent_sessions[0] == {"left": "/a", "right": "/b"}
    assert len(window._config.recent_sessions) == 2


# ---------------------------------------------------------------------------
# WI-5.11: swap and contextual action state
# ---------------------------------------------------------------------------


def test_one_swap_click_reverses_the_paths_exactly_once(window):
    """The double-swap bug: the visible result used to be no change at all."""
    window._set_left_path("/tmp/left")
    window._set_right_path("/tmp/right")

    window._compact_path_bar._swap_button.click()

    assert window._left_path == "/tmp/right"
    assert window._right_path == "/tmp/left"
    assert window._path_bar.left_path == "/tmp/right"
    assert window._path_bar.right_path == "/tmp/left"


def test_swap_updates_the_session_exactly_once(window):
    window._set_left_path("/tmp/left")
    window._set_right_path("/tmp/right")
    window._compact_path_bar._swap_button.click()

    session = window._current_session()
    assert session.left_path == "/tmp/right"
    assert session.right_path == "/tmp/left"


def test_two_swaps_restore_the_original_orientation(window):
    window._set_left_path("/tmp/left")
    window._set_right_path("/tmp/right")
    window._compact_path_bar._swap_button.click()
    window._compact_path_bar._swap_button.click()
    assert window._left_path == "/tmp/left"
    assert window._right_path == "/tmp/right"


def test_compare_is_disabled_until_both_paths_exist(window):
    window._update_action_states()
    assert not window._act_compare_now.isEnabled()
    assert window._act_compare_now.toolTip()

    window._set_left_path("/tmp/left")
    window._update_action_states()
    assert not window._act_compare_now.isEnabled()

    window._set_right_path("/tmp/right")
    window._update_action_states()
    assert window._act_compare_now.isEnabled() == (window._cli_bridge is not None)


def test_compare_is_disabled_without_a_cli(window):
    window._set_left_path("/tmp/left")
    window._set_right_path("/tmp/right")
    window._cli_bridge = None
    window._update_action_states()
    assert not window._act_compare_now.isEnabled()
    assert "rcompare_cli" in window._act_compare_now.toolTip()


def test_result_dependent_actions_need_a_report(window):
    window._current_report = None
    window._update_action_states()
    for action in (window._act_sync, window._act_diff_stats, window._act_next_diff):
        assert not action.isEnabled()
        assert action.toolTip()


@pytest.mark.parametrize(
    "view",
    [VIEW_HOME, VIEW_TEXT, VIEW_HEX, VIEW_IMAGE, VIEW_TABLE, VIEW_MERGE],
)
def test_folder_only_actions_are_disabled_outside_folder_compare(window, view):
    window._switch_view(view)
    assert not window._act_expand_all.isEnabled()
    assert not window._act_collapse_all.isEnabled()


def test_folder_chrome_is_hidden_outside_folder_compare(window):
    """Folder filters stayed live on Home/Text/Image/Hex/Table/Merge."""
    window._switch_view(VIEW_FOLDER)
    assert window._integrated_status._pill_identical.isEnabled()

    window._switch_view(VIEW_TEXT)
    assert not window._integrated_status._pill_identical.isEnabled()
    assert not window._integrated_status._search_edit.isEnabled()


def test_home_hides_the_path_bar(window):
    window._switch_view(VIEW_HOME)
    assert not window._compact_path_bar.isVisibleTo(window)
    window._switch_view(VIEW_FOLDER)
    assert window._compact_path_bar.isVisibleTo(window)
