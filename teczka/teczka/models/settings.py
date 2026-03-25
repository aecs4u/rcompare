"""Settings and session profile models."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class ComparisonSettings:
    """Settings for a comparison operation."""
    ignore_patterns: list[str] = field(default_factory=list)
    follow_symlinks: bool = False
    use_hash_verification: bool = True
    cache_dir: Optional[str] = None


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
        self._path = profiles_path or (
            Path.home() / ".config" / "rcompare" / "profiles.json"
        )
        self._profiles: list[SessionProfile] = []
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
            except (json.JSONDecodeError, KeyError):
                self._profiles = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
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
        self._path.write_text(json.dumps(data, indent=2))

    @property
    def profiles(self) -> list[SessionProfile]:
        return list(self._profiles)

    def add(self, profile: SessionProfile) -> None:
        self._profiles.append(profile)
        self._save()

    def update(self, profile: SessionProfile) -> None:
        for i, p in enumerate(self._profiles):
            if p.id == profile.id:
                self._profiles[i] = profile
                self._save()
                return

    def delete(self, profile_id: str) -> None:
        self._profiles = [p for p in self._profiles if p.id != profile_id]
        self._save()

    def get(self, profile_id: str) -> Optional[SessionProfile]:
        for p in self._profiles:
            if p.id == profile_id:
                return p
        return None
