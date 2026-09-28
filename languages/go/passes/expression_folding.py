"""Expression folding pass for Go AST.

Per Section 15 of the Master Specification (Phase 9: Go):
Folds constant binary and unary expressions:
- Arithmetic: +, -, *, /, %
- Bitwise: &, |, ^ (XOR), &^ (bit clear), <<, >>
- Boolean: &&, ||, !
- Comparison: ==, !=, <, <=, >, >=
- String concatenation: "a" + "b"
"""

from __future__ import annotations

from typing import Any, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.go.ast_nodes import (
    GoBinaryExpression,
    GoLiteral,
    GoNode,
    GoUnaryExpression,
)
from languages.go.source_printer import GoPrinter
from languages.go.transformer import GoTransformer


class GoExpressionFoldingTransformer(GoTransformer):
    """Folds static constant expressions in Go AST."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_GoBinaryExpression(self, node: GoBinaryExpression) -> Any:
        self.generic_visit(node)
        left = node.left
        right = node.right

        if isinstance(left, GoLiteral) and isinstance(right, GoLiteral):
            op = node.operator

            # 1. String concatenation
            if isinstance(left.value, str) and isinstance(right.value, str) and op == "+":
                res_str = left.value + right.value
                return self._record_folded_binary(node, res_str, repr(res_str), "string")

            # 2. Arithmetic and bitwise operations on numbers
            if isinstance(left.value, (int, float)) and isinstance(right.value, (int, float)):
                res_val = self._fold_numeric_binary(left.value, op, right.value)
                if res_val is not None:
                    tname = "float64" if isinstance(res_val, float) else "int"
                    return self._record_folded_binary(node, res_val, str(res_val), tname)

            # 3. Boolean logic
            if isinstance(left.value, bool) and isinstance(right.value, bool):
                if op == "&&":
                    res_val = left.value and right.value
                    return self._record_folded_binary(node, res_val, "true" if res_val else "false", "bool")
                if op == "||":
                    res_val = left.value or right.value
                    return self._record_folded_binary(node, res_val, "true" if res_val else "false", "bool")

            # 4. Equality and comparisons
            if op in ("==", "!="):
                res_val = (left.value == right.value) if op == "==" else (left.value != right.value)
                return self._record_folded_binary(node, res_val, "true" if res_val else "false", "bool")

        return node

    def visit_GoUnaryExpression(self, node: GoUnaryExpression) -> Any:
        self.generic_visit(node)
        operand = node.operand

        if isinstance(operand, GoLiteral):
            op = node.operator

            # Logical not
            if op == "!" and isinstance(operand.value, bool):
                res_val = not operand.value
                return self._record_folded_unary(node, res_val, "true" if res_val else "false", "bool")

            # Negation
            if op == "-" and isinstance(operand.value, (int, float)):
                res_val = -operand.value
                tname = "float64" if isinstance(res_val, float) else "int"
                return self._record_folded_unary(node, res_val, str(res_val), tname)

            # Bitwise NOT in Go is ^
            if op == "^" and isinstance(operand.value, int):
                res_val = ~operand.value
                return self._record_folded_unary(node, res_val, str(res_val), "int")

        return node

    def _fold_numeric_binary(self, l_val: Any, op: str, r_val: Any) -> Optional[Any]:
        try:
            if op == "+":
                return l_val + r_val
            if op == "-":
                return l_val - r_val
            if op == "*":
                return l_val * r_val
            if op == "/" and r_val != 0:
                if isinstance(l_val, int) and isinstance(r_val, int):
                    return l_val // r_val
                return l_val / r_val
            if op == "%" and r_val != 0 and isinstance(l_val, int) and isinstance(r_val, int):
                return l_val % r_val

            # Bitwise operators (integers only)
            if isinstance(l_val, int) and isinstance(r_val, int):
                if op == "&":
                    return l_val & r_val
                if op == "|":
                    return l_val | r_val
                if op == "^":
                    return l_val ^ r_val
                if op == "&^":  # Bit clear: l & ~r
                    return l_val & (~r_val)
                if op == "<<" and 0 <= r_val < 64:
                    return l_val << r_val
                if op == ">>" and 0 <= r_val < 64:
                    return l_val >> r_val

            # Comparisons
            if op == "<":
                return l_val < r_val
            if op == "<=":
                return l_val <= r_val
            if op == ">":
                return l_val > r_val
            if op == ">=":
                return l_val >= r_val
        except Exception:
            return None
        return None

    def _record_folded_binary(self, node: GoBinaryExpression, val: Any, raw: str, tname: str) -> GoLiteral:
        orig_src = GoPrinter.print_code(node)
        loc = node.location
        res_node = GoLiteral(value=val, raw=raw, type_name=tname, location=loc)
        self.tracker.record(
            pass_name="GoExpressionFolding",
            original=orig_src,
            transformed=GoPrinter.print_code(res_node),
            confidence=Confidence.certain(
                f"Folded constant Go binary expression '{node.operator}'",
                TransformationCategory.SIMPLIFIED,
            ),
            location=loc,
        )
        return res_node

    def _record_folded_unary(self, node: GoUnaryExpression, val: Any, raw: str, tname: str) -> GoLiteral:
        orig_src = GoPrinter.print_code(node)
        loc = node.location
        res_node = GoLiteral(value=val, raw=raw, type_name=tname, location=loc)
        self.tracker.record(
            pass_name="GoExpressionFolding",
            original=orig_src,
            transformed=GoPrinter.print_code(res_node),
            confidence=Confidence.certain(
                f"Folded constant Go unary expression '{node.operator}'",
                TransformationCategory.SIMPLIFIED,
            ),
            location=loc,
        )
        return res_node


class GoExpressionFoldingPass(Pass):
    """Pass that folds constant expressions in Go AST."""

    name = "GoExpressionFolding"
    description = "Evaluates constant arithmetic, bitwise, and string operations in Go."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, GoNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = GoExpressionFoldingTransformer(trk, self.filename)
        return transformer.visit(target)
