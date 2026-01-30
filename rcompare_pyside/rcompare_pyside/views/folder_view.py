"""Side-by-side folder comparison view (Beyond Compare style)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QModelIndex
from PySide6.QtGui import QColor, QPainter, QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QMenu,
    QSplitter,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QWidget,
)

from ..models.comparison import TreeNode
from ..models.tree_model import (
    COL_LEFT_DATE,
    COL_LEFT_SIZE,
    COL_NAME,
    COL_RIGHT_DATE,
    COL_RIGHT_SIZE,
    COL_STATUS,
    ComparisonFilterProxy,
    ComparisonTreeModel,
)
from ..utils.cli_bridge import DiffStatus


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

        # Layout -------------------------------------------------------
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self._left_tree)
        splitter.addWidget(self._right_tree)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        # Synchronisation guards ---------------------------------------
        self._syncing_scroll = False
        self._syncing_expand = False

        # Connect synchronisation signals ------------------------------
        self._connect_sync()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tree(self, root: TreeNode) -> None:
        """Replace the comparison data with a new tree."""
        self._source_model.set_tree(root)

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
        search_text: str = "",
    ) -> None:
        """Apply visibility and search filters."""
        self._proxy_model.set_filter_flags(
            show_identical, show_different, show_left_only, show_right_only,
        )
        self._proxy_model.set_search_text(search_text)

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

    # ------------------------------------------------------------------
    # Tree construction helpers
    # ------------------------------------------------------------------

    def _create_tree(self) -> QTreeView:
        """Build a QTreeView with shared settings."""
        tree = QTreeView(self)
        tree.setModel(self._proxy_model)
        tree.setItemDelegate(self._delegate)

        tree.setAlternatingRowColors(False)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        tree.setUniformRowHeights(True)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)

        tree.customContextMenuRequested.connect(self._on_context_menu)
        tree.doubleClicked.connect(self._on_double_click)

        return tree

    def _configure_left_tree(self) -> None:
        """Hide right-side columns in the left tree."""
        self._left_tree.setColumnHidden(COL_RIGHT_SIZE, True)
        self._left_tree.setColumnHidden(COL_RIGHT_DATE, True)
        self._left_tree.setColumnHidden(COL_STATUS, True)

    def _configure_right_tree(self) -> None:
        """Hide left-side columns in the right tree."""
        self._right_tree.setColumnHidden(COL_LEFT_SIZE, True)
        self._right_tree.setColumnHidden(COL_LEFT_DATE, True)
        self._right_tree.setColumnHidden(COL_STATUS, True)

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

        menu = QMenu(self)

        copy_left_to_right = QAction("Copy Left to Right", menu)
        copy_left_to_right.setData(("copy_lr", node.path))
        menu.addAction(copy_left_to_right)

        copy_right_to_left = QAction("Copy Right to Left", menu)
        copy_right_to_left.setData(("copy_rl", node.path))
        menu.addAction(copy_right_to_left)

        menu.addSeparator()

        open_external = QAction("Open in External Editor", menu)
        open_external.setData(("open_ext", node.path))
        menu.addAction(open_external)

        action = menu.exec(tree.viewport().mapToGlobal(pos))
        if action is not None:
            # The actual handling of these actions is left to whoever
            # connects to a higher-level signal or overrides this method.
            pass
