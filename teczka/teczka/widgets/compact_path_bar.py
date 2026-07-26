"""CompactPathBar - single-row path bar with left/right breadcrumbs and swap button."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from teczka import icons
from teczka.utils.path_picker import pick_folder
from teczka.widgets.breadcrumb_bar import BreadcrumbBar


class CompactPathBar(QWidget):
    """A compact single-row path bar for two-way (or three-way) comparison.

    Layout (2-way):
        [Left BreadcrumbBar] [swap button] [Right BreadcrumbBar]

    Layout (3-way):
        Row 1: [Left BreadcrumbBar] [swap button] [Right BreadcrumbBar]
        Row 2: [Base label] [Base BreadcrumbBar]

    Signals:
        left_path_changed(str): Emitted when the left path changes.
        right_path_changed(str): Emitted when the right path changes.
        base_path_changed(str): Emitted when the base path changes.
        swap_requested(): Emitted when the swap button is clicked.
    """

    left_path_changed = Signal(str)
    right_path_changed = Signal(str)
    base_path_changed = Signal(str)
    swap_requested = Signal()

    # Fallback only; the real row height is derived from the breadcrumb bars in
    # __init__ so the row grows with the system font instead of clipping it.
    _ROW_HEIGHT = 32

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._three_way = False
        self._row_height = self._ROW_HEIGHT

        # --- Outer vertical layout ---
        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)
        self._outer_layout.setSpacing(0)

        # --- Primary row: left + swap + right ---
        primary_row = QWidget()
        self._primary_row = primary_row
        primary_layout = QHBoxLayout(primary_row)
        primary_layout.setContentsMargins(4, 0, 4, 0)
        primary_layout.setSpacing(4)

        self._left_bar = BreadcrumbBar()
        self._left_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._left_bar.path_changed.connect(self._on_left_changed)
        self._left_browse = self._make_browse_button(
            "Select the left folder (local or mounted network location)",
            self._on_browse_left,
        )

        self._swap_button = QToolButton()
        # icons.icon() falls back to an embedded SVG, so the control is never
        # a blank square on a session without a complete FreeDesktop theme.
        self._swap_button.setIcon(
            icons.icon("object-flip-horizontal", icons.SWAP_SVG)
        )
        self._swap_button.setToolTip("Swap left and right paths")
        self._swap_button.setAccessibleName("Swap left and right paths")
        self._swap_button.setFixedSize(24, 24)
        self._swap_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swap_button.setStyleSheet(
            "QToolButton { border: 1px solid palette(mid);"
            " border-radius: 3px; background: palette(button); }"
            "QToolButton:hover { background: palette(light); }"
            "QToolButton:pressed { background: palette(dark); }"
        )
        self._swap_button.clicked.connect(self._on_swap_clicked)

        self._right_bar = BreadcrumbBar()
        self._right_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._right_bar.path_changed.connect(self._on_right_changed)
        self._right_browse = self._make_browse_button(
            "Select the right folder (local or mounted network location)",
            self._on_browse_right,
        )

        primary_layout.addWidget(self._left_bar, 1)
        primary_layout.addWidget(self._left_browse, 0)
        primary_layout.addWidget(self._swap_button, 0)
        primary_layout.addWidget(self._right_bar, 1)
        primary_layout.addWidget(self._right_browse, 0)

        self._outer_layout.addWidget(primary_row)

        # --- Base row (hidden by default, shown in 3-way mode) ---
        self._base_row = QWidget()
        base_layout = QHBoxLayout(self._base_row)
        base_layout.setContentsMargins(4, 0, 4, 0)
        base_layout.setSpacing(4)

        base_label = QLabel("Base:")
        base_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        base_label.setStyleSheet("QLabel { color: palette(mid); font-weight: bold; }")

        self._base_bar = BreadcrumbBar()
        self._base_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._base_bar.path_changed.connect(self._on_base_changed)
        self._base_browse = self._make_browse_button(
            "Select the base (ancestor) folder",
            self._on_browse_base,
        )

        base_layout.addWidget(base_label, 0)
        base_layout.addWidget(self._base_bar, 1)
        base_layout.addWidget(self._base_browse, 0)

        self._base_row.setVisible(False)
        self._outer_layout.addWidget(self._base_row)

        # --- Row sizing ---
        # Derived from the breadcrumb bars, which size themselves to the
        # current font. A fixed 32px clipped the path text once the system
        # font or display scaling grew.
        self._row_height = max(
            self._left_bar.height(),
            self._right_bar.height(),
            self._base_bar.height(),
            self._ROW_HEIGHT,
        )
        self._primary_row.setFixedHeight(self._row_height)
        self._base_row.setFixedHeight(self._row_height)

        # --- Styling: subtle bottom border only ---
        self.setFixedHeight(self._row_height)
        self.setStyleSheet(
            "CompactPathBar { border: none; border-bottom: 1px solid palette(mid); }"
        )

    # ------------------------------------------------------------------
    # Browse buttons
    # ------------------------------------------------------------------

    def _make_browse_button(self, tooltip: str, slot) -> QToolButton:
        """Build a compact folder-picker button matching the swap button."""
        button = QToolButton()
        button.setIcon(icons.icon("folder-open", icons.FOLDER_SVG))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(24, 24)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            "QToolButton { border: 1px solid palette(mid);"
            " border-radius: 3px; background: palette(button); }"
            "QToolButton:hover { background: palette(light); }"
            "QToolButton:pressed { background: palette(dark); }"
        )
        button.clicked.connect(slot)
        return button

    def _on_browse_left(self) -> None:
        chosen = pick_folder(self, "Select Left Folder", self._left_bar.path)
        if chosen:
            self._left_bar.path = chosen
            self.left_path_changed.emit(chosen)

    def _on_browse_right(self) -> None:
        chosen = pick_folder(self, "Select Right Folder", self._right_bar.path)
        if chosen:
            self._right_bar.path = chosen
            self.right_path_changed.emit(chosen)

    def _on_browse_base(self) -> None:
        chosen = pick_folder(self, "Select Base Folder", self._base_bar.path)
        if chosen:
            self._base_bar.path = chosen
            self.base_path_changed.emit(chosen)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def left_path(self) -> str:
        """Return the current left path."""
        return self._left_bar.path

    @left_path.setter
    def left_path(self, value: str) -> None:
        """Set the left path."""
        self._left_bar.path = value

    @property
    def right_path(self) -> str:
        """Return the current right path."""
        return self._right_bar.path

    @right_path.setter
    def right_path(self, value: str) -> None:
        """Set the right path."""
        self._right_bar.path = value

    @property
    def base_path(self) -> str:
        """Return the current base path."""
        return self._base_bar.path

    @base_path.setter
    def base_path(self, value: str) -> None:
        """Set the base path."""
        self._base_bar.path = value

    # ------------------------------------------------------------------
    # Three-way mode
    # ------------------------------------------------------------------

    def set_three_way_mode(self, enabled: bool) -> None:
        """Show or hide the base-path row for three-way comparisons."""
        self._three_way = enabled
        self._base_row.setVisible(enabled)
        if enabled:
            self.setFixedHeight(self._row_height * 2)
        else:
            self.setFixedHeight(self._row_height)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_left_changed(self, path: str) -> None:
        self.left_path_changed.emit(path)

    def _on_right_changed(self, path: str) -> None:
        self.right_path_changed.emit(path)

    def _on_base_changed(self, path: str) -> None:
        self.base_path_changed.emit(path)

    def _on_swap_clicked(self) -> None:
        """Emit swap *intent* only.

        This widget used to perform the swap itself and then emit
        ``swap_requested``, whose handler swapped again — two swaps, no visible
        change. Mutation belongs to whoever owns the session state; this bar is
        a view of it.
        """
        self.swap_requested.emit()
