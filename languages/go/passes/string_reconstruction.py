"""String reconstruction pass for Go AST.

Per Section 15 of the Master Specification (Phase 9: Go):
Reconstructs obfuscated strings from byte/rune slices and join operations:
- string([]byte{ ... })
- string([]rune{ ... })
- string('A') or string(65)
- strings.Join([]string{ ... }, separator)
"""

from __future__ import annotations

from typing import Any, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.go.ast_nodes import (
    GoCallExpression,
    GoCompositeLiteral,
    GoIdentifier,
    GoLiteral,
    GoNode,
    GoSelectorExpression,
)
from languages.go.source_printer import GoPrinter
from languages.go.transformer import GoTransformer


class GoStringReconstructionTransformer(GoTransformer):
    """Reconstructs strings from slices and join calls."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_GoCallExpression(self, node: GoCallExpression) -> Any:
        self.generic_visit(node)

        # 1. string([]byte{...}) or string([]rune{...}) or string('A') or string(65)
        if isinstance(node.callee, GoIdentifier) and node.callee.name == "string" and len(node.args) == 1:
            arg = node.args[0]

            # string([]byte{...}) or string([]rune{...})
            if isinstance(arg, GoCompositeLiteral) and arg.type_name in ("[]byte", "[]rune"):
                byte_vals = []
                all_literals = True
                for elem in arg.elements:
                    if isinstance(elem, GoLiteral):
                        if isinstance(elem.value, int):
                            byte_vals.append(elem.value)
                        elif isinstance(elem.value, str) and len(elem.value) == 1:
                            byte_vals.append(ord(elem.value))
                        else:
                            all_literals = False
                            break
                    else:
                        all_literals = False
                        break

                if all_literals:
                    try:
                        if arg.type_name == "[]byte":
                            reconstructed = bytes(byte_vals).decode("utf-8", errors="replace")
                        else:
                            reconstructed = "".join(chr(r) for r in byte_vals)

                        orig_src = GoPrinter.print_code(node)
                        res_node = GoLiteral(
                            value=reconstructed,
                            raw=repr(reconstructed),
                            type_name="string",
                            location=node.location,
                        )
                        self.tracker.record(
                            pass_name="GoStringReconstruction",
                            original=orig_src,
                            transformed=GoPrinter.print_code(res_node),
                            confidence=Confidence.certain(
                                f"Reconstructed string from {arg.type_name} slice",
                                TransformationCategory.RECOVERED,
                            ),
                            location=node.location,
                        )
                        return res_node
                    except Exception:
                        pass

            # string('A') or string(65) or string("foo")
            if isinstance(arg, GoLiteral):
                if isinstance(arg.value, str) and arg.type_name == "string":
                    return arg
                if isinstance(arg.value, str) and arg.type_name == "rune":
                    orig_src = GoPrinter.print_code(node)
                    res_node = GoLiteral(value=arg.value, raw=repr(arg.value), type_name="string", location=node.location)
                    return self._record_reconstruction(node, res_node, orig_src, "rune literal conversion")
                if isinstance(arg.value, int) and 0 <= arg.value <= 0x10FFFF:
                    try:
                        ch = chr(arg.value)
                        orig_src = GoPrinter.print_code(node)
                        res_node = GoLiteral(value=ch, raw=repr(ch), type_name="string", location=node.location)
                        return self._record_reconstruction(node, res_node, orig_src, "integer to rune conversion")
                    except ValueError:
                        pass

        # 2. strings.Join([]string{ ... }, sep)
        if (
            isinstance(node.callee, GoSelectorExpression)
            and isinstance(node.callee.expression, GoIdentifier)
            and node.callee.expression.name == "strings"
            and node.callee.name == "Join"
            and len(node.args) == 2
        ):
            first_arg = node.args[0]
            second_arg = node.args[1]
            if (
                isinstance(first_arg, GoCompositeLiteral)
                and isinstance(second_arg, GoLiteral)
                and isinstance(second_arg.value, str)
            ):
                str_parts = []
                all_str = True
                for elem in first_arg.elements:
                    if isinstance(elem, GoLiteral) and isinstance(elem.value, str):
                        str_parts.append(elem.value)
                    else:
                        all_str = False
                        break

                if all_str:
                    sep = second_arg.value
                    joined = sep.join(str_parts)
                    orig_src = GoPrinter.print_code(node)
                    res_node = GoLiteral(
                        value=joined,
                        raw=repr(joined),
                        type_name="string",
                        location=node.location,
                    )
                    return self._record_reconstruction(node, res_node, orig_src, "strings.Join unrolling")

        return node

    def _record_reconstruction(self, node: GoCallExpression, res_node: GoLiteral, orig_src: str, reason: str) -> GoLiteral:
        self.tracker.record(
            pass_name="GoStringReconstruction",
            original=orig_src,
            transformed=GoPrinter.print_code(res_node),
            confidence=Confidence.certain(
                f"Reconstructed string via {reason}",
                TransformationCategory.RECOVERED,
            ),
            location=node.location,
        )
        return res_node


class GoStringReconstructionPass(Pass):
    """Pass that reconstructs strings in Go AST."""

    name = "GoStringReconstruction"
    description = "Recovers strings from byte/rune slices and strings.Join calls in Go."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, GoNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = GoStringReconstructionTransformer(trk, self.filename)
        return transformer.visit(target)
