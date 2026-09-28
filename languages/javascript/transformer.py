"""Base AST NodeVisitor and NodeTransformer for JavaScript AST nodes.

Per Section 12 of the Master Specification:
Provides recursive tree-walking and node-replacement infrastructure for JavaScript AST passes.
"""

from __future__ import annotations

from typing import Any, List, Optional
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


class JSTransformer:
    """Base class for JavaScript AST transformations."""

    def visit(self, node: Any) -> Any:
        """Visit a node and dispatch to visit_<Type> method."""
        if node is None:
            return None
        if isinstance(node, list):
            new_list = []
            for item in node:
                visited = self.visit(item)
                if visited is not None:
                    if isinstance(visited, list):
                        new_list.extend(visited)
                    else:
                        new_list.append(visited)
            return new_list

        method_name = f"visit_{type(node).__name__}"
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: JSNode) -> JSNode:
        """Default visitor that walks all fields and visits child nodes."""
        for field_name, value in list(vars(node).items()):
            if field_name == "location":
                continue
            if isinstance(value, JSNode):
                setattr(node, field_name, self.visit(value))
            elif isinstance(value, list) and value and isinstance(value[0], JSNode):
                new_list = []
                for child in value:
                    res = self.visit(child)
                    if res is not None:
                        if isinstance(res, list):
                            new_list.extend(res)
                        else:
                            new_list.append(res)
                setattr(node, field_name, new_list)
        return node
