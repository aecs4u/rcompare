"""Fluent i18n localizer for teczka, modeled after Kalka's approach.

Provides translation via Mozilla's Fluent format with automatic locale
detection and a fallback chain: user locale -> en -> raw key.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_I18N_DIR = Path(__file__).parent / "i18n"
_DEFAULT_LOCALE = "en"

_current_locale: str = _DEFAULT_LOCALE

try:
    from fluent.runtime import FluentLocalization, FluentResourceLoader

    _has_fluent = True
except ImportError:
    _has_fluent = False
    log.info("fluent.runtime not installed; translations will return raw keys")

_localization: FluentLocalization | None = None


def _detect_locale() -> str:
    """Detect the user's locale from environment variables."""
    for var in ("LC_MESSAGES", "LANG", "LC_ALL"):
        value = os.environ.get(var, "")
        if value:
            # Strip encoding suffix like ".UTF-8" and territory variants
            locale = value.split(".")[0]
            # Normalise e.g. "en_US" -> "en" if we don't have the full tag
            if locale and not (_I18N_DIR / locale).is_dir():
                locale = locale.split("_")[0]
            if locale and (_I18N_DIR / locale).is_dir():
                return locale
    return _DEFAULT_LOCALE


def init(locale: str = "") -> None:
    """Initialise the localizer.

    Args:
        locale: BCP-47 locale tag (e.g. ``"en"``, ``"de"``).  When empty the
            locale is auto-detected from ``LANG`` / ``LC_MESSAGES``.
    """
    global _localization, _current_locale

    if not locale:
        locale = _detect_locale()

    _current_locale = locale

    if not _has_fluent:
        _localization = None
        return

    locales: list[str] = [locale]
    if locale != _DEFAULT_LOCALE:
        locales.append(_DEFAULT_LOCALE)

    loader = FluentResourceLoader(str(_I18N_DIR / "{locale}"))
    _localization = FluentLocalization(
        locales=locales,
        resource_ids=["teczka.ftl"],
        resource_loader=loader,
    )
    log.info("localizer initialised: locale=%s, chain=%s", locale, locales)


def tr(key: str, **kwargs: object) -> str:
    """Translate *key* using the current Fluent bundle.

    Any keyword arguments are passed as Fluent message variables.  If the
    ``fluent.runtime`` package is not installed or the key is missing from
    every bundle in the fallback chain the raw *key* is returned.
    """
    if _localization is None:
        return key
    try:
        value = _localization.format_value(key, kwargs if kwargs else None)
    except Exception:
        log.warning("translation error for key %r", key, exc_info=True)
        return key
    # FluentLocalization.format_value returns the key itself when not found
    return value if value is not None else key


def available_locales() -> list[str]:
    """Return locale tags for which an ``i18n/{locale}/`` directory exists."""
    if not _I18N_DIR.is_dir():
        return []
    return sorted(
        entry.name
        for entry in _I18N_DIR.iterdir()
        if entry.is_dir() and not entry.name.startswith("_")
    )


def current_locale() -> str:
    """Return the currently active locale tag."""
    return _current_locale
