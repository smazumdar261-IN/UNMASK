"""Lexer for Go source code.

Per Section 15 of the Master Specification (Phase 9: Go):
Tokenizes Go source files (.go) into tokens with precise 1-indexed SourceLocation provenance.
Supports keywords, identifiers, numeric literals (int, hex, octal, binary, float),
interpreted and raw backtick strings, rune literals, comments, operators, and
automatic semicolon insertion (ASI).
"""

from __future__ import annotations

from enum import Enum, auto
from typing import List, Optional

from core.exceptions import ParseError
from core.provenance import SourceLocation


class GoTokenType(Enum):
    """Go token categories."""

    KEYWORD = auto()
    IDENTIFIER = auto()
    NUMBER = auto()
    STRING = auto()
    RUNE = auto()
    PUNCTUATOR = auto()
    COMMENT = auto()
    EOF = auto()


class GoToken:
    """Represents a single lexical token in Go source."""

    def __init__(self, token_type: GoTokenType, value: str, location: SourceLocation) -> None:
        self.type = token_type
        self.value = value
        self.location = location

    def __repr__(self) -> str:
        return f"GoToken({self.type.name}, {self.value!r}, L{self.location.start_line}:C{self.location.start_col})"


GO_KEYWORDS = {
    "break", "case", "chan", "const", "continue", "default", "defer", "else",
    "fallthrough", "for", "func", "go", "goto", "if", "import", "interface",
    "map", "package", "range", "return", "select", "struct", "switch", "type",
    "var",
}

# Tokens that trigger Go's automatic semicolon insertion when followed by newline
ASI_TRIGGER_PUNCTUATORS = {")", "]", "}", "++", "--"}
ASI_TRIGGER_KEYWORDS = {"break", "continue", "fallthrough", "return"}

MULTI_PUNCTUATORS = [
    # 3-char
    "... ", "<<=", ">>=", "&^=",
    # 2-char
    ":=", "==", "!=", "<=", ">=", "&&", "||", "<<", ">>", "&^", "<-", "++", "--",
    "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=",
]
# Clean up spaces
MULTI_PUNCTUATORS = [p.strip() for p in MULTI_PUNCTUATORS]


