"""Side-by-side folder comparison view (Beyond Compare style)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Optional

from PySide6.QtCore import QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QPlainTextEdit,
    QSplitter,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from ..models.comparison import TreeNode
from ..models.tree_model import (
    ATTRIBUTES,
    COL_LEFT_DATE,
    COL_LEFT_SIZE,
    COL_NAME,
    COL_RIGHT_DATE,
    COL_RIGHT_SIZE,
    COL_STATUS,
    ComparisonFilterProxy,
    ComparisonTreeModel,
    attr_column,
)
from ..utils.cli_bridge import DiffStatus
from ..utils.source_paths import is_remote_source
from ..workers.function_worker import FunctionWorker

_PREVIEW_DEBOUNCE_MS = 200
_PREVIEW_MAX_LINES = 100
_PREVIEW_MAX_BYTES = 64 * 1024  # 64 KB
_AUTO_SIZE_NODE_LIMIT = 2_000  # kept for compatibility
_FIT_PRECISION_ROWS = 300  # rows sampled when fitting columns
_DEFAULT_VISIBLE_KEYS = ("size", "date")
_BASE_KEYS = [("size", "Size"), ("date", "Date"), ("status", "Status")]


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


def _read_remote_preview_side(
    cli_path: str,
    left_root: str,
    right_root: str,
    side: str,
    rel_path: str,
    size: int | None,
) -> str:
    """Fetch a small remote preview through the CLI without using local path APIs."""
    if size is None:
        return "(not present on this side)"
    if size > _PREVIEW_MAX_BYTES:
        return f"(remote preview skipped; file is larger than {_PREVIEW_MAX_BYTES:,} bytes)"
    if not cli_path:
        return "(remote preview requires a configured rcompare_cli)"

    try:
        with tempfile.TemporaryDirectory(prefix="teczka-preview-") as temp_dir:
            output_path = os.path.join(temp_dir, "preview.bin")
            completed = subprocess.run(
                [
                    cli_path,
                    "read",
                    left_root,
                    right_root,
                    "--side",
                    side,
                    "--path",
                    rel_path,
                    "--out",
                    output_path,
                ],
                check=False,
                capture_output=True,
                timeout=30,
            )
            if completed.returncode != 0 or not os.path.isfile(output_path):
                return "(remote file could not be read)"
            with open(output_path, "rb") as preview_file:
                content = preview_file.read(_PREVIEW_MAX_BYTES + 1)
    except (OSError, subprocess.TimeoutExpired):
        return "(remote file could not be read)"

    if len(content) > _PREVIEW_MAX_BYTES:
        content = content[:_PREVIEW_MAX_BYTES]
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > _PREVIEW_MAX_LINES:
        lines = lines[:_PREVIEW_MAX_LINES]
        lines.append("... (preview truncated)")
    return "\n".join(lines)


def _read_preview_pair(
    left_root: str,
    right_root: str,
    rel_path: str,
    cli_path: str = "",
    left_size: int | None = None,
    right_size: int | None = None,
) -> tuple[str, str]:
    left = (
        _read_remote_preview_side(
            cli_path, left_root, right_root, "left", rel_path, left_size
        )
        if is_remote_source(left_root)
        else _read_preview_side(left_root, rel_path)
    )
    right = (
        _read_remote_preview_side(
            cli_path, left_root, right_root, "right", rel_path, right_size
        )
        if is_remote_source(right_root)
        else _read_preview_side(right_root, rel_path)
    )
    return left, right


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

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
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

    # Emitted when selection is limited to one panel or restored to both:
    # "both" | "left" | "right".
    selection_mode_changed = Signal(str)

    # Emitted on double-click.  Arguments: (relative_path, is_directory)
    file_activated = Signal(str, bool)
    # Emitted from context menu. Arguments: (command, relative_path, side)
    context_command = Signal(str, str, str)

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
        self._fitting = False  # True while we resize programmatically
        self._user_sized = False  # user dragged a column: stop auto-fitting
        self._selection_mode = "both"
        self._mirroring_selection = False
        self._connect_selection_mirroring()
        self._visible_keys: set[str] = set(_DEFAULT_VISIBLE_KEYS)
        self._apply_visible_columns()
        for tree in (self._left_tree, self._right_tree):
            header = tree.header()
            if header is not None:
                header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                header.customContextMenuRequested.connect(
                    lambda pos, t=tree: self._on_header_menu(t, pos)
                )

        # Layout -------------------------------------------------------
        self._tree_splitter = QSplitter(Qt.Horizontal)
        self._tree_splitter.addWidget(self._left_tree)
        self._tree_splitter.addWidget(self._right_tree)
        self._tree_splitter.setStretchFactor(0, 1)
        self._tree_splitter.setStretchFactor(1, 1)

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
        layout.addWidget(self._preview_splitter)

        # Synchronisation guards ---------------------------------------
        self._syncing_scroll = False
        self._syncing_expand = False
        self._preview_left_root = ""
        self._preview_right_root = ""
        self._preview_cli_path = ""
        self._preview_pending_path: Optional[str] = None
        self._preview_pending_sizes: tuple[int | None, int | None] = (None, None)
        self._preview_request_path: Optional[str] = None
        self._preview_worker: Optional[FunctionWorker] = None
        self._local_operations_enabled = True
        self._preview_debounce_timer = QTimer(self)
        self._preview_debounce_timer.setSingleShot(True)
        self._preview_debounce_timer.setInterval(_PREVIEW_DEBOUNCE_MS)
        self._preview_debounce_timer.timeout.connect(self._trigger_preview_load)

        # Connect synchronisation signals ------------------------------
        self._connect_sync()
        self._has_persisted_widths = False
        self._fitting = False  # True while we resize programmatically
        self._user_sized = False  # user dragged a column: stop auto-fitting
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(80)
        self._fit_timer.timeout.connect(self._fit_columns)
        for tree in (self._left_tree, self._right_tree):
            header = tree.header()
            if header is not None:
                # Measure only a bounded number of rows so large trees stay fast.
                header.setResizeContentsPrecision(_FIT_PRECISION_ROWS)
                header.sectionResized.connect(self._on_section_resized)
        self._left_tree.expanded.connect(self._schedule_fit)
        self._left_tree.collapsed.connect(self._schedule_fit)
        self._right_tree.expanded.connect(self._schedule_fit)
        self._right_tree.collapsed.connect(self._schedule_fit)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tree(self, root: TreeNode) -> None:
        """Replace the comparison data with a new tree."""
        self._source_model.set_tree(root)
        self._schedule_fit()

    def expand_all(self) -> None:
        """Expand every node in both trees."""
        self._left_tree.expandAll()
        self._right_tree.expandAll()

    def collapse_all(self) -> None:
        """Collapse every node in both trees."""
        self._left_tree.collapseAll()
        self._right_tree.collapseAll()

    def expand_folders_with_differences(
        self, tree: QTreeView, root_index: QModelIndex = QModelIndex()
    ) -> None:
        """Expand visible folders under *root_index* that contain differences."""
        model = tree.model()
        if model is None:
            return

        def _expand_if_different(index: QModelIndex) -> bool:
            node: Optional[TreeNode] = index.data(Qt.UserRole + 1)
            if node is None:
                return False

            has_difference = node.status != DiffStatus.SAME
            if node.is_dir:
                for row in range(model.rowCount(index)):
                    child = model.index(row, COL_NAME, index)
                    has_difference = _expand_if_different(child) or has_difference
                if has_difference:
                    tree.expand(index)
            return has_difference

        if root_index.isValid():
            root_index = model.index(root_index.row(), COL_NAME, root_index.parent())
            _expand_if_different(root_index)
            return
        for row in range(model.rowCount()):
            _expand_if_different(model.index(row, COL_NAME))

    def set_filters(
        self,
        show_identical: bool,
        show_different: bool,
        show_left_only: bool,
        show_right_only: bool,
        show_files_only: bool = False,
        search_text: str = "",
        diff_option_mode: Optional[str] = None,
        search_mode: str = "contains",
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
            search_mode,
        )
        self._schedule_fit()

    @property
    def search_error(self) -> str:
        """Return the active search syntax error, if any."""
        return self._proxy_model.search_error

    def set_diff_option_mode(self, mode: str) -> None:
        self._proxy_model.set_diff_option_mode(mode)
        self._schedule_fit()

    def selected_paths(self, side: Optional[str] = None) -> list[str]:
        """Return unique selected relative paths (both trees, or one *side*)."""
        paths: set[str] = set()
        trees = {"left": (self._left_tree,), "right": (self._right_tree,)}.get(
            side or "", (self._left_tree, self._right_tree)
        )
        for tree in trees:
            sel_model = tree.selectionModel()
            if sel_model is None:
                continue
            for index in sel_model.selectedRows(COL_NAME):
                node: Optional[TreeNode] = index.data(Qt.UserRole + 1)
                if node is not None and node.path:
                    paths.add(node.path)
        return sorted(paths)

    def visible_nodes(self) -> list[TreeNode]:
        """Return all rows accepted by the active folder-view filters.

        The traversal ignores expansion state, so report export includes the
        complete filtered result set rather than only expanded or on-screen
        rows. The proxy model remains the single authority for view filtering.
        """
        proxy = self._proxy_model
        visible: list[TreeNode] = []
        pending = [QModelIndex()]
        while pending:
            parent = pending.pop()
            for row in range(proxy.rowCount(parent)):
                index = proxy.index(row, 0, parent)
                node = proxy.data(index, Qt.UserRole + 1)
                if node is not None:
                    visible.append(node)
                if proxy.rowCount(index):
                    pending.append(index)
        return visible

    def select_paths(
        self,
        rel_paths: list[str],
        side: str = "left",
        *,
        operation: str = "replace",
    ) -> int:
        """Select, add, or remove many filter-visible rows in one tree."""
        from PySide6.QtCore import QItemSelection, QItemSelectionModel

        operations = {
            "replace": QItemSelectionModel.SelectionFlag.ClearAndSelect,
            "add": QItemSelectionModel.SelectionFlag.Select,
            "remove": QItemSelectionModel.SelectionFlag.Deselect,
        }
        if operation not in operations:
            raise ValueError(f"unsupported selection operation: {operation}")

        tree = self._left_tree if side == "left" else self._right_tree
        sel_model = tree.selectionModel()
        if sel_model is None:
            return 0
        selection = QItemSelection()
        count = 0
        last_col = self._proxy_model.columnCount() - 1
        for path in rel_paths:
            src = self._source_model.index_for_path(path)
            if not src.isValid():
                continue
            idx = self._proxy_model.mapFromSource(src)
            if not idx.isValid():
                continue  # hidden by a filter
            selection.select(idx, idx.sibling(idx.row(), last_col))
            count += 1
        if operation == "replace" and not count:
            sel_model.clearSelection()
        else:
            sel_model.select(
                selection,
                operations[operation] | QItemSelectionModel.SelectionFlag.Rows,
            )
        return count

    def select_path(self, rel_path: str) -> None:
        """Select and scroll to a row by its relative path."""
        proxy = self._proxy_model
        source = self._source_model

        source_idx = source.index_for_path(rel_path)
        if not source_idx.isValid():
            return

        proxy_idx = proxy.mapFromSource(source_idx)
        if not proxy_idx.isValid():
            return

        trees = {"left": (self._left_tree,), "right": (self._right_tree,)}.get(
            self._selection_mode, (self._left_tree, self._right_tree)
        )
        for tree in trees:
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

    def capture_view_state(self) -> dict:
        """Capture selection and scroll positions before replacing the tree."""
        selected = self.selected_paths()
        return {
            "selected_path": selected[0] if selected else "",
            "left_scroll": self._left_tree.verticalScrollBar().value(),
            "right_scroll": self._right_tree.verticalScrollBar().value(),
        }

    def restore_view_state(self, state: dict) -> None:
        """Restore a previously selected path and scroll position after refresh."""
        path = state.get("selected_path")
        if isinstance(path, str) and path:
            self.select_path(path)
        for tree, key in (
            (self._left_tree, "left_scroll"),
            (self._right_tree, "right_scroll"),
        ):
            value = state.get(key)
            if isinstance(value, int):
                tree.verticalScrollBar().setValue(value)

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

        wrapped = (forward and next_pos <= current_pos) or (
            not forward and next_pos >= current_pos
        )
        target = flat[next_pos]

        for tree in (self._left_tree, self._right_tree):
            s = tree.selectionModel()
            if s is not None:
                s.setCurrentIndex(
                    target, s.SelectionFlag.ClearAndSelect | s.SelectionFlag.Rows
                )
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

    def column_widths(self) -> dict:
        """Return column widths and the chosen optional columns for persistence."""
        return {
            "visible": self.visible_columns(),
            "left_name": self._left_tree.columnWidth(COL_NAME),
            "left_size": self._left_tree.columnWidth(COL_LEFT_SIZE),
            "left_date": self._left_tree.columnWidth(COL_LEFT_DATE),
            "right_name": self._right_tree.columnWidth(COL_NAME),
            "right_size": self._right_tree.columnWidth(COL_RIGHT_SIZE),
            "right_date": self._right_tree.columnWidth(COL_RIGHT_DATE),
        }

    def set_column_widths(self, widths: dict) -> None:
        """Apply persisted column widths (and optional columns) for both trees."""
        applied = False
        if "visible" in widths:
            self.set_visible_columns(widths.get("visible"))

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

        if applied:
            self._has_persisted_widths = True

    # ------------------------------------------------------------------
    # Tree construction helpers
    # ------------------------------------------------------------------

    def _create_tree(self) -> QTreeView:
        """Build a QTreeView with shared settings."""
        tree = QTreeView(self)
        tree.setModel(self._proxy_model)
        tree.setItemDelegate(self._delegate)

        tree.setAlternatingRowColors(False)
        tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        tree.setUniformRowHeights(True)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        header = tree.header()
        if header is not None:
            header.setStretchLastSection(False)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        tree.customContextMenuRequested.connect(self._on_context_menu)
        tree.doubleClicked.connect(self._on_double_click)

        return tree

    def _configure_left_tree(self) -> None:
        """Hide right-side columns in the left tree."""
        self._left_tree.setColumnHidden(COL_RIGHT_SIZE, True)
        self._left_tree.setColumnHidden(COL_RIGHT_DATE, True)
        self._left_tree.setColumnHidden(COL_STATUS, True)
        for key, _label in ATTRIBUTES:  # the left tree never shows right-side values
            self._left_tree.setColumnHidden(attr_column(key, "right"), True)

    def _configure_right_tree(self) -> None:
        """Hide left-side columns in the right tree."""
        self._right_tree.setColumnHidden(COL_LEFT_SIZE, True)
        self._right_tree.setColumnHidden(COL_LEFT_DATE, True)
        self._right_tree.setColumnHidden(COL_STATUS, True)
        for key, _label in ATTRIBUTES:  # the right tree never shows left-side values
            self._right_tree.setColumnHidden(attr_column(key, "left"), True)

    # -- selection scope: both panels (default) or one -----------------

    def _connect_selection_mirroring(self) -> None:
        for tree, side in ((self._left_tree, "left"), (self._right_tree, "right")):
            sel = tree.selectionModel()
            if sel is not None:
                sel.selectionChanged.connect(
                    lambda *_a, sd=side: self._on_tree_selection(sd)
                )
        for keys, mode in (("Alt+Left", "left"), ("Alt+Right", "right")):
            sc = QShortcut(QKeySequence(keys), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda m=mode: self.toggle_selection_limit(m))

    @property
    def selection_mode(self) -> str:
        return self._selection_mode

    def toggle_selection_limit(self, mode: str) -> None:
        """Limit the selection to *mode*'s panel; repeating it restores both."""
        self.set_selection_mode("both" if self._selection_mode == mode else mode)

    def set_selection_mode(self, mode: str) -> None:
        if mode not in ("both", "left", "right") or mode == self._selection_mode:
            return
        self._selection_mode = mode
        owner = {"left": self._left_tree, "right": self._right_tree}.get(mode)
        if owner is not None:
            self._apply_selection(owner, self._other_tree(owner), clear_only=True)
        else:
            # Back to both: mirror whichever panel currently holds a selection.
            src = (
                self._left_tree
                if self._left_tree.selectionModel().hasSelection()
                else self._right_tree
            )
            self._apply_selection(src, self._other_tree(src))
        self.selection_mode_changed.emit(mode)

    def _other_tree(self, tree: QTreeView) -> QTreeView:
        return self._right_tree if tree is self._left_tree else self._left_tree

    def _apply_selection(
        self, source: QTreeView, target: QTreeView, *, clear_only: bool = False
    ) -> None:
        from PySide6.QtCore import QItemSelectionModel

        tsel = target.selectionModel()
        if tsel is None or self._mirroring_selection:
            return
        self._mirroring_selection = True
        try:
            if clear_only:
                tsel.clearSelection()
            else:
                tsel.select(
                    source.selectionModel().selection(),
                    QItemSelectionModel.SelectionFlag.ClearAndSelect,
                )
        finally:
            self._mirroring_selection = False

    def _on_tree_selection(self, side: str) -> None:
        if self._mirroring_selection:
            return
        source = self._left_tree if side == "left" else self._right_tree
        target = self._other_tree(source)
        if self._selection_mode == "both":
            self._apply_selection(source, target)
        elif self._selection_mode != side:
            # Selection is limited to the other panel: ignore this one.
            self._apply_selection(source, source, clear_only=True)

    # -- optional columns (header right-click menu) --------------------

    def _columns_for_key(self, key: str) -> list[tuple[QTreeView, int]]:
        """(tree, model column) pairs controlled by a header-menu *key*."""
        left, right = self._left_tree, self._right_tree
        if key == "size":
            return [(left, COL_LEFT_SIZE), (right, COL_RIGHT_SIZE)]
        if key == "date":
            return [(left, COL_LEFT_DATE), (right, COL_RIGHT_DATE)]
        if key == "status":
            return [(left, COL_STATUS), (right, COL_STATUS)]
        return [(left, attr_column(key, "left")), (right, attr_column(key, "right"))]

    def _all_keys(self) -> list[str]:
        return [k for k, _ in _BASE_KEYS] + [k for k, _ in ATTRIBUTES]

    def _apply_visible_columns(self) -> None:
        # Hiding/showing a column emits sectionResized; that is not a user drag.
        was_fitting, self._fitting = self._fitting, True
        try:
            for key in self._all_keys():
                hidden = key not in self._visible_keys
                for tree, col in self._columns_for_key(key):
                    tree.setColumnHidden(col, hidden)
        finally:
            self._fitting = was_fitting

    def visible_columns(self) -> list[str]:
        """Keys of the optional columns currently shown, in menu order."""
        return [k for k in self._all_keys() if k in self._visible_keys]

    def set_visible_columns(self, keys) -> None:
        valid = set(self._all_keys())
        if not isinstance(keys, (list, tuple)):
            return
        self._visible_keys = {k for k in keys if k in valid}
        self._apply_visible_columns()
        self._schedule_fit()

    def reset_columns(self) -> None:
        self._visible_keys = set(_DEFAULT_VISIBLE_KEYS)
        self._apply_visible_columns()
        self.fit_columns_to_contents()

    def _toggle_column_key(self, key: str, on: bool) -> None:
        if on:
            self._visible_keys.add(key)
        else:
            self._visible_keys.discard(key)
        self._apply_visible_columns()
        if on and self._user_sized:
            # Keep the user's widths; just size the newly shown column.
            self._fitting = True
            try:
                for tree, col in self._columns_for_key(key):
                    tree.resizeColumnToContents(col)
            finally:
                self._fitting = False
        else:
            self._schedule_fit()

    def _on_header_menu(self, tree: QTreeView, pos) -> None:
        menu = QMenu(self)
        name_act = menu.addAction("Name")
        name_act.setCheckable(True)
        name_act.setChecked(True)
        name_act.setEnabled(False)
        labels = _BASE_KEYS + list(ATTRIBUTES)
        for i, (key, label) in enumerate(labels):
            if i == len(_BASE_KEYS):
                menu.addSeparator()
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(key in self._visible_keys)
            act.toggled.connect(lambda on, k=key: self._toggle_column_key(k, on))
        menu.addSeparator()
        menu.addAction("Fit Columns to Contents", self.fit_columns_to_contents)
        menu.addAction("Reset Columns", self.reset_columns)
        header = tree.header()
        menu.exec(
            header.viewport().mapToGlobal(pos)
            if header is not None
            else tree.mapToGlobal(pos)
        )

    def _resize_visible_columns(self) -> None:
        """Compatibility wrapper: fit columns to their contents."""
        self._fit_columns()

    def _schedule_fit(self, *_args) -> None:
        """Debounced auto-fit, unless the user chose widths themselves."""
        if self._user_sized:
            return
        self._fit_timer.start()

    def _on_section_resized(self, _logical: int, _old: int, _new: int) -> None:
        if not self._fitting:
            self._user_sized = True

    def fit_columns_to_contents(self) -> None:
        """Re-fit all columns now, overriding earlier manual or saved widths."""
        self._user_sized = False
        self._has_persisted_widths = False
        self._fit_columns()

    def _fit_columns(self) -> None:
        self._fitting = True
        try:
            for tree in (self._left_tree, self._right_tree):
                cols = tuple(
                    c
                    for c in range(tree.model().columnCount())
                    if not tree.isColumnHidden(c)
                )
                self._fit_tree_columns(tree, cols)
        finally:
            self._fitting = False

    def _fit_tree_columns(self, tree: QTreeView, columns: tuple[int, ...]) -> None:
        for col in columns:
            tree.resizeColumnToContents(col)
        # Keep the name column from crowding out Size/Date on deep paths.
        viewport = tree.viewport().width()
        cap = max(240, int(viewport * 0.6)) if viewport > 0 else 720
        name_width = tree.columnWidth(COL_NAME)
        if name_width > cap:
            tree.setColumnWidth(COL_NAME, cap)
        elif name_width < 120:
            tree.setColumnWidth(COL_NAME, 120)

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
            if not enabled and not self._local_operations_enabled:
                action.setToolTip(
                    "This action requires local filesystem access and is unavailable for remote sources."
                )
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
        _add_action(
            menu,
            "Expand Subfolders with Differences",
            "expand_differences",
            enabled=node.is_dir,
        )
        _add_action(menu, "Close Subfolders", "close_subfolders", enabled=node.is_dir)
        menu.addSeparator()

        local_enabled = self._local_operations_enabled
        _add_action(
            menu, "Set as Base Folder", "set_base_folder", enabled=local_enabled
        )
        _add_action(
            menu, "Set as Base on Other Side", "set_base_other", enabled=local_enabled
        )
        _add_action(
            menu,
            "Open in New View",
            "open_new_view",
            enabled=not node.is_dir and local_enabled,
        )

        open_with_menu = menu.addMenu("Open With")
        _add_action(
            open_with_menu,
            "Open with System Default",
            "open_ext",
            enabled=local_enabled,
        )
        _add_action(
            open_with_menu,
            "Open with Saved Application",
            "open_saved",
            enabled=not node.is_dir and local_enabled,
        )
        _add_action(
            open_with_menu,
            "Choose Application…",
            "open_with_picker",
            enabled=not node.is_dir and local_enabled,
        )

        _add_action(
            menu,
            "Compare Contents...",
            "compare_contents",
            shortcut="F7",
            enabled=not node.is_dir and local_enabled,
        )
        _add_action(
            menu, "Align With...", "align_with", shortcut="F6", enabled=local_enabled
        )
        menu.addSeparator()

        _add_action(menu, "Copy Left to Right", "copy_lr", enabled=local_enabled)
        _add_action(menu, "Copy Right to Left", "copy_rl", enabled=local_enabled)
        _add_action(menu, "Copy to Folder...", "copy_to_folder", enabled=local_enabled)
        _add_action(menu, "Move to Folder...", "move_to_folder", enabled=local_enabled)
        _add_action(menu, "Delete...", "delete_item", enabled=local_enabled)
        _add_action(menu, "Rename", "rename_item", shortcut="F2", enabled=local_enabled)
        _add_action(menu, "Attributes...", "attributes", enabled=local_enabled)
        _add_action(menu, "Touch...", "touch_item", enabled=local_enabled)
        _add_action(menu, "Exclude", "exclude_item")
        _add_action(
            menu, "New Folder...", "new_folder", shortcut="Ins", enabled=local_enabled
        )
        _add_action(menu, "Copy Filename", "copy_filename")
        _add_action(menu, "Ignored", "ignored_toggle", checkable=True, checked=False)
        _add_action(menu, "Refresh Selection", "refresh_selection", shortcut="Shift+F5")

        menu.addSeparator()
        sync_menu = menu.addMenu("Synchronize")
        _add_action(
            sync_menu,
            "Open Synchronize Dialog",
            "sync_dialog",
            enabled=local_enabled,
        )

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
            if command == "expand_differences":
                self.expand_folders_with_differences(tree, index)
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

    def set_preview_cli(self, cli_path: str) -> None:
        """Set the CLI executable used to fetch remote file previews."""
        self._preview_cli_path = cli_path

    def set_local_operations_enabled(self, enabled: bool) -> None:
        """Control context actions that require direct local filesystem access."""
        self._local_operations_enabled = bool(enabled)

    def _on_selection_changed(
        self, current: QModelIndex, _previous: QModelIndex
    ) -> None:
        """Update the preview panels when a new row is selected.

        Debounced: rapid arrow-key navigation restarts the timer instead of
        firing a read per row.
        """
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
            self._preview_pending_sizes = (None, None)
            self._preview_debounce_timer.stop()
            self._left_preview.setPlainText("")
            self._right_preview.setPlainText("")
            return

        self._preview_pending_path = node.path
        self._preview_pending_sizes = (node.left_size, node.right_size)
        self._preview_debounce_timer.start()

    def _trigger_preview_load(self) -> None:
        """Start the background read for the debounced pending selection."""
        rel_path = self._preview_pending_path
        if rel_path is None:
            return
        self._preview_request_path = rel_path

        worker = FunctionWorker(
            _read_preview_pair,
            self._preview_left_root,
            self._preview_right_root,
            rel_path,
            self._preview_cli_path,
            *self._preview_pending_sizes,
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
