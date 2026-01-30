"""Data models for comparison results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Optional

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

    @property
    def row(self) -> int:
        """Return this node's index within its parent's children."""
        if self.parent is None:
            return 0
        return self.parent.children.index(self)

    @property
    def child_count(self) -> int:
        return len(self.children)


def build_tree(report: ScanReport) -> TreeNode:
    """Build a hierarchical tree from flat DiffEntry list."""
    root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)

    for entry in report.entries:
        parts = PurePosixPath(entry.path).parts
        current = root
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            # Find existing child
            child = None
            for c in current.children:
                if c.name == part:
                    child = c
                    break
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
                current.children.append(child)
            if is_last:
                child.status = entry.status
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
    for child in node.children:
        _sort_children(child)
