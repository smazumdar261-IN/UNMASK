"""Dead code elimination pass for Java AST.

Per Section 14 of the Master Specification (Phase 8: Java):
Prunes dead branches conditioned on known boolean constants:
- if (true) { A } else { B } -> A
- if (false) { A } else { B } -> B
- if (false) { A } -> removed
- Prunes unreachable statements after return statements
"""

from __future__ import annotations

from typing import Any, List, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.java.ast_nodes import (
    JavaBlock,
    JavaIfStatement,
    JavaLiteral,
    JavaNode,
    JavaReturnStatement,
    JavaStatement,
)
from languages.java.source_printer import JavaPrinter
from languages.java.transformer import JavaTransformer


class JavaDeadCodeTransformer(JavaTransformer):
    """Prunes dead branches and unreachable statements."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_JavaBlock(self, node: JavaBlock) -> Any:
        new_stmts: List[JavaStatement] = []
        has_returned = False

        for stmt in node.statements:
            if has_returned:
                # Omit statements after a return
                orig_src = JavaPrinter.print_code(stmt)
                self.tracker.record(
                    pass_name="JavaDeadCode",
                    original=orig_src,
                    transformed="/* pruned unreachable code */",
                    confidence=Confidence.certain(
                        "Eliminated unreachable statement after return",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=stmt.location,
                )
                continue

            visited = self.visit(stmt)
            if visited is not None:
                if isinstance(visited, list):
                    new_stmts.extend(visited)
                else:
                    new_stmts.append(visited)

            if isinstance(stmt, JavaReturnStatement):
                has_returned = True

        node.statements = new_stmts
        return node

    def visit_JavaIfStatement(self, node: JavaIfStatement) -> Any:
        self.generic_visit(node)
        if isinstance(node.condition, JavaLiteral) and isinstance(node.condition.value, bool):
            orig_src = JavaPrinter.print_code(node)
            if node.condition.value is True:
                self.tracker.record(
                    pass_name="JavaDeadCode",
                    original=orig_src,
                    transformed=JavaPrinter.print_code(node.then_branch),
                    confidence=Confidence.certain(
                        "Pruned dead branch from if(true)",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=node.location,
                )
                return node.then_branch
            else:
                replacement = node.else_branch if node.else_branch else None
                self.tracker.record(
                    pass_name="JavaDeadCode",
                    original=orig_src,
                    transformed=JavaPrinter.print_code(replacement) if replacement else "/* dead branch pruned */",
                    confidence=Confidence.certain(
                        "Pruned dead branch from if(false)",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=node.location,
                )
                return replacement
        return node


class JavaDeadCodePass(Pass):
    """Pass that prunes dead branches and unreachable statements in Java AST."""

    name = "JavaDeadCode"
    description = "Prunes dead branches and unreachable statements in Java AST."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, JavaNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = JavaDeadCodeTransformer(trk, self.filename)
        return transformer.visit(target)
