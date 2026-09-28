"""Language-independent decoder evaluation pass for Common Intermediate Representation.

Per Section 16, Section 17 & Phase 10:
Evaluates static encoding/decoding functions (base64, hex, string normalization)
directly on Common IR.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any, Optional

from core.confidence import Confidence, TransformationCategory
from core.ir import (
    IRCall,
    IRConstant,
    IRExpression,
    IRMemberAccess,
    IRString,
    IRTransformer,
    IRVariable,
    format_ir,
)
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation


class IRDecoderTransformer(IRTransformer):
    """Evaluates static decoders and string normalization calls in Common IR."""

    def __init__(self, tracker: Optional[ProvenanceTracker] = None) -> None:
        self.tracker = tracker

    def visit_IRCall(self, node: IRCall) -> IRExpression:
        self.generic_visit(node)

        callee_name = self._resolve_callee_name(node.callee)

        # Base64 Decoders across all languages
        if callee_name in (
            "base64.b64decode",
            "b64decode",
            "atob",
            "Base64.getDecoder().decode",
            "base64.StdEncoding.DecodeString",
        ):
            if len(node.args) >= 1 and isinstance(node.args[0], IRConstant) and isinstance(node.args[0].value, str):
                encoded_str = node.args[0].value.strip()
                try:
                    decoded_bytes = base64.b64decode(encoded_str)
                    try:
                        decoded_text = decoded_bytes.decode("utf-8")
                        return self._record(node, decoded_text, f"Statically evaluated Base64 decode ({callee_name})")
                    except UnicodeDecodeError:
                        return self._record(node, decoded_bytes.hex(), f"Evaluated Base64 decode to hex ({callee_name})")
                except Exception:
                    pass

        # Hex Decoders
        if callee_name in ("bytes.fromhex", "fromhex", "hex.DecodeString"):
            if len(node.args) >= 1 and isinstance(node.args[0], IRConstant) and isinstance(node.args[0].value, str):
                hex_str = node.args[0].value.strip()
                try:
                    decoded_bytes = bytes.fromhex(hex_str)
                    try:
                        decoded_text = decoded_bytes.decode("utf-8")
                        return self._record(node, decoded_text, f"Statically evaluated Hex decode ({callee_name})")
                    except UnicodeDecodeError:
                        pass
                except Exception:
                    pass

        # String transforms: replace / replaceAll / toLowerCase / toUpperCase / trim / strip
        if callee_name in ("replace", "replaceAll", "strings.ReplaceAll"):
            if len(node.args) == 2 and isinstance(node.callee, IRMemberAccess):
                target = node.callee.target
                if (
                    isinstance(target, IRConstant)
                    and isinstance(target.value, str)
                    and isinstance(node.args[0], IRConstant)
                    and isinstance(node.args[1], IRConstant)
                ):
                    orig = str(target.value)
                    old = str(node.args[0].value)
                    new = str(node.args[1].value)
                    replaced = orig.replace(old, new)
                    return self._record(node, replaced, "Statically evaluated string replace")

            elif len(node.args) == 3 and callee_name == "strings.ReplaceAll":
                if all(isinstance(a, IRConstant) and isinstance(a.value, str) for a in node.args):
                    orig = str(node.args[0].value)
                    old = str(node.args[1].value)
                    new = str(node.args[2].value)
                    replaced = orig.replace(old, new)
                    return self._record(node, replaced, "Statically evaluated strings.ReplaceAll")

        if callee_name in ("toLowerCase", "lower", "strings.ToLower"):
            if isinstance(node.callee, IRMemberAccess):
                target = node.callee.target
                if isinstance(target, IRConstant) and isinstance(target.value, str):
                    return self._record(node, target.value.lower(), "Statically evaluated lower-case")
            elif len(node.args) == 1 and isinstance(node.args[0], IRConstant) and isinstance(node.args[0].value, str):
                return self._record(node, node.args[0].value.lower(), "Statically evaluated lower-case")

        if callee_name in ("toUpperCase", "upper", "strings.ToUpper"):
            if isinstance(node.callee, IRMemberAccess):
                target = node.callee.target
                if isinstance(target, IRConstant) and isinstance(target.value, str):
                    return self._record(node, target.value.upper(), "Statically evaluated upper-case")
            elif len(node.args) == 1 and isinstance(node.args[0], IRConstant) and isinstance(node.args[0].value, str):
                return self._record(node, node.args[0].value.upper(), "Statically evaluated upper-case")

        if callee_name in ("trim", "strip", "trimSpace", "strings.TrimSpace"):
            if isinstance(node.callee, IRMemberAccess):
                target = node.callee.target
                if isinstance(target, IRConstant) and isinstance(target.value, str):
                    return self._record(node, target.value.strip(), "Statically evaluated trim/strip")
            elif len(node.args) == 1 and isinstance(node.args[0], IRConstant) and isinstance(node.args[0].value, str):
                return self._record(node, node.args[0].value.strip(), "Statically evaluated trim/strip")

        return node

    def _resolve_callee_name(self, callee: IRExpression) -> str:
        if isinstance(callee, IRVariable):
            return callee.name
        if isinstance(callee, IRMemberAccess):
            prefix = self._resolve_callee_name(callee.target)
            return f"{prefix}.{callee.member}" if prefix else callee.member
        return ""

    def _record(self, original_node: IRExpression, result_val: str, rationale: str) -> IRString:
        orig_text = format_ir(original_node)
        loc = original_node.location or SourceLocation()
        replacement = IRString(value=result_val, location=loc)

        if self.tracker:
            self.tracker.record(
                pass_name="IRDecoderEvaluation",
                original=orig_text,
                transformed=format_ir(replacement),
                confidence=Confidence.certain(
                    reason=f"{rationale}: {result_val!r}",
                    category=TransformationCategory.RECOVERED,
                ),
                location=loc,
            )
        return replacement


class IRDecoderEvaluation(Pass):
    """Language-independent decoder evaluation pass on Common IR."""

    name = "IRDecoderEvaluation"
    description = "Statically evaluates standard decoding functions (base64, hex, string) in Common IR"

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        transformer = IRDecoderTransformer(tracker=tracker)
        return transformer.visit(target)
