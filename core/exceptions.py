"""Custom exceptions for the Universal Deobfuscator framework."""

from typing import Any, Optional


class DeobfuscatorError(Exception):
    """Base exception for all universal deobfuscator errors."""

    def __init__(self, message: str, details: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class ParseError(DeobfuscatorError):
    """Raised when source code cannot be parsed."""

    def __init__(
        self,
        message: str,
        filename: Optional[str] = None,
        lineno: Optional[int] = None,
        col_offset: Optional[int] = None,
        text: Optional[str] = None,
        location: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        if location is not None:
            filename = filename or getattr(location, "file", None)
            lineno = lineno if lineno is not None else getattr(location, "line", None)
            col_offset = col_offset if col_offset is not None else getattr(location, "column", None)
        self.filename = filename
        self.lineno = lineno
        self.col_offset = col_offset
        self.text = text

    def __str__(self) -> str:
        loc = []
        if self.filename:
            loc.append(f"file: {self.filename}")
        if self.lineno is not None:
            loc.append(f"line {self.lineno}")
        if self.col_offset is not None:
            loc.append(f"col {self.col_offset}")
        loc_str = f" ({', '.join(loc)})" if loc else ""
        text_str = f"\n  --> {self.text.strip()}" if self.text else ""
        return f"ParseError{loc_str}: {self.message}{text_str}"


class UnsupportedLanguageError(DeobfuscatorError):
    """Raised when an unsupported language is requested or encountered."""


class SemanticPreservationError(DeobfuscatorError):
    """Raised when a transformation threatens to alter program semantics."""


class AnalysisError(DeobfuscatorError):
    """Raised when an analysis pass encounters an unrecoverable failure."""
