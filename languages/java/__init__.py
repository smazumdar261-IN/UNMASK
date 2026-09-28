"""Java language support module.

Per Section 14 of the Master Specification (Phase 8: Java):
Registers Java source and bytecode decompiler handlers:
- JavaLanguage: Parses and unparses Java source files (.java)
- JavaBytecodeLanguage: Decompiles JVM class files (.class) and JAR archives (.jar) into Java AST
- Bidirectional Common IR conversion via JavaIRConverter
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from core.exceptions import ParseError
from languages import BaseLanguage, registry
from languages.java.ast_nodes import JavaCompilationUnit, JavaNode
from languages.java.bytecode import parse_class_or_jar
from languages.java.source_parser import JavaParser
from languages.java.source_printer import JavaPrinter


class JavaLanguage(BaseLanguage):
    """Java source code language handler."""

    name = "java"
    extensions = [".java"]

    def parse(self, source: str, filename: Optional[str] = None) -> JavaCompilationUnit:
        """Parse Java source string into a JavaCompilationUnit AST."""
        if filename and (filename.endswith(".class") or filename.endswith(".jar")):
            file_bytes = Path(filename).read_bytes()
            return parse_class_or_jar(file_bytes, filename=filename)

        try:
            parser = JavaParser(source, filename=filename)
            return parser.parse()
        except RecursionError as e:
            raise ParseError(f"Recursion limit exceeded while parsing Java: {e}", filename=filename) from e

    def unparse(self, ast_tree: Any) -> str:
        """Unparse Java AST back into formatted Java source."""
        if not isinstance(ast_tree, JavaNode):
            raise TypeError(f"Expected JavaNode, got {type(ast_tree).__name__}")
        return JavaPrinter.print_code(ast_tree)

    def to_ir(self, ast_tree: Any) -> Any:
        from languages.java.ir_converter import JavaIRConverter
        return JavaIRConverter.to_ir(ast_tree)

    def from_ir(self, ir_module: Any) -> Any:
        from languages.java.ir_converter import JavaIRConverter
        return JavaIRConverter.from_ir(ir_module)


class JavaBytecodeLanguage(BaseLanguage):
    """Java bytecode (.class / .jar) decompiler language handler."""

    name = "java-bytecode"
    extensions = [".class", ".jar"]

    def parse(self, source: Any, filename: Optional[str] = None) -> JavaCompilationUnit:
        """Decompile Java bytecode from file path or binary buffer."""
        if isinstance(source, (bytes, bytearray)):
            file_bytes = bytes(source)
        elif filename and Path(filename).exists():
            file_bytes = Path(filename).read_bytes()
        else:
            file_bytes = source.encode("latin-1")
        return parse_class_or_jar(file_bytes, filename=filename)

    def unparse(self, ast_tree: Any) -> str:
        """Unparse decompiled Java AST into formatted Java source."""
        if not isinstance(ast_tree, JavaNode):
            raise TypeError(f"Expected JavaNode, got {type(ast_tree).__name__}")
        return JavaPrinter.print_code(ast_tree)


# Register Java in the global LanguageRegistry
java_lang = JavaLanguage()
bytecode_lang = JavaBytecodeLanguage()
registry.register(java_lang)
registry.register(bytecode_lang)
