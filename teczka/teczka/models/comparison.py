"""Data models for comparison results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterable, Optional

from ..utils.cli_bridge import DiffEntry, DiffStatus, ScanReport


@dataclass
class TreeNode:
    """A node in the comparison tree."""

    name: str
    path: str
    status: DiffStatus
    is_dir: bool
    left_size: Optional[int] = None
    left_modified: Optional[int] = None
    right_size: Optional[int] = None
    right_modified: Optional[int] = None
    children: list[TreeNode] = field(default_factory=list)
    parent: Optional[TreeNode] = field(default=None, repr=False)
    _row: int = field(default=0, repr=False)
    _child_map: dict[str, TreeNode] = field(default_factory=dict, repr=False)
    entry: Optional[DiffEntry] = field(default=None, repr=False, compare=False)
    # Set on the root node only: the scanned folders, used to read extra
    # file attributes (permissions, owner, ...) on demand.
    left_root: str = ""
    right_root: str = ""

    @property
    def row(self) -> int:
        """Return this node's index within its parent's children.

        Cached at insertion/sort time — no longer a linear
        ``parent.children.index(self)`` scan.
        """
        return self._row

    @property
    def child_count(self) -> int:
        return len(self.children)

    def add_child(self, child: TreeNode) -> None:
        """Append *child*, keeping the name->node lookup map in sync."""
        child._row = len(self.children)
        self.children.append(child)
        self._child_map[child.name] = child

    def get_child(self, name: str) -> Optional[TreeNode]:
        """O(1) lookup of a direct child by name."""
        return self._child_map.get(name)


def build_tree(report: ScanReport) -> TreeNode:
    """Build a hierarchical tree from flat DiffEntry list."""
    return _build_tree_from_entries(report.entries)


def _build_tree_with_options_impl(
    report: ScanReport,
    mode: str = "compare_structure",
    *,
    always_show_folders: bool = True,
) -> TreeNode:
    """Build a tree according to folder-view options.

    Modes:
    - ``compare_structure``: default hierarchical tree.
    - ``files_only``: focus on files; directories are optional.
    - ``ignore_structure``: flat list of files (path shown as name).
    """
    mode = (mode or "compare_structure").strip().lower()

    if mode == "compare_structure":
        return _build_tree_from_entries(report.entries)

    if mode == "files_only":
        filtered: list[DiffEntry] = []
        for entry in report.entries:
            is_dir = entry_is_dir(entry)
            if is_dir and not always_show_folders:
                continue
            filtered.append(entry)
        return _build_tree_from_entries(filtered)

    if mode == "ignore_structure":
        return _build_flat_file_tree(report.entries)

    return _build_tree_from_entries(report.entries)


def _build_tree_from_entries(entries: Iterable[DiffEntry]) -> TreeNode:
    """Build a hierarchical tree from a sequence of entries."""
    root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)

    for entry in entries:
        parts = PurePosixPath(entry.path).parts
        current = root
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            child = current.get_child(part)
            if child is None:
                path_so_far = str(PurePosixPath(*parts[: i + 1]))
                is_dir_node = not is_last
                if is_last and entry.left and entry.left.is_dir:
                    is_dir_node = True
                if is_last and entry.right and entry.right.is_dir:
                    is_dir_node = True
                child = TreeNode(
                    name=part,
                    path=path_so_far,
                    status=DiffStatus.SAME if not is_last else entry.status,
                    is_dir=is_dir_node,
                    parent=current,
                )
                current.add_child(child)
            if is_last:
                child.status = entry.status
                child.entry = entry
                if entry.left:
                    child.left_size = entry.left.size
                    child.left_modified = entry.left.modified_unix
                if entry.right:
                    child.right_size = entry.right.size
                    child.right_modified = entry.right.modified_unix
            current = child

    _aggregate_status(root)
    _sort_children(root)
    return root


def _build_flat_file_tree(entries: Iterable[DiffEntry]) -> TreeNode:
    """Build a flat file list, ignoring folder structure."""
    root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
    seen_paths: set[str] = set()

    for entry in sorted(entries, key=lambda e: e.path.lower()):
        if entry_is_dir(entry):
            continue
        if entry.path in seen_paths:
            continue
        seen_paths.add(entry.path)
        node = TreeNode(
            name=entry.path,
            path=entry.path,
            status=entry.status,
            is_dir=False,
            parent=root,
            entry=entry,
        )
        if entry.left:
            node.left_size = entry.left.size
            node.left_modified = entry.left.modified_unix
        if entry.right:
            node.right_size = entry.right.size
            node.right_modified = entry.right.modified_unix
        root.add_child(node)

    _aggregate_status(root)
    _sort_children(root)
    return root


def entry_is_dir(entry: DiffEntry) -> bool:
    """Return whether either side identifies an entry as a directory."""
    if entry.left and entry.left.is_dir:
        return True
    if entry.right and entry.right.is_dir:
        return True
    return False


def _aggregate_status(node: TreeNode) -> None:
    """Propagate worst status up from children."""
    if not node.children:
        return
    for child in node.children:
        _aggregate_status(child)
    node.status = aggregate_node_status(node)


def aggregate_node_status(node: TreeNode) -> DiffStatus:
    """Return a folder's status from its direct result and current children."""
    base_status = node.entry.status if node.entry is not None else DiffStatus.SAME
    statuses = {c.status for c in node.children}
    if DiffStatus.DIFFERENT in statuses:
        return DiffStatus.DIFFERENT
    if DiffStatus.ORPHAN_LEFT in statuses or DiffStatus.ORPHAN_RIGHT in statuses:
        return DiffStatus.DIFFERENT
    if DiffStatus.UNCHECKED in statuses:
        return DiffStatus.UNCHECKED
    return base_status


def _sort_children(node: TreeNode) -> None:
    """Sort: directories first, then alphabetically."""
    node.children.sort(key=lambda c: (not c.is_dir, c.name.lower()))
    for i, child in enumerate(node.children):
        child._row = i
        _sort_children(child)


def build_tree_with_options(
    report: ScanReport,
    mode: str = "compare_structure",
    *,
    always_show_folders: bool = True,
) -> TreeNode:
    """Build the tree for *report* and record the scanned roots on its root node."""
    tree = _build_tree_with_options_impl(
        report, mode, always_show_folders=always_show_folders
    )
    tree.left_root = str(getattr(report, "left", "") or "")
    tree.right_root = str(getattr(report, "right", "") or "")
    return tree
