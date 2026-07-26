"""Bridge to rcompare_cli subprocess for all comparison operations."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from .telemetry import log_exception


# Major version of the rcompare_cli JSON schema this GUI understands.
#
# rcompare_cli emits {"schema_version": "1.1.0", ...}. Without a check at this
# boundary, a schema bump surfaces as a KeyError raised inside a worker thread
# with no indication that a version mismatch is the cause.
SUPPORTED_SCHEMA_MAJOR = 1
# Emitted by CLI builds predating the schema_version field.
_ASSUMED_LEGACY_SCHEMA = "1.0.0"


class SchemaVersionError(RuntimeError):
    """Raised when the CLI emits a JSON schema this GUI cannot parse."""

    def __init__(self, received: str, expected_major: int) -> None:
        self.received = received
        self.expected_major = expected_major
        super().__init__(
            f"rcompare_cli reported JSON schema version {received!r}, but this "
            f"version of teczka only understands schema {expected_major}.x. "
            "Update teczka, or point Settings > CLI at a matching rcompare_cli "
            "binary."
        )


def parse_schema_version(raw: object) -> tuple[int, str]:
    """Return ``(major, normalized)`` for a reported schema version.

    Missing or unparseable values are treated as the legacy 1.0.0 schema
    rather than rejected, so a mismatch is reported only when the CLI actually
    declares an incompatible version.
    """
    if not isinstance(raw, str) or not raw.strip():
        return 1, _ASSUMED_LEGACY_SCHEMA
    text = raw.strip()
    head = text.split(".", 1)[0]
    try:
        return int(head), text
    except ValueError:
        return 1, text


def check_schema_version(data: dict) -> str:
    """Validate ``data['schema_version']``, raising :class:`SchemaVersionError`.

    Returns the normalized version string on success.
    """
    major, normalized = parse_schema_version(data.get("schema_version"))
    if major != SUPPORTED_SCHEMA_MAJOR:
        raise SchemaVersionError(normalized, SUPPORTED_SCHEMA_MAJOR)
    return normalized


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
    schema_version: str = _ASSUMED_LEGACY_SCHEMA
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
        self._caps_cache: Optional[dict[str, frozenset]] = None

    def build_command(self, args: list[str]) -> list[str]:
        """Build a command list for QProcess usage."""
        return [self._cli_path] + args

    @staticmethod
    def parse_entry_obj(obj: dict) -> DiffEntry:
        """Build a :class:`DiffEntry` from one decoded ``--jsonl`` entry line."""
        def side(key: str) -> Optional[FileSide]:
            raw = obj.get(key)
            if not raw:
                return None
            return FileSide(
                size=raw["size"],
                modified_unix=raw.get("modified_unix"),
                is_dir=raw["is_dir"],
            )

        return DiffEntry(
            path=obj["path"],
            status=DiffStatus(obj["status"]),
            left=side("left"),
            right=side("right"),
        )

    @staticmethod
    def parse_summary_obj(obj: dict) -> ScanSummary:
        """Build a :class:`ScanSummary` from the ``--jsonl`` summary line.

        The summary is emitted *first* in JSONL mode, so counts can be shown
        before a single entry has been rendered.
        """
        check_schema_version(obj)
        raw = obj.get("summary", obj)
        try:
            return ScanSummary(
                total=raw["total"],
                same=raw["same"],
                different=raw["different"],
                orphan_left=raw["orphan_left"],
                orphan_right=raw["orphan_right"],
                unchecked=raw["unchecked"],
            )
        except (KeyError, TypeError) as exc:
            raise SchemaVersionError(
                f"jsonl summary (missing field {exc})", SUPPORTED_SCHEMA_MAJOR
            ) from exc

    def supports_flag(self, command: str, flag: str) -> bool:
        """Return whether the configured CLI advertises *flag* for *command*.

        Feature-detected via ``rcompare_cli capabilities --json`` and cached for
        the life of the bridge. The GUI and the binary are versioned and shipped
        independently (a stale ``~/.cargo/bin/rcompare_cli`` easily shadows a
        newer build on PATH), so newer flags must be probed, not assumed.
        Anything unexpected — old binary, no ``capabilities`` command, malformed
        output — resolves to False so the caller falls back to older behaviour.
        """
        caps = self._capabilities()
        return flag in caps.get(command, frozenset())

    def _capabilities(self) -> dict[str, frozenset]:
        if self._caps_cache is not None:
            return self._caps_cache
        caps: dict[str, frozenset] = {}
        try:
            proc = subprocess.run(
                [self._cli_path, "capabilities", "--json"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                for cmd in data.get("commands", []):
                    name = cmd.get("name")
                    if not name:
                        continue
                    flags: set[str] = set()
                    for raw in cmd.get("flags", []):
                        # Entries may combine a pair, e.g.
                        # "--verify-hashes/--no-verify-hashes".
                        flags.update(part for part in str(raw).split("/") if part)
                    caps[name] = frozenset(flags)
        except (OSError, ValueError, subprocess.SubprocessError):
            log_exception("could not read rcompare_cli capabilities")
        self._caps_cache = caps
        return caps

    def parse_scan_report(self, json_str: str) -> ScanReport:
        """Parse JSON string into ScanReport."""
        try:
            data = json.loads(json_str)
        except Exception:
            log_exception("failed to decode scan JSON")
            raise
        if not isinstance(data, dict):
            raise ValueError("rcompare_cli did not emit a JSON object")

        # Check the contract before touching any field, so an incompatible
        # schema is reported as such rather than as a KeyError deep in parsing.
        schema_version = check_schema_version(data)

        try:
            raw_summary = data["summary"]
            summary = ScanSummary(
                total=raw_summary["total"],
                same=raw_summary["same"],
                different=raw_summary["different"],
                orphan_left=raw_summary["orphan_left"],
                orphan_right=raw_summary["orphan_right"],
                unchecked=raw_summary["unchecked"],
            )
        except (KeyError, TypeError) as exc:
            raise SchemaVersionError(
                f"{schema_version} (missing field {exc})", SUPPORTED_SCHEMA_MAJOR
            ) from exc

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
            schema_version=schema_version,
            text_diffs=text_diffs,
            image_diffs=image_diffs,
            csv_diffs=data.get("csv_diffs") or [],
            excel_diffs=data.get("excel_diffs") or [],
            json_diffs=data.get("json_diffs") or [],
            yaml_diffs=data.get("yaml_diffs") or [],
            parquet_diffs=data.get("parquet_diffs") or [],
        )

    def build_sync_args(
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
    ) -> list[str]:
        """Build the argument list for a `sync` invocation (no execution)."""
        args = [
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
            args.append("--dry-run")
        if follow_symlinks:
            args.append("--follow-symlinks")
        if verify_hashes:
            args.append("--verify-hashes")
        for pattern in ignore_patterns or []:
            args.extend(["--ignore", pattern])
        return args

    def build_copy_args(
        self,
        left: str,
        right: str,
        direction: str,
        paths: list[str],
        dry_run: bool = False,
    ) -> list[str]:
        """Build the argument list for a `copy` invocation (no execution)."""
        args = [
            "copy",
            left,
            right,
            "--direction",
            direction,
            "--json",
        ]
        for rel_path in paths:
            args.extend(["--path", rel_path])
        if dry_run:
            args.append("--dry-run")
        return args

