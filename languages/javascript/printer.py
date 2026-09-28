"""JavaScript source code generator / unparser.

Per Section 12 of the Master Specification:
Generates formatted JavaScript source code from an ESTree AST.
"""

from __future__ import annotations

from typing import Any, List

from languages.javascript.ast_nodes import (
    JSArrayExpression,
    JSArrowFunctionExpression,
    JSAssignmentExpression,
    JSBinaryExpression,
    JSBlockStatement,
    JSBreakStatement,
    JSCallExpression,
    JSConditionalExpression,
    JSContinueStatement,
    JSEmptyStatement,
    JSExpression,
    JSExpressionStatement,
    JSForStatement,
    JSFunctionDeclaration,
    JSFunctionExpression,
    JSIdentifier,
    JSIfStatement,
    JSLiteral,
    JSMemberExpression,
    JSNode,
    JSObjectExpression,
    JSProgram,
    JSProperty,
    JSReturnStatement,
    JSSequenceExpression,
    JSStatement,
    JSUnaryExpression,
    JSVariableDeclaration,
    JSVariableDeclarator,
    JSWhileStatement,
)


class JSPrinter:
    """Walks a JavaScript ESTree AST and generates formatted source code."""

    def __init__(self, indent_size: int = 4) -> None:
        self.indent_size = indent_size
        self._indent_level = 0

    @classmethod
    def print_code(cls, node: JSNode) -> str:
        """Convenience method to unparse a node to JavaScript string."""
        printer = cls()
        return printer.unparse(node)

    def unparse(self, node: JSNode) -> str:
        """Dispatch unparsing for any JSNode."""
        method_name = f"_unparse_{type(node).__name__}"
        method = getattr(self, method_name, self._unparse_fallback)
        return method(node)

    def _indent(self) -> str:
        return " " * (self._indent_level * self.indent_size)

    def _unparse_fallback(self, node: JSNode) -> str:
        return f"/* <unhandled: {type(node).__name__}> */"

    def _unparse_JSProgram(self, node: JSProgram) -> str:
        lines: List[str] = []
        for stmt in node.body:
            lines.append(self.unparse(stmt))
        return "\n".join(lines)

    def _unparse_JSBlockStatement(self, node: JSBlockStatement) -> str:
        if not node.body:
            return "{}"
        self._indent_level += 1
        inner_lines: List[str] = []
        for s in node.body:
            inner_lines.append(f"{self._indent()}{self.unparse(s)}")
        self._indent_level -= 1
        return "{\n" + "\n".join(inner_lines) + f"\n{self._indent()}" + "}"

    def _unparse_JSExpressionStatement(self, node: JSExpressionStatement) -> str:
        return f"{self.unparse(node.expression)};"

    def _unparse_JSEmptyStatement(self, node: JSEmptyStatement) -> str:
        return ";"

    def _unparse_JSBreakStatement(self, node: JSBreakStatement) -> str:
        return "break;"

    def _unparse_JSContinueStatement(self, node: JSContinueStatement) -> str:
        return "continue;"

    def _unparse_JSVariableDeclaration(self, node: JSVariableDeclaration) -> str:
        decl_strs: List[str] = []
        for decl in node.declarations:
            if decl.init:
                decl_strs.append(f"{self.unparse(decl.id)} = {self.unparse(decl.init)}")
            else:
                decl_strs.append(self.unparse(decl.id))
        return f"{node.kind} {', '.join(decl_strs)};"

    def _unparse_JSFunctionDeclaration(self, node: JSFunctionDeclaration) -> str:
        fn_name = f" {self.unparse(node.id)}" if node.id else ""
        params = ", ".join(self.unparse(p) for p in node.params)
        body = self.unparse(node.body)
        return f"function{fn_name}({params}) {body}"

    def _unparse_JSFunctionExpression(self, node: JSFunctionExpression) -> str:
        fn_name = f" {self.unparse(node.id)}" if node.id else ""
        params = ", ".join(self.unparse(p) for p in node.params)
        body = self.unparse(node.body)
        return f"function{fn_name}({params}) {body}"

    def _unparse_JSArrowFunctionExpression(self, node: JSArrowFunctionExpression) -> str:
        params = ", ".join(self.unparse(p) for p in node.params)
        body = self.unparse(node.body)
        return f"({params}) => {body}"

    def _unparse_JSReturnStatement(self, node: JSReturnStatement) -> str:
        if node.argument:
            return f"return {self.unparse(node.argument)};"
        return "return;"

    def _unparse_JSIfStatement(self, node: JSIfStatement) -> str:
        test = self.unparse(node.test)
        consequent = self.unparse(node.consequent)
        if not isinstance(node.consequent, JSBlockStatement):
            consequent = f"{{\n{self._indent()}    {consequent}\n{self._indent()}}}"
        res = f"if ({test}) {consequent}"
        if node.alternate:
            alternate = self.unparse(node.alternate)
            if not isinstance(node.alternate, (JSBlockStatement, JSIfStatement)):
                alternate = f"{{\n{self._indent()}    {alternate}\n{self._indent()}}}"
            res += f" else {alternate}"
        return res

    def _unparse_JSWhileStatement(self, node: JSWhileStatement) -> str:
        test = self.unparse(node.test)
        body = self.unparse(node.body)
        if not isinstance(node.body, JSBlockStatement):
            body = f"{{\n{self._indent()}    {body}\n{self._indent()}}}"
        return f"while ({test}) {body}"

    def _unparse_JSForStatement(self, node: JSForStatement) -> str:
        init_str = self.unparse(node.init) if node.init else ""
        if init_str.endswith(";"):
            init_str = init_str[:-1]
        test_str = self.unparse(node.test) if node.test else ""
        update_str = self.unparse(node.update) if node.update else ""
        body_str = self.unparse(node.body)
        if not isinstance(node.body, JSBlockStatement):
            body_str = f"{{\n{self._indent()}    {body_str}\n{self._indent()}}}"
        return f"for ({init_str}; {test_str}; {update_str}) {body_str}"

    def _unparse_JSIdentifier(self, node: JSIdentifier) -> str:
        return node.name

    def _unparse_JSLiteral(self, node: JSLiteral) -> str:
        if node.value is None:
            return "null"
        if isinstance(node.value, bool):
            return "true" if node.value else "false"
        if isinstance(node.value, str):
            # Escape single quotes and backslashes for clean JS representation
            escaped = (
                node.value.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
            )
            return f"'{escaped}'"
        return str(node.value)

    def _unparse_JSBinaryExpression(self, node: JSBinaryExpression) -> str:
        left = self.unparse(node.left)
        right = self.unparse(node.right)
        if isinstance(node.left, (JSBinaryExpression, JSConditionalExpression)):
            left = f"({left})"
        if isinstance(node.right, (JSBinaryExpression, JSConditionalExpression)):
            right = f"({right})"
        return f"{left} {node.operator} {right}"

    def _unparse_JSUnaryExpression(self, node: JSUnaryExpression) -> str:
        arg = self.unparse(node.argument)
        if isinstance(node.argument, JSBinaryExpression):
            arg = f"({arg})"
        if node.operator in ("typeof", "void"):
            return f"{node.operator} {arg}"
        return f"{node.operator}{arg}"

    def _unparse_JSCallExpression(self, node: JSCallExpression) -> str:
        callee = self.unparse(node.callee)
        if isinstance(node.callee, (JSFunctionExpression, JSArrowFunctionExpression)):
            callee = f"({callee})"
        args = ", ".join(self.unparse(a) for a in node.arguments)
        return f"{callee}({args})"

    def _unparse_JSMemberExpression(self, node: JSMemberExpression) -> str:
        obj = self.unparse(node.object)
        if isinstance(node.object, (JSFunctionExpression, JSBinaryExpression, JSLiteral)):
            obj = f"({obj})"
        if node.computed:
            return f"{obj}[{self.unparse(node.property)}]"
        return f"{obj}.{self.unparse(node.property)}"

    def _unparse_JSArrayExpression(self, node: JSArrayExpression) -> str:
        return f"[{', '.join(self.unparse(el) for el in node.elements)}]"

    def _unparse_JSObjectExpression(self, node: JSObjectExpression) -> str:
        if not node.properties:
            return "{}"
        props = ", ".join(f"{self.unparse(p.key)}: {self.unparse(p.value)}" for p in node.properties)
        return f"{{ {props} }}"

    def _unparse_JSAssignmentExpression(self, node: JSAssignmentExpression) -> str:
        return f"{self.unparse(node.left)} {node.operator} {self.unparse(node.right)}"

    def _unparse_JSConditionalExpression(self, node: JSConditionalExpression) -> str:
        test = self.unparse(node.test)
        consequent = self.unparse(node.consequent)
        alternate = self.unparse(node.alternate)
        return f"{test} ? {consequent} : {alternate}"

    def _unparse_JSSequenceExpression(self, node: JSSequenceExpression) -> str:
        return f"({', '.join(self.unparse(e) for e in node.expressions)})"
