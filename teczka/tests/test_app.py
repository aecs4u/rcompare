"""Tests for the GUI startup flow."""

from __future__ import annotations

from teczka import app as app_module
from teczka.utils.config import AppConfig


class _FakeApplication:
    def __init__(self, _args):
        self.exit_code = 0

    def setApplicationName(self, _name):
        pass

    def setApplicationVersion(self, _version):
        pass

    def setOrganizationName(self, _name):
        pass

    def setDesktopFileName(self, _name):
        pass

    def setStyle(self, _style):
        pass

    def exec(self):
        return self.exit_code


class _FakeWindow:
    def __init__(self, config):
        self.config = config
        self.shown = False

    def resize(self, *_args):
        pass

    def move(self, *_args):
        pass

    def show(self):
        self.shown = True


def _prepare_launch(monkeypatch, config: AppConfig) -> tuple[list[int], list[str]]:
    exit_codes: list[int] = []
    themes: list[str] = []
    monkeypatch.setattr(app_module, "QApplication", _FakeApplication)
    monkeypatch.setattr(app_module, "MainWindow", _FakeWindow)
    monkeypatch.setattr(app_module.AppConfig, "load", classmethod(lambda _cls: config))
    monkeypatch.setattr(app_module, "setup_logging", lambda **_kwargs: None)
    monkeypatch.setattr(
        app_module, "apply_theme", lambda _application, theme: themes.append(theme)
    )
    monkeypatch.setattr(app_module.sys, "exit", exit_codes.append)
    return exit_codes, themes


def test_path_launch_bypasses_splash(monkeypatch):
    config = AppConfig(show_splash=True)
    exit_codes, themes = _prepare_launch(monkeypatch, config)

    class UnexpectedSplash:
        def __init__(self):
            raise AssertionError("path-based launch must not create the splash")

    monkeypatch.setattr(app_module, "SplashDialog", UnexpectedSplash)
    app_module.launch(left="/tmp/from-file-manager")

    assert config.last_paths["left"] == "/tmp/from-file-manager"
    assert themes == [config.theme]
    assert exit_codes == [0]


def test_dont_show_again_is_persisted(monkeypatch):
    config = AppConfig(show_splash=True)
    saved: list[bool] = []
    config.save = lambda: saved.append(config.show_splash)  # type: ignore[method-assign]
    exit_codes, themes = _prepare_launch(monkeypatch, config)

    class HiddenNextTimeSplash:
        class DialogCode:
            Accepted = 1

        def exec(self):
            return self.DialogCode.Accepted

        def should_show_again(self):
            return False

    monkeypatch.setattr(app_module, "SplashDialog", HiddenNextTimeSplash)
    app_module.launch()

    assert config.show_splash is False
    assert saved == [False]
    assert themes == [config.theme]
    assert exit_codes == [0]
