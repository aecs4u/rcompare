from types import SimpleNamespace as NS

from teczka.utils.cli_bridge import DiffStatus
from teczka.utils.criteria import CompareCriteria, apply_criteria


def entry(lsize, lt, rsize, rt, status=DiffStatus.SAME):
    return NS(path="f", status=status,
              left=NS(size=lsize, modified_unix=lt, is_dir=False),
              right=NS(size=rsize, modified_unix=rt, is_dir=False))


def run(e, **kw):
    rep = NS(entries=[e], summary=None)
    apply_criteria(rep, CompareCriteria(**kw))
    return rep.entries[0].status


def test_content_mode_leaves_cli_result():
    assert run(entry(1, 0, 2, 999)) == DiffStatus.SAME


def test_size_only():
    assert run(entry(1, 0, 1, 999), mode="size") == DiffStatus.SAME
    assert run(entry(1, 0, 2, 0), mode="size") == DiffStatus.DIFFERENT


def test_time_tolerance():
    assert run(entry(1, 100, 9, 102), mode="time", tolerance_s=2) == DiffStatus.SAME
    assert run(entry(1, 100, 1, 103), mode="size_time", tolerance_s=2) == DiffStatus.DIFFERENT


def test_whole_hour_offsets():
    e = entry(1, 1000, 1, 1000 + 3600)
    assert run(e, mode="time") == DiffStatus.DIFFERENT
    assert run(entry(1, 1000, 1, 1000 + 7200), mode="time", ignore_hour_offsets=True) == DiffStatus.SAME
    assert run(entry(1, 1000, 1, 1000 + 3601), mode="time", ignore_hour_offsets=True) == DiffStatus.DIFFERENT


def test_orphans_and_dirs_untouched_and_summary_updates():
    orphan = NS(path="o", status=DiffStatus.ORPHAN_LEFT, left=NS(size=1, modified_unix=0, is_dir=False), right=None)
    rep = NS(entries=[orphan, entry(1, 0, 1, 50)], summary=None)
    apply_criteria(rep, CompareCriteria(mode="size"))
    assert rep.entries[0].status == DiffStatus.ORPHAN_LEFT
    assert rep.summary.same == 1 and rep.summary.orphan_left == 1 and rep.summary.total == 2


def test_roundtrip_and_bad_data():
    c = CompareCriteria("time", 5, True)
    assert CompareCriteria.from_dict(c.to_dict()) == c
    assert CompareCriteria.from_dict({"mode": "nope", "tolerance_s": "x"}) == CompareCriteria()
