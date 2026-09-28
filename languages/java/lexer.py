"""Java source code lexer.

Per Section 14 of the Master Specification (Phase 8: Java):
Tokenizes Java source code with exact line and column tracking:
- Keywords, identifiers, numeric literals (int, long, float, double, hex, binary)
- String literals and character literals with unicode and escape sequence decoding
- Multi-character punctuators (==, !=, <=, >=, &&, ||, >>, <<, >>>, etc.)
- Strips whitespace and comments (// and /* ... */)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional

from core.exceptions import ParseError
from core.provenance import SourceLocation


class JavaTokenType(Enum):
    KEYWORD = auto()
    IDENTIFIER = auto()
    NUMBER = auto()
    STRING = auto()
    CHAR = auto()
    PUNCTUATOR = auto()
    EOF = auto()


JAVA_KEYWORDS = {
    "abstract", "boolean", "break", "byte", "case", "catch", "char", "class",
    "const", "continue", "default", "do", "double", "else", "enum", "extends",
    "final", "finally", "float", "for", "goto", "if", "implements", "import",
    "instanceof", "int", "interface", "long", "native", "new", "package",
    "private", "protected", "public", "return", "short", "static", "strictfp",
    "super", "switch", "synchronized", "this", "throw", "throws", "transient",
    "try", "void", "volatile", "while", "true", "false", "null", "record",
}

MULTI_PUNCTUATORS = [
    ">>>=", ">>>", "===",
    "==", "!=", "<=", ">=", "&&", "||", "++", "--",
    "<<", ">>", "+=", "-=", "*=", "/=", "%=", "^=", "&=", "|=", "->", "::",
]

SINGLE_PUNCTUATORS = set("+-*/%^&|~!><=?:.,;()[]{}@")


@dataclass(frozen=True)
class JavaToken:
    type: JavaTokenType
    value: str
    location: SourceLocation

    def __repr__(self) -> str:
        return f"JavaToken({self.type.name}, {self.value!r} at {self.location})"


class JavaLexer:
    """Tokenizes Java source text into a list of JavaTokens."""

    def __init__(self, source: str, filename: Optional[str] = None) -> None:
        self.source = source
        self.filename = filename or "<java>"
        self.pos = 0
        self.line = 1
        self.col = 1
        self.length = len(source)

    def tokenize(self) -> List[JavaToken]:
        tokens: List[JavaToken] = []
        while self.pos < self.length:
            self._skip_whitespace_and_comments()
            if self.pos >= self.length:
                break

            loc = SourceLocation(filename=self.filename, start_line=self.line, start_col=self.col)
            ch = self.source[self.pos]

            # 1. String literal
            if ch == '"':
                tokens.append(self._read_string(loc))
            # 2. Character literal
            elif ch == "'":
                tokens.append(self._read_char(loc))
            # 3. Numeric literal
            elif ch.isdigit() or (ch == "." and self.pos + 1 < self.length and self.source[self.pos + 1].isdigit()):
                tokens.append(self._read_number(loc))
            # 4. Identifier or Keyword
            elif ch.isalpha() or ch in ("_", "$"):
                tokens.append(self._read_identifier_or_keyword(loc))
            # 5. Multi-character punctuator
            elif self._match_multi_punctuator():
                op = self._read_multi_punctuator()
                tokens.append(JavaToken(JavaTokenType.PUNCTUATOR, op, loc))
            # 6. Single punctuator
            elif ch in SINGLE_PUNCTUATORS:
                self._advance()
                tokens.append(JavaToken(JavaTokenType.PUNCTUATOR, ch, loc))
            else:
                raise ParseError(
                    message=f"Unexpected character in Java source: '{ch}'",
                    filename=self.filename,
                    lineno=self.line,
                    col_offset=self.col,
                )

        eof_loc = SourceLocation(filename=self.filename, start_line=self.line, start_col=self.col)
        tokens.append(JavaToken(JavaTokenType.EOF, "", eof_loc))
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

    def _skip_whitespace_and_comments(self) -> None:
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch in (" ", "\t", "\r", "\n"):
                self._advance()
            elif ch == "/" and self.pos + 1 < self.length and self.source[self.pos + 1] == "/":
                # Line comment
                while self.pos < self.length and self.source[self.pos] != "\n":
                    self._advance()
            elif ch == "/" and self.pos + 1 < self.length and self.source[self.pos + 1] == "*":
                # Block comment
                self._advance()
                self._advance()
                while self.pos + 1 < self.length:
                    if self.source[self.pos] == "*" and self.source[self.pos + 1] == "/":
                        self._advance()
                        self._advance()
                        break
                    self._advance()
            else:
                break

    def _read_string(self, start_loc: SourceLocation) -> JavaToken:
        self._advance()  # Skip opening "
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
                elif esc == "t":
                    chars.append("\t")
                elif esc == "r":
                    chars.append("\r")
                elif esc == "b":
                    chars.append("\b")
                elif esc == "f":
                    chars.append("\f")
                elif esc == '"':
                    chars.append('"')
                elif esc == "\\":
                    chars.append("\\")
                elif esc == "u" and self.pos + 4 <= self.length:
                    hex_code = self.source[self.pos : self.pos + 4]
                    try:
                        chars.append(chr(int(hex_code, 16)))
                        for _ in range(4):
                            self._advance()
                    except ValueError:
                        chars.append("u")
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
        return JavaToken(JavaTokenType.STRING, "".join(chars), end_loc)

    def _read_char(self, start_loc: SourceLocation) -> JavaToken:
        self._advance()  # Skip opening '
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
        return JavaToken(JavaTokenType.CHAR, "".join(chars), end_loc)

    def _read_number(self, start_loc: SourceLocation) -> JavaToken:
        chars: List[str] = []
        is_hex = False
        is_bin = False

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

        while self.pos < self.length:
            ch = self.source[self.pos]
            if is_hex and (ch.isdigit() or ch.lower() in "abcdef"):
                chars.append(self._advance())
            elif is_bin and ch in ("0", "1"):
                chars.append(self._advance())
            elif not is_hex and not is_bin and (ch.isdigit() or ch in (".", "e", "E", "_")):
                chars.append(self._advance())
            elif ch.lower() in ("l", "f", "d"):
                chars.append(self._advance())
                break
            else:
                break

        num_str = "".join(chars).replace("_", "")
        end_loc = SourceLocation(
            filename=self.filename,
            start_line=start_loc.start_line,
            start_col=start_loc.start_col,
            end_line=self.line,
            end_col=self.col,
        )
        return JavaToken(JavaTokenType.NUMBER, num_str, end_loc)

    def _read_identifier_or_keyword(self, start_loc: SourceLocation) -> JavaToken:
        chars: List[str] = []
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch.isalnum() or ch in ("_", "$"):
                chars.append(self._advance())
            else:
                break
        name = "".join(chars)
        ttype = JavaTokenType.KEYWORD if name in JAVA_KEYWORDS else JavaTokenType.IDENTIFIER
        end_loc = SourceLocation(
            filename=self.filename,
            start_line=start_loc.start_line,
            start_col=start_loc.start_col,
            end_line=self.line,
            end_col=self.col,
        )
        return JavaToken(ttype, name, end_loc)

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
