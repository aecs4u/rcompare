"""Side-by-side folder comparison view (Beyond Compare style)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QModelIndex, QTimer
from PySide6.QtGui import QColor, QPainter, QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
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
        """Apply visibility and search filters."""
        self._proxy_model.set_filter_flags(
            show_identical, show_different, show_left_only, show_right_only, show_files_only,
        )
        if diff_option_mode is not None:
            self._proxy_model.set_diff_option_mode(diff_option_mode)
        self._proxy_model.set_search_text(search_text)

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

    def column_widths(self) -> dict[str, int]:
        """Return current visible column widths for persistence."""
        return {
            "left_name": self._left_tree.columnWidth(COL_NAME),
            "left_size": self._left_tree.columnWidth(COL_LEFT_SIZE),
            "left_date": self._left_tree.columnWidth(COL_LEFT_DATE),
            "right_name": self._right_tree.columnWidth(COL_NAME),
            "right_size": self._right_tree.columnWidth(COL_RIGHT_SIZE),
            "right_date": self._right_tree.columnWidth(COL_RIGHT_DATE),
        }

    def set_column_widths(self, widths: dict[str, int]) -> None:
        """Apply persisted column widths for both trees."""
        applied = False

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

    def _configure_right_tree(self) -> None:
        """Hide left-side columns in the right tree."""
        self._right_tree.setColumnHidden(COL_LEFT_SIZE, True)
        self._right_tree.setColumnHidden(COL_LEFT_DATE, True)
        self._right_tree.setColumnHidden(COL_STATUS, True)

    def _resize_visible_columns(self) -> None:
        """Auto-size visible columns for both LH/RH trees after loading data."""
        self._resize_tree_columns(self._left_tree, (COL_NAME, COL_LEFT_SIZE, COL_LEFT_DATE))
        self._resize_tree_columns(self._right_tree, (COL_NAME, COL_RIGHT_SIZE, COL_RIGHT_DATE))

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
        """Update the preview panels when a new row is selected."""
        if not self._preview_visible:
            return
        if not current.isValid():
            return

        source_index = self._proxy_model.mapToSource(current)
        node = source_index.internalPointer()
        if node is None or not hasattr(node, "path") or not hasattr(node, "is_dir"):
            return
        if node.is_dir:
            self._left_preview.setPlainText("")
            self._right_preview.setPlainText("")
            return

        self._load_preview(node.path)

    def _load_preview(self, rel_path: str) -> None:
        """Load file content previews for both sides."""
        import os

        max_preview_lines = 100
        max_preview_bytes = 64 * 1024  # 64 KB

        for root, preview_widget in (
            (self._preview_left_root, self._left_preview),
            (self._preview_right_root, self._right_preview),
        ):
            if not root:
                preview_widget.setPlainText("")
                continue

            full_path = os.path.join(root, rel_path)
            if not os.path.isfile(full_path):
                preview_widget.setPlainText(f"(not present on this side)")
                continue

            try:
                size = os.path.getsize(full_path)
                if size > max_preview_bytes:
                    with open(full_path, "r", errors="replace") as f:
                        lines = []
                        for i, line in enumerate(f):
                            if i >= max_preview_lines:
                                break
                            lines.append(line.rstrip("\n"))
                    lines.append(f"\n... (truncated, {size:,} bytes total)")
                    preview_widget.setPlainText("\n".join(lines))
                else:
                    with open(full_path, "r", errors="replace") as f:
                        content = f.read()
                    preview_widget.setPlainText(content)
            except (OSError, UnicodeDecodeError):
                preview_widget.setPlainText("(binary or unreadable file)")

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
