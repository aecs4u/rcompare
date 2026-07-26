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


def build_tree_with_options(
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
            is_dir = _entry_is_dir(entry)
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
        _insert_entry(root, entry)

    _aggregate_status(root)
    _sort_children(root)
    return root


class IncrementalTreeBuilder:
    """Builds a comparison tree entry-by-entry as results stream in.

    ``_build_tree_from_entries`` needs the complete entry list up front, which
    forces the GUI to wait for the whole scan before showing anything. This
    builder inserts one entry at a time so partial results can be published
    while the CLI is still running (see ``workers/comparison_worker.py``).

    ``finish()`` applies the aggregation and sorting passes that the batch
    builder does at the end; ``snapshot()`` applies them to a copy so a partial
    tree can be handed to the model without freezing further insertion.
    """

    def __init__(self) -> None:
        self.root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
        self._count = 0

    def __len__(self) -> int:
        return self._count

    def add(self, entry: DiffEntry) -> None:
        """Insert a single entry, creating intermediate nodes as needed."""
        _insert_entry(self.root, entry)
        self._count += 1

    def finish(self) -> TreeNode:
        """Aggregate and sort in place, returning the completed tree."""
        _aggregate_status(self.root)
        _sort_children(self.root)
        return self.root

    def snapshot(self) -> TreeNode:
        """Return an aggregated, sorted copy safe to publish mid-stream."""
        copy = _copy_tree(self.root, None)
        _aggregate_status(copy)
        _sort_children(copy)
        return copy


def _insert_entry(root: TreeNode, entry: DiffEntry) -> None:
    """Insert one entry into *root*, creating missing intermediate nodes."""
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
            if entry.left:
                child.left_size = entry.left.size
                child.left_modified = entry.left.modified_unix
            if entry.right:
                child.right_size = entry.right.size
                child.right_modified = entry.right.modified_unix
        current = child


def _copy_tree(node: TreeNode, parent: Optional[TreeNode]) -> TreeNode:
    """Deep-copy a tree so the original can keep growing independently."""
    clone = TreeNode(
        name=node.name,
        path=node.path,
        status=node.status,
        is_dir=node.is_dir,
        left_size=node.left_size,
        left_modified=node.left_modified,
        right_size=node.right_size,
        right_modified=node.right_modified,
        parent=parent,
    )
    clone.children = [_copy_tree(c, clone) for c in node.children]
    return clone


def _build_flat_file_tree(entries: Iterable[DiffEntry]) -> TreeNode:
    """Build a flat file list, ignoring folder structure."""
    root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
    seen_paths: set[str] = set()

    for entry in sorted(entries, key=lambda e: e.path.lower()):
        if _entry_is_dir(entry):
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


def _entry_is_dir(entry: DiffEntry) -> bool:
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
    statuses = {c.status for c in node.children}
    if DiffStatus.DIFFERENT in statuses:
        node.status = DiffStatus.DIFFERENT
    elif DiffStatus.ORPHAN_LEFT in statuses or DiffStatus.ORPHAN_RIGHT in statuses:
        node.status = DiffStatus.DIFFERENT
    elif DiffStatus.UNCHECKED in statuses:
        node.status = DiffStatus.UNCHECKED


def _sort_children(node: TreeNode) -> None:
    """Sort: directories first, then alphabetically."""
    node.children.sort(key=lambda c: (not c.is_dir, c.name.lower()))
    for i, child in enumerate(node.children):
        child._row = i
        _sort_children(child)
