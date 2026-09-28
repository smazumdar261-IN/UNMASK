"""Constant propagation pass for Go AST.

Per Section 15 of the Master Specification (Phase 9: Go):
Tracks constant declarations and single-assignment variables across functions and blocks.
Propagates known literals to their identifier references while guarding reassignments and parameters.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.go.ast_nodes import (
    GoAssignmentStatement,
    GoConstSpec,
    GoField,
    GoFunctionDecl,
    GoIdentifier,
    GoLiteral,
    GoNode,
    GoVarSpec,
)
from languages.go.source_printer import GoPrinter
from languages.go.transformer import GoTransformer


def collect_reassigned_or_parameter_names(node: GoNode) -> Set[str]:
    """Collects names assigned multiple times or declared as function parameters."""
    assigned_counts: Dict[str, int] = {}
    invalidated: Set[str] = set()

    def walk(n: Any) -> None:
        if n is None:
            return
        if isinstance(n, list):
            for item in n:
                walk(item)
            return
        if not isinstance(n, GoNode):
            return

        if isinstance(n, GoFunctionDecl):
            for p in n.params:
                if p.name:
                    invalidated.add(p.name)
            if n.receiver and n.receiver.name:
                invalidated.add(n.receiver.name)

        if isinstance(n, GoConstSpec):
            for name in n.names:
                assigned_counts[name] = assigned_counts.get(name, 0) + 1

        if isinstance(n, GoVarSpec):
            for name in n.names:
                assigned_counts[name] = assigned_counts.get(name, 0) + 1

        if isinstance(n, GoAssignmentStatement):
            for target in n.left:
                if isinstance(target, GoIdentifier):
                    assigned_counts[target.name] = assigned_counts.get(target.name, 0) + 1

        for field_name, val in vars(n).items():
            if field_name != "location":
                walk(val)

    walk(node)
    for name, count in assigned_counts.items():
        if count > 1:
            invalidated.add(name)
    return invalidated


class GoConstantPropagationTransformer(GoTransformer):
    """Replaces identifier references with their known constant values."""

    def __init__(self, tracker: ProvenanceTracker, reassigned: Set[str], filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename
        self.constants: Dict[str, GoLiteral] = {}
        self.reassigned = set(reassigned)

    def visit_GoConstSpec(self, node: GoConstSpec) -> Any:
        self.generic_visit(node)
        for name, val in zip(node.names, node.values):
            if isinstance(val, GoLiteral) and name not in self.reassigned:
                self.constants[name] = val
        return node

    def visit_GoVarSpec(self, node: GoVarSpec) -> Any:
        self.generic_visit(node)
        for name, val in zip(node.names, node.values):
            if isinstance(val, GoLiteral) and name not in self.reassigned:
                self.constants[name] = val
        return node

    def visit_GoAssignmentStatement(self, node: GoAssignmentStatement) -> Any:
        # Check for reassignments in assignment statement
        for target in node.left:
            if isinstance(target, GoIdentifier):
                if target.name in self.constants and node.operator not in (":=",):
                    self.reassigned.add(target.name)
                    self.constants.pop(target.name, None)

        self.generic_visit(node)

        # Track assignments: x := literal or x, _ := literal
        if len(node.left) == len(node.right):
            for target, val in zip(node.left, node.right):
                if isinstance(target, GoIdentifier) and target.name != "_":
                    if isinstance(val, GoLiteral) and target.name not in self.reassigned:
                        self.constants[target.name] = val
        elif len(node.left) == 2 and isinstance(node.left[1], GoIdentifier) and node.left[1].name == "_" and len(node.right) == 1:
            target = node.left[0]
            val = node.right[0]
            if isinstance(target, GoIdentifier) and target.name != "_":
                if isinstance(val, GoLiteral) and target.name not in self.reassigned:
                    self.constants[target.name] = val
        return node

    def visit_GoIdentifier(self, node: GoIdentifier) -> Any:
        if node.name in self.constants:
            const_val = self.constants[node.name]
            loc = node.location
            self.tracker.record(
                pass_name="GoConstantPropagation",
                original=node.name,
                transformed=GoPrinter.print_code(const_val),
                confidence=Confidence.certain(
                    f"Propagated constant value for Go variable '{node.name}'",
                    TransformationCategory.RECOVERED,
                ),
                location=loc,
            )
            return GoLiteral(
                value=const_val.value,
                raw=const_val.raw,
                type_name=const_val.type_name,
                location=loc,
            )
        return node


class GoConstantPropagationPass(Pass):
    """Pass that propagates constant values across Go code."""

    name = "GoConstantPropagation"
    description = "Propagates known constants to variable references in Go AST."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, GoNode):
            return target
        trk = tracker or ProvenanceTracker()
        reassigned = collect_reassigned_or_parameter_names(target)
        transformer = GoConstantPropagationTransformer(trk, reassigned, self.filename)
        return transformer.visit(target)
