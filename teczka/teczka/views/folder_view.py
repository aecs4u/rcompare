"""Side-by-side folder comparison view (Beyond Compare style)."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QByteArray, Qt, Signal, QModelIndex, QPoint, QTimer
from PySide6.QtGui import QColor, QPainter, QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QSplitter,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from ..models.comparison import TreeNode
from ..models.tree_model import (
    COL_LEFT_DATE,
    COL_LEFT_SIZE,
    COL_EXTENSION,
    COL_NAME,
    COL_PATH,
    COL_RIGHT_DATE,
    COL_RIGHT_SIZE,
    COL_STATUS,
    COL_TYPE,
    ComparisonFilterProxy,
    ComparisonTreeModel,
)
from ..utils.cli_bridge import DiffStatus
from ..workers.function_worker import FunctionWorker

_PREVIEW_DEBOUNCE_MS = 200
_PREVIEW_MAX_LINES = 100
_PREVIEW_MAX_BYTES = 64 * 1024  # 64 KB
_AUTO_SIZE_NODE_LIMIT = 2_000
_COLUMN_STATE_VERSION = 2

_COLUMN_TITLES = {
    COL_NAME: "Name",
    COL_LEFT_SIZE: "Size",
    COL_LEFT_DATE: "Modified",
    COL_STATUS: "Comparison status",
    COL_RIGHT_SIZE: "Size",
    COL_RIGHT_DATE: "Modified",
    COL_EXTENSION: "Extension",
    COL_TYPE: "Type",
    COL_PATH: "Relative path",
}


def _read_preview_side(root: str, rel_path: str) -> str:
    """Read a bounded preview of one side's file. Runs off the GUI thread
    so slow/network storage doesn't stall the UI.
    """
    if not root:
        return ""

    full_path = os.path.join(root, rel_path)
    if not os.path.isfile(full_path):
        return "(not present on this side)"

    try:
        size = os.path.getsize(full_path)
        if size > _PREVIEW_MAX_BYTES:
            with open(full_path, "r", errors="replace") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= _PREVIEW_MAX_LINES:
                        break
                    lines.append(line.rstrip("\n"))
            lines.append(f"\n... (truncated, {size:,} bytes total)")
            return "\n".join(lines)
        with open(full_path, "r", errors="replace") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return "(binary or unreadable file)"


def _read_preview_pair(left_root: str, right_root: str, rel_path: str) -> tuple[str, str]:
    return _read_preview_side(left_root, rel_path), _read_preview_side(right_root, rel_path)


# Row background colours keyed by DiffStatus
_STATUS_COLORS: dict[DiffStatus, QColor] = {
    DiffStatus.SAME: QColor("#ffffff"),
    DiffStatus.DIFFERENT: QColor("#ffe1e1"),
    DiffStatus.ORPHAN_LEFT: QColor("#dbe8ff"),
    DiffStatus.ORPHAN_RIGHT: QColor("#ffd2d9"),
    DiffStatus.UNCHECKED: QColor("#f1f4f8"),
}


class DiffStatusDelegate(QStyledItemDelegate):
    """Paints row backgrounds based on the DiffStatus stored in Qt.UserRole."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        status = index.data(Qt.UserRole)
        if status is not None and status in _STATUS_COLORS:
            bg = _STATUS_COLORS[status]
            if status != DiffStatus.SAME:
                painter.fillRect(option.rect, bg)
        super().paint(painter, option, index)


