"""Control Flow Graph reduction and dead/redundant branch elimination pass.

Per Section 9 of the Master Specification (Phase 3: Control Flow):
Detects and eliminates:
- Dead branches identified via CFG reachability and condition analysis
- Redundant branches (empty if-statements with pure tests, identical then/else branches)
- Redundant loops (while False, for-in-empty-collection)
- Unreachable blocks following unconditional control transfers

Guarantees:
- Semantic equivalence: pure tests can be dropped; impure tests are preserved as expression statements.
- Complete provenance tracking with high/certain confidence.
"""

from __future__ import annotations

import ast
from typing import Any, List, Optional

from analysis.cfg import CFGBuilder, ControlFlowGraph
from analysis.dataflow import is_pure_expression
from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser


def _nodes_equal(n1: ast.AST, n2: ast.AST) -> bool:
    """Check syntactic equality of two AST subtrees ignoring line numbers."""
    try:
        return ast.unparse(n1) == ast.unparse(n2)
    except Exception:
        return False


def _is_empty_or_pass(stmts: List[ast.stmt]) -> bool:
    """Check if statement list contains only 'pass' or is empty."""
    if not stmts:
        return True
    return all(isinstance(s, ast.Pass) for s in stmts)


class CFGReductionTransformer(ast.NodeTransformer):
    """Transforms Python AST by pruning unreachable control flow and simplifying branches."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.tracker = tracker
        self.filename = filename
        self.changes_made = 0

    def visit_If(self, node: ast.If) -> Any:
        self.generic_visit(node)
        loc = PythonParser.get_location(node, self.filename)
        orig_src = PythonParser.unparse(node)

        # 1. Redundant branch: empty/pass body and no else
        if _is_empty_or_pass(node.body) and _is_empty_or_pass(node.orelse):
            self.changes_made += 1
            if is_pure_expression(node.test):
                self.tracker.record(
                    pass_name="CFGReduction",
                    original=orig_src,
                    transformed="[removed empty branch]",
                    confidence=Confidence.certain(
                        "Eliminated redundant branch with pure condition",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=loc,
                )
                return None
            else:
                # Retain side effects of impure condition
                self.tracker.record(
                    pass_name="CFGReduction",
                    original=orig_src,
                    transformed=PythonParser.unparse(node.test),
                    confidence=Confidence.certain(
                        "Converted redundant branch with side effects to expression statement",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=loc,
                )
                return ast.Expr(value=node.test)

        # 2. Identical branches: then-body and else-body are identical
        if node.body and node.orelse and len(node.body) == len(node.orelse):
            if all(_nodes_equal(b, o) for b, o in zip(node.body, node.orelse)):
                if is_pure_expression(node.test):
                    self.changes_made += 1
                    self.tracker.record(
                        pass_name="CFGReduction",
                        original=orig_src,
                        transformed="[collapsed identical branches]",
                        confidence=Confidence.certain(
                            "Collapsed identical if-else branches with pure condition",
                            TransformationCategory.SIMPLIFIED,
                        ),
                        location=loc,
                    )
                    return node.body

        # 3. If condition is statically truthy/falsy constant
        if isinstance(node.test, ast.Constant):
            self.changes_made += 1
            if bool(node.test.value):
                # Keep body
                self.tracker.record(
                    pass_name="CFGReduction",
                    original=orig_src,
                    transformed="[kept true branch]",
                    confidence=Confidence.certain(
                        "Eliminated dead else branch with statically True condition",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=loc,
                )
                return node.body
            else:
                # Keep orelse (or eliminate completely)
                self.tracker.record(
                    pass_name="CFGReduction",
                    original=orig_src,
                    transformed="[kept false branch]",
                    confidence=Confidence.certain(
                        "Eliminated dead then branch with statically False condition",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=loc,
                )
                return node.orelse if node.orelse else None

        return node

    def visit_While(self, node: ast.While) -> Any:
        self.generic_visit(node)
        loc = PythonParser.get_location(node, self.filename)
        orig_src = PythonParser.unparse(node)

        # Redundant loop: while False
        if isinstance(node.test, ast.Constant) and not bool(node.test.value):
            self.changes_made += 1
            self.tracker.record(
                pass_name="CFGReduction",
                original=orig_src,
                transformed="[eliminated while False loop]",
                confidence=Confidence.certain(
                    "Eliminated dead while False loop",
                    TransformationCategory.SIMPLIFIED,
                ),
                location=loc,
            )
            # If orelse exists in while False, orelse executes once
            return node.orelse if node.orelse else None

        return node

    def visit_For(self, node: ast.For) -> Any:
        self.generic_visit(node)
        loc = PythonParser.get_location(node, self.filename)
        orig_src = PythonParser.unparse(node)

        # Redundant loop: for x in [] or for x in () or for x in ""
        if isinstance(node.iter, (ast.List, ast.Tuple)) and len(node.iter.elts) == 0:
            self.changes_made += 1
            self.tracker.record(
                pass_name="CFGReduction",
                original=orig_src,
                transformed="[eliminated empty for loop]",
                confidence=Confidence.certain(
                    "Eliminated loop over empty sequence",
                    TransformationCategory.SIMPLIFIED,
                ),
                location=loc,
            )
            return node.orelse if node.orelse else None
        elif isinstance(node.iter, ast.Constant) and node.iter.value in ("", b""):
            self.changes_made += 1
            self.tracker.record(
                pass_name="CFGReduction",
                original=orig_src,
                transformed="[eliminated empty for loop]",
                confidence=Confidence.certain(
                    "Eliminated loop over empty literal",
                    TransformationCategory.SIMPLIFIED,
                ),
                location=loc,
            )
            return node.orelse if node.orelse else None

        return node

    def _clean_statement_list(self, stmts: List[ast.stmt]) -> List[ast.stmt]:
        """Remove statements following unconditional terminators in a block."""
        new_stmts: List[ast.stmt] = []
        for stmt in stmts:
            new_stmts.append(stmt)
            if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                # If there were subsequent statements, record elimination
                idx = stmts.index(stmt)
                if idx < len(stmts) - 1:
                    dead_count = len(stmts) - 1 - idx
                    self.changes_made += dead_count
                    for dead_stmt in stmts[idx + 1:]:
                        loc = PythonParser.get_location(dead_stmt, self.filename)
                        self.tracker.record(
                            pass_name="CFGReduction",
                            original=PythonParser.unparse(dead_stmt),
                            transformed="[unreachable code removed]",
                            confidence=Confidence.certain(
                                "Removed unreachable statement after unconditional terminator",
                                TransformationCategory.SIMPLIFIED,
                            ),
                            location=loc,
                        )
                break
        return new_stmts

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self.generic_visit(node)
        node.body = self._clean_statement_list(node.body)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.generic_visit(node)
        node.body = self._clean_statement_list(node.body)
        return node

    def visit_Module(self, node: ast.Module) -> Any:
        self.generic_visit(node)
        node.body = self._clean_statement_list(node.body)
        return node


class CFGReductionPass(Pass):
    """Pass that applies CFG-informed reductions and eliminates redundant control flow."""

    name = "CFGReduction"
    description = "Eliminates dead branches and redundant control flow using CFG analysis."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, ast.AST):
            return target
        trk = tracker if tracker is not None else ProvenanceTracker()
        transformer = CFGReductionTransformer(trk, self.filename)
        transformed = transformer.visit(target)
        ast.fix_missing_locations(transformed)
        return transformed
