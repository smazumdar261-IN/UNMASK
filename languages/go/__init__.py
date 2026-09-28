"""Go language support package.

Per Section 15 of the Master Specification (Phase 9: Go):
Registers Go language support (.go) into the universal deobfuscator registry.
"""

from __future__ import annotations

from typing import Any, Optional

from core.exceptions import ParseError
from languages import BaseLanguage, registry
from languages.go.ast_nodes import GoFile, GoNode
from languages.go.source_parser import GoParser
from languages.go.source_printer import GoPrinter


class GoLanguage(BaseLanguage):
    """Go source code language handler."""

    name = "go"
    extensions = [".go"]

    def parse(self, source: str, filename: Optional[str] = None) -> GoFile:
        """Parse Go source code into a GoFile AST."""
        try:
            return GoParser(source, filename=filename).parse()
        except RecursionError as e:
            raise ParseError(f"Recursion limit exceeded while parsing Go: {e}", filename=filename) from e

    def unparse(self, ast_tree: Any) -> str:
        """Unparse Go AST into formatted Go source code."""
        if not isinstance(ast_tree, GoNode):
            raise TypeError(f"Expected GoNode, got {type(ast_tree).__name__}")
        return GoPrinter.print_code(ast_tree)

    def to_ir(self, ast_tree: Any) -> Any:
        from languages.go.ir_converter import GoIRConverter
        return GoIRConverter.to_ir(ast_tree)

    def from_ir(self, ir_module: Any) -> Any:
        from languages.go.ir_converter import GoIRConverter
        return GoIRConverter.from_ir(ir_module)


# Register Go in the global LanguageRegistry
go_lang = GoLanguage()
registry.register(go_lang)
