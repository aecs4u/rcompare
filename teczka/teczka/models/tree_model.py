"""Qt tree model for folder comparison results."""

from __future__ import annotations

import datetime
from typing import Any, Optional

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QStyle

from ..utils.cli_bridge import DiffStatus
from ..utils.name_search import NameSearch, compile_name_search, normalize_search_mode
from ..utils.view_filter import diff_mode_matches, status_is_enabled
from .comparison import TreeNode, aggregate_node_status

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
_BASE_COLUMNS = len(_COLUMN_HEADERS)

# Extra, optional per-side columns the user can switch on from the header menu.
# Each attribute adds a left and a right column after the base columns.
ATTRIBUTES: list[tuple[str, str]] = [
    ("ext", "Type"),
    ("perms", "Permissions"),
    ("owner", "Owner"),
    ("group", "Group"),
    ("atime", "Accessed"),
    ("ctime", "Changed"),
    ("folder", "Folder"),
]
ATTR_KEYS = [k for k, _ in ATTRIBUTES]
for _key, _label in ATTRIBUTES:
    _COLUMN_HEADERS.append(f"Left {_label}")
    _COLUMN_HEADERS.append(f"Right {_label}")


def attr_column(key: str, side: str) -> int:
    """Model column index of attribute *key* for *side* ("left"/"right")."""
    return _BASE_COLUMNS + 2 * ATTR_KEYS.index(key) + (0 if side == "left" else 1)


def _attr_of_column(column: int) -> Optional[tuple[str, str]]:
    if column < _BASE_COLUMNS or column >= len(_COLUMN_HEADERS):
        return None
    i, side = divmod(column - _BASE_COLUMNS, 2)
    return ATTR_KEYS[i], ("left" if side == 0 else "right")


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


def _missing_side_for_column(node: TreeNode, column: int) -> Optional[str]:
    """Return the absent side for a metadata column on an orphan row."""
    attr = _attr_of_column(column)
    left_column = column in (COL_LEFT_SIZE, COL_LEFT_DATE) or (
        attr is not None and attr[1] == "left"
    )
    right_column = column in (COL_RIGHT_SIZE, COL_RIGHT_DATE) or (
        attr is not None and attr[1] == "right"
    )
    if left_column and node.status == DiffStatus.ORPHAN_RIGHT:
        return "left"
    if right_column and node.status == DiffStatus.ORPHAN_LEFT:
        return "right"
    return None


