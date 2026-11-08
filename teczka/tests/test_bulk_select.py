from types import SimpleNamespace as NS

from teczka.utils.bulk_select import (
    collapse_to_top_level,
    find_by_criteria,
    find_by_status,
    find_identical,
)
from teczka.utils.cli_bridge import DiffStatus

S, D, OL, OR = (
    DiffStatus.SAME,
    DiffStatus.DIFFERENT,
    DiffStatus.ORPHAN_LEFT,
    DiffStatus.ORPHAN_RIGHT,
)


def f(path, status=S, left=True, right=True):
    return NS(
        path=path,
        status=status,
        left=NS(is_dir=False) if left else None,
        right=NS(is_dir=False) if right else None,
    )


def d(path, left=True, right=True, status=S):
    return NS(
        path=path,
        status=status,
        left=NS(is_dir=True) if left else None,
        right=NS(is_dir=True) if right else None,
    )


REPORT = NS(
    entries=[
        d("same_dir"),
        f("same_dir/a.txt"),
        f("same_dir/b.txt"),
        d("mixed"),
        f("mixed/ok.txt"),
        f("mixed/changed.txt", D),
        d("with_orphan"),
        f("with_orphan/x.txt"),
        f("with_orphan/new.txt", OR, left=False),
        d("nested"),
        d("nested/inner"),
        f("nested/inner/z.txt"),
        d("right_only_dir", left=False),
        f("right_only_dir/q.txt", OR, left=False),
        f("top.txt"),
        f("lonely.txt", OL, right=False),
    ]
)


def test_files_only():
    sel = find_identical(REPORT, include_folders=False)
    assert sel.folders == ()
    assert set(sel.files) == {
        "same_dir/a.txt",
        "same_dir/b.txt",
        "mixed/ok.txt",
        "with_orphan/x.txt",
        "nested/inner/z.txt",
        "top.txt",
    }


def test_folders_option_collapses_to_top_level_folders():
    sel = find_identical(REPORT, include_folders=True)
    assert set(sel.folders) == {"same_dir", "nested"}
    assert set(sel.files) == {"mixed/ok.txt", "with_orphan/x.txt", "top.txt"}


def test_folder_with_orphan_or_difference_is_never_selected():
    folders = set(find_identical(REPORT, True).folders)
    assert not folders & {"mixed", "with_orphan", "right_only_dir"}


def test_collapse_to_top_level():
    assert collapse_to_top_level(["a/b/c.txt", "a", "a/b", "z.txt", "z.txt"]) == [
        "a",
        "z.txt",
    ]


def test_status_and_criteria_selection_supports_orphans_and_globs():
    nodes = [
        NS(path="left/report.txt", status=OL, left_size=1024),
        NS(path="left/large.txt", status=OL, left_size=4096),
        NS(path="right/report.txt", status=OR, left_size=None),
        NS(path="same.txt", status=S, left_size=1024),
        NS(
            path="newer-left.txt",
            status=D,
            left_size=1024,
            left_modified=200,
            right_modified=100,
        ),
        NS(
            path="newer-right.txt",
            status=D,
            left_size=1024,
            left_modified=100,
            right_modified=200,
        ),
    ]

    assert find_by_status(nodes, {DiffStatus.ORPHAN_LEFT}) == (
        "left/large.txt",
        "left/report.txt",
    )
    assert find_by_criteria(
        nodes,
        {
            "statuses": ["left_only"],
            "pattern": "*.txt",
            "min_size": 2,
            "max_size": 4,
            "mode": "select",
        },
    ) == ["left/large.txt"]

    assert find_by_criteria(
        nodes,
        {
            "statuses": ["different"],
            "newer_sides": ["left"],
            "pattern": "*.txt",
            "min_size": 0,
            "max_size": 0,
        },
    ) == ["newer-left.txt"]


def test_newer_criteria_supports_both_sides_and_ignores_ties():
    nodes = [
        NS(
            path="newer-left.txt",
            status=D,
            left_size=1024,
            left_modified=200,
            right_modified=100,
        ),
        NS(
            path="newer-right.txt",
            status=D,
            left_size=1024,
            left_modified=100,
            right_modified=200,
        ),
        NS(
            path="same-time.txt",
            status=D,
            left_size=1024,
            left_modified=200,
            right_modified=200,
        ),
    ]

    criteria = {
        "statuses": ["different"],
        "newer_sides": ["left", "right"],
        "pattern": "",
        "min_size": 0,
        "max_size": 0,
    }
    assert find_by_criteria(nodes, criteria) == ["newer-left.txt", "newer-right.txt"]
