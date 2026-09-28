"""Constant propagation pass for Java AST.

Per Section 14 of the Master Specification:
Tracks constant assignments within methods and propagates known literals to variable usages.
Guarantees reassignment safety and parameter shielding.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.java.ast_nodes import (
    JavaAssignmentExpression,
    JavaFieldDeclaration,
    JavaIdentifier,
    JavaLiteral,
    JavaMethodDeclaration,
    JavaNode,
    JavaVariableDeclarationStatement,
)
from languages.java.source_printer import JavaPrinter
from languages.java.transformer import JavaTransformer


def collect_reassigned_or_parameter_names(node: JavaNode) -> Set[str]:
    """Collects names assigned multiple times or declared as method parameters."""
    assigned_counts: Dict[str, int] = {}
    invalidated: Set[str] = set()

    def walk(n: Any) -> None:
        if n is None:
            return
        if isinstance(n, list):
            for item in n:
                walk(item)
            return
        if not isinstance(n, JavaNode):
            return

        if isinstance(n, JavaMethodDeclaration):
            for p in n.parameters:
                invalidated.add(p.name)

        if isinstance(n, (JavaVariableDeclarationStatement, JavaFieldDeclaration)):
            assigned_counts[n.name] = assigned_counts.get(n.name, 0) + 1

        if isinstance(n, JavaAssignmentExpression):
            if isinstance(n.target, JavaIdentifier):
                assigned_counts[n.target.name] = assigned_counts.get(n.target.name, 0) + 1

        for field_name, val in vars(n).items():
            if field_name != "location":
                walk(val)

    walk(node)
    for name, count in assigned_counts.items():
        if count > 1:
            invalidated.add(name)
    return invalidated


class JavaConstantPropagationTransformer(JavaTransformer):
    """Replaces identifier references with their known constant values."""

    def __init__(self, tracker: ProvenanceTracker, reassigned: Set[str], filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename
        self.constants: Dict[str, JavaLiteral] = {}
        self.reassigned = set(reassigned)

    def visit_JavaFieldDeclaration(self, node: JavaFieldDeclaration) -> Any:
        if node.initializer is not None:
            node.initializer = self.visit(node.initializer)
        if isinstance(node.initializer, JavaLiteral) and node.name not in self.reassigned:
            self.constants[node.name] = node.initializer
        return node

    def visit_JavaVariableDeclarationStatement(self, node: JavaVariableDeclarationStatement) -> Any:
        if node.initializer is not None:
            node.initializer = self.visit(node.initializer)
        if isinstance(node.initializer, JavaLiteral) and node.name not in self.reassigned:
            self.constants[node.name] = node.initializer
        return node

    def visit_JavaAssignmentExpression(self, node: JavaAssignmentExpression) -> Any:
        if isinstance(node.target, JavaIdentifier):
            self.reassigned.add(node.target.name)
            self.constants.pop(node.target.name, None)
        node.value = self.visit(node.value)
        return node

    def visit_JavaIdentifier(self, node: JavaIdentifier) -> Any:
        if node.name in self.constants:
            const_val = self.constants[node.name]
            loc = node.location
            self.tracker.record(
                pass_name="JavaConstantPropagation",
                original=node.name,
                transformed=JavaPrinter.print_code(const_val),
                confidence=Confidence.certain(
                    f"Propagated constant value for Java variable '{node.name}'",
                    TransformationCategory.RECOVERED,
                ),
                location=loc,
            )
            return JavaLiteral(
                value=const_val.value,
                raw=const_val.raw,
                type_name=const_val.type_name,
                location=loc,
            )
        return node


class JavaConstantPropagationPass(Pass):
    """Pass that propagates constant values across Java code."""

    name = "JavaConstantPropagation"
    description = "Propagates known constants to variable references in Java AST."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, JavaNode):
            return target
        trk = tracker or ProvenanceTracker()
        reassigned = collect_reassigned_or_parameter_names(target)
        transformer = JavaConstantPropagationTransformer(trk, reassigned, self.filename)
        return transformer.visit(target)
