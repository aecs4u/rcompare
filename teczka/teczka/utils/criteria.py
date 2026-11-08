"""Comparison criteria (Beyond Compare "Compare" options for folder sessions)."""

from __future__ import annotations

import dataclasses
from typing import Any

MODES: list[tuple[str, str]] = [
    ("content", "Content (hash / full compare)"),
    ("size_time", "Size and modified time"),
    ("time", "Modified time only"),
    ("size", "Size only"),
]
_MODE_KEYS = {k for k, _ in MODES}


@dataclasses.dataclass(frozen=True)
class CompareCriteria:
    mode: str = "content"
    tolerance_s: int = 0           # modified times closer than this are "equal"
    ignore_hour_offsets: bool = False  # treat whole-hour gaps (DST/timezone) as equal

    @property
    def is_default(self) -> bool:
        return self == CompareCriteria()

    @property
    def needs_hashes(self) -> bool:
        return self.mode == "content"

    def times_equal(self, a: int | None, b: int | None) -> bool:
        if a is None or b is None:
            return a == b
        delta = abs(a - b)
        if delta <= self.tolerance_s:
            return True
        if self.ignore_hour_offsets and delta >= 3600:
            rem = delta % 3600
            return min(rem, 3600 - rem) <= self.tolerance_s
        return False

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "CompareCriteria":
        if not isinstance(data, dict):
            return cls()
        mode = data.get("mode")
        try:
            tol = max(0, int(data.get("tolerance_s", 0)))
        except (TypeError, ValueError):
            tol = 0
        return cls(
            mode=mode if mode in _MODE_KEYS else "content",
            tolerance_s=tol,
            ignore_hour_offsets=bool(data.get("ignore_hour_offsets", False)),
        )

    def summary(self) -> str:
        label = dict(MODES)[self.mode].split(" (")[0]
        extras = []
        if self.mode in ("size_time", "time"):
            if self.tolerance_s:
                extras.append(f"±{self.tolerance_s}s")
            if self.ignore_hour_offsets:
                extras.append("ignore whole-hour offsets")
        return label + (f" ({', '.join(extras)})" if extras else "")


def recompute_summary(report) -> None:
    from .cli_bridge import DiffStatus, ScanSummary

    counts = {s: 0 for s in DiffStatus}
    for e in report.entries:
        counts[e.status] += 1
    report.summary = ScanSummary(
        total=len(report.entries),
        same=counts[DiffStatus.SAME],
        different=counts[DiffStatus.DIFFERENT],
        orphan_left=counts[DiffStatus.ORPHAN_LEFT],
        orphan_right=counts[DiffStatus.ORPHAN_RIGHT],
        unchecked=counts[DiffStatus.UNCHECKED],
    )


def apply_criteria(report, criteria: CompareCriteria):
    """Re-classify paired files in *report* according to *criteria*."""
    from .cli_bridge import DiffStatus

    if criteria.mode == "content":
        return report
    for e in report.entries:
        l, r = e.left, e.right
        if not l or not r or l.is_dir or r.is_dir:
            continue
        same_size = l.size == r.size
        same_time = criteria.times_equal(l.modified_unix, r.modified_unix)
        same = {
            "size": same_size,
            "time": same_time,
            "size_time": same_size and same_time,
        }[criteria.mode]
        new = DiffStatus.SAME if same else DiffStatus.DIFFERENT
        if e.status != new:
            e.status = new
    recompute_summary(report)
    return report
