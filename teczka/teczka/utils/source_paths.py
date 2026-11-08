"""Helpers for distinguishing local paths from remote source URLs."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REMOTE_FILE_SCHEMES = frozenset({"s3", "sftp", "dav", "davs"})


def is_remote_source(source: str) -> bool:
    """Return whether *source* uses an explicit URL scheme delimiter."""
    return "://" in (source or "")


def source_scheme(source: str) -> str | None:
    """Return a remote source's lowercase URL scheme, or ``None`` for local paths."""
    if not is_remote_source(source):
        return None
    try:
        scheme = urlsplit(source).scheme.lower()
    except ValueError:
        return ""
    return scheme


def validate_remote_source(source: str) -> str | None:
    """Return a safe, non-sensitive validation error for a remote source URL."""
    if not is_remote_source(source):
        return None
    try:
        parsed = urlsplit(source)
        host = parsed.hostname
    except ValueError:
        return "The remote source URL is malformed."
    if not parsed.scheme or not parsed.netloc or not host:
        return "The remote source URL must include a scheme and host."
    if parsed.username is not None or parsed.password is not None:
        return (
            "Remove embedded credentials from the remote source URL. Configure "
            "authentication through the CLI environment instead."
        )
    if parsed.query or parsed.fragment:
        return (
            "Remove the query string or fragment from the remote source URL. "
            "Configure authentication through the CLI environment instead."
        )
    return None


def split_source_file(source: str) -> tuple[str, str]:
    """Split a local file path or remote file URL into source root and name.

    The returned relative name is safe to pass to ``rcompare_cli read``.
    Remote URL paths are treated as file paths, so the last URL component is
    read relative to its parent endpoint.
    """
    value = (source or "").strip()
    if not value:
        raise ValueError("Enter a file path or remote file URL.")

    if not is_remote_source(value):
        path = Path(value).expanduser()
        if not path.is_file():
            raise ValueError("The local path must name an existing file.")
        return str(path.parent), path.name

    validation_error = validate_remote_source(value)
    if validation_error:
        raise ValueError(validation_error)

    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in REMOTE_FILE_SCHEMES:
        raise ValueError(
            "Supported remote file schemes are s3, sftp, dav, and davs."
        )

    if not parsed.path or parsed.path.endswith("/"):
        raise ValueError("The remote URL must end with a file name.")
    encoded_path = parsed.path
    parent_path, _, file_name = encoded_path.rpartition("/")
    if not file_name or file_name in {".", ".."}:
        raise ValueError("The remote URL must end with a file name.")
    root = urlunsplit((parsed.scheme, parsed.netloc, parent_path, "", ""))
    return root, file_name


def source_log_label(source: str) -> str:
    """Return a log-safe source label that omits remote paths and credentials."""
    if not is_remote_source(source):
        return source
    try:
        parsed = urlsplit(source)
        scheme = parsed.scheme.lower() or "remote"
        host = parsed.hostname or "unknown-host"
        try:
            port = parsed.port
        except ValueError:
            port = None
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if port is not None:
            host = f"{host}:{port}"
        return f"{scheme}://{host}/…"
    except ValueError:
        return "remote://<invalid-source>"


def local_source_paths(sources: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Return only local filesystem roots, suitable for OS watchers."""
    return tuple(
        source for source in sources if source and not is_remote_source(source)
    )
