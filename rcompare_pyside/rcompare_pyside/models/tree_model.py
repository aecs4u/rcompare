"""Qt tree model for folder comparison results."""

from __future__ import annotations

import datetime
from typing import Any, Optional, Union

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, QSortFilterProxyModel
from PySide6.QtWidgets import QApplication, QStyle
from PySide6.QtGui import QIcon

from .comparison import TreeNode
from ..utils.cli_bridge import DiffStatus


# Column indices
COL_NAME = 0
COL_LEFT_SIZE = 1
COL_LEFT_DATE = 2
COL_STATUS = 3
COL_RIGHT_SIZE = 4
COL_RIGHT_DATE = 5

_COLUMN_HEADERS = [
    "Name",
    "Left Size",
    "Left Date",
    "Status",
    "Right Size",
    "Right Date",
]

_STATUS_LABELS = {
    DiffStatus.SAME: "Identical",
    DiffStatus.DIFFERENT: "Different",
    DiffStatus.ORPHAN_LEFT: "Left Only",
    DiffStatus.ORPHAN_RIGHT: "Right Only",
    DiffStatus.UNCHECKED: "Unchecked",
}


def _format_size(size: Optional[int]) -> str:
    """Format a byte count as a human-readable string."""
    if size is None:
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.2f} GB"


def _format_date(timestamp: Optional[int]) -> str:
    """Format a unix timestamp as YYYY-MM-DD HH:MM:SS."""
    if timestamp is None:
        return ""
    try:
        dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError, OverflowError):
        return ""


class ComparisonTreeModel(QAbstractItemModel):
    """Tree model that wraps a TreeNode hierarchy from a folder comparison."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root: Optional[TreeNode] = None
        self._node_map: dict[int, TreeNode] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tree(self, root: TreeNode) -> None:
        """Replace the entire tree with a new root node."""
        self.beginResetModel()
        self._root = root
        self._node_map.clear()
        if root is not None:
            self._register_nodes(root)
        self.endResetModel()

    def node_from_index(self, index: QModelIndex) -> Optional[TreeNode]:
        """Return the TreeNode for a given model index, or None."""
        if not index.isValid():
            return self._root
        node_id = index.internalId()
        return self._node_map.get(node_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_nodes(self, node: TreeNode) -> None:
        """Recursively register all nodes in the id-lookup map."""
        self._node_map[id(node)] = node
        for child in node.children:
            self._register_nodes(child)

    def _node_for_index(self, index: QModelIndex) -> Optional[TreeNode]:
        """Resolve a QModelIndex to its TreeNode."""
        if not index.isValid():
            return self._root
        node_id = index.internalId()
        return self._node_map.get(node_id)

    # ------------------------------------------------------------------
    # QAbstractItemModel interface
    # ------------------------------------------------------------------

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_node = self._node_for_index(parent)
        if parent_node is None:
            return QModelIndex()

        if row < 0 or row >= len(parent_node.children):
            return QModelIndex()

        child = parent_node.children[row]
        return self.createIndex(row, column, id(child))

    def parent(self, index: QModelIndex = QModelIndex()) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        child_node = self._node_for_index(index)
        if child_node is None or child_node.parent is None:
            return QModelIndex()

        parent_node = child_node.parent
        # The root's children have root as parent; root itself has no parent index
        if parent_node is self._root or parent_node.parent is None:
            return QModelIndex()

        return self.createIndex(parent_node.row, 0, id(parent_node))

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.column() > 0:
            return 0
        node = self._node_for_index(parent)
        if node is None:
            return 0
        return len(node.children)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(_COLUMN_HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        node = self._node_for_index(index)
        if node is None:
            return None

        col = index.column()

        if role == Qt.DisplayRole:
            if col == COL_NAME:
                return node.name
            if col == COL_LEFT_SIZE:
                return _format_size(node.left_size)
            if col == COL_LEFT_DATE:
                return _format_date(node.left_modified)
            if col == COL_STATUS:
                return _STATUS_LABELS.get(node.status, "")
            if col == COL_RIGHT_SIZE:
                return _format_size(node.right_size)
            if col == COL_RIGHT_DATE:
                return _format_date(node.right_modified)

        elif role == Qt.DecorationRole:
            if col == COL_NAME:
                style = QApplication.style()
                if style is None:
                    return None
                if node.is_dir:
                    return style.standardIcon(QStyle.SP_DirIcon)
                return style.standardIcon(QStyle.SP_FileIcon)

        elif role == Qt.UserRole:
            return node.status

        elif role == Qt.UserRole + 1:
            return node

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(_COLUMN_HEADERS):
                return _COLUMN_HEADERS[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


class ComparisonFilterProxy(QSortFilterProxyModel):
    """Filter proxy that hides rows based on DiffStatus visibility and search text.

    The filter is recursive: a directory row is shown if any of its
    descendants match the current filter criteria.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._show_identical: bool = True
        self._show_different: bool = True
        self._show_left_only: bool = True
        self._show_right_only: bool = True
        self._search_text: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_filter_flags(
        self,
        show_identical: bool,
        show_different: bool,
        show_left_only: bool,
        show_right_only: bool,
    ) -> None:
        """Update which DiffStatus values are visible."""
        self._show_identical = show_identical
        self._show_different = show_different
        self._show_left_only = show_left_only
        self._show_right_only = show_right_only
        self.invalidateFilter()

    def set_search_text(self, text: str) -> None:
        """Update the name search filter."""
        self._search_text = text.strip().lower()
        self.invalidateFilter()

    # ------------------------------------------------------------------
    # QSortFilterProxyModel overrides
    # ------------------------------------------------------------------

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source_model = self.sourceModel()
        if source_model is None:
            return True

        index = source_model.index(source_row, 0, source_parent)
        node: Optional[TreeNode] = source_model.data(index, Qt.UserRole + 1)
        if node is None:
            return True

        # For directory nodes, accept if any descendant passes the filter
        if node.is_dir and node.children:
            if self._accepts_node(node):
                return True
            return self._any_descendant_accepted(node)

        return self._accepts_node(node)

    def _accepts_node(self, node: TreeNode) -> bool:
        """Check if a single node passes the status and search filters."""
        # Status filter
        status = node.status
        if status == DiffStatus.SAME and not self._show_identical:
            return False
        if status == DiffStatus.DIFFERENT and not self._show_different:
            return False
        if status == DiffStatus.ORPHAN_LEFT and not self._show_left_only:
            return False
        if status == DiffStatus.ORPHAN_RIGHT and not self._show_right_only:
            return False

        # Search text filter
        if self._search_text and self._search_text not in node.name.lower():
            return False

        return True

    def _any_descendant_accepted(self, node: TreeNode) -> bool:
        """Recursively check if any descendant of *node* passes the filter."""
        for child in node.children:
            if self._accepts_node(child):
                return True
            if child.is_dir and child.children:
                if self._any_descendant_accepted(child):
                    return True
        return False
