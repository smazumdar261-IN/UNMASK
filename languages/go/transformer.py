"""AST Transformer for Go.

Per Section 15 of the Master Specification (Phase 9: Go):
Provides a recursive visitor/transformer base class for Go AST nodes.
Allows passes to inspect, modify, or replace AST nodes while preserving tree integrity.
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


class GoTransformer:
    """Base class for AST transformation on Go nodes."""

    def visit(self, node: Any) -> Any:
        """Dispatches visit to the specialized method for the node's type."""
        if node is None:
            return None

        if isinstance(node, list):
            new_list = []
            for item in node:
                res = self.visit(item)
                if res is not None:
                    if isinstance(res, list):
                        new_list.extend(res)
                    else:
                        new_list.append(res)
            return new_list

        if not isinstance(node, GoNode):
            return node

        method_name = f"visit_{type(node).__name__}"
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: GoNode) -> GoNode:
        """Visits all GoNode and list attributes of the given node."""
        for field_name, value in vars(node).items():
            if field_name == "location":
                continue

            if isinstance(value, GoNode):
                setattr(node, field_name, self.visit(value))
            elif isinstance(value, list):
                new_items = []
                for item in value:
                    res = self.visit(item)
                    if res is not None:
                        if isinstance(res, list):
                            new_items.extend(res)
                        else:
                            new_items.append(res)
                setattr(node, field_name, new_items)

        return node

    def visit_GoFile(self, node: GoFile) -> Any:
        return self.generic_visit(node)

    def visit_GoConstSpec(self, node: GoConstSpec) -> Any:
        return self.generic_visit(node)

    def visit_GoVarSpec(self, node: GoVarSpec) -> Any:
        return self.generic_visit(node)

    def visit_GoFunctionDecl(self, node: GoFunctionDecl) -> Any:
        return self.generic_visit(node)

    def visit_GoBlock(self, node: GoBlock) -> Any:
        return self.generic_visit(node)

    def visit_GoExpressionStatement(self, node: GoExpressionStatement) -> Any:
        return self.generic_visit(node)

    def visit_GoAssignmentStatement(self, node: GoAssignmentStatement) -> Any:
        return self.generic_visit(node)

    def visit_GoIfStatement(self, node: GoIfStatement) -> Any:
        return self.generic_visit(node)

    def visit_GoForStatement(self, node: GoForStatement) -> Any:
        return self.generic_visit(node)

    def visit_GoRangeStatement(self, node: GoRangeStatement) -> Any:
        return self.generic_visit(node)

    def visit_GoReturnStatement(self, node: GoReturnStatement) -> Any:
        return self.generic_visit(node)

    def visit_GoBranchStatement(self, node: GoBranchStatement) -> Any:
        return self.generic_visit(node)

    def visit_GoDeferStatement(self, node: GoDeferStatement) -> Any:
        return self.generic_visit(node)

    def visit_GoGoStatement(self, node: GoGoStatement) -> Any:
        return self.generic_visit(node)

    def visit_GoSwitchStatement(self, node: GoSwitchStatement) -> Any:
        return self.generic_visit(node)

    def visit_GoCaseClause(self, node: GoCaseClause) -> Any:
        return self.generic_visit(node)

    def visit_GoLiteral(self, node: GoLiteral) -> Any:
        return node

    def visit_GoIdentifier(self, node: GoIdentifier) -> Any:
        return node

    def visit_GoBinaryExpression(self, node: GoBinaryExpression) -> Any:
        return self.generic_visit(node)

    def visit_GoUnaryExpression(self, node: GoUnaryExpression) -> Any:
        return self.generic_visit(node)

    def visit_GoCallExpression(self, node: GoCallExpression) -> Any:
        return self.generic_visit(node)

    def visit_GoSelectorExpression(self, node: GoSelectorExpression) -> Any:
        return self.generic_visit(node)

    def visit_GoIndexExpression(self, node: GoIndexExpression) -> Any:
        return self.generic_visit(node)

    def visit_GoSliceExpression(self, node: GoSliceExpression) -> Any:
        return self.generic_visit(node)

    def visit_GoTypeAssertExpression(self, node: GoTypeAssertExpression) -> Any:
        return self.generic_visit(node)

    def visit_GoCompositeLiteral(self, node: GoCompositeLiteral) -> Any:
        return self.generic_visit(node)

    def visit_GoKeyValueExpression(self, node: GoKeyValueExpression) -> Any:
        return self.generic_visit(node)
