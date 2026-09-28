"""TypeScript AST code generator / unparser.

Per Section 13 of the Master Specification (Phase 7: TypeScript):
Generates TypeScript source code or JavaScript output:
- Distinguishes TypeScript source from JavaScript output via `target_js=True/False`.
- Preserves interfaces, type aliases, enums, generics, and decorators in TypeScript mode.
- Strips type annotations, interfaces, and type aliases when targeting JavaScript.
"""

from __future__ import annotations

from typing import Any, List, Optional

from languages.javascript.ast_nodes import (
    JSBlockStatement,
    JSFunctionDeclaration,
    JSNode,
    JSProgram,
    JSVariableDeclaration,
)
from languages.javascript.printer import JSPrinter
from languages.typescript.ast_nodes import (
    TSAsExpression,
    TSDecorator,
    TSEnumDeclaration,
    TSEnumMember,
    TSInterfaceDeclaration,
    TSMethodSignature,
    TSParameter,
    TSPropertySignature,
    TSTypeAliasDeclaration,
    TSTypeAnnotation,
    TSTypeParameter,
    TSTypeParameterDeclaration,
)


class TSPrinter(JSPrinter):
    """Generates TypeScript or JavaScript source code from TypeScript AST."""

    def __init__(self, indent_size: int = 4, target_js: bool = False) -> None:
        super().__init__(indent_size=indent_size)
        self.target_js = target_js

    @classmethod
    def print_code(cls, node: JSNode, target_js: bool = False) -> str:
        """Unparses AST node to formatted code (TS by default, or JS when target_js=True)."""
        printer = cls(target_js=target_js)
        return printer.unparse(node)

    def _unparse_JSProgram(self, node: JSProgram) -> str:
        lines: List[str] = []
        for stmt in node.body:
            unparsed = self.unparse(stmt)
            if unparsed.strip():
                lines.append(unparsed)
        return "\n".join(lines)

    def _unparse_TSInterfaceDeclaration(self, node: TSInterfaceDeclaration) -> str:
        if self.target_js:
            return ""  # Interfaces do not exist in JavaScript output

        type_params = ""
        if node.type_parameters and node.type_parameters.params:
            type_params = f"<{', '.join(p.name for p in node.type_parameters.params)}>"

        extends = ""
        if node.extends:
            extends = f" extends {', '.join(self.unparse(e) for e in node.extends)}"

        if not node.body:
            return f"interface {self.unparse(node.id)}{type_params}{extends} {{}}"

        self._indent_level += 1
        inner_lines: List[str] = []
        for member in node.body:
            inner_lines.append(f"{self._indent()}{self.unparse(member)}")
        self._indent_level -= 1

        return (
            f"interface {self.unparse(node.id)}{type_params}{extends} {{\n"
            + "\n".join(inner_lines)
            + f"\n{self._indent()}}}"
        )

    def _unparse_TSPropertySignature(self, node: TSPropertySignature) -> str:
        ro = "readonly " if node.readonly else ""
        opt = "?" if node.optional else ""
        type_str = f": {node.type_annotation.raw}" if node.type_annotation else ""
        return f"{ro}{self.unparse(node.key)}{opt}{type_str};"

    def _unparse_TSMethodSignature(self, node: TSMethodSignature) -> str:
        params_str = ", ".join(self.unparse(p) for p in node.params)
        ret_str = f": {node.return_type.raw}" if node.return_type else ""
        return f"{self.unparse(node.key)}({params_str}){ret_str};"

    def _unparse_TSTypeAliasDeclaration(self, node: TSTypeAliasDeclaration) -> str:
        if self.target_js:
            return ""  # Type aliases do not exist in JavaScript output

        type_params = ""
        if node.type_parameters and node.type_parameters.params:
            type_params = f"<{', '.join(p.name for p in node.type_parameters.params)}>"

        type_str = node.type_annotation.raw if node.type_annotation else "any"
        return f"type {self.unparse(node.id)}{type_params} = {type_str};"

    def _unparse_TSEnumDeclaration(self, node: TSEnumDeclaration) -> str:
        if self.target_js:
            # Emit clean JavaScript dictionary object for enum
            props = []
            for mem in node.members:
                val = self.unparse(mem.initializer) if mem.initializer else f"'{mem.id.name}'"
                props.append(f"{mem.id.name}: {val}")
            return f"var {self.unparse(node.id)} = {{ {', '.join(props)} }};"

        prefix = "const enum " if node.is_const else "enum "
        if not node.members:
            return f"{prefix}{self.unparse(node.id)} {{}}"

        self._indent_level += 1
        lines = []
        for mem in node.members:
            mem_str = self.unparse(mem.id)
            if mem.initializer:
                mem_str += f" = {self.unparse(mem.initializer)}"
            lines.append(f"{self._indent()}{mem_str},")
        self._indent_level -= 1

        return f"{prefix}{self.unparse(node.id)} {{\n" + "\n".join(lines) + f"\n{self._indent()}}}"

    def _unparse_TSAsExpression(self, node: TSAsExpression) -> str:
        expr_str = self.unparse(node.expression)
        if self.target_js:
            return expr_str
        type_str = node.type_annotation.raw if node.type_annotation else "any"
        return f"{expr_str} as {type_str}"

    def _unparse_TSDecorator(self, node: TSDecorator) -> str:
        return f"@{self.unparse(node.expression)}"

    def _unparse_TSParameter(self, node: TSParameter) -> str:
        res = self.unparse(node.id)
        if not self.target_js:
            if node.optional:
                res += "?"
            if node.type_annotation:
                res += f": {node.type_annotation.raw}"
        if node.default:
            res += f" = {self.unparse(node.default)}"
        return res

    def _unparse_JSVariableDeclaration(self, node: JSVariableDeclaration) -> str:
        decl_strs: List[str] = []
        for decl in node.declarations:
            decl_id = self.unparse(decl.id)
            if not self.target_js and getattr(decl, "type_annotation", None):
                decl_id += f": {decl.type_annotation.raw}"
            if decl.init:
                decl_strs.append(f"{decl_id} = {self.unparse(decl.init)}")
            else:
                decl_strs.append(decl_id)
        return f"{node.kind} {', '.join(decl_strs)};"

    def _unparse_JSFunctionDeclaration(self, node: JSFunctionDeclaration) -> str:
        decorators_str = ""
        if getattr(node, "decorators", None):
            for dec in node.decorators:
                decorators_str += f"{self.unparse(dec)}\n{self._indent()}"

        fn_name = f" {self.unparse(node.id)}" if node.id else ""
        type_params = ""
        if not self.target_js and getattr(node, "type_parameters", None):
            type_params = f"<{', '.join(p.name for p in node.type_parameters.params)}>"

        params = ", ".join(self.unparse(p) for p in node.params)
        ret_type = ""
        if not self.target_js and getattr(node, "return_type", None):
            ret_type = f": {node.return_type.raw}"

        body = self.unparse(node.body)
        return f"{decorators_str}function{fn_name}{type_params}({params}){ret_type} {body}"
