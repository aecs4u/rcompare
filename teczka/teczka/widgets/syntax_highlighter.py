"""Small, theme-aware syntax highlighting for the side-by-side text editors."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PySide6.QtGui import QColor, QFont, QPalette, QSyntaxHighlighter, QTextCharFormat


@dataclass(frozen=True)
class _Language:
    keywords: frozenset[str]
    line_comments: tuple[str, ...] = ()
    block_comment: tuple[str, str] | None = None
    triple_strings: tuple[str, ...] = ()
    tags: bool = False


_PYTHON = _Language(
    frozenset({
        "and", "as", "assert", "async", "await", "break", "class", "continue",
        "def", "del", "elif", "else", "except", "finally", "for", "from",
        "global", "if", "import", "in", "is", "lambda", "nonlocal", "not", "or",
        "pass", "raise", "return", "try", "while", "with", "yield", "match", "case",
    }),
    line_comments=("#",),
    triple_strings=('"""', "'''"),
)
_C_LIKE = _Language(
    frozenset({
        "abstract", "as", "async", "await", "bool", "break", "case", "catch", "char",
        "class", "const", "continue", "default", "do", "double", "else", "enum",
        "export", "extends", "false", "final", "finally", "float", "for", "function",
        "if", "implements", "import", "in", "int", "interface", "let", "long", "new",
        "null", "package", "private", "protected", "public", "return", "short", "static",
        "struct", "switch", "this", "throw", "true", "try", "typedef", "typeof", "var",
        "void", "volatile", "while", "fn", "mut", "pub", "use", "crate", "self", "super",
        "impl", "trait", "type", "where", "match", "ref", "move", "unsafe",
    }),
    line_comments=("//",),
    block_comment=("/*", "*/"),
)
_LANGUAGES: dict[str, _Language] = {
    "python": _PYTHON,
    "javascript": _C_LIKE,
    "typescript": _C_LIKE,
    "rust": _C_LIKE,
    "c": _C_LIKE,
    "cpp": _C_LIKE,
    "java": _C_LIKE,
    "go": _C_LIKE,
    "shell": _Language(
        frozenset({
            "case", "do", "done", "elif", "else", "esac", "fi", "for", "function", "if",
            "in", "select", "then", "time", "until", "while",
        }),
        line_comments=("#",),
    ),
    "sql": _Language(
        frozenset({
            "all", "alter", "as", "by", "case", "create", "delete", "distinct", "drop",
            "else", "end", "from", "group", "having", "insert", "into", "join", "left",
            "limit", "not", "null", "on", "or", "order", "outer", "right", "select", "set",
            "table", "then", "union", "update", "values", "when", "where", "with",
        }),
        line_comments=("--",),
        block_comment=("/*", "*/"),
    ),
    "json": _Language(frozenset(("true", "false", "null"))),
    "yaml": _Language(
        frozenset(("true", "false", "null", "yes", "no", "on", "off")),
        line_comments=("#",),
    ),
    "toml": _Language(frozenset(("true", "false")), line_comments=("#",)),
    "html": _Language(frozenset(), block_comment=("<!--", "-->"), tags=True),
    "xml": _Language(frozenset(), block_comment=("<!--", "-->"), tags=True),
    "css": _Language(frozenset(), block_comment=("/*", "*/")),
}

_EXTENSIONS = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".java": "java",
    ".go": "go",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".sql": "sql",
    ".json": "json",
    ".jsonc": "javascript",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".svg": "xml",
    ".css": "css",
}

_PALETTES = {
    "light": {
        "keyword": "#005cc5",
        "literal": "#b31d28",
        "string": "#0a7d3b",
        "comment": "#6a737d",
        "number": "#b31d28",
        "function": "#6f42c1",
        "tag": "#0550ae",
        "attribute": "#953800",
    },
    "dark": {
        "keyword": "#79c0ff",
        "literal": "#ff7b72",
        "string": "#a5d6a7",
        "comment": "#8b949e",
        "number": "#ff7b72",
        "function": "#d2a8ff",
        "tag": "#7ee787",
        "attribute": "#ffa657",
    },
}


def language_for_path(path: str) -> str | None:
    """Return the highlighter language for a local path or source URL."""
    candidate = urlsplit(path).path if "://" in path else path
    suffix = Path(unquote(candidate)).suffix.casefold()
    return _EXTENSIONS.get(suffix)


