"""Tests for teczka utility modules."""

from __future__ import annotations

from teczka.hig import format_size, format_duration, format_count, dpi_scale
from teczka.localizer import tr, init, current_locale, available_locales
from teczka.logger import get_logger, setup_logging


class TestHig:
    def test_format_size_bytes(self):
        assert format_size(0) == "0 B"
        assert format_size(512) == "512 B"

    def test_format_size_kib(self):
        assert "KiB" in format_size(2048)

    def test_format_size_mib(self):
        assert "MiB" in format_size(5 * 1024 * 1024)

    def test_format_size_gib(self):
        assert "GiB" in format_size(3 * 1024 * 1024 * 1024)

    def test_format_size_negative(self):
        assert format_size(-1) == "Unknown"

    def test_format_duration_seconds(self):
        assert format_duration(45) == "45s"

    def test_format_duration_minutes(self):
        assert format_duration(125) == "2m05s"

    def test_format_duration_hours(self):
        assert format_duration(3725) == "1h02m"

    def test_format_count(self):
        assert format_count(1234567) == "1,234,567"

    def test_dpi_scale(self, qapp):
        result = dpi_scale(100)
        assert isinstance(result, int)
        assert result >= 100


class TestLocalizer:
    def test_init_default(self):
        init()
        assert current_locale() != ""

    def test_tr_returns_string(self):
        init()
        result = tr("app-name")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_available_locales(self):
        locales = available_locales()
        assert "en" in locales


class TestLogger:
    def test_get_logger(self):
        log = get_logger("test")
        assert log is not None

    def test_setup_logging(self):
        setup_logging(log_level="DEBUG")
