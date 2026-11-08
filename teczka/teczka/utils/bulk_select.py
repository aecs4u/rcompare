"""Pure helpers for "select all identical items" and bulk delete workflows."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Iterable

from .cli_bridge import DiffStatus


@dataclass(frozen=True)
class IdenticalSelection:
    files: tuple[str, ...]
    folders: tuple[str, ...]  # top-most folders containing only identical items

    @property
    def paths(self) -> list[str]:
        return [*self.folders, *self.files]


def _is_dir(e) -> bool:
    return bool((e.left and e.left.is_dir) or (e.right and e.right.is_dir))


def _ancestors(path: str):
    parts = path.split("/")[:-1]
    for i in range(1, len(parts) + 1):
        yield "/".join(parts[:i])


def find_identical(report, include_folders: bool) -> IdenticalSelection:
    """Identical items present on both sides.

    Files: status Same, a file on each side.
    Folders (optional): present on both sides, and *every* entry beneath them is
    an identical item present on both sides.  Only top-most folders are
    returned, and files inside a returned folder are omitted (deleting the
    folder covers them).
    """
    entries = list(report.entries)
    bad_dirs: set[str] = set()  # folders that hold something not identical
    files: list[str] = []
    dirs: list[str] = []
    for e in entries:
        both = bool(e.left and e.right)
        if _is_dir(e):
            if both:
                dirs.append(e.path)
            else:
                bad_dirs.update(_ancestors(e.path))
                bad_dirs.add(e.path)  # a one-sided folder is never "identical"
            continue
        if both and e.status == DiffStatus.SAME:
            files.append(e.path)
        else:
            bad_dirs.update(_ancestors(e.path))

    folders: list[str] = []
    if include_folders:
        chosen: set[str] = set()
        for d in sorted(d for d in dirs if d not in bad_dirs):
            # keep only top-most: skip if an ancestor is already chosen
            if not any(a in chosen for a in _ancestors(d)):
                folders.append(d)
                chosen.add(d)
        files = [f for f in files if not any(a in chosen for a in _ancestors(f))]
    return IdenticalSelection(tuple(sorted(files)), tuple(folders))


def find_by_status(nodes: Iterable, statuses: Iterable[DiffStatus]) -> tuple[str, ...]:
    """Return paths of nodes whose aggregated folder-view status is selected."""
    selected_statuses = set(statuses)
    return tuple(
        sorted(
            {
                node.path
                for node in nodes
                if node.path and node.status in selected_statuses
            }
        )
    )


def find_by_criteria(nodes: Iterable, criteria: dict) -> list[str]:
    """Match filter-visible nodes by status, newer side, path glob, and LHS size."""
    nodes = list(nodes)
    status_by_key = {
        "identical": DiffStatus.SAME,
        "different": DiffStatus.DIFFERENT,
        "left_only": DiffStatus.ORPHAN_LEFT,
        "right_only": DiffStatus.ORPHAN_RIGHT,
    }
    statuses = {
        status_by_key[key]
        for key in criteria.get("statuses", ())
        if key in status_by_key
    }
    newer_sides = set(criteria.get("newer_sides", ())) & {"left", "right"}
    status_candidates = set(find_by_status(nodes, statuses))
    newer_candidates = {
        node.path
        for node in nodes
        if (left_modified := getattr(node, "left_modified", None)) is not None
        and (right_modified := getattr(node, "right_modified", None)) is not None
        if node.path
        and (
            ("left" in newer_sides and left_modified > right_modified)
            or ("right" in newer_sides and right_modified > left_modified)
        )
    }
    if statuses and newer_sides:
        candidates = status_candidates & newer_candidates
    elif statuses:
        candidates = status_candidates
    else:
        candidates = newer_candidates
    pattern = str(criteria.get("pattern", "")).strip().casefold()
    min_bytes = max(0, int(criteria.get("min_size", 0))) * 1024
    max_kb = max(0, int(criteria.get("max_size", 0)))
    max_bytes = max_kb * 1024 if max_kb else None

    matches: list[str] = []
    for node in nodes:
        path = node.path
        if path not in candidates:
            continue
        if pattern and not fnmatchcase(path.casefold(), pattern):
            continue
        size = node.left_size if node.left_size is not None else 0
        if size < min_bytes or (max_bytes is not None and size > max_bytes):
            continue
        matches.append(path)
    return sorted(set(matches))


def collapse_to_top_level(paths) -> list[str]:
    """Drop paths nested under another path in the list (delete the parent once)."""
    unique = sorted(set(paths))
    chosen: list[str] = []
    chosen_set: set[str] = set()
    for p in unique:
        if not any(a in chosen_set for a in _ancestors(p)):
            chosen.append(p)
            chosen_set.add(p)
    return chosen
