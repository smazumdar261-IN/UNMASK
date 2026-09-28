"""Immediately Invoked Function Expression (IIFE) normalization pass.

Per Section 12 of the Master Specification:
Inlines and unrolls simple IIFE patterns:
(function() { return 'value'; })() -> 'value'
(function(x) { return x + 10; })(20) -> 20 + 10
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.javascript.ast_nodes import (
    JSBlockStatement,
    JSCallExpression,
    JSExpression,
    JSFunctionExpression,
    JSIdentifier,
    JSNode,
    JSReturnStatement,
)
from languages.javascript.printer import JSPrinter
from languages.javascript.transformer import JSTransformer


class _ParamSubstitutor(JSTransformer):
    """Substitutes parameter identifiers with argument expressions."""

    def __init__(self, mapping: Dict[str, JSExpression]) -> None:
        self.mapping = mapping

    def visit_JSMemberExpression(self, node: Any) -> Any:
        node.object = self.visit(node.object)
        if getattr(node, "computed", False):
            node.property = self.visit(node.property)
        return node

    def visit_JSProperty(self, node: Any) -> Any:
        if getattr(node, "computed", False):
            node.key = self.visit(node.key)
        node.value = self.visit(node.value)
        return node

    def visit_JSIdentifier(self, node: JSIdentifier) -> Any:
        if node.name in self.mapping:
            return self.mapping[node.name]
        return node


class JSIIFENormalizationTransformer(JSTransformer):
    """Replaces single-return IIFE call expressions with their body expressions."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_JSCallExpression(self, node: JSCallExpression) -> Any:
        self.generic_visit(node)

        # Check if callee is a JSFunctionExpression
        if isinstance(node.callee, JSFunctionExpression):
            fn = node.callee
            # Check if function body is a single return statement
            if (
                isinstance(fn.body, JSBlockStatement)
                and len(fn.body.body) == 1
                and isinstance(fn.body.body[0], JSReturnStatement)
            ):
                ret_stmt = fn.body.body[0]
                if ret_stmt.argument is not None:
                    # Parameter mapping
                    if len(fn.params) == len(node.arguments):
                        mapping: Dict[str, JSExpression] = {}
                        for p, arg in zip(fn.params, node.arguments):
                            mapping[p.name] = arg

                        substitutor = _ParamSubstitutor(mapping)
                        inlined_expr = substitutor.visit(ret_stmt.argument)

                        orig_src = JSPrinter.print_code(node)
                        self.tracker.record(
                            pass_name="JSIIFENormalization",
                            original=orig_src,
                            transformed=JSPrinter.print_code(inlined_expr),
                            confidence=Confidence.certain(
                                "Inlined single-return IIFE expression",
                                TransformationCategory.SIMPLIFIED,
                            ),
                            location=node.location,
                        )
                        return inlined_expr

        return node


class JSIIFENormalizationPass(Pass):
    """Pass that inlines and simplifies simple IIFEs in JavaScript AST."""

    name = "JSIIFENormalization"
    description = "Inlines single-statement pure IIFEs in JavaScript."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, JSNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = JSIIFENormalizationTransformer(trk, self.filename)
        return transformer.visit(target)
