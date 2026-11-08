"""Tests for folder-tree navigation actions."""

from __future__ import annotations

from teczka.models.comparison import TreeNode
from teczka.utils.cli_bridge import DiffStatus
from teczka.views.folder_view import FolderView


def test_expand_folders_with_differences_keeps_identical_branches_closed(qtbot):
    root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
    outer = TreeNode(name="outer", path="outer", status=DiffStatus.SAME, is_dir=True)
    changed = TreeNode(
        name="changed", path="outer/changed", status=DiffStatus.SAME, is_dir=True
    )
    changed.add_child(
        TreeNode(
            name="diff.txt",
            path="outer/changed/diff.txt",
            status=DiffStatus.DIFFERENT,
            is_dir=False,
        )
    )
    unchanged = TreeNode(
        name="unchanged", path="outer/unchanged", status=DiffStatus.SAME, is_dir=True
    )
    unchanged.add_child(
        TreeNode(
            name="same.txt",
            path="outer/unchanged/same.txt",
            status=DiffStatus.SAME,
            is_dir=False,
        )
    )
    outer.add_child(changed)
    outer.add_child(unchanged)
    root.add_child(outer)

    view = FolderView()
    qtbot.addWidget(view)
    view.set_tree(root)
    tree = view._left_tree
    source_index = view._source_model.index_for_path("outer")
    proxy_index = view._proxy_model.mapFromSource(source_index)

    view.expand_folders_with_differences(tree, proxy_index)

    changed_index = view._proxy_model.mapFromSource(
        view._source_model.index_for_path("outer/changed")
    )
    unchanged_index = view._proxy_model.mapFromSource(
        view._source_model.index_for_path("outer/unchanged")
    )
    assert tree.isExpanded(proxy_index)
    assert tree.isExpanded(changed_index)
    assert not tree.isExpanded(unchanged_index)


def test_path_selection_can_add_and_remove_without_clearing_other_rows(qtbot):
    root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
    for name, status in (
        ("left.txt", DiffStatus.ORPHAN_LEFT),
        ("different.txt", DiffStatus.DIFFERENT),
        ("same.txt", DiffStatus.SAME),
    ):
        root.add_child(
            TreeNode(name=name, path=name, status=status, is_dir=False)
        )

    view = FolderView()
    qtbot.addWidget(view)
    view.set_tree(root)
    view.set_filters(True, True, True, True)

    assert view.select_paths(["left.txt"], side="left") == 1
    assert view.select_paths(
        ["different.txt"], side="left", operation="add"
    ) == 1
    assert set(view.selected_paths("left")) == {"left.txt", "different.txt"}

    assert view.select_paths(
        ["left.txt"], side="left", operation="remove"
    ) == 1
    assert view.selected_paths("left") == ["different.txt"]
