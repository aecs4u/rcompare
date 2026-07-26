"""Filesystem path validation for operations rooted in a comparison side."""

from __future__ import annotations

from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when an operation path could escape its selected root."""


def resolve_safe_relative(root: Path, relative: str | Path) -> Path:
    """Resolve *relative* below *root*, rejecting absolute paths and traversal.

    Comparison entries normally come from ``rcompare_cli``, but the CLI binary
    is user-configurable and local fallbacks must not treat its output as a
    trusted filesystem path.
    """

    rel = Path(relative)
    if not str(rel) or rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise UnsafePathError(f"Unsafe relative path: {relative!s}")

    resolved_root = root.resolve(strict=False)
    candidate = (resolved_root / rel).resolve(strict=False)
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise UnsafePathError(f"Path escapes comparison root: {relative!s}") from exc
    return candidate


def validate_child_name(name: str) -> str:
    """Return a safe single path component or raise ``UnsafePathError``."""

    value = name.strip()
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise UnsafePathError(f"Invalid file or folder name: {name!r}")
    return value
