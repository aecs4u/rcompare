"""Tests for teczka configuration."""

from __future__ import annotations

import json

from teczka.utils.config import AppConfig


class TestAppConfig:
    def test_default_config(self):
        config = AppConfig()
        assert config.theme == "light"
        assert config.recent_sessions == []

    def test_save_load_roundtrip(self, tmp_path):
        config = AppConfig()
        config._config_file = str(tmp_path / "test.json")
        config.theme = "dark"
        config.bookmarks = [{"name": "test", "left": "/a", "right": "/b"}]
        config.save()

        loaded = json.loads((tmp_path / "test.json").read_text())
        assert loaded["theme"] == "dark"
        assert len(loaded["bookmarks"]) == 1
