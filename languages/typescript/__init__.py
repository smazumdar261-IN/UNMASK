"""TypeScript language support module.

Per Section 13 of the Master Specification (Phase 7: TypeScript):
Registers TypeScript parser, AST printer, and deobfuscation integration:
- Extensions: .ts, .tsx, .mts, .cts
- Preserves interfaces, types, enums, generics, decorators, type annotations
- Supports distinguishing TypeScript source from JavaScript output
"""

from __future__ import annotations

from typing import Any, Optional

from core.exceptions import ParseError
from languages import BaseLanguage, registry
from languages.javascript.ast_nodes import JSNode, JSProgram
from languages.typescript.parser import TSParser
from languages.typescript.printer import TSPrinter


class TypeScriptLanguage(BaseLanguage):
    """TypeScript language handler."""

    name = "typescript"
    extensions = [".ts", ".tsx", ".mts", ".cts"]

    def parse(self, source: str, filename: Optional[str] = None) -> JSProgram:
        """Parse TypeScript source string into an AST."""
        try:
            parser = TSParser(source, filename=filename)
            return parser.parse()
        except RecursionError as e:
            raise ParseError(f"Recursion limit exceeded while parsing TypeScript: {e}", filename=filename) from e

    def unparse(self, ast_tree: Any, target_js: bool = False) -> str:
        """Unparse TypeScript AST back into formatted TypeScript or JavaScript source."""
        if not isinstance(ast_tree, JSNode):
            raise TypeError(f"Expected JSNode, got {type(ast_tree).__name__}")
        return TSPrinter.print_code(ast_tree, target_js=target_js)

    def to_ir(self, ast_tree: Any) -> Any:
        from languages.typescript.ir_converter import TSIRConverter
        return TSIRConverter.to_ir(ast_tree)

    def from_ir(self, ir_module: Any) -> Any:
        from languages.typescript.ir_converter import TSIRConverter
        return TSIRConverter.from_ir(ir_module)


# Register TypeScript in the global LanguageRegistry
ts_language = TypeScriptLanguage()
registry.register(ts_language)
