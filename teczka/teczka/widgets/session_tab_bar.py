"""SessionTabBar widget providing a tabbed session bar with Compare/Stop actions."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QTabBar,
    QToolButton,
    QWidget,
)

# Accent color for the Compare button (the only hardcoded color, per spec)
_ACCENT = "#2979ff"

_COMPARE_BUTTON_STYLE = f"""
QPushButton {{
    background-color: {_ACCENT};
    color: white;
    border: none;
    border-radius: 3px;
    padding: 4px 14px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: #448aff;
}}
QPushButton:pressed {{
    background-color: #2962ff;
}}
QPushButton:disabled {{
    background-color: palette(mid);
    color: palette(midlight);
}}
"""

_STOP_BUTTON_STYLE = """
QPushButton {
    background-color: palette(button);
    color: palette(button-text);
    border: 1px solid palette(mid);
    border-radius: 3px;
    padding: 4px 14px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: palette(light);
}
QPushButton:pressed {
    background-color: palette(dark);
}
"""

_TAB_BAR_STYLE = """
QTabBar {
    border: none;
    background: transparent;
}
QTabBar::tab {
    border: none;
    border-bottom: 2px solid transparent;
    padding: 4px 12px;
    margin-right: 2px;
    background: transparent;
    color: palette(text);
}
QTabBar::tab:selected {
    border-bottom: 2px solid palette(highlight);
    color: palette(highlight);
}
QTabBar::tab:hover:!selected {
    border-bottom: 2px solid palette(mid);
}
QTabBar::close-button {
    subcontrol-position: right;
    image: none;
    border: none;
    padding: 0px;
}
"""

_ADD_BUTTON_STYLE = """
QToolButton {
    border: 1px solid palette(mid);
    border-radius: 3px;
    background: palette(button);
    color: palette(button-text);
    font-weight: bold;
    font-size: 14px;
}
QToolButton:hover {
    background: palette(light);
}
QToolButton:pressed {
    background: palette(dark);
}
"""


class SessionTabBar(QWidget):
    """Horizontal bar with session tabs, a [+] button, and Compare/Stop actions.

    Signals:
        new_session_requested: Emitted when the [+] button is clicked.
        session_changed(int): Emitted when the active tab changes.
        session_close_requested(int): Emitted when a tab close button is clicked.
        compare_requested: Emitted when the Compare button is clicked.
        stop_requested: Emitted when the Stop button is clicked.
    """

    new_session_requested = Signal()
    session_changed = Signal(int)
    session_close_requested = Signal(int)
    compare_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        # --- Tab bar ---
        self._tab_bar = QTabBar()
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setExpanding(False)
        self._tab_bar.setDrawBase(False)
        self._tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self._tab_bar.setDocumentMode(True)
        self._tab_bar.setStyleSheet(_TAB_BAR_STYLE)
        self._tab_bar.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )

        self._tab_bar.currentChanged.connect(self.session_changed)
        self._tab_bar.tabCloseRequested.connect(self.session_close_requested)

        layout.addWidget(self._tab_bar, 0)

        # --- Add-session button ---
        self._add_button = QToolButton()
        self._add_button.setText("+")
        self._add_button.setToolTip("New session")
        self._add_button.setFixedSize(24, 24)
        self._add_button.setStyleSheet(_ADD_BUTTON_STYLE)
        self._add_button.clicked.connect(self.new_session_requested)

        layout.addWidget(self._add_button, 0)

        # Push action buttons to the right
        layout.addStretch(1)

        # --- Compare button ---
        self._compare_button = QPushButton("Compare")
        self._compare_button.setStyleSheet(_COMPARE_BUTTON_STYLE)
        self._compare_button.clicked.connect(self.compare_requested)

        layout.addWidget(self._compare_button, 0)

        # --- Stop button ---
        self._stop_button = QPushButton("Stop")
        self._stop_button.setStyleSheet(_STOP_BUTTON_STYLE)
        self._stop_button.clicked.connect(self.stop_requested)
        self._stop_button.setVisible(False)

        layout.addWidget(self._stop_button, 0)

        # Bottom border via the widget's own stylesheet
        self.setStyleSheet(
            "SessionTabBar { border-bottom: 1px solid palette(mid); }"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_session(self, name: str) -> int:
        """Add a new tab with the given *name* and return its index."""
        index = self._tab_bar.addTab(name)
        self._tab_bar.setCurrentIndex(index)
        return index

    def remove_session(self, index: int) -> None:
        """Remove the tab at *index*."""
        if 0 <= index < self._tab_bar.count():
            self._tab_bar.removeTab(index)

    def set_session_name(self, index: int, name: str) -> None:
        """Update the label text for the tab at *index*."""
        if 0 <= index < self._tab_bar.count():
            self._tab_bar.setTabText(index, name)

    def set_comparing(self, active: bool) -> None:
        """Toggle between Compare and Stop button visibility.

        When *active* is ``True`` the Stop button is shown and Compare is
        hidden, indicating a comparison is in progress.  When ``False`` the
        Compare button is restored.
        """
        self._compare_button.setVisible(not active)
        self._stop_button.setVisible(active)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_index(self) -> int:
        """Return the index of the currently selected tab, or -1 if none."""
        return self._tab_bar.currentIndex()

    @current_index.setter
    def current_index(self, index: int) -> None:
        """Set the currently selected tab to *index*."""
        self._tab_bar.setCurrentIndex(index)
