"""Expression folding pass for JavaScript AST.

Per Section 12 of the Master Specification:
Evaluates and simplifies constant binary, unary, and string concatenation operations in JavaScript.
"""

from __future__ import annotations

from typing import Any, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.javascript.ast_nodes import (
    JSBinaryExpression,
    JSLiteral,
    JSNode,
    JSUnaryExpression,
)
from languages.javascript.printer import JSPrinter
from languages.javascript.transformer import JSTransformer


class JSExpressionFoldingTransformer(JSTransformer):
    """Evaluates constant operations in JavaScript AST."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_JSBinaryExpression(self, node: JSBinaryExpression) -> Any:
        self.generic_visit(node)
        if isinstance(node.left, JSLiteral) and isinstance(node.right, JSLiteral):
            folded = self._fold_binary(node.operator, node.left.value, node.right.value)
            if folded is not None:
                orig_src = JSPrinter.print_code(node)
                res_node = JSLiteral(value=folded, raw=repr(folded), location=node.location)
                self.tracker.record(
                    pass_name="JSExpressionFolding",
                    original=orig_src,
                    transformed=JSPrinter.print_code(res_node),
                    confidence=Confidence.certain(
                        f"Folded constant binary expression '{node.operator}'",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=node.location,
                )
                return res_node
        return node

    def visit_JSUnaryExpression(self, node: JSUnaryExpression) -> Any:
        self.generic_visit(node)
        if isinstance(node.argument, JSLiteral):
            val = node.argument.value
            folded = None
            if node.operator == "!":
                folded = not bool(val)
            elif node.operator == "-" and isinstance(val, (int, float)):
                folded = -val
            elif node.operator == "+" and isinstance(val, (int, float)):
                folded = +val
            elif node.operator == "~" and isinstance(val, int):
                folded = ~val
            elif node.operator == "typeof":
                if val is None:
                    folded = "object"
                elif isinstance(val, bool):
                    folded = "boolean"
                elif isinstance(val, (int, float)):
                    folded = "number"
                elif isinstance(val, str):
                    folded = "string"

            if folded is not None:
                orig_src = JSPrinter.print_code(node)
                res_node = JSLiteral(value=folded, raw=repr(folded), location=node.location)
                self.tracker.record(
                    pass_name="JSExpressionFolding",
                    original=orig_src,
                    transformed=JSPrinter.print_code(res_node),
                    confidence=Confidence.certain(
                        f"Folded constant unary expression '{node.operator}'",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=node.location,
                )
                return res_node

        return node

    def _fold_binary(self, op: str, v1: Any, v2: Any) -> Optional[Any]:
        try:
            # String concatenation (computed strings)
            if op == "+":
                if isinstance(v1, str) or isinstance(v2, str):
                    s1 = str(v1) if not isinstance(v1, bool) else ("true" if v1 else "false")
                    s2 = str(v2) if not isinstance(v2, bool) else ("true" if v2 else "false")
                    if len(s1) + len(s2) <= 65536:
                        return s1 + s2
                elif isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                    return v1 + v2

            if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                if op == "-":
                    return v1 - v2
                elif op == "*":
                    return v1 * v2
                elif op == "/" and v2 != 0:
                    return v1 / v2
                elif op == "%" and v2 != 0:
                    return v1 % v2

            if isinstance(v1, int) and isinstance(v2, int):
                if op == "^":
                    return v1 ^ v2
                elif op == "&":
                    return v1 & v2
                elif op == "|":
                    return v1 | v2
                elif op == "<<" and 0 <= v2 <= 32:
                    return v1 << v2
                elif op == ">>" and 0 <= v2 <= 32:
                    return v1 >> v2

            if op in ("===", "=="):
                return v1 == v2
            if op in ("!==", "!="):
                return v1 != v2
            if op == "<":
                return v1 < v2
            if op == "<=":
                return v1 <= v2
            if op == ">":
                return v1 > v2
            if op == ">=":
                return v1 >= v2

        except Exception:
            return None
        return None


class JSExpressionFoldingPass(Pass):
    """Pass that folds constant operations in JavaScript."""

    name = "JSExpressionFolding"
    description = "Evaluates constant arithmetic, logical, and string operations in JavaScript."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, JSNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = JSExpressionFoldingTransformer(trk, self.filename)
        return transformer.visit(target)
