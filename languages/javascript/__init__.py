"""JavaScript language support module.

Per Section 12 of the Master Specification (Phase 6: JavaScript):
Registers JavaScript parser, AST printer, and deobfuscation passes.
"""

from __future__ import annotations

from typing import Any, Optional

from core.exceptions import ParseError
from languages import BaseLanguage, registry
from languages.javascript.ast_nodes import JSNode, JSProgram
from languages.javascript.parser import JSParser
from languages.javascript.printer import JSPrinter


class JavaScriptLanguage(BaseLanguage):
    """JavaScript (ECMAScript) language handler."""

    name = "javascript"
    extensions = [".js", ".mjs", ".cjs"]

    def parse(self, source: str, filename: Optional[str] = None) -> JSProgram:
        """Parse JavaScript source string into an ESTree JSProgram AST."""
        try:
            parser = JSParser(source, filename=filename)
            return parser.parse()
        except RecursionError as e:
            raise ParseError(f"Recursion limit exceeded while parsing JavaScript: {e}", filename=filename) from e

    def unparse(self, ast_tree: Any) -> str:
        """Unparse JavaScript AST back into formatted JavaScript source."""
        if not isinstance(ast_tree, JSNode):
            raise TypeError(f"Expected JSNode, got {type(ast_tree).__name__}")
        return JSPrinter.print_code(ast_tree)

    def to_ir(self, ast_tree: Any) -> Any:
        from languages.javascript.ir_converter import JSIRConverter
        return JSIRConverter.to_ir(ast_tree)

    def from_ir(self, ir_module: Any) -> Any:
        from languages.javascript.ir_converter import JSIRConverter
        return JSIRConverter.from_ir(ir_module)


# Register JavaScript in the global LanguageRegistry
js_language = JavaScriptLanguage()
registry.register(js_language)