class ComparisonTreeModel(QAbstractItemModel):
    """Tree model that wraps a TreeNode hierarchy from a folder comparison."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root: Optional[TreeNode] = None
        self._node_map: dict[int, TreeNode] = {}
        self._dir_icon: Optional[QIcon] = None
        self._file_icon: Optional[QIcon] = None
        self._roots: dict[str, str] = {"left": "", "right": ""}
        self._stat_cache: dict[tuple[str, str], Any] = {}
        self._owner_cache: dict[tuple[str, int], str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tree(self, root: TreeNode) -> None:
        """Replace the entire tree with a new root node."""
        self.beginResetModel()
        self._root = root
        self._roots = {
            "left": getattr(root, "left_root", "") if root is not None else "",
            "right": getattr(root, "right_root", "") if root is not None else "",
        }
        self._stat_cache.clear()
        self._node_map.clear()
        self._path_map = {}
        if root is not None:
            self._register_nodes(root)
        self.endResetModel()

    def node_from_index(self, index: QModelIndex) -> Optional[TreeNode]:
        """Return the TreeNode for a given model index, or None."""
        if not index.isValid():
            return self._root
        node_id = index.internalId()
        return self._node_map.get(node_id)

    @property
    def node_count(self) -> int:
        """Number of indexed nodes, excluding no special model rows."""
        return len(self._node_map)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_nodes(self, node: TreeNode) -> None:
        """Recursively register all nodes in the id-lookup map."""
        self._node_map[id(node)] = node
        self._path_map[node.path] = node
        for child in node.children:
            self._register_nodes(child)

    def index_for_path(self, path: str) -> QModelIndex:
        """O(1) lookup of the (column 0) index for a node's relative path."""
        node = getattr(self, "_path_map", {}).get(path)
        if node is None or node is self._root:
            return QModelIndex()
        return self.createIndex(node.row, 0, id(node))

    def entry_for_path(self, path: str):
        """Return the scan entry represented by *path*, if it is in the tree."""
        node = getattr(self, "_path_map", {}).get(path)
        return node.entry if node is not None else None

    def update_entry_status(self, path: str, status: DiffStatus) -> DiffStatus | None:
        """Update one file result and refresh ancestor folder statuses in place.

        Returns the previous entry status, or ``None`` if *path* is not a file
        row in the current model. The scan entry itself is updated as well.
        """
        node = getattr(self, "_path_map", {}).get(path)
        if node is None or node.entry is None or node.is_dir:
            return None

        previous = node.entry.status
        if previous == status:
            return previous

        node.entry.status = status
        node.status = status
        changed_nodes = [node]
        parent = node.parent
        while parent is not None:
            previous_parent = parent.status
            parent.status = aggregate_node_status(parent)
            if previous_parent != parent.status:
                changed_nodes.append(parent)
            parent = parent.parent

        roles = [Qt.DisplayRole, Qt.UserRole, Qt.UserRole + 1]
        last_column = self.columnCount() - 1
        for changed in changed_nodes:
            start = self.index_for_path(changed.path)
            if not start.isValid():
                continue
            self.dataChanged.emit(start, start.siblingAtColumn(last_column), roles)
        return previous

    def _node_for_index(self, index: QModelIndex) -> Optional[TreeNode]:
        """Resolve a QModelIndex to its TreeNode."""
        if not index.isValid():
            return self._root
        node_id = index.internalId()
        return self._node_map.get(node_id)

    # ------------------------------------------------------------------
    # QAbstractItemModel interface
    # ------------------------------------------------------------------

    def index(
        self, row: int, column: int, parent: QModelIndex = QModelIndex()
    ) -> QModelIndex:
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
            if col >= _BASE_COLUMNS:
                if _missing_side_for_column(node, col):
                    return "—"
                return self._attribute_text(node, col)
            if col == COL_NAME:
                return node.name
            if col == COL_LEFT_SIZE:
                if _missing_side_for_column(node, col):
                    return "—"
                return _format_size(node.left_size)
            if col == COL_LEFT_DATE:
                if _missing_side_for_column(node, col):
                    return "—"
                return _format_date(node.left_modified)
            if col == COL_STATUS:
                return _STATUS_LABELS.get(node.status, "")
            if col == COL_RIGHT_SIZE:
                if _missing_side_for_column(node, col):
                    return "—"
                return _format_size(node.right_size)
            if col == COL_RIGHT_DATE:
                if _missing_side_for_column(node, col):
                    return "—"
                return _format_date(node.right_modified)

        elif role == Qt.ToolTipRole:
            missing_side = _missing_side_for_column(node, col)
            if missing_side:
                return f"Not present on the {missing_side} side."

        elif role == Qt.ForegroundRole and _missing_side_for_column(node, col):
            palette = QApplication.palette()
            return QColor(palette.color(QPalette.ColorRole.Mid))

        elif role == Qt.DecorationRole:
            if col == COL_NAME:
                return (
                    self._dir_icon_cached() if node.is_dir else self._file_icon_cached()
                )

        elif role == Qt.UserRole:
            return node.status

        elif role == Qt.UserRole + 1:
            return node

        return None

    # -- optional attribute columns ------------------------------------

    _MAX_STAT_CACHE = 50_000

    def _stat_for(self, side: str, node: TreeNode):
        """lstat() of *node* on *side*, cached; None if unavailable (remote/missing)."""
        root = self._roots.get(side) or ""
        if not root or not node.path or "://" in root:
            return None
        key = (side, node.path)
        if key in self._stat_cache:
            return self._stat_cache[key]
        try:
            import os

            result = os.lstat(os.path.join(root, node.path))
        except (OSError, ValueError):
            result = None
        if len(self._stat_cache) >= self._MAX_STAT_CACHE:
            self._stat_cache.clear()
        self._stat_cache[key] = result
        return result

    def _owner_name(self, kind: str, ident: int) -> str:
        cache_key = (kind, ident)
        name = self._owner_cache.get(cache_key)
        if name is None:
            try:
                if kind == "user":
                    import pwd

                    name = pwd.getpwuid(ident).pw_name
                else:
                    import grp

                    name = grp.getgrgid(ident).gr_name
            except (ImportError, KeyError, OverflowError):
                name = str(ident)
            self._owner_cache[cache_key] = name
        return name

    def _attribute_text(self, node: TreeNode, column: int) -> str:
        attr = _attr_of_column(column)
        if attr is None:
            return ""
        key, side = attr
        if key == "ext":
            if node.is_dir:
                return "Folder"
            name = node.name.rsplit("/", 1)[-1]
            return name.rsplit(".", 1)[-1].lower() if "." in name.strip(".") else ""
        if key == "folder":
            return node.path.rsplit("/", 1)[0] if "/" in node.path else ""
        st = self._stat_for(side, node)
        if st is None:
            return ""
        if key == "perms":
            import stat as _stat

            return _stat.filemode(st.st_mode)
        if key == "owner":
            return self._owner_name("user", st.st_uid)
        if key == "group":
            return self._owner_name("group", st.st_gid)
        if key == "atime":
            return _format_date(int(st.st_atime))
        if key == "ctime":
            return _format_date(int(st.st_ctime))
        return ""

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(_COLUMN_HEADERS):
                return _COLUMN_HEADERS[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def _dir_icon_cached(self) -> Optional[QIcon]:
        if self._dir_icon is None:
            style = QApplication.style()
            if style is None:
                return None
            self._dir_icon = style.standardIcon(QStyle.SP_DirIcon)
        return self._dir_icon

    def _file_icon_cached(self) -> Optional[QIcon]:
        if self._file_icon is None:
            style = QApplication.style()
            if style is None:
                return None
            self._file_icon = style.standardIcon(QStyle.SP_FileIcon)
        return self._file_icon


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
        self._show_files_only: bool = False
        self._search_text: str = ""
        self._search_mode: str = "contains"
        self._search_matcher: NameSearch = compile_name_search("")
        self._diff_option_mode: str = "show_differences"
        # Cleared on every row-filter invalidation (results depend on the
        # current filter criteria); avoids re-walking the same subtree
        # repeatedly across the many filterAcceptsRow() calls Qt issues
        # for a single filter change.
        self._descendant_match_cache: dict[int, bool] = {}
        # Relative paths are stable for the lifetime of a tree. Cache their
        # case-folded form so contains-mode searches stay cheap on large trees.
        self._search_path_casefold_cache: dict[int, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def setSourceModel(self, source_model) -> None:  # noqa: N802 - Qt override
        old = self.sourceModel()
        if old is not None:
            try:
                old.modelAboutToBeReset.disconnect(self._on_source_about_to_reset)
            except (RuntimeError, TypeError):
                pass
        super().setSourceModel(source_model)
        if source_model is not None:
            source_model.modelAboutToBeReset.connect(self._on_source_about_to_reset)

    def _on_source_about_to_reset(self) -> None:
        self._descendant_match_cache.clear()
        self._search_path_casefold_cache.clear()

    def _begin_rows_filter_change(self) -> bool:
        self._descendant_match_cache.clear()
        # Qt 6.10+ brackets filter-state changes with begin/endFilterChange.
        # Qt 6.9 exposes beginFilterChange without endFilterChange; older
        # versions supported by the project use invalidateFilter().
        begin_change = getattr(self, "beginFilterChange", None)
        end_change = getattr(self, "endFilterChange", None)
        if begin_change is None or end_change is None:
            return False
        begin_change()
        return True

    def _end_rows_filter_change(self, began_change: bool) -> None:
        if began_change:
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            super().invalidateFilter()

    def set_filter_flags(
        self,
        show_identical: bool,
        show_different: bool,
        show_left_only: bool,
        show_right_only: bool,
        show_files_only: bool = False,
    ) -> None:
        """Update which DiffStatus values are visible."""
        began_change = self._begin_rows_filter_change()
        self._show_identical = show_identical
        self._show_different = show_different
        self._show_left_only = show_left_only
        self._show_right_only = show_right_only
        self._show_files_only = show_files_only
        self._end_rows_filter_change(began_change)

    def set_search_text(self, text: str) -> None:
        """Update the name search filter."""
        began_change = self._begin_rows_filter_change()
        self._search_text = text.strip()
        self._search_matcher = compile_name_search(self._search_text, self._search_mode)
        self._end_rows_filter_change(began_change)

    @property
    def search_error(self) -> str:
        """Return the active search syntax error, if any."""
        return self._search_matcher.error

    def set_search_mode(self, mode: str) -> None:
        """Change how the current search text is interpreted."""
        began_change = self._begin_rows_filter_change()
        self._search_mode = normalize_search_mode(mode)
        self._search_matcher = compile_name_search(self._search_text, self._search_mode)
        self._end_rows_filter_change(began_change)

    def set_diff_option_mode(self, mode: str) -> None:
        """Update the high-level diff option mode."""
        began_change = self._begin_rows_filter_change()
        self._diff_option_mode = (mode or "show_differences").strip().lower()
        self._end_rows_filter_change(began_change)

    def apply_filters(
        self,
        show_identical: bool,
        show_different: bool,
        show_left_only: bool,
        show_right_only: bool,
        show_files_only: bool,
        search_text: str,
        diff_option_mode: Optional[str] = None,
        search_mode: str = "contains",
    ) -> None:
        """Set all filter/search state and invalidate the proxy exactly once.

        Prefer this over calling set_filter_flags()/set_search_text()/
        set_diff_option_mode() individually, which each trigger their own
        (expensive, recursive) row-filter invalidation pass.
        """
        began_change = self._begin_rows_filter_change()
        self._show_identical = show_identical
        self._show_different = show_different
        self._show_left_only = show_left_only
        self._show_right_only = show_right_only
        self._show_files_only = show_files_only
        self._search_text = search_text.strip()
        self._search_mode = normalize_search_mode(search_mode)
        self._search_matcher = compile_name_search(self._search_text, self._search_mode)
        if diff_option_mode is not None:
            self._diff_option_mode = (
                (diff_option_mode or "show_differences").strip().lower()
            )
        self._end_rows_filter_change(began_change)

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

        # Files-only mode hides directory rows themselves but keeps
        # directories that have accepted descendants so matching files
        # remain reachable in the tree.
        if node.is_dir and self._show_files_only:
            return self._any_descendant_accepted(node)

        # For directory nodes, accept if they match directly or any descendant passes
        if node.is_dir and node.children:
            if self._accepts_node(node):
                return True
            return self._any_descendant_accepted(node)

        return self._accepts_node(node)

    def _accepts_node(self, node: TreeNode) -> bool:
        """Check if a single node passes the status and search filters."""
        if self._show_files_only and node.is_dir:
            return False

        if not status_is_enabled(
            node.status,
            show_identical=self._show_identical,
            show_different=self._show_different,
            show_left_only=self._show_left_only,
            show_right_only=self._show_right_only,
        ):
            return False

        if not diff_mode_matches(
            node.status,
            node.left_modified,
            node.right_modified,
            self._diff_option_mode,
        ):
            return False

        # Search text filter
        if self._search_matcher.text:
            if self._search_matcher.mode == "contains":
                if self._search_matcher.folded_text not in self._search_path_casefold(
                    node
                ):
                    return False
            elif not self._search_matcher.matches(node.path or node.name):
                return False

        return True

    def _search_path_casefold(self, node: TreeNode) -> str:
        key = id(node)
        cached = self._search_path_casefold_cache.get(key)
        if cached is None:
            cached = (node.path or node.name).casefold()
            self._search_path_casefold_cache[key] = cached
        return cached

    def _any_descendant_accepted(self, node: TreeNode) -> bool:
        """Recursively check if any descendant of *node* passes the filter.

        Cached per node for the lifetime of the current filter criteria
        (cleared in _begin_rows_filter_change()) since the same directory is asked
        about repeatedly across the many filterAcceptsRow() calls Qt
        issues for a single filter change.
        """
        key = id(node)
        cached = self._descendant_match_cache.get(key)
        if cached is not None:
            return cached

        result = False
        for child in node.children:
            if self._accepts_node(child):
                result = True
                break
            if child.is_dir and child.children and self._any_descendant_accepted(child):
                result = True
                break

        self._descendant_match_cache[key] = result
        return result
