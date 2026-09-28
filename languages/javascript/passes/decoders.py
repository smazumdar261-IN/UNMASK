"""Standard JavaScript decoder detection and evaluation pass.

Per Section 12 of the Master Specification:
Evaluates calls to standard JavaScript decoding routines on constant arguments:
- atob(...)
- btoa(...)
- decodeURIComponent(...)
- unescape(...)
"""

from __future__ import annotations

import base64
import re
import urllib.parse
from typing import Any, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.javascript.ast_nodes import (
    JSCallExpression,
    JSIdentifier,
    JSLiteral,
    JSMemberExpression,
    JSNode,
)
from languages.javascript.printer import JSPrinter
from languages.javascript.transformer import JSTransformer


class JSDecoderDetectionTransformer(JSTransformer):
    """Detects and statically executes atob, btoa, decodeURIComponent, unescape."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_JSCallExpression(self, node: JSCallExpression) -> Any:
        self.generic_visit(node)

        # Extract function name: e.g. atob(...) or window.atob(...)
        fn_name = self._extract_callee_name(node.callee)
        if not fn_name:
            return node

        # Must have exactly 1 argument that is a JSLiteral string
        if len(node.arguments) != 1 or not isinstance(node.arguments[0], JSLiteral) or not isinstance(node.arguments[0].value, str):
            return node

        arg_val: str = node.arguments[0].value
        decoded_val: Optional[str] = None
        decoder_label = ""

        # 1. atob (Base64 decode)
        if fn_name == "atob":
            try:
                decoded_bytes = base64.b64decode(arg_val.strip(), validate=True)
                decoded_val = decoded_bytes.decode("utf-8", errors="replace")
                decoder_label = "atob (Base64)"
            except Exception:
                pass

        # 2. btoa (Base64 encode)
        elif fn_name == "btoa":
            try:
                encoded_bytes = base64.b64encode(arg_val.encode("latin-1"))
                decoded_val = encoded_bytes.decode("ascii")
                decoder_label = "btoa (Base64 encode)"
            except Exception:
                pass

        # 3. decodeURIComponent
        elif fn_name in ("decodeURIComponent", "decodeURI"):
            try:
                decoded_val = urllib.parse.unquote(arg_val)
                decoder_label = "decodeURIComponent"
            except Exception:
                pass

        # 4. unescape
        elif fn_name == "unescape":
            try:
                decoded_val = self._js_unescape(arg_val)
                decoder_label = "unescape"
            except Exception:
                pass

        if decoded_val is not None:
            orig_src = JSPrinter.print_code(node)
            res_node = JSLiteral(value=decoded_val, raw=repr(decoded_val), location=node.location)
            self.tracker.record(
                pass_name="JSDecoderDetection",
                original=orig_src,
                transformed=JSPrinter.print_code(res_node),
                confidence=Confidence.certain(
                    f"Evaluated {decoder_label} call",
                    TransformationCategory.RECOVERED,
                ),
                location=node.location,
            )
            return res_node

        return node

    def _extract_callee_name(self, callee: Any) -> Optional[str]:
        if isinstance(callee, JSIdentifier):
            return callee.name
        if isinstance(callee, JSMemberExpression):
            # window.atob or globalThis.atob
            if isinstance(callee.object, JSIdentifier) and callee.object.name in ("window", "globalThis", "self", "global"):
                if isinstance(callee.property, JSIdentifier) and not callee.computed:
                    return callee.property.name
                if isinstance(callee.property, JSLiteral) and callee.computed and isinstance(callee.property.value, str):
                    return callee.property.value
        return None

    def _js_unescape(self, s: str) -> str:
        """Emulate JavaScript legacy unescape() (%uXXXX and %XX)."""
        def unquote_u(match: re.Match) -> str:
            return chr(int(match.group(1), 16))

        # Replace %uXXXX
        s = re.sub(r"%u([0-9a-fA-F]{4})", unquote_u, s)
        # Replace %XX
        return urllib.parse.unquote(s)


class JSDecoderDetectionPass(Pass):
    """Pass that detects and executes standard JavaScript decoders."""

    name = "JSDecoderDetection"
    description = "Statically evaluates calls to atob, btoa, decodeURIComponent, and unescape."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, JSNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = JSDecoderDetectionTransformer(trk, self.filename)
        return transformer.visit(target)
