"""Helpers for launching user-selected external applications safely."""

from __future__ import annotations

import shlex
from pathlib import Path

FILE_PLACEHOLDER = "{file}"


def handler_key(path: Path) -> str:
    """Return the case-insensitive extension key used for saved handlers."""
    return path.suffix.casefold() or "<no-extension>"


def application_argv(command: str, path: Path) -> list[str]:
    """Parse an application template without invoking a shell.

    If ``{file}`` appears in any argument, replace it there. Otherwise append
    the selected path as the final argument.
    """
    try:
        arguments = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"Invalid application command: {exc}") from exc
    if not arguments or not arguments[0].strip():
        raise ValueError("Enter an application command.")

    file_path = str(path)
    has_placeholder = any(FILE_PLACEHOLDER in arg for arg in arguments)
    arguments = [arg.replace(FILE_PLACEHOLDER, file_path) for arg in arguments]
    if not has_placeholder:
        arguments.append(file_path)
    return arguments
