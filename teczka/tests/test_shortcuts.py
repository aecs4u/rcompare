"""WI-5.1 — the keyboard surface must stay correct without hand maintenance.

Three defects motivated these tests, and each has a case here:

* ``QKeySequence.StandardKey.Quit`` resolves to the ``Exit`` *multimedia* key
  on Linux, so Ctrl+Q did nothing. Same trap for ``Preferences`` → ``Settings``.
* ``Ctrl+P`` was bound to both Print and Profiles; ``Ctrl+Y`` to both Redo
  (via ``StandardKey.Redo``) and Synchronize.
* The About dialog's keyboard table was a second, hand-written copy that had
  drifted from the live bindings.

Without these tests the collisions recur, which is the point of the work item.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QKeySequence

from teczka.dialogs.about_dialog import AboutDialog
from teczka.main_window import MainWindow
from teczka.shortcuts import (
    collect_shortcuts,
    find_collisions,
    is_typeable,
    standard_key,
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
# standard_key() / is_typeable()
# ---------------------------------------------------------------------------


def test_multimedia_keys_are_not_typeable(qapp):
    """A bare Exit/Settings hardware key is not a usable menu accelerator."""
    assert not is_typeable(QKeySequence("Exit"))
    assert not is_typeable(QKeySequence("Settings"))
    assert not is_typeable(QKeySequence())


def test_chords_with_modifiers_are_typeable(qapp):
    assert is_typeable(QKeySequence("Ctrl+Q"))
    assert is_typeable(QKeySequence("F5"))


def test_standard_key_falls_back_when_platform_binding_is_unusable(qapp):
    """Quit/Preferences must resolve to a real chord on every platform."""
    quit_seq = standard_key(QKeySequence.StandardKey.Quit, "Ctrl+Q")
    prefs_seq = standard_key(QKeySequence.StandardKey.Preferences, "Ctrl+,")
    assert is_typeable(quit_seq)
    assert is_typeable(prefs_seq)


def test_standard_key_prefers_a_usable_platform_binding(qapp):
    """Where the platform binding works, it wins over the fallback."""
    seq = standard_key(QKeySequence.StandardKey.Print, "Ctrl+Alt+Z")
    assert seq == QKeySequence(QKeySequence.StandardKey.Print)


# ---------------------------------------------------------------------------
# Live menu tree
# ---------------------------------------------------------------------------


def test_no_duplicate_shortcuts_in_the_menu_tree(window):
    """No chord may be bound to two actions — including alternate bindings.

    ``StandardKey.Redo`` carries Ctrl+Y as an alternate on Linux/Windows, which
    is exactly how the Synchronize collision hid.
    """
    collisions = find_collisions(window.action_registry())
    assert collisions == {}, f"colliding shortcuts: {collisions}"


def test_quit_and_preferences_resolve_to_real_chords(window):
    """The two actions that silently lost their binding."""
    assert is_typeable(window._act_quit.shortcut())
    assert is_typeable(window._act_preferences.shortcut())
    assert window._act_quit.shortcut() == QKeySequence("Ctrl+Q")
    assert window._act_preferences.shortcut() == QKeySequence("Ctrl+,")


def test_profiles_no_longer_collides_with_print(window):
    assert window._act_profiles.shortcut() != window._act_print.shortcut()


def test_synchronize_no_longer_collides_with_redo(window):
    sync = window._act_sync.shortcut()
    assert sync not in window._act_redo.shortcuts()


def test_about_table_matches_the_live_actions(window, qapp):
    """The About keyboard table is generated, not maintained by hand."""
    registry = collect_shortcuts(window.action_registry())
    dialog = AboutDialog(window, shortcuts=registry)
    rendered = {chord for chord, _ in dialog.shortcut_rows}

    live = {
        action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        for action in window.action_registry()
        if not action.shortcut().isEmpty()
    }
    assert live <= rendered
    # The stale hand-written entries must be gone: Ctrl+N was advertised for an
    # action actually bound to Ctrl+T.
    assert "Ctrl+N" not in rendered
    dialog.deleteLater()


def test_every_bound_action_has_a_description(window):
    """A chord with no readable label would render as a blank table row."""
    for chord, label in collect_shortcuts(window.action_registry()):
        assert chord.strip()
        assert label.strip()
