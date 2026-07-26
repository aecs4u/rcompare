"""WI-5.7 — the visible shell owns user-visible state.

The modern shell created a visible ``SessionTabBar``/``CompactPathBar``/
``IntegratedStatusBar`` and then kept hidden ``FilterBar``, ``ColorLegend``,
``QTabBar``, status-label and progress widgets as "compatibility shims" that
still owned the behaviour. Over forty operations wrote to
``statusBar().showMessage()`` after the native status bar had been hidden;
structured progress wrote to a detached progress bar; and
``set_diff_position()`` had no caller at all, so the footer read ``0/0``
forever.

These tests pin the repaired contract, including a source check that rejects
new writes to the hidden native status bar.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from teczka.main_window import MainWindow
from teczka.utils.config import AppConfig
from teczka.widgets.integrated_status_bar import IntegratedStatusBar
from teczka.workers.comparison_worker import ProgressInfo

_TECZKA_PACKAGE = Path(__file__).resolve().parent.parent / "teczka"


@pytest.fixture
def window(qapp, tmp_path):
    config = AppConfig()
    config._config_file = str(tmp_path / "pyside.json")
    win = MainWindow(config)
    yield win
    win.close()
    win.deleteLater()


# ---------------------------------------------------------------------------
# The status surface itself
# ---------------------------------------------------------------------------


def test_status_bar_exposes_the_three_shell_methods(qapp):
    """The API WI-5.7 requires every caller to route through."""
    bar = IntegratedStatusBar()
    for name in ("show_message", "set_progress", "set_navigation_position"):
        assert callable(getattr(bar, name))
    bar.deleteLater()


def test_timed_message_reverts_to_the_persistent_summary(qapp):
    bar = IntegratedStatusBar()
    bar.set_status("12 identical, 3 different")
    bar.show_message("Copying...", 50)
    assert bar.message == "Copying..."
    bar._message_timer.stop()
    bar._restore_persistent_message()
    assert bar.message == "12 identical, 3 different"
    bar.deleteLater()


def test_setting_progress_reveals_the_bar(qapp):
    bar = IntegratedStatusBar()
    bar.set_progress(42, 100)
    assert bar.progress_value == 42
    assert bar._progress_bar.isVisible() or bar._progress_bar.isVisibleTo(bar)
    bar.show_progress(False)
    assert bar.progress_value == 0
    bar.deleteLater()


# ---------------------------------------------------------------------------
# The window routes through it
# ---------------------------------------------------------------------------


def test_native_status_bar_is_hidden(window):
    assert window.statusBar().isHidden()


def test_operation_feedback_reaches_the_visible_bar(window):
    """A representative operation message must be visible, not swallowed."""
    window._notify("Copied 3 item(s).", 0)
    assert "Copied 3 item(s)." in window._integrated_status.message


@pytest.mark.parametrize(
    "operation",
    [
        lambda w: w._notify("Deleted: file.txt", 0),
        lambda w: w._notify("Renamed to: other.txt", 0),
        lambda w: w._notify("Sync complete: 2 copied.", 0),
        lambda w: w._notify("Bookmark 'work' added.", 0),
        lambda w: w._notify("Dropped two paths — starting comparison...", 0),
    ],
)
def test_each_operation_class_produces_visible_feedback(window, operation):
    window._integrated_status.set_status("Ready")
    operation(window)
    assert window._integrated_status.message != "Ready"


def test_synthetic_progress_updates_the_visible_percentage_and_stage(window):
    """Structured progress used to write to a widget nobody could see."""
    info = ProgressInfo(
        stage="comparing",
        stage_label="Comparing files...",
        stage_index=2,
        stage_count=6,
        entries_done=250,
        entries_total=1000,
        percent=25,
    )
    window._on_progress_update(info)
    assert window._integrated_status.progress_value == 25
    # The stage names the phase and carries the running count.
    stage = window._integrated_status.stage
    assert stage.startswith("Comparing files...")
    assert "250" in stage and "1,000" in stage
    assert "250" in window._integrated_status.message


def test_navigation_counter_is_published(window):
    """set_diff_position() had no caller, so the footer stayed at 0/0."""
    assert window._integrated_status.navigation_position == "0/0"
    window._set_navigation_position(3, 12)
    assert window._integrated_status.navigation_position == "3/12"


def test_status_summary_survives_a_timed_message(window):
    window._set_status_summary("5 identical, 1 different")
    window._notify("Copying...", 50)
    window._integrated_status._message_timer.stop()
    window._integrated_status._restore_persistent_message()
    assert window._integrated_status.message == "5 identical, 1 different"


# ---------------------------------------------------------------------------
# No hidden widget owns visible state
# ---------------------------------------------------------------------------


def test_compatibility_shims_are_gone(window):
    """The hidden widgets that used to own filters, tabs and status."""
    for attr in (
        "_filter_bar",
        "_color_legend",
        "_view_switcher",
        "_status_summary_label",
        "_status_stage",
        "_status_files",
        "_status_diffs",
        "_tb_compare",
        "_tb_cancel",
        "_tb_three_way",
    ):
        assert not hasattr(window, attr), f"{attr} is still present"


def test_no_source_writes_to_the_hidden_native_status_bar():
    """Reject new ``statusBar().showMessage()`` calls (WI-5.7 acceptance #5).

    The native bar is hidden, so anything written there is invisible. Only the
    single ``statusBar().hide()`` call is allowed.
    """
    offenders: list[str] = []
    for path in _TECZKA_PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            # Match `<anything>.statusBar().<method>(...)`, which is the shape
            # of every call that writes to the native bar.
            if not isinstance(node, ast.Call):
                continue
            method = node.func
            if not isinstance(method, ast.Attribute):
                continue
            inner = method.value
            if not (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "statusBar"
            ):
                continue
            if method.attr == "hide":
                continue  # the one permitted use
            offenders.append(f"{path.name}:{node.lineno}: statusBar().{method.attr}()")
    assert not offenders, "write to the visible status bar instead:\n" + "\n".join(
        offenders
    )
