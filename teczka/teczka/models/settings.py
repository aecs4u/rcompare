"""Settings and session profile models."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..utils.config import atomic_write_json, default_config_dir


# Whitespace modes accepted by ``rcompare_cli --ignore-whitespace``. "none"
# is the GUI's way of saying "omit the flag"; the CLI has no such value.
WHITESPACE_MODES: tuple[str, ...] = ("none", "all", "leading", "trailing", "changes")


@dataclass
class ComparisonSettings:
    """Settings for a comparison operation.

    Every field here reaches ``rcompare_cli``. Nothing is stored in this model
    that the engine cannot act on — a preference the backend ignores is worse
    than an absent one, because the user cannot tell it did nothing.
    """

    ignore_patterns: list[str] = field(default_factory=list)
    follow_symlinks: bool = False
    use_hash_verification: bool = True
    cache_dir: Optional[str] = None

    # -- Text comparison (--text-diff, --ignore-whitespace, --ignore-case) ---
    text_diff: bool = True
    ignore_whitespace: str = "none"
    ignore_case: bool = False
    regex_rules: list[str] = field(default_factory=list)

    # -- Format-specific comparison (--image-diff, --csv-diff, ...) ---------
    image_diff: bool = False
    csv_diff: bool = False
    json_diff: bool = False
    excel_diff: bool = False

    def __post_init__(self) -> None:
        if self.ignore_whitespace not in WHITESPACE_MODES:
            self.ignore_whitespace = "none"

    def copy(self) -> "ComparisonSettings":
        """Return an independent copy, list fields included.

        Sessions snapshot and restore their settings through this rather than
        listing fields at the call site, so adding a field here cannot silently
        stop being carried across a session switch.
        """
        return replace(
            self,
            ignore_patterns=list(self.ignore_patterns),
            regex_rules=list(self.regex_rules),
        )

    @property
    def whitespace_flag(self) -> Optional[str]:
        """Return the ``--ignore-whitespace`` value, or ``None`` to omit it."""
        return None if self.ignore_whitespace == "none" else self.ignore_whitespace

    def to_dict(self) -> dict:
        return {
            "ignore_patterns": list(self.ignore_patterns),
            "follow_symlinks": self.follow_symlinks,
            "use_hash_verification": self.use_hash_verification,
            "cache_dir": self.cache_dir,
            "text_diff": self.text_diff,
            "ignore_whitespace": self.ignore_whitespace,
            "ignore_case": self.ignore_case,
            "regex_rules": list(self.regex_rules),
            "image_diff": self.image_diff,
            "csv_diff": self.csv_diff,
            "json_diff": self.json_diff,
            "excel_diff": self.excel_diff,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "ComparisonSettings":
        """Rebuild from persisted JSON, ignoring anything malformed.

        Config files are edited by hand and survive downgrades, so every field
        is validated rather than trusted.
        """
        data = data or {}

        def _str_list(key: str) -> list[str]:
            raw = data.get(key, [])
            return [s for s in raw if isinstance(s, str)] if isinstance(raw, list) else []

        cache_dir = data.get("cache_dir")
        whitespace = data.get("ignore_whitespace", "none")
        return cls(
            ignore_patterns=_str_list("ignore_patterns"),
            follow_symlinks=bool(data.get("follow_symlinks", False)),
            use_hash_verification=bool(data.get("use_hash_verification", True)),
            cache_dir=cache_dir if isinstance(cache_dir, str) else None,
            text_diff=bool(data.get("text_diff", True)),
            ignore_whitespace=(
                whitespace if isinstance(whitespace, str) else "none"
            ),
            ignore_case=bool(data.get("ignore_case", False)),
            regex_rules=_str_list("regex_rules"),
            image_diff=bool(data.get("image_diff", False)),
            csv_diff=bool(data.get("csv_diff", False)),
            json_diff=bool(data.get("json_diff", False)),
            excel_diff=bool(data.get("excel_diff", False)),
        )


@dataclass
class SessionProfile:
    """A saved session configuration."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    left_path: str = ""
    right_path: str = ""
    base_path: str = ""
    ignore_patterns: list[str] = field(default_factory=list)
    follow_symlinks: bool = False
    hash_verification: bool = True
    last_used: str = field(default_factory=lambda: datetime.now().isoformat())


class ProfileManager:
    """Manages session profiles on disk."""

    def __init__(self, profiles_path: Optional[Path] = None):
        self._path = profiles_path or (default_config_dir() / "profiles.json")
        self._profiles: list[SessionProfile] = []
        self.last_save_error: str | None = None
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._profiles = [
                    SessionProfile(
                        id=p.get("id", str(uuid.uuid4())),
                        name=p["name"],
                        left_path=p.get("left_path", ""),
                        right_path=p.get("right_path", ""),
                        base_path=p.get("base_path", ""),
                        ignore_patterns=p.get("ignore_patterns", []),
                        follow_symlinks=p.get("follow_symlinks", False),
                        hash_verification=p.get("hash_verification", True),
                        last_used=p.get("last_used", ""),
                    )
                    for p in data
                ]
            except (json.JSONDecodeError, KeyError, TypeError, OSError):
                self._profiles = []

    def _save(self) -> bool:
        data = [
            {
                "id": p.id,
                "name": p.name,
                "left_path": p.left_path,
                "right_path": p.right_path,
                "base_path": p.base_path,
                "ignore_patterns": p.ignore_patterns,
                "follow_symlinks": p.follow_symlinks,
                "hash_verification": p.hash_verification,
                "last_used": p.last_used,
            }
            for p in self._profiles
        ]
        saved = atomic_write_json(self._path, data)
        self.last_save_error = None if saved else f"Could not write profiles to {self._path}"
        return saved

    @property
    def profiles(self) -> list[SessionProfile]:
        return list(self._profiles)

    def add(self, profile: SessionProfile) -> bool:
        self._profiles.append(profile)
        if self._save():
            return True
        self._profiles.pop()
        return False

    def update(self, profile: SessionProfile) -> bool:
        for i, p in enumerate(self._profiles):
            if p.id == profile.id:
                self._profiles[i] = profile
                if self._save():
                    return True
                self._profiles[i] = p
                return False
        return False

    def delete(self, profile_id: str) -> bool:
        original = self._profiles
        self._profiles = [p for p in original if p.id != profile_id]
        if self._save():
            return True
        self._profiles = original
        return False

    def get(self, profile_id: str) -> Optional[SessionProfile]:
        for p in self._profiles:
            if p.id == profile_id:
                return p
        return None
