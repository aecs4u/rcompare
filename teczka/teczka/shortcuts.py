"""Keyboard shortcut resolution and the application's action registry.

Two problems this module exists to solve:

1. ``QKeySequence.StandardKey`` is not portable in the way it looks. On Linux
   ``StandardKey.Quit`` resolves to the ``Exit`` *multimedia* key, and
   ``StandardKey.Preferences`` to ``Settings`` — neither of which is a chord a
   user can type. Menu entries built from those keys silently stop working.
   :func:`standard_key` validates the platform binding and falls back to an
   explicit chord when it is unusable.

2. Shortcut collisions and the About dialog's keyboard table were maintained by
   hand in three places. :func:`collect_shortcuts` reads them back off the live
   actions so documentation and collision tests share one source of truth.
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence

# Qt maps several StandardKey values onto multimedia/system keys rather than
# typeable chords. A binding whose text contains one of these names cannot be
# produced from an ordinary keyboard, so it must never be used as a menu
# accelerator.
_UNTYPEABLE_KEY_NAMES = (
    "Exit",
    "Settings",
    "LaunchMedia",
    "HomePage",
    "Search",
    "Standby",
    "WakeUp",
    "Favorites",
)


def is_typeable(sequence: QKeySequence) -> bool:
    """Return whether *sequence* is a chord a user can actually press.

    Rejects empty sequences and bare multimedia/system keys such as ``Exit``.
    A sequence with a modifier (``Ctrl+Q``) is always accepted, since the
    modifier proves it is a real chord rather than a hardware key.
    """
    if sequence.isEmpty():
        return False
    text = sequence.toString(QKeySequence.SequenceFormat.PortableText)
    if not text:
        return False
    if "+" in text:
        return True
    return text not in _UNTYPEABLE_KEY_NAMES


def standard_key(
    key: QKeySequence.StandardKey, fallback: str
) -> QKeySequence:
    """Resolve a platform standard key, falling back to *fallback*.

    Uses the platform binding when it produces a typeable chord so KDE/macOS
    conventions still win, and the explicit *fallback* otherwise.
    """
    sequence = QKeySequence(key)
    if is_typeable(sequence):
        return sequence
    return QKeySequence(fallback)


def collect_shortcuts(actions: list[QAction]) -> list[tuple[str, str]]:
    """Return ``(chord, description)`` pairs for every bound action.

    ``description`` is the action text with menu mnemonics stripped. Actions
    without a shortcut are skipped. Sorted by description so the About dialog
    renders a stable table.
    """
    rows: list[tuple[str, str]] = []
    for action in actions:
        sequence = action.shortcut()
        if sequence.isEmpty():
            continue
        label = action.text().replace("&", "").replace("...", "").strip()
        if not label:
            continue
        rows.append(
            (sequence.toString(QKeySequence.SequenceFormat.NativeText), label)
        )
    rows.sort(key=lambda row: row[1].lower())
    return rows


def find_collisions(actions: list[QAction]) -> dict[str, list[str]]:
    """Return chords bound to more than one action, mapped to their labels."""
    by_chord: dict[str, list[str]] = {}
    for action in actions:
        for sequence in action.shortcuts():
            if sequence.isEmpty():
                continue
            chord = sequence.toString(QKeySequence.SequenceFormat.PortableText)
            label = action.text().replace("&", "").strip() or action.objectName()
            by_chord.setdefault(chord, []).append(label)
    return {chord: labels for chord, labels in by_chord.items() if len(labels) > 1}