class FolderView(QWidget):
    """Side-by-side tree view for folder comparison results.

    The left tree displays Name / Left Size / Left Date columns while the
    right tree displays Name / Right Size / Right Date columns.  Row
    backgrounds are painted by a :class:`DiffStatusDelegate` to indicate
    the comparison status (identical, different, left-only, right-only,
    unchecked).

    The two trees are synchronised: expanding or collapsing a node in one
    tree automatically mirrors the action in the other, and vertical
    scrolling is kept in lock-step.
    """

    # Emitted on double-click.  Arguments: (relative_path, is_directory)
    file_activated = Signal(str, bool)
    # Emitted from context menu. Arguments: (command, relative_path, side)
    context_command = Signal(str, str, str)
    # Emitted whenever the selected row changes, so the window can enable or
    # disable the copy/apply actions that need a selection.
    selection_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Models -------------------------------------------------------
        self._source_model = ComparisonTreeModel(self)
        self._proxy_model = ComparisonFilterProxy(self)
        self._proxy_model.setSourceModel(self._source_model)

        # Delegates ----------------------------------------------------
        self._delegate = DiffStatusDelegate(self)

        # Trees --------------------------------------------------------
        self._left_tree = self._create_tree()
        self._right_tree = self._create_tree()

        self._configure_left_tree()
        self._configure_right_tree()
        self._column_menus: dict[QTreeView, QMenu] = {}
        self._left_pane = self._build_pane(self._left_tree, "left")
        self._right_pane = self._build_pane(self._right_tree, "right")

        # Layout -------------------------------------------------------
        self._tree_splitter = QSplitter(Qt.Horizontal)
        self._tree_splitter.setObjectName("comparisonSplitter")
        self._tree_splitter.addWidget(self._left_pane)
        self._tree_splitter.addWidget(self._right_pane)
        self._tree_splitter.setStretchFactor(0, 1)
        self._tree_splitter.setStretchFactor(1, 1)
        self._tree_splitter.setChildrenCollapsible(False)

        # Preview panel (collapsible below the trees)
        self._preview_splitter = QSplitter(Qt.Vertical)

        self._left_preview = QPlainTextEdit()
        self._left_preview.setReadOnly(True)
        self._left_preview.setMaximumHeight(200)
        self._left_preview.setPlaceholderText("Select a file to preview left side")

        self._right_preview = QPlainTextEdit()
        self._right_preview.setReadOnly(True)
        self._right_preview.setMaximumHeight(200)
        self._right_preview.setPlaceholderText("Select a file to preview right side")

        preview_container = QSplitter(Qt.Horizontal)
        preview_container.addWidget(self._left_preview)
        preview_container.addWidget(self._right_preview)
        preview_container.setStretchFactor(0, 1)
        preview_container.setStretchFactor(1, 1)

        self._preview_splitter.addWidget(self._tree_splitter)
        self._preview_splitter.addWidget(preview_container)
        self._preview_splitter.setStretchFactor(0, 3)
        self._preview_splitter.setStretchFactor(1, 1)
        self._preview_visible = False
        preview_container.hide()
        self._preview_container = preview_container

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._preview_splitter)

        self.setStyleSheet(
            """
            QFrame#folderPane {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 7px;
            }
            QWidget#paneHeader {
                background-color: palette(alternate-base);
                border-bottom: 1px solid palette(mid);
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
            }
            QLabel#sideBadge {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                border-radius: 8px;
                font-size: 10px;
                font-weight: 700;
            }
            QLabel#paneTitle {
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#paneHint {
                color: palette(text);
                font-size: 10px;
            }
            QToolButton#columnsButton {
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 4px 8px;
            }
            QToolButton#columnsButton:hover,
            QToolButton#columnsButton:pressed {
                background-color: palette(button);
                border-color: palette(mid);
            }
            QTreeView#comparisonTree {
                border: none;
                border-bottom-left-radius: 7px;
                border-bottom-right-radius: 7px;
            }
            QSplitter#comparisonSplitter::handle {
                background-color: transparent;
                width: 8px;
            }
            """
        )

        # Synchronisation guards ---------------------------------------
        self._syncing_scroll = False
        self._syncing_expand = False
        self._preview_left_root = ""
        self._preview_right_root = ""
        self._preview_pending_path: Optional[str] = None
        self._preview_request_path: Optional[str] = None
        self._preview_worker: Optional[FunctionWorker] = None
        self._preview_debounce_timer = QTimer(self)
        self._preview_debounce_timer.setSingleShot(True)
        self._preview_debounce_timer.setInterval(_PREVIEW_DEBOUNCE_MS)
        self._preview_debounce_timer.timeout.connect(self._trigger_preview_load)

        # Connect synchronisation signals ------------------------------
        self._connect_sync()
        self._has_persisted_widths = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tree(self, root: TreeNode) -> None:
        """Replace the comparison data with a new tree."""
        self._source_model.set_tree(root)
        if not self._has_persisted_widths:
            # Defer column sizing until after model-reset/layout updates complete.
            QTimer.singleShot(0, self._resize_visible_columns)

    def expand_all(self) -> None:
        """Expand every node in both trees."""
        self._left_tree.expandAll()
        self._right_tree.expandAll()

    def collapse_all(self) -> None:
        """Collapse every node in both trees."""
        self._left_tree.collapseAll()
        self._right_tree.collapseAll()

    def set_filters(
        self,
        show_identical: bool,
        show_different: bool,
        show_left_only: bool,
        show_right_only: bool,
        show_files_only: bool = False,
        search_text: str = "",
        diff_option_mode: Optional[str] = None,
    ) -> None:
        """Apply visibility and search filters in a single proxy invalidation."""
        self._proxy_model.apply_filters(
            show_identical,
            show_different,
            show_left_only,
            show_right_only,
            show_files_only,
            search_text,
            diff_option_mode,
        )

    def set_diff_option_mode(self, mode: str) -> None:
        self._proxy_model.set_diff_option_mode(mode)

    def selected_paths(self) -> list[str]:
        """Return unique selected relative paths from both trees."""
        paths: set[str] = set()
        for tree in (self._left_tree, self._right_tree):
            sel_model = tree.selectionModel()
            if sel_model is None:
                continue
            for index in sel_model.selectedRows(COL_NAME):
                node: Optional[TreeNode] = index.data(Qt.UserRole + 1)
                if node is not None and node.path:
                    paths.add(node.path)
        return sorted(paths)

    def select_path(self, rel_path: str) -> None:
        """Select and scroll to a row by its relative path."""
        proxy = self._proxy_model
        source = self._source_model

        def _find_in_model(parent: QModelIndex, target: str) -> Optional[QModelIndex]:
            for row in range(source.rowCount(parent)):
                idx = source.index(row, COL_NAME, parent)
                node: Optional[TreeNode] = idx.data(Qt.UserRole + 1)
                if node is not None and node.path == target:
                    return idx
                # Recurse into children
                child = _find_in_model(idx, target)
                if child is not None:
                    return child
            return None

        source_idx = _find_in_model(QModelIndex(), rel_path)
        if source_idx is None:
            return

        proxy_idx = proxy.mapFromSource(source_idx)
        if not proxy_idx.isValid():
            return

        for tree in (self._left_tree, self._right_tree):
            sel = tree.selectionModel()
            if sel is not None:
                sel.clearSelection()
                sel.select(proxy_idx, sel.SelectionFlag.Select | sel.SelectionFlag.Rows)
                tree.scrollTo(proxy_idx, QAbstractItemView.ScrollHint.PositionAtCenter)
                # Ensure parent is expanded
                parent = proxy_idx.parent()
                while parent.isValid():
                    tree.expand(parent)
                    parent = parent.parent()

    def select_next_match(self) -> bool:
        """Move selection to the next visible row. Returns True if wrapped."""
        return self._navigate_match(forward=True)

    def select_prev_match(self) -> bool:
        """Move selection to the previous visible row. Returns True if wrapped."""
        return self._navigate_match(forward=False)

    def _navigate_match(self, forward: bool) -> bool:
        """Navigate to next/previous visible row in proxy model."""
        proxy = self._proxy_model
        total = proxy.rowCount(QModelIndex())
        if total == 0:
            return False

        # Get current selection
        sel = self._left_tree.selectionModel()
        current = sel.currentIndex() if sel else QModelIndex()

        def _flat_indices(parent: QModelIndex) -> list[QModelIndex]:
            """Collect all visible proxy indices in depth-first order."""
            result = []
            for row in range(proxy.rowCount(parent)):
                idx = proxy.index(row, COL_NAME, parent)
                result.append(idx)
                result.extend(_flat_indices(idx))
            return result

        flat = _flat_indices(QModelIndex())
        if not flat:
            return False

        # Find current position
        current_pos = -1
        for i, idx in enumerate(flat):
            if idx == current:
                current_pos = i
                break

        if forward:
            next_pos = (current_pos + 1) % len(flat)
        else:
            next_pos = (current_pos - 1) % len(flat)

        wrapped = (forward and next_pos <= current_pos) or (not forward and next_pos >= current_pos)
        target = flat[next_pos]

        for tree in (self._left_tree, self._right_tree):
            s = tree.selectionModel()
            if s is not None:
                s.setCurrentIndex(target, s.SelectionFlag.ClearAndSelect | s.SelectionFlag.Rows)
                tree.scrollTo(target, QAbstractItemView.ScrollHint.PositionAtCenter)

        return wrapped and current_pos >= 0

    @property
    def left_tree(self) -> QTreeView:
        return self._left_tree

    @property
    def right_tree(self) -> QTreeView:
        return self._right_tree

    @property
    def source_model(self) -> ComparisonTreeModel:
        return self._source_model

    @property
    def proxy_model(self) -> ComparisonFilterProxy:
        return self._proxy_model

    def column_widths(self) -> dict[str, object]:
        """Return each pane's complete column layout for persistence."""
        left_header = self._left_tree.header()
        right_header = self._right_tree.header()
        return {
            "version": _COLUMN_STATE_VERSION,
            "left_header_state": (
                bytes(left_header.saveState().toBase64().data()).decode("ascii")
                if left_header is not None
                else ""
            ),
            "right_header_state": (
                bytes(right_header.saveState().toBase64().data()).decode("ascii")
                if right_header is not None
                else ""
            ),
            # Keep explicit widths for compatibility with older config files.
            "left_name": self._left_tree.columnWidth(COL_NAME),
            "left_size": self._left_tree.columnWidth(COL_LEFT_SIZE),
            "left_date": self._left_tree.columnWidth(COL_LEFT_DATE),
            "right_name": self._right_tree.columnWidth(COL_NAME),
            "right_size": self._right_tree.columnWidth(COL_RIGHT_SIZE),
            "right_date": self._right_tree.columnWidth(COL_RIGHT_DATE),
        }

    def set_column_widths(self, widths: dict[str, object]) -> None:
        """Restore column visibility, order, and widths for both panes."""
        applied = False

        if widths.get("version") == _COLUMN_STATE_VERSION:
            for tree, key in (
                (self._left_tree, "left_header_state"),
                (self._right_tree, "right_header_state"),
            ):
                encoded = widths.get(key)
                header = tree.header()
                if isinstance(encoded, str) and encoded and header is not None:
                    state = QByteArray.fromBase64(encoded.encode("ascii"))
                    applied = header.restoreState(state) or applied

        def _set(tree: QTreeView, column: int, value: object) -> None:
            nonlocal applied
            if isinstance(value, int) and value > 0:
                tree.setColumnWidth(column, value)
                applied = True

        _set(self._left_tree, COL_NAME, widths.get("left_name"))
        _set(self._left_tree, COL_LEFT_SIZE, widths.get("left_size"))
        _set(self._left_tree, COL_LEFT_DATE, widths.get("left_date"))
        _set(self._right_tree, COL_NAME, widths.get("right_name"))
        _set(self._right_tree, COL_RIGHT_SIZE, widths.get("right_size"))
        _set(self._right_tree, COL_RIGHT_DATE, widths.get("right_date"))

        # A corrupt or stale header state must never reveal the other side's
        # size/date columns or hide the primary Name column.
        self._enforce_side_columns(self._left_tree, "left")
        self._enforce_side_columns(self._right_tree, "right")
        self._sync_column_menu(self._left_tree)
        self._sync_column_menu(self._right_tree)

        if applied:
            self._has_persisted_widths = True

    # ------------------------------------------------------------------
    # Tree construction helpers
    # ------------------------------------------------------------------

    def _build_pane(self, tree: QTreeView, side: str) -> QFrame:
        """Wrap a comparison tree in a labelled, self-contained pane."""
        pane = QFrame(self)
        pane.setObjectName("folderPane")
        pane_layout = QVBoxLayout(pane)
        pane_layout.setContentsMargins(0, 0, 0, 0)
        pane_layout.setSpacing(0)

        header_bar = QWidget(pane)
        header_bar.setObjectName("paneHeader")
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(10, 7, 7, 7)
        header_layout.setSpacing(8)

        badge = QLabel("L" if side == "left" else "R", header_bar)
        badge.setObjectName("sideBadge")
        badge.setFixedSize(17, 17)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Left side" if side == "left" else "Right side", header_bar)
        title.setObjectName("paneTitle")
        hint = QLabel("Comparison pane", header_bar)
        hint.setObjectName("paneHint")

        menu = self._build_column_menu(tree, side)
        self._column_menus[tree] = menu
        columns_button = QToolButton(header_bar)
        columns_button.setObjectName("columnsButton")
        columns_button.setText("Columns")
        columns_button.setToolTip(f"Choose columns shown on the {side} side")
        columns_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        columns_button.setMenu(menu)

        header_layout.addWidget(badge)
        header_layout.addWidget(title)
        header_layout.addWidget(hint)
        header_layout.addStretch(1)
        header_layout.addWidget(columns_button)
        pane_layout.addWidget(header_bar)
        pane_layout.addWidget(tree, 1)
        return pane

    def _create_tree(self) -> QTreeView:
        """Build a QTreeView with shared settings."""
        tree = QTreeView(self)
        tree.setObjectName("comparisonTree")
        tree.setModel(self._proxy_model)
        tree.setItemDelegate(self._delegate)

        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        tree.setUniformRowHeights(True)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.setRootIsDecorated(True)
        tree.setItemsExpandable(True)
        tree.setAnimated(True)
        header = tree.header()
        if header is not None:
            header.setStretchLastSection(False)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setSectionsMovable(True)
            header.setSectionsClickable(True)
            header.setMinimumSectionSize(52)
            header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            header.setToolTip("Drag columns to reorder · Right-click to choose columns")
            header.customContextMenuRequested.connect(
                lambda pos, current_tree=tree: self._show_column_menu(current_tree, pos)
            )

        tree.customContextMenuRequested.connect(self._on_context_menu)
        tree.doubleClicked.connect(self._on_double_click)

        return tree

    def _configure_left_tree(self) -> None:
        """Apply the default left-side column set."""
        self._left_tree.setColumnHidden(COL_RIGHT_SIZE, True)
        self._left_tree.setColumnHidden(COL_RIGHT_DATE, True)
        self._reset_columns(self._left_tree, "left", sync_menu=False)

    def _configure_right_tree(self) -> None:
        """Apply the default right-side column set."""
        self._right_tree.setColumnHidden(COL_LEFT_SIZE, True)
        self._right_tree.setColumnHidden(COL_LEFT_DATE, True)
        self._reset_columns(self._right_tree, "right", sync_menu=False)

    def _side_columns(self, side: str) -> tuple[int, ...]:
        size_column = COL_LEFT_SIZE if side == "left" else COL_RIGHT_SIZE
        date_column = COL_LEFT_DATE if side == "left" else COL_RIGHT_DATE
        return (
            COL_NAME,
            size_column,
            date_column,
            COL_STATUS,
            COL_EXTENSION,
            COL_TYPE,
            COL_PATH,
        )

    def _build_column_menu(self, tree: QTreeView, side: str) -> QMenu:
        menu = QMenu(f"{side.title()} columns", self)
        menu.setToolTipsVisible(True)
        for column in self._side_columns(side):
            action = menu.addAction(_COLUMN_TITLES[column])
            action.setData(column)
            action.setCheckable(True)
            action.setChecked(not tree.isColumnHidden(column))
            if column == COL_NAME:
                action.setEnabled(False)
                action.setToolTip("The Name column is always visible")
            else:
                action.toggled.connect(
                    lambda checked, current_tree=tree, current_column=column:
                    self._set_column_visible(current_tree, current_column, checked)
                )

        menu.addSeparator()
        fit_action = menu.addAction("Fit visible columns")
        fit_action.triggered.connect(lambda: self._resize_visible_columns_for(tree))
        reset_action = menu.addAction("Reset columns")
        reset_action.triggered.connect(lambda: self._reset_columns(tree, side))
        menu.aboutToShow.connect(lambda: self._sync_column_menu(tree))
        return menu

    def _show_column_menu(self, tree: QTreeView, pos: QPoint) -> None:
        header = tree.header()
        menu = self._column_menus.get(tree)
        if header is not None and menu is not None:
            self._sync_column_menu(tree)
            menu.exec(header.mapToGlobal(pos))

    def _sync_column_menu(self, tree: QTreeView) -> None:
        menu = self._column_menus.get(tree)
        if menu is None:
            return
        for action in menu.actions():
            column = action.data()
            if isinstance(column, int):
                action.blockSignals(True)
                action.setChecked(not tree.isColumnHidden(column))
                action.blockSignals(False)

    def _set_column_visible(
        self,
        tree: QTreeView,
        column: int,
        visible: bool,
    ) -> None:
        tree.setColumnHidden(column, not visible)
        if visible:
            tree.resizeColumnToContents(column)
            if tree.columnWidth(column) < 90:
                tree.setColumnWidth(column, 90)

    def _reset_columns(
        self,
        tree: QTreeView,
        side: str,
        *,
        sync_menu: bool = True,
    ) -> None:
        default_columns = {
            COL_NAME,
            COL_LEFT_SIZE if side == "left" else COL_RIGHT_SIZE,
            COL_LEFT_DATE if side == "left" else COL_RIGHT_DATE,
        }
        for column in self._side_columns(side):
            tree.setColumnHidden(column, column not in default_columns)
        self._apply_default_column_order(tree, side)
        self._enforce_side_columns(tree, side)
        if sync_menu:
            self._sync_column_menu(tree)
            self._resize_visible_columns_for(tree)

    def _enforce_side_columns(self, tree: QTreeView, side: str) -> None:
        tree.setColumnHidden(COL_NAME, False)
        if side == "left":
            tree.setColumnHidden(COL_RIGHT_SIZE, True)
            tree.setColumnHidden(COL_RIGHT_DATE, True)
        else:
            tree.setColumnHidden(COL_LEFT_SIZE, True)
            tree.setColumnHidden(COL_LEFT_DATE, True)

    def _apply_default_column_order(self, tree: QTreeView, side: str) -> None:
        """Keep each pane's visible metadata in the same intuitive order."""
        header = tree.header()
        if header is None:
            return
        opposite_columns = (
            (COL_RIGHT_SIZE, COL_RIGHT_DATE)
            if side == "left"
            else (COL_LEFT_SIZE, COL_LEFT_DATE)
        )
        logical_order = (*self._side_columns(side), *opposite_columns)
        for target_position, logical_index in enumerate(logical_order):
            current_position = header.visualIndex(logical_index)
            if current_position != target_position:
                header.moveSection(current_position, target_position)

    def _resize_visible_columns(self) -> None:
        """Auto-size visible columns for both LH/RH trees after loading data."""
        if self._source_model.node_count > _AUTO_SIZE_NODE_LIMIT:
            # resizeColumnToContents walks the complete model for every
            # column. Stable practical widths keep large comparisons O(1).
            for tree in (self._left_tree, self._right_tree):
                tree.setColumnWidth(COL_NAME, 360)
                tree.setColumnWidth(COL_LEFT_SIZE, 100)
                tree.setColumnWidth(COL_RIGHT_SIZE, 100)
                tree.setColumnWidth(COL_LEFT_DATE, 155)
                tree.setColumnWidth(COL_RIGHT_DATE, 155)
                tree.setColumnWidth(COL_STATUS, 120)
                tree.setColumnWidth(COL_EXTENSION, 90)
                tree.setColumnWidth(COL_TYPE, 110)
                tree.setColumnWidth(COL_PATH, 280)
            return
        self._resize_visible_columns_for(self._left_tree)
        self._resize_visible_columns_for(self._right_tree)

    def _resize_visible_columns_for(self, tree: QTreeView) -> None:
        columns = tuple(
            column
            for column in range(self._source_model.columnCount())
            if not tree.isColumnHidden(column)
        )
        self._resize_tree_columns(tree, columns)

    def _resize_tree_columns(self, tree: QTreeView, columns: tuple[int, ...]) -> None:
        for col in columns:
            tree.resizeColumnToContents(col)

        # Keep the name column practical for browsing deep paths.
        name_width = tree.columnWidth(COL_NAME)
        if name_width < 240:
            tree.setColumnWidth(COL_NAME, 240)
        elif name_width > 720:
            tree.setColumnWidth(COL_NAME, 720)

    # ------------------------------------------------------------------
    # Synchronisation
    # ------------------------------------------------------------------

    def _connect_sync(self) -> None:
        """Wire up expand/collapse and scroll synchronisation."""
        # Expand / collapse
        self._left_tree.expanded.connect(self._on_left_expanded)
        self._left_tree.collapsed.connect(self._on_left_collapsed)
        self._right_tree.expanded.connect(self._on_right_expanded)
        self._right_tree.collapsed.connect(self._on_right_collapsed)

        # Vertical scroll
        left_vbar = self._left_tree.verticalScrollBar()
        right_vbar = self._right_tree.verticalScrollBar()
        if left_vbar is not None and right_vbar is not None:
            left_vbar.valueChanged.connect(self._on_left_scrolled)
            right_vbar.valueChanged.connect(self._on_right_scrolled)

        # Selection change -> preview update
        left_sel = self._left_tree.selectionModel()
        if left_sel is not None:
            left_sel.currentChanged.connect(self._on_selection_changed)
        right_sel = self._right_tree.selectionModel()
        if right_sel is not None:
            right_sel.currentChanged.connect(self._on_selection_changed)

    # -- expand / collapse sync ----------------------------------------

    def _on_left_expanded(self, index: QModelIndex) -> None:
        if self._syncing_expand:
            return
        self._syncing_expand = True
        try:
            self._right_tree.expand(index)
        finally:
            self._syncing_expand = False

    def _on_left_collapsed(self, index: QModelIndex) -> None:
        if self._syncing_expand:
            return
        self._syncing_expand = True
        try:
            self._right_tree.collapse(index)
        finally:
            self._syncing_expand = False

    def _on_right_expanded(self, index: QModelIndex) -> None:
        if self._syncing_expand:
            return
        self._syncing_expand = True
        try:
            self._left_tree.expand(index)
        finally:
            self._syncing_expand = False

    def _on_right_collapsed(self, index: QModelIndex) -> None:
        if self._syncing_expand:
            return
        self._syncing_expand = True
        try:
            self._left_tree.collapse(index)
        finally:
            self._syncing_expand = False

    # -- scroll sync ---------------------------------------------------

    def _on_left_scrolled(self, value: int) -> None:
        if self._syncing_scroll:
            return
        self._syncing_scroll = True
        try:
            right_vbar = self._right_tree.verticalScrollBar()
            if right_vbar is not None:
                right_vbar.setValue(value)
        finally:
            self._syncing_scroll = False

    def _on_right_scrolled(self, value: int) -> None:
        if self._syncing_scroll:
            return
        self._syncing_scroll = True
        try:
            left_vbar = self._left_tree.verticalScrollBar()
            if left_vbar is not None:
                left_vbar.setValue(value)
        finally:
            self._syncing_scroll = False

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _on_double_click(self, index: QModelIndex) -> None:
        """Emit *file_activated* when the user double-clicks a row."""
        node: Optional[TreeNode] = index.data(Qt.UserRole + 1)
        if node is not None:
            self.file_activated.emit(node.path, node.is_dir)

    def _on_context_menu(self, pos) -> None:
        """Show a context menu with common comparison actions."""
        tree: QTreeView = self.sender()  # type: ignore[assignment]
        index = tree.indexAt(pos)
        if not index.isValid():
            return

        node: Optional[TreeNode] = index.data(Qt.UserRole + 1)
        if node is None:
            return

        side = "left" if tree is self._left_tree else "right"

        menu = QMenu(self)

        def _add_action(
            parent_menu: QMenu,
            text: str,
            command: str,
            *,
            shortcut: Optional[str] = None,
            enabled: bool = True,
            checkable: bool = False,
            checked: bool = False,
        ) -> QAction:
            action = QAction(text, parent_menu)
            action.setData((command, node.path))
            action.setEnabled(enabled)
            action.setCheckable(checkable)
            if checkable:
                action.setChecked(checked)
            if shortcut:
                action.setShortcut(shortcut)
                action.setShortcutVisibleInContextMenu(True)
            parent_menu.addAction(action)
            return action

        _add_action(menu, "Close Folder", "close_folder", enabled=node.is_dir)
        _add_action(menu, "Open Subfolders", "open_subfolders", enabled=node.is_dir)
        _add_action(menu, "Close Subfolders", "close_subfolders", enabled=node.is_dir)
        menu.addSeparator()

        _add_action(menu, "Set as Base Folder", "set_base_folder")
        _add_action(menu, "Set as Base on Other Side", "set_base_other")
        _add_action(menu, "Open in New View", "open_new_view", enabled=not node.is_dir)

        open_with_menu = menu.addMenu("Open With")
        _add_action(open_with_menu, "Open in External Editor", "open_ext")

        _add_action(
            menu,
            "Compare Contents...",
            "compare_contents",
            shortcut="F7",
            enabled=not node.is_dir,
        )
        _add_action(menu, "Align With...", "align_with", shortcut="F6")
        menu.addSeparator()

        _add_action(menu, "Copy Left to Right", "copy_lr")
        _add_action(menu, "Copy Right to Left", "copy_rl")
        _add_action(menu, "Copy to Folder...", "copy_to_folder")
        _add_action(menu, "Move to Folder...", "move_to_folder")
        _add_action(menu, "Delete...", "delete_item")
        _add_action(menu, "Rename", "rename_item", shortcut="F2")
        _add_action(menu, "Attributes...", "attributes")
        _add_action(menu, "Touch...", "touch_item")
        _add_action(menu, "Exclude", "exclude_item")
        _add_action(menu, "New Folder...", "new_folder", shortcut="Ins")
        _add_action(menu, "Copy Filename", "copy_filename")
        _add_action(menu, "Ignored", "ignored_toggle", checkable=True, checked=False)
        _add_action(menu, "Refresh Selection", "refresh_selection", shortcut="Shift+F5")

        menu.addSeparator()
        sync_menu = menu.addMenu("Synchronize")
        _add_action(sync_menu, "Open Synchronize Dialog", "sync_dialog")

        action = menu.exec(tree.viewport().mapToGlobal(pos))
        if action is None:
            return

        payload = action.data()
        if (
            isinstance(payload, tuple)
            and len(payload) == 2
            and isinstance(payload[0], str)
            and isinstance(payload[1], str)
        ):
            command = payload[0]
            if command == "close_folder":
                tree.collapse(index)
                return
            if command == "open_subfolders":
                tree.expandRecursively(index)
                return
            if command == "close_subfolders":
                self._collapse_subfolders(tree, index)
                return
            self.context_command.emit(payload[0], payload[1], side)

    # ------------------------------------------------------------------
    # File content preview panel
    # ------------------------------------------------------------------

    def set_preview_visible(self, visible: bool) -> None:
        """Show or hide the preview panel below the trees."""
        self._preview_visible = visible
        self._preview_container.setVisible(visible)

    def set_preview_roots(self, left_root: str, right_root: str) -> None:
        """Set the root paths for resolving preview file paths."""
        self._preview_left_root = left_root
        self._preview_right_root = right_root

    def _on_selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """Update the preview panels when a new row is selected.

        Debounced: rapid arrow-key navigation restarts the timer instead of
        firing a read per row.
        """
        self.selection_changed.emit()
        if not self._preview_visible:
            return
        if not current.isValid():
            return

        source_index = self._proxy_model.mapToSource(current)
        node = source_index.internalPointer()
        if node is None or not hasattr(node, "path") or not hasattr(node, "is_dir"):
            return
        if node.is_dir:
            self._preview_pending_path = None
            self._preview_debounce_timer.stop()
            self._left_preview.setPlainText("")
            self._right_preview.setPlainText("")
            return

        self._preview_pending_path = node.path
        self._preview_debounce_timer.start()

    def _trigger_preview_load(self) -> None:
        """Start the background read for the debounced pending selection."""
        rel_path = self._preview_pending_path
        if rel_path is None:
            return
        self._preview_request_path = rel_path

        worker = FunctionWorker(
            _read_preview_pair, self._preview_left_root, self._preview_right_root, rel_path,
            parent=self,
        )
        worker.finished_with_result.connect(
            lambda result, p=rel_path: self._on_preview_loaded(p, result)
        )
        worker.finished.connect(worker.deleteLater)
        self._preview_worker = worker
        worker.start()

    def _on_preview_loaded(self, rel_path: str, result: tuple[str, str]) -> None:
        if self._preview_request_path != rel_path:
            return  # a newer selection superseded this preview request
        left_text, right_text = result
        self._left_preview.setPlainText(left_text)
        self._right_preview.setPlainText(right_text)

    def _collapse_subfolders(self, tree: QTreeView, root_index: QModelIndex) -> None:
        """Recursively collapse all descendants and then the root index."""
        model = tree.model()
        if model is None:
            return

        def _walk(idx: QModelIndex) -> None:
            child_count = model.rowCount(idx)
            for row in range(child_count):
                child = model.index(row, 0, idx)
                if child.isValid():
                    _walk(child)
            tree.collapse(idx)

        _walk(root_index)
