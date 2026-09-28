"""Language-independent string reconstruction pass for Common Intermediate Representation.

Per Section 16 & Phase 10:
Reconstructs obfuscated strings, byte sequences, char-code calls, and joined slices in Common IR.
"""

from __future__ import annotations

from typing import Any, List, Optional

from core.confidence import Confidence, TransformationCategory
from core.ir import (
    IRCall,
    IRConstant,
    IRExpression,
    IRListLiteral,
    IRMemberAccess,
    IRString,
    IRTransformer,
    IRVariable,
    format_ir,
)
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation


class IRStringReconstructionTransformer(IRTransformer):
    """Reconstructs strings from character arrays, byte literals, and joins in Common IR."""

    def __init__(self, tracker: Optional[ProvenanceTracker] = None) -> None:
        self.tracker = tracker

    def visit_IRCall(self, node: IRCall) -> IRExpression:
        self.generic_visit(node)

        callee_name = self._resolve_callee_name(node.callee)

        # Pattern 1: String.fromCharCode(65, 66, 67) or chr(...)
        if callee_name in ("String.fromCharCode", "fromCharCode", "chr"):
            if all(isinstance(a, IRConstant) and isinstance(a.value, int) for a in node.args):
                try:
                    reconstructed = "".join(chr(a.value) for a in node.args)
                    return self._record(node, reconstructed, "Evaluated character code sequence into string")
                except Exception:
                    pass

        # Pattern 2: "".join(["a", "b", "c"]) or [..].join("") or strings.Join([]string{...}, sep)
        if callee_name in ("join", "strings.Join", "String.join") or (
            isinstance(node.callee, IRMemberAccess) and node.callee.member == "join"
        ):
            sep = ""
            elements: Optional[List[IRExpression]] = None

            if isinstance(node.callee, IRMemberAccess) and node.callee.member == "join":
                target = node.callee.target
                if isinstance(target, IRListLiteral):
                    elements = target.elements
                    if len(node.args) >= 1 and isinstance(node.args[0], IRConstant):
                        sep = str(node.args[0].value) if node.args[0].value is not None else ""
                elif isinstance(target, IRCall) and isinstance(target.callee, IRMemberAccess) and target.callee.member == "reverse":
                    # target is .reverse()
                    rev_target = target.callee.target
                    if isinstance(rev_target, IRCall) and isinstance(rev_target.callee, IRMemberAccess) and rev_target.callee.member == "split":
                        split_str_node = rev_target.callee.target
                        if isinstance(split_str_node, IRConstant) and isinstance(split_str_node.value, str):
                            reversed_str = split_str_node.value[::-1]
                            return self._record(node, reversed_str, "Evaluated string reversal (.split.reverse.join)")

            if callee_name == "strings.Join" and len(node.args) == 2:
                if isinstance(node.args[0], IRListLiteral) and isinstance(node.args[1], IRConstant):
                    elements = node.args[0].elements
                    sep = str(node.args[1].value)
            elif len(node.args) == 1 and isinstance(node.args[0], IRListLiteral):
                elements = node.args[0].elements

            if elements is not None and all(isinstance(e, IRConstant) and isinstance(e.value, str) for e in elements):
                reconstructed = sep.join(str(e.value) for e in elements)
                return self._record(node, reconstructed, "Joined static string array elements")

        # Pattern 3: bytes([104, 101, ...]).decode() or string([]byte{...})
        if callee_name in ("bytes.decode", "decode", "string"):
            if len(node.args) == 1:
                arg = node.args[0]
                if isinstance(arg, IRListLiteral) and all(
                    isinstance(e, IRConstant) and isinstance(e.value, int) for e in arg.elements
                ):
                    try:
                        byte_vals = bytes(int(e.value) for e in arg.elements)
                        decoded = byte_vals.decode("utf-8")
                        return self._record(node, decoded, "Decoded byte array literal into UTF-8 string")
                    except Exception:
                        pass

        return node

    def _resolve_callee_name(self, callee: IRExpression) -> str:
        if isinstance(callee, IRVariable):
            return callee.name
        if isinstance(callee, IRMemberAccess):
            prefix = self._resolve_callee_name(callee.target)
            return f"{prefix}.{callee.member}" if prefix else callee.member
        return ""

    def _record(self, original_node: IRExpression, result_str: str, rationale: str) -> IRString:
        orig_text = format_ir(original_node)
        loc = original_node.location or SourceLocation()
        replacement = IRString(value=result_str, location=loc)

        if self.tracker:
            self.tracker.record(
                pass_name="IRStringReconstruction",
                original=orig_text,
                transformed=format_ir(replacement),
                confidence=Confidence.certain(
                    reason=f"{rationale}: {result_str!r}",
                    category=TransformationCategory.RECOVERED,
                ),
                location=loc,
            )
        return replacement


class IRStringReconstruction(Pass):
    """Language-independent string reconstruction pass on Common IR."""

    name = "IRStringReconstruction"
    description = "Reconstructs obfuscated strings and byte sequences in Common IR"

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        transformer = IRStringReconstructionTransformer(tracker=tracker)
        return transformer.visit(target)
