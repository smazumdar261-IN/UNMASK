"""TypeScript Lexer.

Per Section 13 of the Master Specification (Phase 7: TypeScript):
Extends JavaScript lexer with TypeScript keywords and syntax support:
- Keywords: interface, type, enum, as, implements, declare, namespace, etc.
- Decorators: @decorator
- Parameter and property modifiers: readonly, public, private, protected
"""

from __future__ import annotations

from typing import Optional

from core.provenance import SourceLocation
from languages.javascript.lexer import (
    JS_KEYWORDS,
    JSLexer,
    JSToken,
    JSTokenType,
)

TS_KEYWORDS = JS_KEYWORDS | {
    "interface",
    "type",
    "enum",
    "as",
    "implements",
    "declare",
    "namespace",
    "module",
    "readonly",
    "private",
    "protected",
    "public",
    "abstract",
    "override",
    "keyof",
    "infer",
    "is",
}


class TSLexer(JSLexer):
    """Lexer for TypeScript source text."""

    def __init__(self, source: str, filename: Optional[str] = None) -> None:
        super().__init__(source, filename or "<typescript>")

    def _read_identifier_or_keyword(self, start_loc: SourceLocation) -> JSToken:
        chars = []
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch.isalnum() or ch in ("_", "$"):
                chars.append(self._advance())
            else:
                break
        name = "".join(chars)
        ttype = JSTokenType.KEYWORD if name in TS_KEYWORDS else JSTokenType.IDENTIFIER
        end_loc = SourceLocation(
            filename=self.filename,
            start_line=start_loc.start_line,
            start_col=start_loc.start_col,
            end_line=self.line,
            end_col=self.col,
        )
        return JSToken(ttype, name, end_loc)
