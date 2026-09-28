"""Dead code elimination pass for Go AST.

Per Section 15 of the Master Specification (Phase 9: Go):
Detects and removes unreachable code:
- Prunes if (false) blocks and simplifies if (true) constructs
- Removes dead statements following return, break, continue, or panic
"""

from __future__ import annotations

from typing import Any, List, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.go.ast_nodes import (
    GoBlock,
    GoBranchStatement,
    GoCallExpression,
    GoExpressionStatement,
    GoIdentifier,
    GoIfStatement,
    GoLiteral,
    GoNode,
    GoReturnStatement,
    GoStatement,
)
from languages.go.source_printer import GoPrinter
from languages.go.transformer import GoTransformer


class GoDeadCodeTransformer(GoTransformer):
    """Prunes dead branches and unreachable statements in Go AST."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_GoBlock(self, node: GoBlock) -> Any:
        self.generic_visit(node)
        new_stmts: List[GoStatement] = []

        for stmt in node.statements:
            new_stmts.append(stmt)
            # Statements after return or unconditional branch or panic are unreachable
            if isinstance(stmt, (GoReturnStatement, GoBranchStatement)):
                break
            if isinstance(stmt, GoExpressionStatement) and isinstance(stmt.expression, GoCallExpression):
                if isinstance(stmt.expression.callee, GoIdentifier) and stmt.expression.callee.name == "panic":
                    break

        if len(new_stmts) < len(node.statements):
            pruned_count = len(node.statements) - len(new_stmts)
            self.tracker.record(
                pass_name="GoDeadCode",
                original=GoPrinter.print_code(node),
                transformed=GoPrinter.print_code(GoBlock(statements=new_stmts)),
                confidence=Confidence.certain(
                    f"Removed {pruned_count} unreachable statement(s) after terminating control flow",
                    TransformationCategory.SIMPLIFIED,
                ),
                location=node.location,
            )

        node.statements = new_stmts
        return node

    def visit_GoIfStatement(self, node: GoIfStatement) -> Any:
        self.generic_visit(node)

        # Pattern: if false { ... }
        if isinstance(node.condition, GoLiteral) and node.condition.value is False:
            orig_src = GoPrinter.print_code(node)
            loc = node.location

            if node.else_branch:
                self.tracker.record(
                    pass_name="GoDeadCode",
                    original=orig_src,
                    transformed=GoPrinter.print_code(node.else_branch),
                    confidence=Confidence.certain(
                        "Pruned false branch and retained else branch",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=loc,
                )
                return node.else_branch

            # No else branch: eliminate entirely
            self.tracker.record(
                pass_name="GoDeadCode",
                original=orig_src,
                transformed="/* pruned dead if(false) */",
                confidence=Confidence.certain(
                    "Pruned dead if(false) block",
                    TransformationCategory.SIMPLIFIED,
                ),
                location=loc,
            )
            return None

        # Pattern: if true { then } else { ... }
        if isinstance(node.condition, GoLiteral) and node.condition.value is True:
            if node.else_branch:
                orig_src = GoPrinter.print_code(node)
                loc = node.location
                self.tracker.record(
                    pass_name="GoDeadCode",
                    original=orig_src,
                    transformed=GoPrinter.print_code(node.body),
                    confidence=Confidence.certain(
                        "Pruned else branch from if(true)",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=loc,
                )
                node.else_branch = None

        return node


class GoDeadCodePass(Pass):
    """Pass that removes dead code from Go AST."""

    name = "GoDeadCode"
    description = "Prunes dead conditional branches and unreachable statements in Go."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, GoNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = GoDeadCodeTransformer(trk, self.filename)
        return transformer.visit(target)
