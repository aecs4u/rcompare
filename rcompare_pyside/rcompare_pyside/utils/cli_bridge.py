"""Bridge to rcompare_cli subprocess for all comparison operations."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from .telemetry import log_error, log_exception, log_info


class DiffStatus(str, Enum):
    """Mirror of rcompare_common::DiffStatus."""
    SAME = "Same"
    DIFFERENT = "Different"
    ORPHAN_LEFT = "OrphanLeft"
    ORPHAN_RIGHT = "OrphanRight"
    UNCHECKED = "Unchecked"


@dataclass
class FileSide:
    """One side of a file comparison entry."""
    size: int
    modified_unix: Optional[int]
    is_dir: bool


@dataclass
class DiffEntry:
    """A single comparison entry from CLI JSON output."""
    path: str
    status: DiffStatus
    left: Optional[FileSide]
    right: Optional[FileSide]


@dataclass
class ScanSummary:
    """Summary statistics from a scan."""
    total: int
    same: int
    different: int
    orphan_left: int
    orphan_right: int
    unchecked: int


@dataclass
class TextDiffLine:
    """A line from text diff output."""
    line_number_left: Optional[int]
    line_number_right: Optional[int]
    content: str
    change_type: str  # "Equal", "Insert", "Delete"
    highlighted_segments: list[dict] = field(default_factory=list)


@dataclass
class TextDiffReport:
    """Text diff result for a single file."""
    path: str
    total_lines: int
    equal_lines: int
    inserted_lines: int
    deleted_lines: int
    lines: list[TextDiffLine] = field(default_factory=list)


@dataclass
class ImageDiffReport:
    """Image diff result for a single file pair."""
    path: str
    result: dict  # Raw JSON dict of ImageDiffResult


@dataclass
class ScanReport:
    """Complete scan result from CLI JSON output."""
    left: str
    right: str
    summary: ScanSummary
    entries: list[DiffEntry]
    text_diffs: list[TextDiffReport] = field(default_factory=list)
    image_diffs: list[ImageDiffReport] = field(default_factory=list)
    csv_diffs: list[dict] = field(default_factory=list)
    excel_diffs: list[dict] = field(default_factory=list)
    json_diffs: list[dict] = field(default_factory=list)
    yaml_diffs: list[dict] = field(default_factory=list)
    parquet_diffs: list[dict] = field(default_factory=list)


class CliBridge:
    """Manages subprocess calls to rcompare_cli."""

    def __init__(self, cli_path: str):
        self._cli_path = cli_path

    def build_command(self, args: list[str]) -> list[str]:
        """Build a command list for QProcess usage."""
        return [self._cli_path] + args

    def scan_folders(
        self,
        left: str,
        right: str,
        ignore_patterns: list[str] | None = None,
        follow_symlinks: bool = False,
        verify_hashes: bool = False,
        text_diff: bool = False,
        image_diff: bool = False,
        image_exif: bool = False,
        image_tolerance: int = 1,
        csv_diff: bool = False,
        excel_diff: bool = False,
        json_diff: bool = False,
        yaml_diff: bool = False,
        parquet_diff: bool = False,
        ignore_whitespace: Optional[str] = None,
        ignore_case: bool = False,
    ) -> ScanReport:
        """Run folder comparison and return parsed JSON result."""
        cmd = [self._cli_path, "scan", left, right, "--json"]
        if follow_symlinks:
            cmd.append("--follow-symlinks")
        if verify_hashes:
            cmd.append("--verify-hashes")
        for pattern in ignore_patterns or []:
            cmd.extend(["--ignore", pattern])
        if text_diff:
            cmd.append("--text-diff")
        if image_diff:
            cmd.append("--image-diff")
        if image_exif:
            cmd.append("--image-exif")
        if image_tolerance != 1:
            cmd.extend(["--image-tolerance", str(image_tolerance)])
        if csv_diff:
            cmd.append("--csv-diff")
        if excel_diff:
            cmd.append("--excel-diff")
        if json_diff:
            cmd.append("--json-diff")
        if yaml_diff:
            cmd.append("--yaml-diff")
        if parquet_diff:
            cmd.append("--parquet-diff")
        if ignore_whitespace:
            cmd.extend(["--ignore-whitespace", ignore_whitespace])
        if ignore_case:
            cmd.append("--ignore-case")

        log_info("running scan command", command=cmd[0], args=cmd[1:])
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
        )
        # rcompare_cli uses exit code 2 when differences are found.
        if result.returncode not in (0, 2):
            details = result.stderr.strip() or "no stderr output"
            log_error("scan command failed", exit_code=result.returncode, details=details)
            raise RuntimeError(
                f"rcompare_cli failed (exit {result.returncode}): {details}"
            )

        log_info("scan command completed", exit_code=result.returncode)
        return self.parse_scan_report(result.stdout)

    def parse_scan_report(self, json_str: str) -> ScanReport:
        """Parse JSON string into ScanReport."""
        try:
            data = json.loads(json_str)
        except Exception:
            log_exception("failed to decode scan JSON")
            raise
        summary = ScanSummary(
            total=data["summary"]["total"],
            same=data["summary"]["same"],
            different=data["summary"]["different"],
            orphan_left=data["summary"]["orphan_left"],
            orphan_right=data["summary"]["orphan_right"],
            unchecked=data["summary"]["unchecked"],
        )

        entries = []
        for e in data["entries"]:
            left = None
            if e.get("left"):
                left = FileSide(
                    size=e["left"]["size"],
                    modified_unix=e["left"].get("modified_unix"),
                    is_dir=e["left"]["is_dir"],
                )
            right = None
            if e.get("right"):
                right = FileSide(
                    size=e["right"]["size"],
                    modified_unix=e["right"].get("modified_unix"),
                    is_dir=e["right"]["is_dir"],
                )
            entries.append(DiffEntry(
                path=e["path"],
                status=DiffStatus(e["status"]),
                left=left,
                right=right,
            ))

        text_diffs = []
        for td in data.get("text_diffs") or []:
            lines = []
            for line in td.get("lines", []):
                lines.append(TextDiffLine(
                    line_number_left=line.get("line_number_left"),
                    line_number_right=line.get("line_number_right"),
                    content=line.get("content", ""),
                    change_type=line.get("change_type", "Equal"),
                    highlighted_segments=line.get("highlighted_segments", []),
                ))
            text_diffs.append(TextDiffReport(
                path=td["path"],
                total_lines=td.get("total_lines", 0),
                equal_lines=td.get("equal_lines", 0),
                inserted_lines=td.get("inserted_lines", 0),
                deleted_lines=td.get("deleted_lines", 0),
                lines=lines,
            ))

        image_diffs = []
        for img in data.get("image_diffs") or []:
            image_diffs.append(ImageDiffReport(
                path=img["path"],
                result=img.get("result", {}),
            ))

        return ScanReport(
            left=data["left"],
            right=data["right"],
            summary=summary,
            entries=entries,
            text_diffs=text_diffs,
            image_diffs=image_diffs,
            csv_diffs=data.get("csv_diffs") or [],
            excel_diffs=data.get("excel_diffs") or [],
            json_diffs=data.get("json_diffs") or [],
            yaml_diffs=data.get("yaml_diffs") or [],
            parquet_diffs=data.get("parquet_diffs") or [],
        )

    def sync_folders(
        self,
        left: str,
        right: str,
        direction: str,
        dry_run: bool,
        use_trash: bool,
        ignore_patterns: list[str] | None = None,
        follow_symlinks: bool = False,
        verify_hashes: bool = False,
        conflict: str = "newest",
    ) -> dict[str, Any]:
        """Run rcompare_cli sync and return parsed JSON report."""
        cmd = [
            self._cli_path,
            "sync",
            left,
            right,
            "--direction",
            direction,
            "--delete-mode",
            "trash" if use_trash else "permanent",
            "--conflict",
            conflict,
            "--json",
        ]
        if dry_run:
            cmd.append("--dry-run")
        if follow_symlinks:
            cmd.append("--follow-symlinks")
        if verify_hashes:
            cmd.append("--verify-hashes")
        for pattern in ignore_patterns or []:
            cmd.extend(["--ignore", pattern])

        log_info("running sync command", command=cmd[0], args=cmd[1:])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            details = result.stderr.strip() or "no stderr output"
            log_error("sync command failed", exit_code=result.returncode, details=details)
            raise RuntimeError(
                f"rcompare_cli sync failed (exit {result.returncode}): {details}"
            )
        log_info("sync command completed")
        return json.loads(result.stdout)

    def copy_paths(
        self,
        left: str,
        right: str,
        direction: str,
        paths: list[str],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run selected-path copy operation and return JSON report."""
        cmd = [
            self._cli_path,
            "copy",
            left,
            right,
            "--direction",
            direction,
            "--json",
        ]
        for rel_path in paths:
            cmd.extend(["--path", rel_path])
        if dry_run:
            cmd.append("--dry-run")

        log_info("running copy command", count=len(paths), direction=direction)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            details = result.stderr.strip() or "no stderr output"
            log_error("copy command failed", exit_code=result.returncode, details=details)
            raise RuntimeError(
                f"rcompare_cli copy failed (exit {result.returncode}): {details}"
            )
        log_info("copy command completed")
        return json.loads(result.stdout)

    def diff_file(
        self,
        left: str,
        right: str,
        rel_path: str,
        mode: str = "auto",
        ignore_whitespace: Optional[str] = None,
        ignore_case: bool = False,
        image_exif: bool = False,
        image_tolerance: int = 1,
        max_binary_ranges: int = 2000,
    ) -> dict[str, Any]:
        """Run diff-file on one relative path and return JSON report."""
        cmd = [
            self._cli_path,
            "diff-file",
            left,
            right,
            "--path",
            rel_path,
            "--mode",
            mode,
            "--json",
            "--max-binary-ranges",
            str(max_binary_ranges),
        ]
        if ignore_whitespace:
            cmd.extend(["--ignore-whitespace", ignore_whitespace])
        if ignore_case:
            cmd.append("--ignore-case")
        if image_exif:
            cmd.append("--image-exif")
        if image_tolerance != 1:
            cmd.extend(["--image-tolerance", str(image_tolerance)])

        log_info("running diff-file command", path=rel_path, mode=mode)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            details = result.stderr.strip() or "no stderr output"
            log_error("diff-file command failed", exit_code=result.returncode, details=details)
            raise RuntimeError(
                f"rcompare_cli diff-file failed (exit {result.returncode}): {details}"
            )
        log_info("diff-file command completed", path=rel_path, mode=mode)
        return json.loads(result.stdout)

    def read_file(
        self,
        left: str,
        right: str,
        side: str,
        rel_path: str,
        out_path: Optional[str] = None,
    ) -> bytes:
        """Read file bytes from one side/path via CLI read command."""
        cmd = [
            self._cli_path,
            "read",
            left,
            right,
            "--side",
            side,
            "--path",
            rel_path,
        ]

        if out_path:
            cmd.extend(["--out", out_path])
            log_info("running read command to output path", side=side, path=rel_path, out=out_path)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            if result.returncode != 0:
                details = result.stderr.strip() or "no stderr output"
                log_error("read command failed", exit_code=result.returncode, details=details)
                raise RuntimeError(
                    f"rcompare_cli read failed (exit {result.returncode}): {details}"
                )
            log_info("read command completed to output path", out=out_path)
            return Path(out_path).read_bytes()

        log_info("running read command to stdout", side=side, path=rel_path)
        result = subprocess.run(cmd, capture_output=True, timeout=900)
        if result.returncode != 0:
            details = (
                result.stderr.decode("utf-8", errors="replace").strip()
                if result.stderr
                else "no stderr output"
            )
            log_error("read command failed", exit_code=result.returncode, details=details)
            raise RuntimeError(
                f"rcompare_cli read failed (exit {result.returncode}): {details}"
            )
        log_info("read command completed to stdout", bytes=len(result.stdout))
        return bytes(result.stdout)
