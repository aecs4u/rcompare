"""Beyond Compare-style file filters.

Syntax (entries separated by ``;`` or newlines)::

    *.py;*.rs          include only files matching these globs
    -*.tmp             exclude files matching the glob
    -build/            exclude every folder named ``build`` (and its contents)
    src/                include only things under folders named ``src``
    -docs/*.md         patterns containing ``/`` match the relative path

An empty filter matches everything.  Include rules apply to files only;
folders stay visible when they contain at least one matching file.
"""

from __future__ import annotations

import dataclasses
from fnmatch import fnmatchcase
from typing import Iterable

PRESETS: list[tuple[str, str]] = [
    ("(no filter)", ""),
    ("Source code", "*.py;*.rs;*.c;*.h;*.cpp;*.hpp;*.js;*.ts;*.go;*.java;*.toml;*.md"),
    ("Hide VCS and build output", "-.git/;-.svn/;-.hg/;-node_modules/;-target/;-build/;-__pycache__/"),
    ("Hide temporary files", "-*.tmp;-*.bak;-*.swp;-*~;-.DS_Store"),
    ("Images only", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp;*.svg"),
]


@dataclasses.dataclass(frozen=True)
class _Rule:
    pattern: str
    is_dir: bool  # trailing "/" in the source text

    def matches(self, rel_path: str, entry_is_dir: bool) -> bool:
        parts = rel_path.strip("/").split("/")
        dirs = parts if entry_is_dir else parts[:-1]
        if self.is_dir:
            if "/" in self.pattern:
                prefix = ""
                for d in dirs:
                    prefix = f"{prefix}/{d}" if prefix else d
                    if fnmatchcase(prefix, self.pattern):
                        return True
                return False
            return any(fnmatchcase(d, self.pattern) for d in dirs)
        if "/" in self.pattern:
            candidate = "/".join(parts)
            if fnmatchcase(candidate, self.pattern):
                return True
            prefix = ""
            for d in dirs:  # a matching ancestor folder also matches
                prefix = f"{prefix}/{d}" if prefix else d
                if fnmatchcase(prefix, self.pattern):
                    return True
            return False
        return fnmatchcase(parts[-1], self.pattern)


@dataclasses.dataclass(frozen=True)
class FileFilter:
    includes: tuple[_Rule, ...] = ()
    excludes: tuple[_Rule, ...] = ()

    @property
    def active(self) -> bool:
        return bool(self.includes or self.excludes)

    def excluded(self, rel_path: str, is_dir: bool) -> bool:
        return any(r.matches(rel_path, is_dir) for r in self.excludes)

    def included(self, rel_path: str, is_dir: bool) -> bool:
        return not self.includes or any(r.matches(rel_path, is_dir) for r in self.includes)

    def ignore_args(self) -> list[str]:
        """Exclude rules as gitignore-style patterns for the CLI's ``--ignore``."""
        return [r.pattern + ("/" if r.is_dir else "") for r in self.excludes]


def parse_filter(text: str) -> FileFilter:
    inc: list[_Rule] = []
    exc: list[_Rule] = []
    for raw in text.replace("\n", ";").split(";"):
        tok = raw.strip()
        if not tok:
            continue
        exclude = tok.startswith("-")
        if tok[0] in "+-":
            tok = tok[1:].strip()
        if not tok:
            continue
        is_dir = tok.endswith("/")
        rule = _Rule(tok.rstrip("/"), is_dir)
        if not rule.pattern:
            continue
        (exc if exclude else inc).append(rule)
    return FileFilter(tuple(inc), tuple(exc))


def filter_entries(entries: Iterable, flt: FileFilter) -> list:
    """Return the entries that survive *flt* (works on cli_bridge.DiffEntry)."""
    if not flt.active:
        return list(entries)

    def is_dir(e) -> bool:
        return bool((e.left and e.left.is_dir) or (e.right and e.right.is_dir))

    kept: list = []
    needed_dirs: set[str] = set()
    dir_entries: list = []
    for e in entries:
        d = is_dir(e)
        if flt.excluded(e.path, d):
            continue
        if d:
            dir_entries.append(e)
            continue
        if not flt.included(e.path, False):
            continue
        kept.append(e)
        parts = e.path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            needed_dirs.add("/".join(parts[:i]))
    for e in dir_entries:
        # With include rules, folders only stay if they hold a surviving file.
        if not flt.includes or e.path in needed_dirs:
            kept.append(e)
    order = {id(e): i for i, e in enumerate(entries if isinstance(entries, list) else [])}
    if order:
        kept.sort(key=lambda e: order[id(e)])
    return kept


def apply_to_report(report, text: str):
    """Filter ``report.entries`` in place and recompute its summary."""
    from .criteria import recompute_summary

    flt = parse_filter(text)
    if not flt.active:
        return report
    report.entries = filter_entries(list(report.entries), flt)
    recompute_summary(report)
    return report
