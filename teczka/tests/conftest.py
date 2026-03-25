"""Shared test fixtures for teczka."""

from __future__ import annotations

import os

import pytest

# Force offscreen rendering for CI
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Create or reuse QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def tmp_config(tmp_path):
    """Create a temporary config file for testing."""
    config_file = tmp_path / "pyside.json"
    config_file.write_text("{}")
    return config_file


@pytest.fixture
def sample_dirs(tmp_path):
    """Create sample left/right directories with test files."""
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "same.txt").write_text("identical content")
    (right / "same.txt").write_text("identical content")
    (left / "diff.txt").write_text("left version")
    (right / "diff.txt").write_text("right version")
    (left / "only_left.txt").write_text("only in left")
    (right / "only_right.txt").write_text("only in right")
    return left, right