class SyntaxHighlighter(QSyntaxHighlighter):
    """Highlight common source and data formats without changing diff rows."""

    def __init__(self, document, language: str, editor) -> None:
        super().__init__(document)
        self._editor = editor
        self._formats = {
            palette_name: {
                category: self._build_format(palette_name, category)
                for category in _PALETTES[palette_name]
            }
            for palette_name in _PALETTES
        }
        self._configure_language(language)

    def set_language(self, language: str) -> None:
        if language != self._language:
            self._configure_language(language)
            self.rehighlight()

    def _build_format(self, palette_name: str, category: str) -> QTextCharFormat:
        result = QTextCharFormat()
        result.setForeground(QColor(_PALETTES[palette_name][category]))
        if category == "keyword":
            result.setFontWeight(QFont.Weight.DemiBold)
        return result

    def _configure_language(self, language: str) -> None:
        self._language = language
        spec = _LANGUAGES[language]
        self._number_pattern = re.compile(r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b")
        self._literal_pattern = re.compile(r"\b(?:None|True|False|undefined|NaN|Infinity)\b")
        self._function_pattern = re.compile(r"\b[A-Za-z_$][\w$]*(?=\s*\()")
        self._tag_pattern = re.compile(r"</?[A-Za-z][^>]*?/?>") if spec.tags else None
        if spec.keywords:
            words = "|".join(
                re.escape(word) for word in sorted(spec.keywords, key=len, reverse=True)
            )
            flags = re.IGNORECASE if language in {"sql", "yaml"} else re.RegexFlag(0)
            self._keyword_pattern = re.compile(rf"\b(?:{words})\b", flags)
        else:
            self._keyword_pattern = None

    def _background(self) -> QColor:
        block_number = self.currentBlock().blockNumber()
        line_colors = getattr(self._editor, "_line_colors", ())
        if block_number < len(line_colors):
            color = line_colors[block_number]
            base = self._editor.palette().color(QPalette.ColorRole.Base)
            if color.isValid() and color != base:
                return color
        return self._editor.palette().color(QPalette.ColorRole.Base)

    def highlightBlock(self, text: str) -> None:
        language = _LANGUAGES[self._language]
        background = self._background()
        palette_name = "dark" if background.lightness() < 145 else "light"
        formats = self._formats[palette_name]
        occupied = [False] * len(text)
        offsets = [0]
        for character in text:
            offsets.append(offsets[-1] + (2 if ord(character) > 0xFFFF else 1))

        def paint(start: int, end: int, category: str) -> None:
            if end <= start:
                return
            self.setFormat(offsets[start], offsets[end] - offsets[start], formats[category])
            occupied[start:end] = [True] * (end - start)

        def find_next(start: int, markers: tuple[str, ...]) -> tuple[int, str] | None:
            found = [(text.find(marker, start), marker) for marker in markers]
            found = [(index, marker) for index, marker in found if index >= 0]
            return min(found, key=lambda item: (item[0], -len(item[1])), default=None)

        def find_unescaped(marker: str, start: int) -> int:
            index = text.find(marker, start)
            while index >= 0:
                backslashes = 0
                cursor = index - 1
                while cursor >= 0 and text[cursor] == "\\":
                    backslashes += 1
                    cursor -= 1
                if backslashes % 2 == 0:
                    return index
                index = text.find(marker, index + 1)
            return -1

        state = self.previousBlockState()
        cursor = 0
        if state == 1 or state >= 2:
            closing = language.block_comment[1] if state == 1 and language.block_comment else (
                language.triple_strings[state - 2] if state >= 2 else ""
            )
            end = text.find(closing, cursor) if closing else -1
            if end < 0:
                paint(0, len(text), "comment" if state == 1 else "string")
                self.setCurrentBlockState(state)
                return
            finish = end + len(closing)
            paint(0, finish, "comment" if state == 1 else "string")
            cursor = finish
            self.setCurrentBlockState(0)

        block_start = (language.block_comment[0],) if language.block_comment else ()
        markers = (
            *language.line_comments,
            *block_start,
            *language.triple_strings,
            "\"",
            "'",
            "`",
        )
        while cursor < len(text):
            match = find_next(cursor, markers)
            if match is None:
                break
            start, marker = match
            if marker in language.line_comments:
                paint(start, len(text), "comment")
                break
            if marker in language.triple_strings:
                end = text.find(marker, start + len(marker))
                if end < 0:
                    paint(start, len(text), "string")
                    self.setCurrentBlockState(2 + language.triple_strings.index(marker))
                    break
                finish = end + len(marker)
                paint(start, finish, "string")
                cursor = finish
                continue
            if marker == "/*" and language.block_comment:
                end = text.find(language.block_comment[1], start + len(marker))
                if end < 0:
                    paint(start, len(text), "comment")
                    self.setCurrentBlockState(1)
                    break
                finish = end + len(language.block_comment[1])
                paint(start, finish, "comment")
                cursor = finish
                continue
            finish = find_unescaped(marker, start + len(marker))
            finish = len(text) if finish < 0 else finish + len(marker)
            paint(start, finish, "string")
            cursor = finish

        def apply_pattern(pattern: re.Pattern[str] | None, category: str) -> None:
            if pattern is None:
                return
            for match in pattern.finditer(text):
                start, end = match.span()
                if start < end and not any(occupied[start:end]):
                    paint(start, end, category)

        apply_pattern(self._number_pattern, "number")
        apply_pattern(self._keyword_pattern, "keyword")
        apply_pattern(self._literal_pattern, "literal")
        apply_pattern(self._function_pattern, "function")
        apply_pattern(self._tag_pattern, "tag")