class GoLexer:
    """Lexer for Go source code."""

    def __init__(self, source: str, filename: Optional[str] = None) -> None:
        self.source = source
        self.filename = filename or "<go>"
        self.pos = 0
        self.line = 1
        self.col = 1
        self.length = len(source)

    def tokenize(self) -> List[GoToken]:
        """Scans the source code and returns a list of GoTokens with ASI."""
        raw_tokens: List[GoToken] = []

        while self.pos < self.length:
            self._skip_whitespace_except_newline()
            if self.pos >= self.length:
                break

            start_loc = SourceLocation(
                filename=self.filename,
                start_line=self.line,
                start_col=self.col,
            )
            ch = self.source[self.pos]

            # Newline handling for automatic semicolon insertion
            if ch == "\n":
                self._advance()
                if raw_tokens and self._should_insert_semicolon(raw_tokens[-1]):
                    semi_loc = SourceLocation(
                        filename=self.filename,
                        start_line=start_loc.start_line,
                        start_col=start_loc.start_col,
                        end_line=start_loc.start_line,
                        end_col=start_loc.start_col + 1,
                    )
                    raw_tokens.append(GoToken(GoTokenType.PUNCTUATOR, ";", semi_loc))
                continue

            # Line comment
            if ch == "/" and self.pos + 1 < self.length and self.source[self.pos + 1] == "/":
                self._read_line_comment()
                continue

            # Block comment
            if ch == "/" and self.pos + 1 < self.length and self.source[self.pos + 1] == "*":
                comment_tok = self._read_block_comment(start_loc)
                # If block comment contains newline and preceded by trigger token, insert semicolon
                if "\n" in comment_tok.value and raw_tokens and self._should_insert_semicolon(raw_tokens[-1]):
                    raw_tokens.append(GoToken(GoTokenType.PUNCTUATOR, ";", start_loc))
                continue

            # String literal (interpreted: "..." or raw: `...`)
            if ch == '"':
                raw_tokens.append(self._read_interpreted_string(start_loc))
                continue
            if ch == "`":
                raw_tokens.append(self._read_raw_string(start_loc))
                continue

            # Rune literal ('a', '\n')
            if ch == "'":
                raw_tokens.append(self._read_rune(start_loc))
                continue

            # Number literal
            if ch.isdigit() or (ch == "." and self.pos + 1 < self.length and self.source[self.pos + 1].isdigit()):
                raw_tokens.append(self._read_number(start_loc))
                continue

            # Multi-character punctuator
            if self._match_multi_punctuator():
                op = self._read_multi_punctuator()
                end_loc = SourceLocation(
                    filename=self.filename,
                    start_line=start_loc.start_line,
                    start_col=start_loc.start_col,
                    end_line=self.line,
                    end_col=self.col,
                )
                raw_tokens.append(GoToken(GoTokenType.PUNCTUATOR, op, end_loc))
                continue

            # Single-character punctuator
            if ch in "(){}[];,.:+-*/%&|^!~<>=?":
                val = self._advance()
                end_loc = SourceLocation(
                    filename=self.filename,
                    start_line=start_loc.start_line,
                    start_col=start_loc.start_col,
                    end_line=self.line,
                    end_col=self.col,
                )
                raw_tokens.append(GoToken(GoTokenType.PUNCTUATOR, val, end_loc))
                continue

            # Identifier or Keyword
            if ch.isalpha() or ch == "_":
                raw_tokens.append(self._read_identifier_or_keyword(start_loc))
                continue

            raise ParseError(
                f"Unexpected character in Go source: {ch!r}",
                filename=self.filename,
                lineno=self.line,
                col_offset=self.col,
            )

        # Final ASI before EOF if needed
        if raw_tokens and self._should_insert_semicolon(raw_tokens[-1]):
            eof_semi_loc = SourceLocation(
                filename=self.filename,
                start_line=self.line,
                start_col=self.col,
                end_line=self.line,
                end_col=self.col,
            )
            raw_tokens.append(GoToken(GoTokenType.PUNCTUATOR, ";", eof_semi_loc))

        eof_loc = SourceLocation(filename=self.filename, start_line=self.line, start_col=self.col)
        raw_tokens.append(GoToken(GoTokenType.EOF, "", eof_loc))
        return raw_tokens

    def _should_insert_semicolon(self, last_tok: GoToken) -> bool:
        """Determines if the preceding token requires an automatic semicolon."""
        if last_tok.type in (GoTokenType.IDENTIFIER, GoTokenType.NUMBER, GoTokenType.STRING, GoTokenType.RUNE):
            return True
        if last_tok.type == GoTokenType.KEYWORD and last_tok.value in ASI_TRIGGER_KEYWORDS:
            return True
        if last_tok.type == GoTokenType.PUNCTUATOR and last_tok.value in ASI_TRIGGER_PUNCTUATORS:
            return True
        return False

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _skip_whitespace_except_newline(self) -> None:
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch in (" ", "\t", "\r"):
                self._advance()
            else:
                break

    def _read_line_comment(self) -> None:
        while self.pos < self.length and self.source[self.pos] != "\n":
            self._advance()

    def _read_block_comment(self, start_loc: SourceLocation) -> GoToken:
        self._advance()  # /
        self._advance()  # *
        content: List[str] = []
        while self.pos < self.length:
            if self.source[self.pos] == "*" and self.pos + 1 < self.length and self.source[self.pos + 1] == "/":
                self._advance()
                self._advance()
                break
            content.append(self._advance())
        end_loc = SourceLocation(
            filename=self.filename,
            start_line=start_loc.start_line,
            start_col=start_loc.start_col,
            end_line=self.line,
            end_col=self.col,
        )
        return GoToken(GoTokenType.COMMENT, "".join(content), end_loc)

    def _read_interpreted_string(self, start_loc: SourceLocation) -> GoToken:
        self._advance()  # Opening "
        chars: List[str] = []
        while self.pos < self.length:
            ch = self._advance()
            if ch == '"':
                break
            if ch == "\\":
                if self.pos >= self.length:
                    break
                esc = self._advance()
                if esc == "n":
                    chars.append("\n")
                elif esc == "r":
                    chars.append("\r")
                elif esc == "t":
                    chars.append("\t")
                elif esc == "\\":
                    chars.append("\\")
                elif esc == '"':
                    chars.append('"')
                elif esc == "x" and self.pos + 2 <= self.length:
                    hex_str = self.source[self.pos : self.pos + 2]
                    self._advance()
                    self._advance()
                    try:
                        chars.append(chr(int(hex_str, 16)))
                    except ValueError:
                        chars.append(f"\\x{hex_str}")
                elif esc == "u" and self.pos + 4 <= self.length:
                    hex_str = self.source[self.pos : self.pos + 4]
                    for _ in range(4):
                        self._advance()
                    try:
                        chars.append(chr(int(hex_str, 16)))
                    except ValueError:
                        chars.append(f"\\u{hex_str}")
                else:
                    chars.append(esc)
            else:
                chars.append(ch)

        end_loc = SourceLocation(
            filename=self.filename,
            start_line=start_loc.start_line,
            start_col=start_loc.start_col,
            end_line=self.line,
            end_col=self.col,
        )
        return GoToken(GoTokenType.STRING, "".join(chars), end_loc)

    def _read_raw_string(self, start_loc: SourceLocation) -> GoToken:
        self._advance()  # Opening `
        chars: List[str] = []
        while self.pos < self.length:
            ch = self._advance()
            if ch == "`":
                break
            chars.append(ch)
        end_loc = SourceLocation(
            filename=self.filename,
            start_line=start_loc.start_line,
            start_col=start_loc.start_col,
            end_line=self.line,
            end_col=self.col,
        )
        return GoToken(GoTokenType.STRING, "".join(chars), end_loc)

    def _read_rune(self, start_loc: SourceLocation) -> GoToken:
        self._advance()  # Opening '
        chars: List[str] = []
        while self.pos < self.length:
            ch = self._advance()
            if ch == "'":
                break
            if ch == "\\":
                if self.pos >= self.length:
                    break
                esc = self._advance()
                if esc == "n":
                    chars.append("\n")
                elif esc == "t":
                    chars.append("\t")
                elif esc == "'":
                    chars.append("'")
                elif esc == "\\":
                    chars.append("\\")
                else:
                    chars.append(esc)
            else:
                chars.append(ch)
        end_loc = SourceLocation(
            filename=self.filename,
            start_line=start_loc.start_line,
            start_col=start_loc.start_col,
            end_line=self.line,
            end_col=self.col,
        )
        return GoToken(GoTokenType.RUNE, "".join(chars), end_loc)

    def _read_number(self, start_loc: SourceLocation) -> GoToken:
        chars: List[str] = []
        is_hex = False
        is_bin = False
        is_oct = False

        if self.source[self.pos] == "0" and self.pos + 1 < self.length:
            next_ch = self.source[self.pos + 1].lower()
            if next_ch == "x":
                is_hex = True
                chars.append(self._advance())
                chars.append(self._advance())
            elif next_ch == "b":
                is_bin = True
                chars.append(self._advance())
                chars.append(self._advance())
            elif next_ch == "o":
                is_oct = True
                chars.append(self._advance())
                chars.append(self._advance())

        while self.pos < self.length:
            ch = self.source[self.pos]
            if is_hex and (ch.isdigit() or ch.lower() in "abcdef"):
                chars.append(self._advance())
            elif is_bin and ch in ("0", "1"):
                chars.append(self._advance())
            elif is_oct and ch in "01234567":
                chars.append(self._advance())
            elif not is_hex and not is_bin and not is_oct and (ch.isdigit() or ch in (".", "e", "E", "_")):
                chars.append(self._advance())
            elif ch == "_" and (is_hex or is_bin or is_oct):
                chars.append(self._advance())
            else:
                break

        num_str = "".join(chars)
        end_loc = SourceLocation(
            filename=self.filename,
            start_line=start_loc.start_line,
            start_col=start_loc.start_col,
            end_line=self.line,
            end_col=self.col,
        )
        return GoToken(GoTokenType.NUMBER, num_str, end_loc)

    def _read_identifier_or_keyword(self, start_loc: SourceLocation) -> GoToken:
        chars: List[str] = []
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch.isalnum() or ch == "_":
                chars.append(self._advance())
            else:
                break
        name = "".join(chars)
        ttype = GoTokenType.KEYWORD if name in GO_KEYWORDS else GoTokenType.IDENTIFIER
        end_loc = SourceLocation(
            filename=self.filename,
            start_line=start_loc.start_line,
            start_col=start_loc.start_col,
            end_line=self.line,
            end_col=self.col,
        )
        return GoToken(ttype, name, end_loc)

    def _match_multi_punctuator(self) -> bool:
        for p in MULTI_PUNCTUATORS:
            if self.source.startswith(p, self.pos):
                return True
        return False

    def _read_multi_punctuator(self) -> str:
        for p in MULTI_PUNCTUATORS:
            if self.source.startswith(p, self.pos):
                for _ in range(len(p)):
                    self._advance()
                return p
        return ""
