"""Lexer for JavaScript source code.

Per Section 12 of the Master Specification:
Tokenizes JavaScript source text with exact line and column tracking:
- Identifiers and reserved keywords
- Number literals (decimal, hex 0x..., octal, binary, floats)
- String literals (single quotes, double quotes, backtick template strings, hex/unicode escapes)
- Operators, punctuation, and multi-character operators (===, !==, =>, etc.)
- Strips whitespace and comments (// and /* ... */)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional

from core.exceptions import ParseError
from core.provenance import SourceLocation


class JSTokenType(Enum):
    KEYWORD = auto()
    IDENTIFIER = auto()
    NUMBER = auto()
    STRING = auto()
    PUNCTUATOR = auto()
    EOF = auto()


JS_KEYWORDS = {
    "var", "let", "const", "function", "return", "if", "else", "while", "for",
    "break", "continue", "true", "false", "null", "undefined", "typeof", "void",
    "new", "this", "try", "catch", "finally", "throw", "switch", "case", "default"
}

MULTI_PUNCTUATORS = [
    "===", "!==", ">>>",
    "<=", ">=", "==", "!=", "&&", "||", "++", "--", "=>",
    "<<", ">>", "+=", "-=", "*=", "/=", "%=", "^=", "&=", "|=",
]

SINGLE_PUNCTUATORS = set("+-*/%^&|~!><=?:.,;(){}[]@")


@dataclass(frozen=True)
class JSToken:
    type: JSTokenType
    value: str
    location: SourceLocation

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r} at {self.location})"


class JSLexer:
    """Tokenizes JavaScript source string into a stream of JSTokens."""

    def __init__(self, source: str, filename: Optional[str] = None) -> None:
        self.source: str = source
        self.filename: str = filename or "<javascript>"
        self.pos: int = 0
        self.line: int = 1
        self.col: int = 1
        self.length: int = len(source)

    def tokenize(self) -> List[JSToken]:
        tokens: List[JSToken] = []
        while self.pos < self.length:
            self._skip_whitespace_and_comments()
            if self.pos >= self.length:
                break

            loc = SourceLocation(filename=self.filename, start_line=self.line, start_col=self.col)
            ch = self.source[self.pos]

            # 1. String literal
            if ch in ("'", '"', "`"):
                token = self._read_string(ch, loc)
                tokens.append(token)
            # 2. Number literal
            elif ch.isdigit() or (ch == "." and self.pos + 1 < self.length and self.source[self.pos + 1].isdigit()):
                token = self._read_number(loc)
                tokens.append(token)
            # 3. Identifier or Keyword
            elif ch.isalpha() or ch in ("_", "$"):
                token = self._read_identifier_or_keyword(loc)
                tokens.append(token)
            # 4. Multi-character punctuator
            elif self._match_multi_punctuator():
                op = self._read_multi_punctuator()
                tokens.append(JSToken(JSTokenType.PUNCTUATOR, op, loc))
            # 5. Single punctuator
            elif ch in SINGLE_PUNCTUATORS:
                self._advance()
                tokens.append(JSToken(JSTokenType.PUNCTUATOR, ch, loc))
            else:
                raise ParseError(
                    message=f"Unexpected character in JavaScript source: '{ch}'",
                    filename=self.filename,
                    lineno=self.line,
                    col_offset=self.col,
                    text=self.source.splitlines()[self.line - 1] if self.line <= len(self.source.splitlines()) else ch,
                )

        loc_eof = SourceLocation(filename=self.filename, start_line=self.line, start_col=self.col)
        tokens.append(JSToken(JSTokenType.EOF, "", loc_eof))
        return tokens

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        if idx < self.length:
            return self.source[idx]
        return ""

    def _skip_whitespace_and_comments(self) -> None:
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch in (" ", "\t", "\r", "\n"):
                self._advance()
            # Single line comment //
            elif ch == "/" and self._peek(1) == "/":
                while self.pos < self.length and self.source[self.pos] != "\n":
                    self._advance()
            # Multi line comment /* ... */
            elif ch == "/" and self._peek(1) == "*":
                self._advance()  # /
                self._advance()  # *
                while self.pos < self.length and not (self.source[self.pos] == "*" and self._peek(1) == "/"):
                    self._advance()
                if self.pos < self.length:
                    self._advance()  # *
                    self._advance()  # /
            else:
                break

    def _read_string(self, quote: str, start_loc: SourceLocation) -> JSToken:
        self._advance()  # Skip opening quote
        chars: List[str] = []
        raw_chars: List[str] = [quote]

        while self.pos < self.length:
            ch = self._advance()
            raw_chars.append(ch)
            if ch == quote:
                break
            if ch == "\\":
                # Escape sequence
                if self.pos >= self.length:
                    break
                esc = self._advance()
                raw_chars.append(esc)
                if esc == "n":
                    chars.append("\n")
                elif esc == "r":
                    chars.append("\r")
                elif esc == "t":
                    chars.append("\t")
                elif esc == "0":
                    chars.append("\0")
                elif esc == "\\":
                    chars.append("\\")
                elif esc == quote:
                    chars.append(quote)
                elif esc == "x":
                    # Hex escape \xHH
                    hex_digits = self.source[self.pos:self.pos + 2]
                    if len(hex_digits) == 2 and all(c in "0123456789abcdefABCDEF" for c in hex_digits):
                        chars.append(chr(int(hex_digits, 16)))
                        raw_chars.extend(hex_digits)
                        self._advance()
                        self._advance()
                    else:
                        chars.append("x")
                elif esc == "u":
                    # Unicode escape \uHHHH
                    u_digits = self.source[self.pos:self.pos + 4]
                    if len(u_digits) == 4 and all(c in "0123456789abcdefABCDEF" for c in u_digits):
                        chars.append(chr(int(u_digits, 16)))
                        raw_chars.extend(u_digits)
                        for _ in range(4):
                            self._advance()
                    else:
                        chars.append("u")
                else:
                    chars.append(esc)
            else:
                chars.append(ch)

        val = "".join(chars)
        end_loc = SourceLocation(
            filename=self.filename,
            start_line=start_loc.start_line,
            start_col=start_loc.start_col,
            end_line=self.line,
            end_col=self.col,
        )
        return JSToken(JSTokenType.STRING, val, end_loc)

    def _read_number(self, start_loc: SourceLocation) -> JSToken:
        chars: List[str] = []
        # Hex literal 0x...
        if self.source[self.pos] == "0" and self._peek(1).lower() in ("x", "b", "o"):
            chars.append(self._advance())
            chars.append(self._advance())
            while self.pos < self.length and (self.source[self.pos].isalnum()):
                chars.append(self._advance())
        else:
            has_dot = False
            has_e = False
            while self.pos < self.length:
                ch = self.source[self.pos]
                if ch.isdigit():
                    chars.append(self._advance())
                elif ch == "." and not has_dot and not has_e:
                    has_dot = True
                    chars.append(self._advance())
                elif ch in ("e", "E") and not has_e:
                    has_e = True
                    chars.append(self._advance())
                    if self.pos < self.length and self.source[self.pos] in ("+", "-"):
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
        return JSToken(JSTokenType.NUMBER, num_str, end_loc)

    def _read_identifier_or_keyword(self, start_loc: SourceLocation) -> JSToken:
        chars: List[str] = []
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch.isalnum() or ch in ("_", "$"):
                chars.append(self._advance())
            else:
                break
        name = "".join(chars)
        ttype = JSTokenType.KEYWORD if name in JS_KEYWORDS else JSTokenType.IDENTIFIER
        end_loc = SourceLocation(
            filename=self.filename,
            start_line=start_loc.start_line,
            start_col=start_loc.start_col,
            end_line=self.line,
            end_col=self.col,
        )
        return JSToken(ttype, name, end_loc)

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
