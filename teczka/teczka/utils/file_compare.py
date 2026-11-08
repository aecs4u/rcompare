"""Helpers for comparing file contents without loading whole files at once."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def files_have_identical_contents(
    left_path: str | Path,
    right_path: str | Path,
    *,
    chunk_size: int = 1024 * 1024,
    cancelled: Callable[[], bool] | None = None,
) -> bool:
    """Return whether two files contain the same bytes.

    The comparison reads both files instead of trusting their sizes,
    timestamps, or a cached shallow-comparison result.
    """
    left = Path(left_path)
    right = Path(right_path)
    if left.stat().st_size != right.stat().st_size:
        return False

    with left.open("rb") as left_file, right.open("rb") as right_file:
        while True:
            if cancelled is not None and cancelled():
                raise InterruptedError("file comparison cancelled")
            left_chunk = left_file.read(chunk_size)
            right_chunk = right_file.read(chunk_size)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True
