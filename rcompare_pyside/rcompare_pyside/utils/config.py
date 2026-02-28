"""Application configuration management."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _default_config_path() -> Path:
    """Return the default config file path."""
    config_dir = Path.home() / ".config" / "rcompare"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "pyside.json"


def _find_cli() -> Optional[str]:
    """Locate the rcompare_cli binary."""
    found = shutil.which("rcompare_cli")
    if found:
        return found

    exe_name = "rcompare_cli.exe" if os.name == "nt" else "rcompare_cli"
    # Try relative to project root (assume project root is 4 levels up from this file)
    project_root = Path(__file__).parent.parent.parent.parent

    target_dirs: list[Path] = []
    env_target = os.environ.get("CARGO_TARGET_DIR")
    if env_target:
        env_path = Path(env_target).expanduser()
        if env_path.is_absolute():
            target_dirs.append(env_path)
        else:
            target_dirs.append((project_root / env_path).resolve())

    target_dirs.extend(
        [
            project_root / "target",
            project_root / "rcompare_cli" / "target",
        ]
    )

    seen: set[Path] = set()
    for target_dir in target_dirs:
        if target_dir in seen:
            continue
        seen.add(target_dir)
        for subdir in ("release", "debug"):
            candidate = target_dir / subdir / exe_name
            if candidate.exists():
                return str(candidate)
    return None


@dataclass
class AppConfig:
    """Application configuration."""

    cli_path: Optional[str] = None
    theme: str = "light"
    recent_sessions: list[dict] = field(default_factory=list)
    window_geometry: dict = field(default_factory=dict)
    comparison_settings: dict = field(default_factory=dict)
    filter_options: dict = field(default_factory=dict)
    last_paths: dict = field(default_factory=dict)
    folder_columns: dict = field(default_factory=dict)
    active_view: int = 0
    three_way_mode: bool = False
    _config_file: Optional[str] = field(default=None, repr=False)

    @classmethod
    def load(cls) -> AppConfig:
        """Load config from disk, or create default."""
        path = _default_config_path()
        if path.exists():
            try:
                data = json.loads(path.read_text())
                config = cls(
                    cli_path=data.get("cli_path"),
                    theme=data.get("theme", "light"),
                    recent_sessions=data.get("recent_sessions", []),
                    window_geometry=data.get("window_geometry", {}),
                    comparison_settings=data.get("comparison_settings", {}),
                    filter_options=data.get("filter_options", {}),
                    last_paths=data.get("last_paths", {}),
                    folder_columns=data.get("folder_columns", {}),
                    active_view=int(data.get("active_view", 0)),
                    three_way_mode=bool(data.get("three_way_mode", False)),
                )
                config._config_file = str(path)
                return config
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
        config = cls()
        config._config_file = str(path)
        # Auto-detect CLI path
        if config.cli_path is None:
            config.cli_path = _find_cli()
        return config

    def save(self) -> None:
        """Persist config to disk."""
        path = Path(self._config_file or str(_default_config_path()))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cli_path": self.cli_path,
            "theme": self.theme,
            "recent_sessions": self.recent_sessions,
            "window_geometry": self.window_geometry,
            "comparison_settings": self.comparison_settings,
            "filter_options": self.filter_options,
            "last_paths": self.last_paths,
            "folder_columns": self.folder_columns,
            "active_view": self.active_view,
            "three_way_mode": self.three_way_mode,
        }
        path.write_text(json.dumps(data, indent=2))

    def get_cli_path(self) -> str:
        """Return CLI path, raising if not found."""
        if self.cli_path and Path(self.cli_path).exists():
            return self.cli_path
        # Re-scan
        found = _find_cli()
        if found:
            self.cli_path = found
            return found
        raise FileNotFoundError(
            "rcompare_cli binary not found. Please set the path in Tools > Options."
        )
