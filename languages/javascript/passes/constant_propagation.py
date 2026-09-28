"""Constant propagation pass for JavaScript AST.

Per Section 12 of the Master Specification:
Propagates constant literal assignments across variable reads within lexical scopes.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.javascript.ast_nodes import (
    JSArrowFunctionExpression,
    JSAssignmentExpression,
    JSFunctionDeclaration,
    JSFunctionExpression,
    JSIdentifier,
    JSLiteral,
    JSMemberExpression,
    JSNode,
    JSVariableDeclaration,
    JSVariableDeclarator,
)
from languages.javascript.printer import JSPrinter
from languages.javascript.transformer import JSTransformer


def collect_reassigned_or_parameter_names(node: JSNode) -> set[str]:
    """Collects names assigned multiple times, modified, or used as parameters."""
    assigned_counts: dict[str, int] = {}
    invalidated: set[str] = set()

    def walk(n: Any) -> None:
        if n is None:
            return
        if isinstance(n, list):
            for item in n:
                walk(item)
            return
        if not isinstance(n, JSNode):
            return

        if isinstance(n, (JSFunctionDeclaration, JSFunctionExpression, JSArrowFunctionExpression)):
            for p in n.params:
                if isinstance(p, JSIdentifier):
                    invalidated.add(p.name)

        if isinstance(n, JSVariableDeclarator):
            if isinstance(n.id, JSIdentifier):
                name = n.id.name
                assigned_counts[name] = assigned_counts.get(name, 0) + 1

        if isinstance(n, JSAssignmentExpression):
            if isinstance(n.left, JSIdentifier):
                name = n.left.name
                assigned_counts[name] = assigned_counts.get(name, 0) + 1

        for field_name, val in vars(n).items():
            if field_name != "location":
                walk(val)

    walk(node)
    for name, count in assigned_counts.items():
        if count > 1:
            invalidated.add(name)
    return invalidated


class JSConstantPropagationTransformer(JSTransformer):
    """Replaces identifier references with their known constant values."""

    def __init__(self, tracker: ProvenanceTracker, reassigned: set[str], filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename
        self.constants: Dict[str, JSLiteral] = {}
        self.reassigned: set[str] = set(reassigned)

    def visit_JSVariableDeclaration(self, node: JSVariableDeclaration) -> Any:
        for decl in node.declarations:
            if decl.init is not None:
                decl.init = self.visit(decl.init)
            if isinstance(decl.id, JSIdentifier) and isinstance(decl.init, JSLiteral):
                if decl.id.name not in self.reassigned:
                    self.constants[decl.id.name] = decl.init
        return node

    def visit_JSVariableDeclarator(self, node: JSVariableDeclarator) -> Any:
        if node.init is not None:
            node.init = self.visit(node.init)
        return node

    def visit_JSFunctionDeclaration(self, node: JSFunctionDeclaration) -> Any:
        node.body = self.visit(node.body)
        return node

    def visit_JSFunctionExpression(self, node: JSFunctionExpression) -> Any:
        node.body = self.visit(node.body)
        return node

    def visit_JSArrowFunctionExpression(self, node: Any) -> Any:
        node.body = self.visit(node.body)
        return node

    def visit_JSMemberExpression(self, node: JSMemberExpression) -> Any:
        node.object = self.visit(node.object)
        if node.computed:
            node.property = self.visit(node.property)
        return node

    def visit_JSProperty(self, node: Any) -> Any:
        if getattr(node, "computed", False):
            node.key = self.visit(node.key)
        node.value = self.visit(node.value)
        return node

    def visit_JSAssignmentExpression(self, node: JSAssignmentExpression) -> Any:
        if isinstance(node.left, JSIdentifier):
            self.reassigned.add(node.left.name)
            self.constants.pop(node.left.name, None)
        elif isinstance(node.left, JSMemberExpression):
            node.left = self.visit(node.left)
        node.right = self.visit(node.right)
        return node

    def visit_JSIdentifier(self, node: JSIdentifier) -> Any:
        if node.name in self.constants:
            const_val = self.constants[node.name]
            loc = node.location
            self.tracker.record(
                pass_name="JSConstantPropagation",
                original=node.name,
                transformed=JSPrinter.print_code(const_val),
                confidence=Confidence.certain(
                    f"Propagated constant value for variable '{node.name}'",
                    TransformationCategory.RECOVERED,
                ),
                location=loc,
            )
            return JSLiteral(value=const_val.value, raw=const_val.raw, location=loc)
        return node


class JSConstantPropagationPass(Pass):
    """Pass that propagates constant values across JavaScript code."""

    name = "JSConstantPropagation"
    description = "Propagates known constants to variable references in JavaScript AST."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, JSNode):
            return target
        trk = tracker or ProvenanceTracker()
        reassigned = collect_reassigned_or_parameter_names(target)
        transformer = JSConstantPropagationTransformer(trk, reassigned, self.filename)
        return transformer.visit(target)
