"""Property access normalization pass for JavaScript AST.

Per Section 12 of the Master Specification:
Normalizes dynamic/computed bracket property access:
obj['property'] -> obj.property
when property is a valid JavaScript identifier name.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.javascript.ast_nodes import (
    JSIdentifier,
    JSLiteral,
    JSMemberExpression,
    JSNode,
)
from languages.javascript.lexer import JS_KEYWORDS
from languages.javascript.printer import JSPrinter
from languages.javascript.transformer import JSTransformer

VALID_JS_ID_REGEX = re.compile(r"^[a-zA-Z_$][a-zA-Z0-9_$]*$")


class JSPropertyNormalizationTransformer(JSTransformer):
    """Converts bracket notation to dot notation where safe."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_JSMemberExpression(self, node: JSMemberExpression) -> Any:
        self.generic_visit(node)
        if node.computed and isinstance(node.property, JSLiteral) and isinstance(node.property.value, str):
            prop_name = node.property.value
            if VALID_JS_ID_REGEX.match(prop_name) and prop_name not in JS_KEYWORDS:
                orig_src = JSPrinter.print_code(node)
                node.computed = False
                node.property = JSIdentifier(name=prop_name, location=node.property.location)
                self.tracker.record(
                    pass_name="JSPropertyNormalization",
                    original=orig_src,
                    transformed=JSPrinter.print_code(node),
                    confidence=Confidence.certain(
                        f"Normalized bracket property access '{prop_name}' to dot notation",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=node.location,
                )
        return node


class JSPropertyNormalizationPass(Pass):
    """Pass that normalizes dynamic bracket property access to standard dot notation."""

    name = "JSPropertyNormalization"
    description = "Normalizes obj['prop'] to obj.prop when prop is a valid identifier."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, JSNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = JSPropertyNormalizationTransformer(trk, self.filename)
        return transformer.visit(target)
