"""Unimportant-text normalization shared by folder results and text previews."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

TEXT_EXTENSIONS = frozenset(
    {
        ".txt", ".md", ".markdown", ".rst", ".log", ".rs", ".toml", ".yaml",
        ".yml", ".json", ".xml", ".html", ".htm", ".css", ".js", ".ts",
        ".tsx", ".jsx", ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx",
        ".cs", ".java", ".py", ".rb", ".go", ".php", ".pl", ".sh", ".bash",
        ".zsh", ".fish", ".sql", ".conf", ".cfg", ".ini", ".properties",
        ".cmake", ".make", ".dockerfile", ".gitignore", ".gitattributes",
    }
)


class RuleValidationError(ValueError):
    """Raised when an unimportant-text rule has an invalid pattern."""


def validate_rules(raw_rules: Any) -> list[dict[str, str]]:
    """Return normalized rule dictionaries or raise for malformed patterns."""
    if raw_rules is None:
        return []
    if not isinstance(raw_rules, (list, tuple)):
        raise RuleValidationError("Rules must be a list.")

    normalized: list[dict[str, str]] = []
    for index, raw in enumerate(raw_rules, start=1):
        if not isinstance(raw, dict):
            raise RuleValidationError(f"Rule {index} must be a rule object.")
        pattern = raw.get("pattern", "")
        replacement = raw.get("replacement", "")
        description = raw.get("description", "")
        if not all(isinstance(value, str) for value in (pattern, replacement, description)):
            raise RuleValidationError(f"Rule {index} fields must be text.")
        if not pattern:
            raise RuleValidationError(f"Rule {index} needs a regular expression.")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise RuleValidationError(f"Rule {index} has an invalid pattern: {exc}") from exc
        try:
            compiled.sub(replacement, "")
        except re.error as exc:
            raise RuleValidationError(f"Rule {index} has an invalid replacement: {exc}") from exc
        normalized.append(
            {
                "pattern": pattern,
                "replacement": replacement,
                "description": description,
            }
        )
    return normalized


def normalize_lines(text: str, rules: list[dict[str, str]]) -> list[str]:
    """Apply rules to each line, preserving line count and order."""
    result = text.splitlines()
    for rule in rules:
        pattern = re.compile(rule["pattern"])
        result = [pattern.sub(rule["replacement"], line) for line in result]
    return result


def apply_to_report(report, left_root: str, right_root: str, raw_rules: Any) -> int:
    """Reclassify text entries whose contents match after rule normalization.

    Only paired text files reported as different or unchecked are read. Read
    errors leave their original status intact so a rule cannot turn an
    inaccessible file into an identical result.
    """
    from .cli_bridge import DiffStatus
    from .criteria import recompute_summary

    rules = validate_rules(raw_rules)
    if not rules:
        return 0

    left_base = Path(left_root).expanduser()
    right_base = Path(right_root).expanduser()
    updated = 0
    for entry in report.entries:
        if entry.status not in (DiffStatus.DIFFERENT, DiffStatus.UNCHECKED):
            continue
        if entry.left is None or entry.right is None or entry.left.is_dir or entry.right.is_dir:
            continue
        relative = PurePosixPath(entry.path)
        if (
            not relative.parts
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in entry.path
        ):
            continue
        if Path(entry.path).suffix.casefold() not in TEXT_EXTENSIONS:
            continue
        try:
            left_text = (left_base / Path(*relative.parts)).read_text(encoding="utf-8")
            right_text = (right_base / Path(*relative.parts)).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue

        status = (
            DiffStatus.SAME
            if normalize_lines(left_text, rules) == normalize_lines(right_text, rules)
            else DiffStatus.DIFFERENT
        )
        if entry.status != status:
            entry.status = status
            updated += 1

    if updated:
        recompute_summary(report)
    return updated
