"""Java source code generator / unparser.

Per Section 14 of the Master Specification (Phase 8: Java):
Generates clean, formatted Java source code from a Java AST.
"""

from __future__ import annotations

from typing import Any, List

from languages.java.ast_nodes import (
    JavaArrayAccess,
    JavaAssignmentExpression,
    JavaBinaryExpression,
    JavaBlock,
    JavaCastExpression,
    JavaClassDeclaration,
    JavaCompilationUnit,
    JavaExpression,
    JavaExpressionStatement,
    JavaFieldAccess,
    JavaFieldDeclaration,
    JavaIdentifier,
    JavaIfStatement,
    JavaImportDeclaration,
    JavaInterfaceDeclaration,
    JavaLiteral,
    JavaMethodCall,
    JavaMethodDeclaration,
    JavaNewArrayExpression,
    JavaNewClassExpression,
    JavaNode,
    JavaPackageDeclaration,
    JavaParameter,
    JavaReturnStatement,
    JavaStatement,
    JavaUnaryExpression,
    JavaVariableDeclarationStatement,
    JavaWhileStatement,
)


class JavaPrinter:
    """Pretty prints Java AST nodes back into Java source code."""

    def __init__(self, indent_size: int = 4) -> None:
        self.indent_size = indent_size
        self._indent_level = 0

    @classmethod
    def print_code(cls, node: JavaNode) -> str:
        """Convenience method to unparse an AST node to a Java source string."""
        printer = cls()
        return printer.unparse(node)

    def unparse(self, node: JavaNode) -> str:
        """Dispatch unparsing for any JavaNode."""
        method_name = f"_unparse_{type(node).__name__}"
        method = getattr(self, method_name, self._unparse_fallback)
        return method(node)

    def _indent(self) -> str:
        return " " * (self._indent_level * self.indent_size)

    def _unparse_fallback(self, node: JavaNode) -> str:
        return f"/* <unhandled Java: {type(node).__name__}> */"

    def _unparse_JavaCompilationUnit(self, node: JavaCompilationUnit) -> str:
        sections: List[str] = []
        if node.package:
            sections.append(self.unparse(node.package))
        if node.imports:
            imp_lines = [self.unparse(imp) for imp in node.imports]
            sections.append("\n".join(imp_lines))
        for t in node.types:
            sections.append(self.unparse(t))
        return "\n\n".join(sections)

    def _unparse_JavaPackageDeclaration(self, node: JavaPackageDeclaration) -> str:
        return f"package {node.name};"

    def _unparse_JavaImportDeclaration(self, node: JavaImportDeclaration) -> str:
        st = "static " if node.is_static else ""
        return f"import {st}{node.name};"

    def _unparse_JavaClassDeclaration(self, node: JavaClassDeclaration) -> str:
        mods = f"{' '.join(node.modifiers)} " if node.modifiers else ""
        sup = f" extends {node.super_class}" if node.super_class else ""
        ifaces = f" implements {', '.join(node.interfaces)}" if node.interfaces else ""

        header = f"{mods}class {node.name}{sup}{ifaces} {{"
        if not node.members:
            return f"{header}\n}}"

        self._indent_level += 1
        lines: List[str] = []
        for m in node.members:
            unp = self.unparse(m)
            lines.append(f"{self._indent()}{unp}")
        self._indent_level -= 1

        return f"{header}\n" + "\n\n".join(lines) + f"\n{self._indent()}}}"

    def _unparse_JavaInterfaceDeclaration(self, node: JavaInterfaceDeclaration) -> str:
        mods = f"{' '.join(node.modifiers)} " if node.modifiers else ""
        ext = f" extends {', '.join(node.extends)}" if node.extends else ""

        header = f"{mods}interface {node.name}{ext} {{"
        if not node.members:
            return f"{header}\n}}"

        self._indent_level += 1
        lines: List[str] = []
        for m in node.members:
            unp = self.unparse(m)
            lines.append(f"{self._indent()}{unp}")
        self._indent_level -= 1

        return f"{header}\n" + "\n\n".join(lines) + f"\n{self._indent()}}}"

    def _unparse_JavaFieldDeclaration(self, node: JavaFieldDeclaration) -> str:
        mods = f"{' '.join(node.modifiers)} " if node.modifiers else ""
        init_str = f" = {self.unparse(node.initializer)}" if node.initializer else ""
        return f"{mods}{node.type_name} {node.name}{init_str};"

    def _unparse_JavaParameter(self, node: JavaParameter) -> str:
        return f"{node.type_name} {node.name}"

    def _unparse_JavaMethodDeclaration(self, node: JavaMethodDeclaration) -> str:
        mods = f"{' '.join(node.modifiers)} " if node.modifiers else ""
        params_str = ", ".join(self.unparse(p) for p in node.parameters)
        ret = f"{node.return_type} " if node.return_type else ""
        header = f"{mods}{ret}{node.name}({params_str})"

        if node.body is None:
            return f"{header};"

        body_str = self.unparse(node.body)
        return f"{header} {body_str}"

    def _unparse_JavaBlock(self, node: JavaBlock) -> str:
        if not node.statements:
            return "{}"

        self._indent_level += 1
        lines: List[str] = []
        for s in node.statements:
            lines.append(f"{self._indent()}{self.unparse(s)}")
        self._indent_level -= 1

        return "{\n" + "\n".join(lines) + f"\n{self._indent()}}}"

    def _unparse_JavaVariableDeclarationStatement(self, node: JavaVariableDeclarationStatement) -> str:
        fin = "final " if node.is_final else ""
        init_str = f" = {self.unparse(node.initializer)}" if node.initializer else ""
        return f"{fin}{node.type_name} {node.name}{init_str};"

    def _unparse_JavaExpressionStatement(self, node: JavaExpressionStatement) -> str:
        return f"{self.unparse(node.expression)};"

    def _unparse_JavaIfStatement(self, node: JavaIfStatement) -> str:
        cond = self.unparse(node.condition)
        then_b = self.unparse(node.then_branch)
        if not isinstance(node.then_branch, JavaBlock):
            then_b = f"{{\n{self._indent()}    {then_b}\n{self._indent()}}}"

        res = f"if ({cond}) {then_b}"
        if node.else_branch:
            else_b = self.unparse(node.else_branch)
            if not isinstance(node.else_branch, (JavaBlock, JavaIfStatement)):
                else_b = f"{{\n{self._indent()}    {else_b}\n{self._indent()}}}"
            res += f" else {else_b}"
        return res

    def _unparse_JavaWhileStatement(self, node: JavaWhileStatement) -> str:
        cond = self.unparse(node.condition)
        body = self.unparse(node.body)
        if not isinstance(node.body, JavaBlock):
            body = f"{{\n{self._indent()}    {body}\n{self._indent()}}}"
        return f"while ({cond}) {body}"

    def _unparse_JavaReturnStatement(self, node: JavaReturnStatement) -> str:
        if node.expression:
            return f"return {self.unparse(node.expression)};"
        return "return;"

    def _unparse_JavaLiteral(self, node: JavaLiteral) -> str:
        if node.value is None:
            return "null"
        if isinstance(node.value, bool):
            return "true" if node.value else "false"
        if node.type_name == "char" and isinstance(node.value, str):
            escaped = node.value.replace("\\", "\\\\").replace("'", "\\'")
            return f"'{escaped}'"
        if isinstance(node.value, str):
            escaped = (
                node.value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
            )
            return f'"{escaped}"'
        if node.type_name == "long":
            return f"{node.value}L"
        return str(node.value)

    def _unparse_JavaIdentifier(self, node: JavaIdentifier) -> str:
        return node.name

    def _unparse_JavaBinaryExpression(self, node: JavaBinaryExpression) -> str:
        left = self.unparse(node.left)
        right = self.unparse(node.right)
        if isinstance(node.left, JavaBinaryExpression):
            left = f"({left})"
        if isinstance(node.right, JavaBinaryExpression):
            right = f"({right})"
        return f"{left} {node.operator} {right}"

    def _unparse_JavaUnaryExpression(self, node: JavaUnaryExpression) -> str:
        oprd = self.unparse(node.operand)
        if isinstance(node.operand, JavaBinaryExpression):
            oprd = f"({oprd})"
        if node.is_prefix:
            return f"{node.operator}{oprd}"
        return f"{oprd}{node.operator}"

    def _unparse_JavaMethodCall(self, node: JavaMethodCall) -> str:
        args_str = ", ".join(self.unparse(a) for a in node.arguments)
        if node.target:
            target_str = self.unparse(node.target)
            return f"{target_str}.{node.name}({args_str})"
        return f"{node.name}({args_str})"

    def _unparse_JavaFieldAccess(self, node: JavaFieldAccess) -> str:
        return f"{self.unparse(node.target)}.{node.name}"

    def _unparse_JavaNewClassExpression(self, node: JavaNewClassExpression) -> str:
        args_str = ", ".join(self.unparse(a) for a in node.arguments)
        return f"new {node.type_name}({args_str})"

    def _unparse_JavaNewArrayExpression(self, node: JavaNewArrayExpression) -> str:
        if node.initializers:
            inits = ", ".join(self.unparse(i) for i in node.initializers)
            return f"new {node.type_name}[] {{ {inits} }}"
        dims_str = "".join(f"[{self.unparse(d)}]" for d in node.dimensions)
        return f"new {node.type_name}{dims_str}"

    def _unparse_JavaArrayAccess(self, node: JavaArrayAccess) -> str:
        return f"{self.unparse(node.target)}[{self.unparse(node.index)}]"

    def _unparse_JavaAssignmentExpression(self, node: JavaAssignmentExpression) -> str:
        return f"{self.unparse(node.target)} {node.operator} {self.unparse(node.value)}"

    def _unparse_JavaCastExpression(self, node: JavaCastExpression) -> str:
        return f"({node.type_name}) {self.unparse(node.expression)}"
