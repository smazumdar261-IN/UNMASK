"""Go source code pretty printer / code generator.

Per Section 15 of the Master Specification (Phase 9: Go):
Unparses Go AST nodes back into idiomatic, formatted Go source code.
"""

from __future__ import annotations

from typing import Any, List, Optional

from languages.go.ast_nodes import (
    GoAssignmentStatement,
    GoBinaryExpression,
    GoBlock,
    GoBranchStatement,
    GoCallExpression,
    GoCaseClause,
    GoCompositeLiteral,
    GoConstSpec,
    GoDecl,
    GoDeferStatement,
    GoExpression,
    GoExpressionStatement,
    GoField,
    GoFile,
    GoForStatement,
    GoFunctionDecl,
    GoGoStatement,
    GoIdentifier,
    GoIfStatement,
    GoImportSpec,
    GoIndexExpression,
    GoKeyValueExpression,
    GoLiteral,
    GoNode,
    GoRangeStatement,
    GoReturnStatement,
    GoSelectorExpression,
    GoSliceExpression,
    GoStatement,
    GoSwitchStatement,
    GoTypeAssertExpression,
    GoTypeDecl,
    GoUnaryExpression,
    GoVarSpec,
)


class GoPrinter:
    """Pretty printer that unparses Go AST nodes to formatted Go source code."""

    def __init__(self, indent_str: str = "    ") -> None:
        self.indent_str = indent_str
        self._indent_level = 0

    @classmethod
    def print_code(cls, node: GoNode) -> str:
        """Class method for convenient one-off printing."""
        return cls().unparse(node)

    def _indent(self) -> str:
        return self.indent_str * self._indent_level

    def unparse(self, node: Optional[GoNode]) -> str:
        """Dispatches node to its corresponding unparse handler."""
        if node is None:
            return ""

        handler_name = f"_unparse_{type(node).__name__}"
        handler = getattr(self, handler_name, None)
        if handler:
            return handler(node)

        # Fallback for unknown node types
        return f"/* <unknown {type(node).__name__}> */"

    def _unparse_GoFile(self, node: GoFile) -> str:
        sections: List[str] = [f"package {node.package}"]

        if node.imports:
            if len(node.imports) == 1:
                sections.append(f"import {self._unparse_GoImportSpec(node.imports[0])}")
            else:
                imp_lines = [f"{self.indent_str}{self._unparse_GoImportSpec(imp)}" for imp in node.imports]
                sections.append("import (\n" + "\n".join(imp_lines) + "\n)")

        for decl in node.decls:
            sections.append(self.unparse(decl))

        return "\n\n".join(sections) + "\n"

    def _unparse_GoImportSpec(self, node: GoImportSpec) -> str:
        if node.name:
            return f'{node.name} "{node.path}"'
        return f'"{node.path}"'

    def _unparse_GoConstSpec(self, node: GoConstSpec) -> str:
        names_str = ", ".join(node.names)
        type_str = f" {node.type_name}" if node.type_name else ""
        if node.values:
            vals_str = ", ".join(self.unparse(v) for v in node.values)
            return f"const {names_str}{type_str} = {vals_str}"
        return f"const {names_str}{type_str}"

    def _unparse_GoVarSpec(self, node: GoVarSpec) -> str:
        names_str = ", ".join(node.names)
        type_str = f" {node.type_name}" if node.type_name else ""
        if node.values:
            vals_str = ", ".join(self.unparse(v) for v in node.values)
            return f"var {names_str}{type_str} = {vals_str}"
        return f"var {names_str}{type_str}"

    def _unparse_GoTypeDecl(self, node: GoTypeDecl) -> str:
        alias_str = " = " if node.is_alias else " "
        return f"type {node.name}{alias_str}{node.type_def}"

    def _unparse_GoFunctionDecl(self, node: GoFunctionDecl) -> str:
        recv_str = f"({self._unparse_GoField(node.receiver)}) " if node.receiver else ""
        params_str = ", ".join(self._unparse_GoField(p) for p in node.params)

        results_str = ""
        if node.results:
            if len(node.results) == 1 and not node.results[0].name:
                results_str = f" {node.results[0].type_name}"
            else:
                results_str = f" ({', '.join(self._unparse_GoField(r) for r in node.results)})"

        header = f"func {recv_str}{node.name}({params_str}){results_str}"
        if node.body is None:
            return header

        return f"{header} {self.unparse(node.body)}"

    def _unparse_GoField(self, node: GoField) -> str:
        if node.name:
            return f"{node.name} {node.type_name}"
        return node.type_name

    def _unparse_GoBlock(self, node: GoBlock) -> str:
        if not node.statements:
            return "{}"

        self._indent_level += 1
        lines: List[str] = []
        for s in node.statements:
            lines.append(f"{self._indent()}{self.unparse(s)}")
        self._indent_level -= 1

        return "{\n" + "\n".join(lines) + f"\n{self._indent()}}}"

    def _unparse_GoExpressionStatement(self, node: GoExpressionStatement) -> str:
        return self.unparse(node.expression)

    def _unparse_GoAssignmentStatement(self, node: GoAssignmentStatement) -> str:
        left_str = ", ".join(self.unparse(e) for e in node.left)
        right_str = ", ".join(self.unparse(e) for e in node.right)
        return f"{left_str} {node.operator} {right_str}"

    def _unparse_GoIfStatement(self, node: GoIfStatement) -> str:
        init_str = f"{self.unparse(node.init)}; " if node.init else ""
        cond_str = self.unparse(node.condition)
        body_str = self.unparse(node.body)

        res = f"if {init_str}{cond_str} {body_str}"
        if node.else_branch:
            else_str = self.unparse(node.else_branch)
            res += f" else {else_str}"
        return res

    def _unparse_GoForStatement(self, node: GoForStatement) -> str:
        body_str = self.unparse(node.body)

        # Infinite loop
        if node.init is None and node.condition is None and node.post is None:
            return f"for {body_str}"

        # While-style loop
        if node.init is None and node.post is None and node.condition:
            return f"for {self.unparse(node.condition)} {body_str}"

        init_str = self.unparse(node.init) if node.init else ""
        cond_str = f" {self.unparse(node.condition)}" if node.condition else ""
        post_str = f" {self.unparse(node.post)}" if node.post else ""
        return f"for {init_str};{cond_str};{post_str} {body_str}"

    def _unparse_GoRangeStatement(self, node: GoRangeStatement) -> str:
        body_str = self.unparse(node.body)
        target = self.unparse(node.expression)

        if node.key and node.value:
            k = self.unparse(node.key)
            v = self.unparse(node.value)
            return f"for {k}, {v} {node.operator} range {target} {body_str}"
        elif node.key:
            k = self.unparse(node.key)
            return f"for {k} {node.operator} range {target} {body_str}"
        return f"for range {target} {body_str}"

    def _unparse_GoReturnStatement(self, node: GoReturnStatement) -> str:
        if node.results:
            return f"return {', '.join(self.unparse(r) for r in node.results)}"
        return "return"

    def _unparse_GoBranchStatement(self, node: GoBranchStatement) -> str:
        if node.label:
            return f"{node.token} {node.label}"
        return node.token

    def _unparse_GoDeferStatement(self, node: GoDeferStatement) -> str:
        return f"defer {self.unparse(node.call)}"

    def _unparse_GoGoStatement(self, node: GoGoStatement) -> str:
        return f"go {self.unparse(node.call)}"

    def _unparse_GoSwitchStatement(self, node: GoSwitchStatement) -> str:
        init_str = f"{self.unparse(node.init)}; " if node.init else ""
        tag_str = f" {self.unparse(node.tag)}" if node.tag else ""
        header = f"switch {init_str}{tag_str}".strip()

        if not node.cases:
            return f"{header} {{}}"

        self._indent_level += 1
        case_lines: List[str] = []
        for c in node.cases:
            if c.cases:
                c_head = f"case {', '.join(self.unparse(e) for e in c.cases)}:"
            else:
                c_head = "default:"
            case_lines.append(f"{self._indent()}{c_head}")

            self._indent_level += 1
            for s in c.body:
                case_lines.append(f"{self._indent()}{self.unparse(s)}")
            self._indent_level -= 1

        self._indent_level -= 1
        return f"{header} {{\n" + "\n".join(case_lines) + f"\n{self._indent()}}}"

    def _unparse_GoLiteral(self, node: GoLiteral) -> str:
        if node.value is None:
            return "nil"
        if isinstance(node.value, bool):
            return "true" if node.value else "false"
        if node.type_name == "rune":
            return f"'{node.value}'"
        if isinstance(node.value, str):
            escaped = (
                node.value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
            )
            return f'"{escaped}"'
        return str(node.value)

    def _unparse_GoIdentifier(self, node: GoIdentifier) -> str:
        return node.name

    def _unparse_GoBinaryExpression(self, node: GoBinaryExpression) -> str:
        left = self.unparse(node.left)
        right = self.unparse(node.right)
        if isinstance(node.left, GoBinaryExpression):
            left = f"({left})"
        if isinstance(node.right, GoBinaryExpression):
            right = f"({right})"
        return f"{left} {node.operator} {right}"

    def _unparse_GoUnaryExpression(self, node: GoUnaryExpression) -> str:
        operand = self.unparse(node.operand)
        if isinstance(node.operand, GoBinaryExpression):
            operand = f"({operand})"
        if node.operator in ("++", "--"):
            return f"{operand}{node.operator}"
        return f"{node.operator}{operand}"

    def _unparse_GoCallExpression(self, node: GoCallExpression) -> str:
        callee = self.unparse(node.callee)
        args_str = ", ".join(self.unparse(a) for a in node.args)
        if node.has_ellipsis:
            args_str += "..."
        return f"{callee}({args_str})"

    def _unparse_GoSelectorExpression(self, node: GoSelectorExpression) -> str:
        expr = self.unparse(node.expression)
        return f"{expr}.{node.name}"

    def _unparse_GoIndexExpression(self, node: GoIndexExpression) -> str:
        expr = self.unparse(node.expression)
        idx = self.unparse(node.index)
        return f"{expr}[{idx}]"

    def _unparse_GoSliceExpression(self, node: GoSliceExpression) -> str:
        expr = self.unparse(node.expression)
        low = self.unparse(node.low) if node.low else ""
        high = self.unparse(node.high) if node.high else ""
        max_str = f":{self.unparse(node.max)}" if node.max else ""
        return f"{expr}[{low}:{high}{max_str}]"

    def _unparse_GoTypeAssertExpression(self, node: GoTypeAssertExpression) -> str:
        expr = self.unparse(node.expression)
        return f"{expr}.({node.type_name})"

    def _unparse_GoCompositeLiteral(self, node: GoCompositeLiteral) -> str:
        elems = ", ".join(self.unparse(e) for e in node.elements)
        return f"{node.type_name}{{{elems}}}"

    def _unparse_GoKeyValueExpression(self, node: GoKeyValueExpression) -> str:
        return f"{self.unparse(node.key)}: {self.unparse(node.value)}"
