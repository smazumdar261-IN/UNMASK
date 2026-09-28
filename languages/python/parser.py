"""Python parser and AST manipulation module.

Phase 1A: Python Static Engine Parser
Uses Python standard library `ast` (Python 3.11+).
Features:
- Syntax parsing with detailed error reporting
- Safe AST traversal helpers
- Source code regeneration (unparse)
- Node location extraction
"""

import ast
import logging
from typing import Any, Callable, Generator, List, Optional, Tuple

from core.exceptions import ParseError
from core.provenance import SourceLocation
from languages import BaseLanguage, registry

logger = logging.getLogger("universal_deobfuscator.languages.python")


class PythonParser:
    """Handles parsing, validation, traversal, and code regeneration for Python source."""

    @staticmethod
    def parse(source: str, filename: Optional[str] = None) -> ast.Module:
        """Parse Python source code into an AST Module.

        Raises:
            ParseError: If syntax is invalid.
        """
        try:
            return ast.parse(source, filename=filename or "<string>")
        except SyntaxError as e:
            logger.debug(f"Syntax error while parsing {filename}: {e}")
            raise ParseError(
                message=e.msg,
                filename=e.filename or filename,
                lineno=e.lineno,
                col_offset=e.offset,
                text=e.text,
            ) from e
        except (ValueError, RecursionError) as e:
            logger.debug(f"Parse error while parsing {filename}: {e}")
            raise ParseError(
                message=str(e),
                filename=filename,
            ) from e

    @staticmethod
    def unparse(tree: ast.AST) -> str:
        """Regenerate Python source code from an AST tree.

        Preserves semantic structure while outputting clean, formatted code.
        """
        try:
            return ast.unparse(tree)
        except Exception as e:
            logger.error(f"Failed to unparse AST: {e}", exc_info=True)
            raise

    @staticmethod
    def validate_syntax(source: str, filename: Optional[str] = None) -> Tuple[bool, Optional[ParseError]]:
        """Check if source code is syntactically valid without throwing."""
        try:
            ast.parse(source, filename=filename or "<string>")
            return True, None
        except SyntaxError as e:
            return False, ParseError(
                message=e.msg,
                filename=e.filename or filename,
                lineno=e.lineno,
                col_offset=e.offset,
                text=e.text,
            )
        except (ValueError, RecursionError) as e:
            return False, ParseError(
                message=str(e),
                filename=filename,
            )

    @staticmethod
    def walk(tree: ast.AST) -> Generator[ast.AST, None, None]:
        """Iterate over all nodes in the AST in pre-order."""
        return ast.walk(tree)

    @staticmethod
    def find_nodes(tree: ast.AST, node_type: type) -> List[ast.AST]:
        """Find all nodes in tree matching a specific AST node type."""
        return [node for node in ast.walk(tree) if isinstance(node, node_type)]

    @staticmethod
    def get_location(node: ast.AST, filename: Optional[str] = None) -> SourceLocation:
        """Extract source location span from an AST node if available."""
        lineno = getattr(node, "lineno", None)
        col_offset = getattr(node, "col_offset", None)
        end_lineno = getattr(node, "end_lineno", None)
        end_col_offset = getattr(node, "end_col_offset", None)

        return SourceLocation(
            filename=filename,
            start_line=lineno,
            start_col=col_offset,
            end_line=end_lineno,
            end_col=end_col_offset,
        )


class PythonLanguage(BaseLanguage):
    """Python language implementation."""

    name: str = "python"
    extensions: List[str] = [".py", ".pyw", ".pyi"]

    def __init__(self) -> None:
        self.parser = PythonParser()

    def parse(self, source: str, filename: Optional[str] = None) -> ast.Module:
        return self.parser.parse(source, filename=filename)

    def unparse(self, ast_tree: ast.AST) -> str:
        return self.parser.unparse(ast_tree)

    def to_ir(self, ast_tree: ast.Module) -> Any:
        from languages.python.ir_converter import PythonIRConverter
        return PythonIRConverter.to_ir(ast_tree)

    def from_ir(self, ir_module: Any) -> ast.Module:
        from languages.python.ir_converter import PythonIRConverter
        return PythonIRConverter.from_ir(ir_module)


# Register Python support into the global registry
python_lang = PythonLanguage()
registry.register(python_lang)
