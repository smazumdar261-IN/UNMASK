"""Language-independent expression folding pass for Common Intermediate Representation.

Per Section 16 & Phase 10:
Folds constant binary operations (arithmetic, bitwise, boolean, comparison, string concat)
and unary operations directly on Common IR.
"""

from __future__ import annotations

import operator
from typing import Any, Optional

from core.confidence import Confidence, TransformationCategory
from core.ir import (
    IRBinaryOperation,
    IRConstant,
    IRExpression,
    IRNode,
    IRString,
    IRTransformer,
    IRUnaryOperation,
    format_ir,
)
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation


_BINARY_OPS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "**": operator.pow,
    "&": operator.and_,
    "|": operator.or_,
    "^": operator.xor,
    "<<": operator.lshift,
    ">>": operator.rshift,
    "==": operator.eq,
    "===": operator.eq,
    "!=": operator.ne,
    "!==": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


class IRExpressionFoldingTransformer(IRTransformer):
    """Folds constant operations in an IR tree."""

    def __init__(self, tracker: Optional[ProvenanceTracker] = None) -> None:
        self.tracker = tracker

    def visit_IRBinaryOperation(self, node: IRBinaryOperation) -> IRExpression:
        self.generic_visit(node)

        left = node.left
        right = node.right

        if isinstance(left, IRConstant) and isinstance(right, IRConstant):
            lv = left.value
            rv = right.value
            op = node.op

            # Short-circuit logical ops
            if op == "and":
                res = rv if bool(lv) else lv
                return self._record(node, res)
            elif op == "or":
                res = lv if bool(lv) else rv
                return self._record(node, res)

            # Standard binary operators
            if op in _BINARY_OPS:
                func = _BINARY_OPS[op]
                try:
                    # Prevent unbounded memory exhaustion on huge powers/shifts
                    if op == "**" and (isinstance(lv, int) and isinstance(rv, int) and (rv > 1000 or rv < 0)):
                        return node
                    if op in ("<<", ">>") and (isinstance(rv, int) and (rv > 256 or rv < 0)):
                        return node
                    if op in ("/", "//", "%") and rv == 0:
                        return node

                    res = func(lv, rv)
                    return self._record(node, res)
                except Exception:
                    return node

        return node

    def visit_IRUnaryOperation(self, node: IRUnaryOperation) -> IRExpression:
        self.generic_visit(node)

        operand = node.operand
        if isinstance(operand, IRConstant):
            val = operand.value
            op = node.op

            try:
                if op == "-":
                    res = -val
                elif op == "+":
                    res = +val
                elif op in ("not", "!"):
                    res = not bool(val)
                elif op == "~":
                    res = ~val
                else:
                    return node

                return self._record(node, res)
            except Exception:
                return node

        return node

    def _record(self, original_node: IRNode, result_value: Any) -> IRConstant:
        orig_text = format_ir(original_node)
        loc = original_node.location or SourceLocation()

        if isinstance(result_value, str):
            folded = IRString(value=result_value, location=loc)
        else:
            folded = IRConstant(value=result_value, location=loc)

        if self.tracker:
            self.tracker.record(
                pass_name="IRExpressionFolding",
                original=orig_text,
                transformed=format_ir(folded),
                confidence=Confidence.certain(
                    reason=f"Statically folded expression: {orig_text} -> {result_value}",
                    category=TransformationCategory.SIMPLIFIED,
                ),
                location=loc,
            )
        return folded


class IRExpressionFolding(Pass):
    """Language-independent expression folding pass."""

    name = "IRExpressionFolding"
    description = "Folds constant operations in Common IR"

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        transformer = IRExpressionFoldingTransformer(tracker=tracker)
        return transformer.visit(target)
