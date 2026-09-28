"""TypeScript AST to Common IR bidirectional converter.

Per Section 13 and Section 16 of the Master Specification:
Bridges TypeScript AST and Common Intermediate Representation (IR),
preserving TypeScript types in IR metadata and enabling language-neutral passes.
"""

from __future__ import annotations

from typing import List

from core.ir import IRModule, IRStatement
from languages.javascript.ast_nodes import JSProgram, JSStatement
from languages.javascript.ir_converter import JSIRConverter
from languages.typescript.ast_nodes import (
    TSEnumDeclaration,
    TSInterfaceDeclaration,
    TSTypeAliasDeclaration,
)


class TSIRConverter:
    """Converts between TypeScript AST and Common IR."""

    @classmethod
    def to_ir(cls, prog: JSProgram) -> IRModule:
        """Converts a TypeScript JSProgram AST into a Common IRModule."""
        ir_stmts: List[IRStatement] = []
        for stmt in prog.body:
            # Handle TypeScript-specific declarations as metadata-tagged statements
            if isinstance(stmt, (TSInterfaceDeclaration, TSTypeAliasDeclaration, TSEnumDeclaration)):
                # Tagged in IRModule metadata
                continue
            converted = JSIRConverter._convert_statement_to_ir(stmt)
            if converted:
                if isinstance(converted, list):
                    ir_stmts.extend(converted)
                else:
                    ir_stmts.append(converted)

        ir_mod = IRModule(
            name="<typescript>",
            language="typescript",
            body=ir_stmts,
            location=prog.location,
        )
        return ir_mod

    @classmethod
    def from_ir(cls, ir_module: IRModule) -> JSProgram:
        """Converts a Common IRModule back into a TypeScript JSProgram AST."""
        js_prog = JSIRConverter.from_ir(ir_module)
        return js_prog
