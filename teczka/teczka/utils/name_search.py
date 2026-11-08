"""Shared case-insensitive file-name search for the tree and navigation."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass

SEARCH_MODES = {"contains", "wildcard", "regex"}


@dataclass(frozen=True)
class NameSearch:
    """A precompiled name matcher that can be reused across many rows."""

    text: str
    mode: str
    expression: re.Pattern[str] | None = None
    folded_text: str = ""
    error: str = ""

    def matches(self, value: str) -> bool:
        if not self.text:
            return True
        if self.error:
            return False
        if self.mode == "contains":
            return self.folded_text in value.casefold()
        if self.expression is None:
            return False
        if self.mode == "wildcard":
            return self.expression.fullmatch(value.casefold()) is not None
        return self.expression.search(value) is not None


def normalize_search_mode(mode: str | None) -> str:
    value = (mode or "contains").strip().lower()
    return value if value in SEARCH_MODES else "contains"


def compile_name_search(text: str, mode: str = "contains") -> NameSearch:
    """Compile a search once so filtering and navigation share identical rules."""
    query = (text or "").strip()
    normalized_mode = normalize_search_mode(mode)
    if not query:
        return NameSearch(text="", mode=normalized_mode)
    if normalized_mode == "contains":
        return NameSearch(
            text=query,
            mode=normalized_mode,
            folded_text=query.casefold(),
        )
    if normalized_mode == "wildcard":
        return NameSearch(
            text=query,
            mode=normalized_mode,
            expression=re.compile(fnmatch.translate(query.casefold())),
        )
    try:
        expression = re.compile(query, re.IGNORECASE)
    except re.error as exc:
        return NameSearch(text=query, mode=normalized_mode, error=str(exc))
    return NameSearch(text=query, mode=normalized_mode, expression=expression)
