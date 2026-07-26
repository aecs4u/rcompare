"""Visible tab surface for open comparison documents.

Double-clicking a file in Folder Compare opens a Text/Hex/Image/Table
comparison. Those documents used to be registered in a *hidden* ``QTabBar``:
the widget appeared in the view stack with no visible tab, no close action and
no way back other than the sidebar. This bar makes them real.

The first tab is the originating context (the base view the documents were
opened from) and cannot be closed; it is the return path. Every other tab is a
document and is closable. The whole bar hides itself when no documents are
open, so it costs nothing in the common case.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QTabBar, QWidget

_TAB_BAR_STYLE = """
QTabBar {
    border: none;
    background: transparent;
}
QTabBar::tab {
    border: none;
    border-bottom: 2px solid transparent;
    padding: 3px 10px;
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
"""


class DocumentTabBar(QWidget):
    """Tab strip listing the active context plus every open comparison document.

    Signals:
        document_selected(int): stack index of the newly selected tab.
        document_close_requested(int): stack index the user asked to close.
    """

    document_selected = Signal(int)
    document_close_requested = Signal(int)

    _CONTEXT_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(26)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(0)

        self._tab_bar = QTabBar()
        self._tab_bar.setExpanding(False)
        self._tab_bar.setDrawBase(False)
        self._tab_bar.setDocumentMode(True)
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setElideMode(Qt.TextElideMode.ElideMiddle)
        self._tab_bar.setStyleSheet(_TAB_BAR_STYLE)
        self._tab_bar.setAccessibleName("Open comparison documents")
        self._tab_bar.currentChanged.connect(self._on_current_changed)
        self._tab_bar.tabCloseRequested.connect(self._on_close_requested)
        layout.addWidget(self._tab_bar, 0)
        layout.addStretch(1)

        self._suppress_signals = False
        self.setVisible(False)

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def set_context(self, label: str, stack_index: int) -> None:
        """Set the non-closable first tab describing where documents came from."""
        self._suppress_signals = True
        if self._tab_bar.count() == 0:
            self._tab_bar.addTab(label)
        else:
            self._tab_bar.setTabText(0, label)
        self._tab_bar.setTabData(0, stack_index)
        # A close button on the context tab would imply the base view can be
        # dismissed, which it cannot.
        for position in (
            QTabBar.ButtonPosition.RightSide,
            QTabBar.ButtonPosition.LeftSide,
        ):
            self._tab_bar.setTabButton(0, position, None)
        self._suppress_signals = False
        self._update_visibility()

    def add_document(self, label: str, stack_index: int) -> int:
        """Append a closable document tab and return its tab index."""
        self._suppress_signals = True
        tab_index = self._tab_bar.addTab(label)
        self._tab_bar.setTabData(tab_index, stack_index)
        self._tab_bar.setTabToolTip(tab_index, label)
        self._suppress_signals = False
        self._update_visibility()
        return tab_index

    def remove_document(self, stack_index: int) -> None:
        """Remove the tab pointing at *stack_index*, if present."""
        tab_index = self._tab_index_for(stack_index)
        if tab_index is None or tab_index == 0:
            return
        self._suppress_signals = True
        self._tab_bar.removeTab(tab_index)
        self._suppress_signals = False
        self._update_visibility()

    def reindex(self, remap: dict[int, int]) -> None:
        """Rewrite stored stack indices after the view stack shifts.

        *remap* maps old stack index to new stack index; tabs whose index is
        absent from the map are left alone.
        """
        for tab_index in range(self._tab_bar.count()):
            stored = self._tab_bar.tabData(tab_index)
            if isinstance(stored, int) and stored in remap:
                self._tab_bar.setTabData(tab_index, remap[stored])

    def clear_documents(self) -> None:
        """Remove every document tab, keeping the context tab."""
        self._suppress_signals = True
        while self._tab_bar.count() > 1:
            self._tab_bar.removeTab(self._tab_bar.count() - 1)
        self._suppress_signals = False
        self._update_visibility()

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select_stack_index(self, stack_index: int) -> None:
        """Highlight the tab pointing at *stack_index* without emitting."""
        tab_index = self._tab_index_for(stack_index)
        if tab_index is None:
            return
        self._suppress_signals = True
        self._tab_bar.setCurrentIndex(tab_index)
        self._suppress_signals = False

    def stack_indices(self) -> list[int]:
        """Return the stack index behind every tab, context tab first."""
        result: list[int] = []
        for tab_index in range(self._tab_bar.count()):
            stored = self._tab_bar.tabData(tab_index)
            if isinstance(stored, int):
                result.append(stored)
        return result

    @property
    def document_count(self) -> int:
        """Number of open documents, excluding the context tab."""
        return max(0, self._tab_bar.count() - 1)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _tab_index_for(self, stack_index: int) -> int | None:
        for tab_index in range(self._tab_bar.count()):
            if self._tab_bar.tabData(tab_index) == stack_index:
                return tab_index
        return None

    def _on_current_changed(self, tab_index: int) -> None:
        if self._suppress_signals or tab_index < 0:
            return
        stored = self._tab_bar.tabData(tab_index)
        if isinstance(stored, int):
            self.document_selected.emit(stored)

    def _on_close_requested(self, tab_index: int) -> None:
        if tab_index <= 0:
            return
        stored = self._tab_bar.tabData(tab_index)
        if isinstance(stored, int):
            self.document_close_requested.emit(stored)

    def _update_visibility(self) -> None:
        # Nothing to navigate between until a document exists.
        self.setVisible(self.document_count > 0)
