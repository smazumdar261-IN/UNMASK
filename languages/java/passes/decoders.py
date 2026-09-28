"""Java decoder detection and static evaluation pass.

Per Section 14 of the Master Specification (Phase 8: Java):
Evaluates standard Java decoding routines and string transformations:
- Base64.getDecoder().decode("...")
- new String(Base64.getDecoder().decode("..."))
- Integer.parseInt("...") / Long.parseLong("...")
- String methods: replace, toLowerCase, toUpperCase, substring, trim
"""

from __future__ import annotations

import base64
from typing import Any, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.java.ast_nodes import (
    JavaFieldAccess,
    JavaIdentifier,
    JavaLiteral,
    JavaMethodCall,
    JavaNewClassExpression,
    JavaNode,
)
from languages.java.source_printer import JavaPrinter
from languages.java.transformer import JavaTransformer


class JavaDecoderDetectionTransformer(JavaTransformer):
    """Detects and statically executes Java decoding routines."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_JavaNewClassExpression(self, node: JavaNewClassExpression) -> Any:
        self.generic_visit(node)
        if node.type_name == "String" and len(node.arguments) in (1, 2):
            first_arg = node.arguments[0]
            if isinstance(first_arg, JavaLiteral) and isinstance(first_arg.value, str):
                orig_src = JavaPrinter.print_code(node)
                self.tracker.record(
                    pass_name="JavaDecoderDetection",
                    original=orig_src,
                    transformed=JavaPrinter.print_code(first_arg),
                    confidence=Confidence.certain(
                        "Simplified new String(literal) to string literal",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=node.location,
                )
                return first_arg
            if isinstance(first_arg, JavaMethodCall) and first_arg.name == "decode":
                if len(first_arg.arguments) == 1 and isinstance(first_arg.arguments[0], JavaLiteral):
                    b64_str = first_arg.arguments[0].value
                    if isinstance(b64_str, str):
                        try:
                            decoded_bytes = base64.b64decode(b64_str.strip(), validate=True)
                            encoding = "utf-8"
                            if len(node.arguments) == 2 and isinstance(node.arguments[1], JavaLiteral):
                                encoding = str(node.arguments[1].value)
                            decoded_str = decoded_bytes.decode(encoding, errors="replace")

                            orig_src = JavaPrinter.print_code(node)
                            res_node = JavaLiteral(
                                value=decoded_str,
                                raw=repr(decoded_str),
                                type_name="String",
                                location=node.location,
                            )
                            self.tracker.record(
                                pass_name="JavaDecoderDetection",
                                original=orig_src,
                                transformed=JavaPrinter.print_code(res_node),
                                confidence=Confidence.certain(
                                    "Evaluated new String(Base64.getDecoder().decode(...))",
                                    TransformationCategory.RECOVERED,
                                ),
                                location=node.location,
                            )
                            return res_node
                        except Exception:
                            pass
        return node

    def visit_JavaMethodCall(self, node: JavaMethodCall) -> Any:
        self.generic_visit(node)

        # 1. Base64.getDecoder().decode("...")
        if node.name == "decode" and len(node.arguments) == 1:
            if isinstance(node.arguments[0], JavaLiteral) and isinstance(node.arguments[0].value, str):
                b64_str = node.arguments[0].value
                try:
                    decoded_bytes = base64.b64decode(b64_str.strip(), validate=True)
                    decoded_str = decoded_bytes.decode("utf-8", errors="replace")
                    orig_src = JavaPrinter.print_code(node)
                    res_node = JavaLiteral(
                        value=decoded_str,
                        raw=repr(decoded_str),
                        type_name="String",
                        location=node.location,
                    )
                    self.tracker.record(
                        pass_name="JavaDecoderDetection",
                        original=orig_src,
                        transformed=JavaPrinter.print_code(res_node),
                        confidence=Confidence.certain(
                            "Evaluated Base64 decode call",
                            TransformationCategory.RECOVERED,
                        ),
                        location=node.location,
                    )
                    return res_node
                except Exception:
                    pass

        # 2. Integer.parseInt / Integer.valueOf / Long.parseLong / Long.valueOf
        if node.name in ("parseInt", "valueOf") and len(node.arguments) in (1, 2):
            if isinstance(node.arguments[0], JavaLiteral) and isinstance(node.arguments[0].value, str):
                radix = 10
                if len(node.arguments) == 2 and isinstance(node.arguments[1], JavaLiteral) and isinstance(node.arguments[1].value, int):
                    radix = node.arguments[1].value
                try:
                    val = int(node.arguments[0].value.strip(), radix)
                    orig_src = JavaPrinter.print_code(node)
                    res_node = JavaLiteral(value=val, raw=str(val), type_name="int", location=node.location)
                    self.tracker.record(
                        pass_name="JavaDecoderDetection",
                        original=orig_src,
                        transformed=JavaPrinter.print_code(res_node),
                        confidence=Confidence.certain(
                            f"Evaluated {node.name} call",
                            TransformationCategory.SIMPLIFIED,
                        ),
                        location=node.location,
                    )
                    return res_node
                except ValueError:
                    pass
        elif node.name in ("parseLong",) and len(node.arguments) in (1, 2):
            if isinstance(node.arguments[0], JavaLiteral) and isinstance(node.arguments[0].value, str):
                radix = 10
                if len(node.arguments) == 2 and isinstance(node.arguments[1], JavaLiteral) and isinstance(node.arguments[1].value, int):
                    radix = node.arguments[1].value
                try:
                    val = int(node.arguments[0].value.strip(), radix)
                    orig_src = JavaPrinter.print_code(node)
                    res_node = JavaLiteral(value=val, raw=f"{val}L", type_name="long", location=node.location)
                    self.tracker.record(
                        pass_name="JavaDecoderDetection",
                        original=orig_src,
                        transformed=JavaPrinter.print_code(res_node),
                        confidence=Confidence.certain(
                            f"Evaluated {node.name} call",
                            TransformationCategory.SIMPLIFIED,
                        ),
                        location=node.location,
                    )
                    return res_node
                except ValueError:
                    pass

        # 3. String transformations on string literals
        if isinstance(node.target, JavaLiteral) and isinstance(node.target.value, str):
            s = node.target.value
            res_str = None
            if node.name == "replace" and len(node.arguments) == 2:
                if (
                    isinstance(node.arguments[0], JavaLiteral)
                    and isinstance(node.arguments[1], JavaLiteral)
                    and isinstance(node.arguments[0].value, str)
                    and isinstance(node.arguments[1].value, str)
                ):
                    res_str = s.replace(node.arguments[0].value, node.arguments[1].value)
            elif node.name == "toLowerCase" and not node.arguments:
                res_str = s.lower()
            elif node.name == "toUpperCase" and not node.arguments:
                res_str = s.upper()
            elif node.name == "trim" and not node.arguments:
                res_str = s.strip()
            elif node.name == "substring":
                if len(node.arguments) == 1 and isinstance(node.arguments[0], JavaLiteral) and isinstance(node.arguments[0].value, int):
                    res_str = s[node.arguments[0].value :]
                elif (
                    len(node.arguments) == 2
                    and isinstance(node.arguments[0], JavaLiteral)
                    and isinstance(node.arguments[1], JavaLiteral)
                    and isinstance(node.arguments[0].value, int)
                    and isinstance(node.arguments[1].value, int)
                ):
                    res_str = s[node.arguments[0].value : node.arguments[1].value]

            if res_str is not None:
                orig_src = JavaPrinter.print_code(node)
                res_node = JavaLiteral(
                    value=res_str,
                    raw=repr(res_str),
                    type_name="String",
                    location=node.location,
                )
                self.tracker.record(
                    pass_name="JavaDecoderDetection",
                    original=orig_src,
                    transformed=JavaPrinter.print_code(res_node),
                    confidence=Confidence.certain(
                        f"Evaluated String.{node.name}() method call",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=node.location,
                )
                return res_node

        return node


class JavaDecoderDetectionPass(Pass):
    """Pass that evaluates calls to Base64 and standard string transformations."""

    name = "JavaDecoderDetection"
    description = "Statically evaluates calls to Base64 decoders and string transformations in Java."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, JavaNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = JavaDecoderDetectionTransformer(trk, self.filename)
        return transformer.visit(target)
