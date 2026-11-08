"""Tests for exact, streaming file content comparisons."""

from __future__ import annotations

import os

from teczka.utils.file_compare import files_have_identical_contents


def test_same_size_and_timestamp_different_bytes_are_not_identical(tmp_path):
    left = tmp_path / "left.bin"
    right = tmp_path / "right.bin"
    left.write_bytes(b"abcdef")
    right.write_bytes(b"abcxef")
    timestamp = 1_700_000_000
    os.utime(left, (timestamp, timestamp))
    os.utime(right, (timestamp, timestamp))

    assert left.stat().st_size == right.stat().st_size
    assert left.stat().st_mtime_ns == right.stat().st_mtime_ns
    assert not files_have_identical_contents(left, right, chunk_size=2)


def test_identical_contents_are_compared_across_chunks(tmp_path):
    left = tmp_path / "left.bin"
    right = tmp_path / "right.bin"
    contents = bytes(range(256)) * 7
    left.write_bytes(contents)
    right.write_bytes(contents)

    assert files_have_identical_contents(left, right, chunk_size=31)


def test_different_sizes_are_rejected_without_content_match(tmp_path):
    left = tmp_path / "left.bin"
    right = tmp_path / "right.bin"
    left.write_bytes(b"same")
    right.write_bytes(b"same plus")

    assert not files_have_identical_contents(left, right)
