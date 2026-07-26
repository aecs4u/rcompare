"""Accessibility baseline for the controls touched by Phase 5.

The design review measured the four folder-status pills at green **2.78:1**,
red **3.63:1**, blue **3.59:1** and right-only red **3.76:1** against white
text — all below the WCAG AA 4.5:1 minimum for normal text. In the *unchecked*
state, foreground and background both resolved to ``palette(mid)``, making the
label effectively invisible.

Those numbers are treated as regression fixtures here rather than as a matter
of taste. This covers the parts of WI-7.12 that Phase 5 touched; the full
accessibility pass (focus order across every dialog, screen-reader run,
non-colour markers in every view) is still outstanding.
"""

from __future__ import annotations

import re

import pytest
from PySide6.QtCore import Qt

from teczka.main_window import MainWindow
from teczka.utils.config import AppConfig
from teczka.widgets.integrated_status_bar import (
    _PILL_COLORS,
    _PILL_MARKERS,
    IntegratedStatusBar,
)

# Ratios below which normal text fails WCAG AA / AAA.
_AA_NORMAL_TEXT = 4.5
_AA_LARGE_TEXT = 3.0


def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance for an ``#rrggbb`` colour."""
    value = hex_color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(a: str, b: str) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.fixture
def window(qapp, tmp_path):
    config = AppConfig()
    config._config_file = str(tmp_path / "pyside.json")
    win = MainWindow(config)
    yield win
    win.close()
    win.deleteLater()


# ---------------------------------------------------------------------------
# Contrast
# ---------------------------------------------------------------------------


def test_the_contrast_helper_matches_known_values():
    """Sanity-check the maths before trusting it on the palette."""
    assert _contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert _contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize("status", sorted(_PILL_COLORS))
def test_checked_pill_text_meets_wcag_aa(status):
    """The regression fixture: these measured 2.78-3.76:1 before the fix."""
    ratio = _contrast_ratio(_PILL_COLORS[status], "#ffffff")
    assert ratio >= _AA_NORMAL_TEXT, (
        f"{status} pill: white text on {_PILL_COLORS[status]} is {ratio:.2f}:1, "
        f"below the {_AA_NORMAL_TEXT}:1 minimum for normal text"
    )


@pytest.mark.parametrize("status", sorted(_PILL_COLORS))
def test_pill_colour_is_distinguishable_from_a_light_background(status):
    """The pill border must remain visible as a non-text indicator."""
    assert _contrast_ratio(_PILL_COLORS[status], "#ffffff") >= _AA_LARGE_TEXT


def test_unchecked_pill_does_not_paint_text_and_background_the_same(qapp):
    """Both resolved to palette(mid), making the label invisible."""
    bar = IntegratedStatusBar()
    style = bar._pill_identical.styleSheet()
    # Isolate the unchecked QPushButton block.
    block = style.split("QPushButton:checked")[0]
    background = re.search(r"background-color:\s*([^;]+);", block)
    foreground = re.search(r"[^-]color:\s*([^;]+);", block)
    assert background and foreground
    assert background.group(1).strip() != foreground.group(1).strip()
    bar.deleteLater()


# ---------------------------------------------------------------------------
# Status is not colour-only
# ---------------------------------------------------------------------------


def test_every_status_has_a_non_colour_marker():
    """Same/Different/Left-only/Right-only must survive monochrome."""
    assert set(_PILL_MARKERS) == set(_PILL_COLORS)
    markers = list(_PILL_MARKERS.values())
    assert len(set(markers)) == len(markers)
    assert all(marker.strip() for marker in markers)


def test_pill_labels_carry_their_marker(qapp):
    bar = IntegratedStatusBar()
    for pill, key in (
        (bar._pill_identical, "identical"),
        (bar._pill_different, "different"),
        (bar._pill_left_only, "left_only"),
        (bar._pill_right_only, "right_only"),
    ):
        assert _PILL_MARKERS[key] in pill.text()
    bar.deleteLater()


# ---------------------------------------------------------------------------
# Keyboard reachability
# ---------------------------------------------------------------------------


def test_filter_pills_are_keyboard_reachable(qapp):
    """NoFocus made the whole filter row unusable without a mouse."""
    bar = IntegratedStatusBar()
    for pill in (
        bar._pill_identical,
        bar._pill_different,
        bar._pill_left_only,
        bar._pill_right_only,
    ):
        assert pill.focusPolicy() != Qt.FocusPolicy.NoFocus
    bar.deleteLater()


def test_difference_navigation_buttons_are_keyboard_reachable(qapp):
    bar = IntegratedStatusBar()
    assert bar._btn_prev.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert bar._btn_next.focusPolicy() != Qt.FocusPolicy.NoFocus
    bar.deleteLater()


# ---------------------------------------------------------------------------
# Accessible names on icon-only controls
# ---------------------------------------------------------------------------


def test_status_bar_controls_have_accessible_names(qapp):
    bar = IntegratedStatusBar()
    for widget in (
        bar._pill_identical,
        bar._pill_different,
        bar._pill_left_only,
        bar._pill_right_only,
        bar._search_edit,
        bar._btn_prev,
        bar._btn_next,
        bar._progress_bar,
        bar._status_label,
    ):
        assert widget.accessibleName(), f"{widget} has no accessible name"
    bar.deleteLater()


def test_icon_only_path_controls_have_accessible_names(window):
    """Swap and the two browse buttons render as icons with no text."""
    bar = window._compact_path_bar
    for widget in (bar._swap_button, bar._left_browse, bar._right_browse):
        assert widget.accessibleName()


def test_home_cards_expose_their_title_as_the_button_name(window):
    """The title lived in a child QLabel, so the button announced as unnamed."""
    cards = window._home_view._cards
    assert cards
    for card in cards:
        assert card.accessibleName()
        assert card.accessibleDescription()


def test_session_controls_have_accessible_names(window):
    bar = window._session_tab_bar
    assert bar._add_button.accessibleName()
    assert bar._compare_button.accessibleName()
    assert bar._stop_button.accessibleName()


def test_disabled_actions_explain_themselves(window):
    """An unavailable action without a reason reads as a broken menu."""
    window._current_report = None
    window._left_path = window._right_path = ""
    window._update_action_states()
    for action in (window._act_compare_now, window._act_sync, window._act_diff_stats):
        assert not action.isEnabled()
        assert action.toolTip(), f"{action.text()} is disabled without explanation"
