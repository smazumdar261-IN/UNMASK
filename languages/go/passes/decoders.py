"""Go decoder detection and evaluation pass.

Per Section 15 of the Master Specification (Phase 9: Go):
Detects and statically executes standard Go decoding routines and string transformations:
- base64.StdEncoding.DecodeString("...") / base64.URLEncoding.DecodeString("...")
- hex.DecodeString("...")
- strconv.Atoi("...") / strconv.ParseInt("...", radix, bitSize)
- strings.ReplaceAll("...", old, new), strings.ToLower(), strings.ToUpper(), strings.TrimSpace()
"""

from __future__ import annotations

import base64
import binascii
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


class GoDecoderDetectionTransformer(GoTransformer):
    """Detects and statically executes Go decoders."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_GoCallExpression(self, node: GoCallExpression) -> Any:
        self.generic_visit(node)

        # 1. Base64: base64.StdEncoding.DecodeString("...") / base64.URLEncoding.DecodeString("...")
        if self._is_selector_call(node.callee, "DecodeString"):
            if len(node.args) == 1 and isinstance(node.args[0], GoLiteral) and isinstance(node.args[0].value, str):
                b64_str = node.args[0].value.strip()
                try:
                    decoded_bytes = base64.b64decode(b64_str, validate=True)
                    decoded_str = decoded_bytes.decode("utf-8", errors="replace")
                    orig_src = GoPrinter.print_code(node)
                    res_node = GoLiteral(
                        value=decoded_str,
                        raw=repr(decoded_str),
                        type_name="string",
                        location=node.location,
                    )
                    self.tracker.record(
                        pass_name="GoDecoderDetection",
                        original=orig_src,
                        transformed=GoPrinter.print_code(res_node),
                        confidence=Confidence.certain(
                            "Evaluated base64.DecodeString call",
                            TransformationCategory.RECOVERED,
                        ),
                        location=node.location,
                    )
                    return res_node
                except Exception:
                    pass

        # 2. Hex: hex.DecodeString("...")
        if (
            isinstance(node.callee, GoSelectorExpression)
            and isinstance(node.callee.expression, GoIdentifier)
            and node.callee.expression.name == "hex"
            and node.callee.name == "DecodeString"
            and len(node.args) == 1
        ):
            if isinstance(node.args[0], GoLiteral) and isinstance(node.args[0].value, str):
                hex_str = node.args[0].value.strip()
                try:
                    decoded_bytes = binascii.unhexlify(hex_str)
                    decoded_str = decoded_bytes.decode("utf-8", errors="replace")
                    orig_src = GoPrinter.print_code(node)
                    res_node = GoLiteral(
                        value=decoded_str,
                        raw=repr(decoded_str),
                        type_name="string",
                        location=node.location,
                    )
                    self.tracker.record(
                        pass_name="GoDecoderDetection",
                        original=orig_src,
                        transformed=GoPrinter.print_code(res_node),
                        confidence=Confidence.certain(
                            "Evaluated hex.DecodeString call",
                            TransformationCategory.RECOVERED,
                        ),
                        location=node.location,
                    )
                    return res_node
                except Exception:
                    pass

        # 3. strconv.Atoi / strconv.ParseInt
        if isinstance(node.callee, GoSelectorExpression) and isinstance(node.callee.expression, GoIdentifier) and node.callee.expression.name == "strconv":
            if node.callee.name == "Atoi" and len(node.args) == 1:
                if isinstance(node.args[0], GoLiteral) and isinstance(node.args[0].value, str):
                    try:
                        val = int(node.args[0].value.strip())
                        return self._record_folded_call(node, val, str(val), "int", "strconv.Atoi")
                    except ValueError:
                        pass
            elif node.callee.name == "ParseInt" and len(node.args) in (2, 3):
                if isinstance(node.args[0], GoLiteral) and isinstance(node.args[0].value, str):
                    radix = 10
                    if len(node.args) >= 2 and isinstance(node.args[1], GoLiteral) and isinstance(node.args[1].value, int):
                        radix = node.args[1].value
                    try:
                        val = int(node.args[0].value.strip(), radix)
                        return self._record_folded_call(node, val, str(val), "int", "strconv.ParseInt")
                    except ValueError:
                        pass

        # 4. strings transformations
        if isinstance(node.callee, GoSelectorExpression) and isinstance(node.callee.expression, GoIdentifier) and node.callee.expression.name == "strings":
            fn_name = node.callee.name
            if fn_name == "ReplaceAll" and len(node.args) == 3:
                s, old, new = node.args[0], node.args[1], node.args[2]
                if (
                    isinstance(s, GoLiteral) and isinstance(s.value, str)
                    and isinstance(old, GoLiteral) and isinstance(old.value, str)
                    and isinstance(new, GoLiteral) and isinstance(new.value, str)
                ):
                    res_str = s.value.replace(old.value, new.value)
                    return self._record_folded_call(node, res_str, repr(res_str), "string", "strings.ReplaceAll")

            elif fn_name == "ToLower" and len(node.args) == 1:
                if isinstance(node.args[0], GoLiteral) and isinstance(node.args[0].value, str):
                    res_str = node.args[0].value.lower()
                    return self._record_folded_call(node, res_str, repr(res_str), "string", "strings.ToLower")

            elif fn_name == "ToUpper" and len(node.args) == 1:
                if isinstance(node.args[0], GoLiteral) and isinstance(node.args[0].value, str):
                    res_str = node.args[0].value.upper()
                    return self._record_folded_call(node, res_str, repr(res_str), "string", "strings.ToUpper")

            elif fn_name == "TrimSpace" and len(node.args) == 1:
                if isinstance(node.args[0], GoLiteral) and isinstance(node.args[0].value, str):
                    res_str = node.args[0].value.strip()
                    return self._record_folded_call(node, res_str, repr(res_str), "string", "strings.TrimSpace")

        return node

    def _is_selector_call(self, callee: Any, method_name: str) -> bool:
        if isinstance(callee, GoSelectorExpression):
            return callee.name == method_name
        return False

    def _record_folded_call(self, node: GoCallExpression, val: Any, raw: str, tname: str, op_name: str) -> GoLiteral:
        orig_src = GoPrinter.print_code(node)
        loc = node.location
        res_node = GoLiteral(value=val, raw=raw, type_name=tname, location=loc)
        self.tracker.record(
            pass_name="GoDecoderDetection",
            original=orig_src,
            transformed=GoPrinter.print_code(res_node),
            confidence=Confidence.certain(
                f"Evaluated {op_name} call",
                TransformationCategory.SIMPLIFIED,
            ),
            location=loc,
        )
        return res_node


class GoDecoderDetectionPass(Pass):
    """Pass that detects and evaluates standard Go decoders."""

    name = "GoDecoderDetection"
    description = "Evaluates base64, hex, and string transformations in Go AST."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, GoNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = GoDecoderDetectionTransformer(trk, self.filename)
        return transformer.visit(target)
