"""Expression folding pass for Java AST.

Per Section 14 of the Master Specification (Phase 8: Java):
Evaluates and simplifies constant binary, unary, and string concatenation operations in Java.
"""

from __future__ import annotations

from typing import Any, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.java.ast_nodes import (
    JavaBinaryExpression,
    JavaLiteral,
    JavaNode,
    JavaUnaryExpression,
)
from languages.java.source_printer import JavaPrinter
from languages.java.transformer import JavaTransformer


class JavaExpressionFoldingTransformer(JavaTransformer):
    """Evaluates constant operations in Java AST."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_JavaBinaryExpression(self, node: JavaBinaryExpression) -> Any:
        self.generic_visit(node)
        if isinstance(node.left, JavaLiteral) and isinstance(node.right, JavaLiteral):
            folded, tname = self._fold_binary(node.operator, node.left, node.right)
            if folded is not None:
                orig_src = JavaPrinter.print_code(node)
                res_node = JavaLiteral(value=folded, raw=repr(folded) if tname == "String" else str(folded), type_name=tname, location=node.location)
                self.tracker.record(
                    pass_name="JavaExpressionFolding",
                    original=orig_src,
                    transformed=JavaPrinter.print_code(res_node),
                    confidence=Confidence.certain(
                        f"Folded constant Java binary expression '{node.operator}'",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=node.location,
                )
                return res_node
        return node

    def visit_JavaUnaryExpression(self, node: JavaUnaryExpression) -> Any:
        self.generic_visit(node)
        if isinstance(node.operand, JavaLiteral):
            val = node.operand.value
            tname = node.operand.type_name
            folded = None
            if node.operator == "!" and isinstance(val, bool):
                folded = not val
                tname = "boolean"
            elif node.operator == "-" and isinstance(val, (int, float)):
                folded = -val
            elif node.operator == "+" and isinstance(val, (int, float)):
                folded = +val
            elif node.operator == "~" and isinstance(val, int):
                folded = ~val

            if folded is not None:
                orig_src = JavaPrinter.print_code(node)
                res_node = JavaLiteral(value=folded, raw=str(folded), type_name=tname, location=node.location)
                self.tracker.record(
                    pass_name="JavaExpressionFolding",
                    original=orig_src,
                    transformed=JavaPrinter.print_code(res_node),
                    confidence=Confidence.certain(
                        f"Folded constant Java unary expression '{node.operator}'",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=node.location,
                )
                return res_node
        return node

    def _fold_binary(self, op: str, left: JavaLiteral, right: JavaLiteral) -> tuple[Optional[Any], str]:
        v1 = left.value
        v2 = right.value

        try:
            # String concatenation
            if op == "+":
                if left.type_name == "String" or right.type_name == "String" or isinstance(v1, str) or isinstance(v2, str):
                    s1 = str(v1) if v1 is not None else "null"
                    s2 = str(v2) if v2 is not None else "null"
                    if len(s1) + len(s2) <= 65536:
                        return s1 + s2, "String"
                elif isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                    res_t = "double" if "double" in (left.type_name, right.type_name) else ("float" if "float" in (left.type_name, right.type_name) else ("long" if "long" in (left.type_name, right.type_name) else "int"))
                    return v1 + v2, res_t

            if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                res_t = "double" if "double" in (left.type_name, right.type_name) else ("float" if "float" in (left.type_name, right.type_name) else ("long" if "long" in (left.type_name, right.type_name) else "int"))
                if op == "-":
                    return v1 - v2, res_t
                elif op == "*":
                    return v1 * v2, res_t
                elif op == "/" and v2 != 0:
                    return (v1 // v2 if res_t in ("int", "long") else v1 / v2), res_t
                elif op == "%" and v2 != 0:
                    return v1 % v2, res_t

            if isinstance(v1, int) and isinstance(v2, int):
                res_t = "long" if "long" in (left.type_name, right.type_name) else "int"
                if op == "^":
                    return v1 ^ v2, res_t
                elif op == "&":
                    return v1 & v2, res_t
                elif op == "|":
                    return v1 | v2, res_t
                elif op == "<<" and 0 <= v2 <= 63:
                    return v1 << v2, res_t
                elif op == ">>" and 0 <= v2 <= 63:
                    return v1 >> v2, res_t

            if op == "==":
                return v1 == v2, "boolean"
            if op == "!=":
                return v1 != v2, "boolean"
            if op == "<" and isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                return v1 < v2, "boolean"
            if op == "<=" and isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                return v1 <= v2, "boolean"
            if op == ">" and isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                return v1 > v2, "boolean"
            if op == ">=" and isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                return v1 >= v2, "boolean"

            if isinstance(v1, bool) and isinstance(v2, bool):
                if op == "&&":
                    return v1 and v2, "boolean"
                if op == "||":
                    return v1 or v2, "boolean"

        except Exception:
            return None, ""
        return None, ""


class JavaExpressionFoldingPass(Pass):
    """Pass that evaluates constant operations in Java AST."""

    name = "JavaExpressionFolding"
    description = "Evaluates constant arithmetic, bitwise, boolean, and string operations in Java."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, JavaNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = JavaExpressionFoldingTransformer(trk, self.filename)
        return transformer.visit(target)
