"""Tests for the shared folder-filter and navigation search matcher."""

from __future__ import annotations

from teczka.models.comparison import TreeNode
from teczka.models.tree_model import ComparisonFilterProxy, ComparisonTreeModel
from teczka.utils.cli_bridge import DiffStatus
from teczka.utils.name_search import compile_name_search


def test_contains_search_is_case_insensitive():
    matcher = compile_name_search("REPORT")

    assert matcher.matches("reports/annual-report.txt")
    assert not matcher.matches("notes.txt")


def test_wildcard_search_matches_relative_paths():
    matcher = compile_name_search("*.TXT", "wildcard")

    assert matcher.matches("reports/annual-report.txt")
    assert not matcher.matches("notes.md")


def test_regex_search_and_invalid_expression():
    matcher = compile_name_search(r"^reports/annual-\d+\.txt$", "regex")
    invalid = compile_name_search("[", "regex")

    assert matcher.matches("reports/annual-2026.txt")
    assert not matcher.matches("reports/annual-report.txt")
    assert invalid.error
    assert not invalid.matches("anything")


def test_proxy_uses_search_mode_for_tree_paths(qapp):
    root = TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
    reports = TreeNode(
        name="reports", path="reports", status=DiffStatus.SAME, is_dir=True
    )
    reports.add_child(
        TreeNode(
            name="annual-report.txt",
            path="reports/annual-report.txt",
            status=DiffStatus.DIFFERENT,
            is_dir=False,
        )
    )
    reports.add_child(
        TreeNode(
            name="notes.md",
            path="reports/notes.md",
            status=DiffStatus.DIFFERENT,
            is_dir=False,
        )
    )
    root.add_child(reports)

    source = ComparisonTreeModel()
    source.set_tree(root)
    proxy = ComparisonFilterProxy()
    proxy.setSourceModel(source)
    proxy.apply_filters(True, True, True, True, False, "*.txt", search_mode="wildcard")

    assert proxy.rowCount() == 1
    parent = proxy.index(0, 0)
    assert parent.data() == "reports"
    assert proxy.rowCount(parent) == 1
    assert proxy.index(0, 0, parent).data() == "annual-report.txt"

    proxy.apply_filters(True, True, True, True, False, "[", search_mode="regex")
    assert proxy.search_error
    assert proxy.rowCount() == 0
