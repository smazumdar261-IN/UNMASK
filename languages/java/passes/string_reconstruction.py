"""Java string reconstruction and pattern recovery pass.

Per Section 14 of the Master Specification (Phase 8: Java):
Reconstructs strings from character arrays, byte arrays, and StringBuilder chains:
- new String(new byte[] { 72, 101, 108, 108, 111 }) -> "Hello"
- new String(new char[] { 'H', 'e', 'l', 'l', 'o' }) -> "Hello"
- new StringBuilder().append("a").append("b").toString() -> "ab"
"""

from __future__ import annotations

from typing import Any, List, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.java.ast_nodes import (
    JavaLiteral,
    JavaMethodCall,
    JavaNewArrayExpression,
    JavaNewClassExpression,
    JavaNode,
)
from languages.java.source_printer import JavaPrinter
from languages.java.transformer import JavaTransformer


class JavaStringReconstructionTransformer(JavaTransformer):
    """Reconstructs strings from byte/char arrays and StringBuilder chains."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_JavaNewClassExpression(self, node: JavaNewClassExpression) -> Any:
        self.generic_visit(node)

        # 1. new String(new byte[] { ... }) or new String(new char[] { ... })
        if node.type_name == "String" and len(node.arguments) == 1:
            arg = node.arguments[0]
            if isinstance(arg, JavaNewArrayExpression) and arg.initializers:
                reconstructed = self._try_reconstruct_from_array(arg)
                if reconstructed is not None:
                    orig_src = JavaPrinter.print_code(node)
                    res_node = JavaLiteral(
                        value=reconstructed,
                        raw=repr(reconstructed),
                        type_name="String",
                        location=node.location,
                    )
                    self.tracker.record(
                        pass_name="JavaStringReconstruction",
                        original=orig_src,
                        transformed=JavaPrinter.print_code(res_node),
                        confidence=Confidence.certain(
                            f"Reconstructed string from {arg.type_name} array allocation",
                            TransformationCategory.RECOVERED,
                        ),
                        location=node.location,
                    )
                    return res_node

        return node

    def visit_JavaMethodCall(self, node: JavaMethodCall) -> Any:
        self.generic_visit(node)

        # 2. StringBuilder.append(...)...toString()
        if node.name == "toString":
            appends = self._collect_string_builder_appends(node.target)
            if appends is not None:
                joined = "".join(appends)
                orig_src = JavaPrinter.print_code(node)
                res_node = JavaLiteral(
                    value=joined,
                    raw=repr(joined),
                    type_name="String",
                    location=node.location,
                )
                self.tracker.record(
                    pass_name="JavaStringReconstruction",
                    original=orig_src,
                    transformed=JavaPrinter.print_code(res_node),
                    confidence=Confidence.certain(
                        "Reconstructed string from StringBuilder chain",
                        TransformationCategory.RECOVERED,
                    ),
                    location=node.location,
                )
                return res_node

        return node

    def _try_reconstruct_from_array(self, arr: JavaNewArrayExpression) -> Optional[str]:
        chars: List[str] = []
        for el in arr.initializers:
            if isinstance(el, JavaLiteral):
                if isinstance(el.value, int) and 0 <= el.value <= 0x10FFFF:
                    chars.append(chr(el.value))
                elif isinstance(el.value, str) and len(el.value) == 1:
                    chars.append(el.value)
                else:
                    return None
            else:
                return None
        return "".join(chars)

    def _collect_string_builder_appends(self, target: Optional[JavaNode]) -> Optional[List[str]]:
        """Walks an append chain: new StringBuilder().append(A).append(B)."""
        appends: List[str] = []
        curr: Optional[JavaNode] = target

        while isinstance(curr, JavaMethodCall) and curr.name == "append":
            if len(curr.arguments) == 1 and isinstance(curr.arguments[0], JavaLiteral):
                appends.append(str(curr.arguments[0].value))
                curr = curr.target
            else:
                return None

        # Base must be new StringBuilder()
        if isinstance(curr, JavaNewClassExpression) and curr.type_name in ("StringBuilder", "StringBuffer"):
            if not curr.arguments:
                return appends[::-1]
            if len(curr.arguments) == 1 and isinstance(curr.arguments[0], JavaLiteral):
                return [str(curr.arguments[0].value)] + appends[::-1]

        return None


class JavaStringReconstructionPass(Pass):
    """Pass that reconstructs strings from character/byte arrays and StringBuilder."""

    name = "JavaStringReconstruction"
    description = "Reconstructs strings from byte/char array allocations and StringBuilder chains in Java."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, JavaNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = JavaStringReconstructionTransformer(trk, self.filename)
        return transformer.visit(target)
