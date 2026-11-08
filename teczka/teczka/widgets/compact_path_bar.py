"""CompactPathBar - single-row path bar with left/right breadcrumbs and swap button."""

from __future__ import annotations

import os

from PySide6.QtCore import QDir, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

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

    _ROW_HEIGHT = 32

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._three_way = False

        # --- Outer vertical layout ---
        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)
        self._outer_layout.setSpacing(0)

        # --- Primary row: left + swap + right ---
        primary_row = QWidget()
        primary_row.setFixedHeight(self._ROW_HEIGHT)
        primary_layout = QHBoxLayout(primary_row)
        primary_layout.setContentsMargins(4, 0, 4, 0)
        primary_layout.setSpacing(4)

        self._left_label = QLabel("LHS")
        self._left_label.setToolTip("Left-hand folder")
        self._left_label.setAccessibleName("Left-hand side")
        self._left_label.setFixedWidth(32)
        self._left_label.setStyleSheet("QLabel { font-weight: bold; }")

        self._left_bar = BreadcrumbBar()
        self._left_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._left_bar.path_changed.connect(self._on_left_changed)
        self._left_browse_button = QPushButton("Browse…")
        self._left_browse_button.setObjectName("leftFolderBrowseButton")
        self._left_browse_button.setAccessibleName("Browse for left-hand folder")
        self._left_browse_button.setToolTip("Choose the left-hand folder to compare")
        self._left_browse_button.setFixedHeight(24)
        self._left_browse_button.clicked.connect(self._browse_left)

        left_panel = QWidget()
        left_layout = QHBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        left_layout.addWidget(self._left_label)
        left_layout.addWidget(self._left_bar, 1)
        left_layout.addWidget(self._left_browse_button)

        self._swap_button = QToolButton()
        icon = QIcon.fromTheme("object-flip-horizontal")
        if icon.isNull():
            self._swap_button.setText("\u27f7")
        else:
            self._swap_button.setIcon(icon)
        self._swap_button.setToolTip("Swap left and right paths")
        self._swap_button.setFixedSize(24, 24)
        self._swap_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swap_button.setStyleSheet(
            "QToolButton { border: 1px solid palette(mid);"
            " border-radius: 3px; background: palette(button); }"
            "QToolButton:hover { background: palette(light); }"
            "QToolButton:pressed { background: palette(dark); }"
        )
        self._swap_button.clicked.connect(self._on_swap_clicked)

        self._right_label = QLabel("RHS")
        self._right_label.setToolTip("Right-hand folder")
        self._right_label.setAccessibleName("Right-hand side")
        self._right_label.setFixedWidth(32)
        self._right_label.setStyleSheet("QLabel { font-weight: bold; }")

        self._right_bar = BreadcrumbBar()
        self._right_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._right_bar.path_changed.connect(self._on_right_changed)
        self._right_browse_button = QPushButton("Browse…")
        self._right_browse_button.setObjectName("rightFolderBrowseButton")
        self._right_browse_button.setAccessibleName("Browse for right-hand folder")
        self._right_browse_button.setToolTip("Choose the right-hand folder to compare")
        self._right_browse_button.setFixedHeight(24)
        self._right_browse_button.clicked.connect(self._browse_right)

        right_panel = QWidget()
        right_layout = QHBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(self._right_label)
        right_layout.addWidget(self._right_bar, 1)
        right_layout.addWidget(self._right_browse_button)

        primary_layout.addWidget(left_panel, 1)
        primary_layout.addWidget(self._swap_button, 0)
        primary_layout.addWidget(right_panel, 1)

        self._outer_layout.addWidget(primary_row)

        # --- Base row (hidden by default, shown in 3-way mode) ---
        self._base_row = QWidget()
        self._base_row.setFixedHeight(self._ROW_HEIGHT)
        base_layout = QHBoxLayout(self._base_row)
        base_layout.setContentsMargins(4, 0, 4, 0)
        base_layout.setSpacing(4)

        base_label = QLabel("Base:")
        base_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        base_label.setStyleSheet("QLabel { color: palette(mid); font-weight: bold; }")

        self._base_bar = BreadcrumbBar()
        self._base_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._base_bar.path_changed.connect(self._on_base_changed)
        self._base_browse_button = QPushButton("Browse…")
        self._base_browse_button.setObjectName("baseFolderBrowseButton")
        self._base_browse_button.setAccessibleName("Browse for base folder")
        self._base_browse_button.setToolTip("Choose the common base folder")
        self._base_browse_button.setFixedHeight(24)
        self._base_browse_button.clicked.connect(self._browse_base)

        base_layout.addWidget(base_label, 0)
        base_layout.addWidget(self._base_bar, 1)
        base_layout.addWidget(self._base_browse_button, 0)

        self._base_row.setVisible(False)
        self._outer_layout.addWidget(self._base_row)

        # --- Styling: subtle bottom border only ---
        self.setFixedHeight(self._ROW_HEIGHT)
        self.setStyleSheet(
            "CompactPathBar { border: none; border-bottom: 1px solid palette(mid); }"
        )

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
            self.setFixedHeight(self._ROW_HEIGHT * 2)
        else:
            self.setFixedHeight(self._ROW_HEIGHT)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_left_changed(self, path: str) -> None:
        self.left_path_changed.emit(path)

    def _on_right_changed(self, path: str) -> None:
        self.right_path_changed.emit(path)

    def _on_base_changed(self, path: str) -> None:
        self.base_path_changed.emit(path)

    def _browse_left(self) -> None:
        self._browse_folder("left")

    def _browse_right(self) -> None:
        self._browse_folder("right")

    def _browse_base(self) -> None:
        self._browse_folder("base")

    def _browse_folder(self, side: str) -> None:
        """Open a directory picker for one comparison side."""
        bars = {
            "left": (self._left_bar, "Left"),
            "right": (self._right_bar, "Right"),
            "base": (self._base_bar, "Base"),
        }
        bar, side_label = bars[side]
        current_path = bar.path
        start_dir = current_path if os.path.isdir(current_path) else QDir.homePath()
        selected_path = QFileDialog.getExistingDirectory(
            self,
            f"Select {side_label} Folder",
            start_dir,
            QFileDialog.Option.ShowDirsOnly,
        )
        if not selected_path:
            return

        bar.path = selected_path
        bar.path_changed.emit(bar.path)

    def _on_swap_clicked(self) -> None:
        left = self._left_bar.path
        right = self._right_bar.path
        self._left_bar.path = right
        self._right_bar.path = left
        self.swap_requested.emit()
        self.left_path_changed.emit(self._left_bar.path)
        self.right_path_changed.emit(self._right_bar.path)
