"""Base AST NodeVisitor and NodeTransformer for Java AST nodes.

Per Section 14 of the Master Specification:
Provides recursive tree-walking and node-replacement infrastructure for Java AST passes.
"""

from __future__ import annotations

from typing import Any, List
from languages.java.ast_nodes import JavaNode


class JavaTransformer:
    """Base class for Java AST transformations."""

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

    def generic_visit(self, node: JavaNode) -> JavaNode:
        """Default visitor that walks all fields and visits child nodes."""
        for field_name, value in list(vars(node).items()):
            if field_name == "location":
                continue
            if isinstance(value, JavaNode):
                setattr(node, field_name, self.visit(value))
            elif isinstance(value, list) and value and isinstance(value[0], JavaNode):
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
