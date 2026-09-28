"""Dead code and unreachable code elimination pass.

Phase 1E: Dead-code and unreachable-code elimination.
Features:
- Unreachable branch pruning:
    - if True: body else: dead -> body
    - if False: dead else: body -> body
- Unreachable statement removal:
    - Statements following unconditional return, raise, break, or continue in a block
- Dead assignment elimination:
    - Assignments to variables within functions that have zero uses, provided the assigned value is side-effect-free (pure)
- Redundant pass removal:
    - Eliminates superfluous 'pass' statements when other statements exist

Guarantees:
- Safe conservative analysis (never removes expressions with potential side effects like calls)
- Provenance recording with line/column tracking
"""

import ast
from typing import Any, List, Optional, Set

from analysis.dataflow import DataFlowAnalyzer, is_pure_expression
from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation
from languages.python.parser import PythonParser


TERMINATING_STATEMENTS = (ast.Return, ast.Raise, ast.Break, ast.Continue)


class DeadCodeTransformer(ast.NodeTransformer):
    """AST transformer that removes unreachable branches and dead assignments."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.tracker = tracker
        self.filename = filename
        self.num_removed = 0

    def visit_If(self, node: ast.If) -> Any:
        self.generic_visit(node)

        # Check for constant boolean conditions
        if isinstance(node.test, ast.Constant):
            test_val = bool(node.test.value)
            loc = PythonParser.get_location(node, self.filename)
            orig_repr = PythonParser.unparse(node)

            if test_val:
                # Condition is truthy: keep body, prune orelse
                self.tracker.record(
                    pass_name="DeadCodeElimination",
                    original=orig_repr,
                    transformed="[pruned false branch]",
                    confidence=Confidence.certain("Pruned dead branch with constant True condition", TransformationCategory.SIMPLIFIED),
                    location=loc,
                )
                self.num_removed += 1
                return node.body if node.body else [ast.Pass()]
            else:
                # Condition is falsy: keep orelse, prune body
                self.tracker.record(
                    pass_name="DeadCodeElimination",
                    original=orig_repr,
                    transformed="[pruned true branch]",
                    confidence=Confidence.certain("Pruned dead branch with constant False condition", TransformationCategory.SIMPLIFIED),
                    location=loc,
                )
                self.num_removed += 1
                return node.orelse if node.orelse else None

        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        # First process child nodes
        self.generic_visit(node)

        # Run dataflow analysis scoped to this function
        df = DataFlowAnalyzer(filename=self.filename).analyze(node)
        dead_defs = df.get_dead_definitions()

        if dead_defs:
            dead_nodes = {d.node for d in dead_defs}
            node.body = self._filter_dead_assignments(node.body, dead_nodes)

        # Remove unreachable statements after unconditional return/raise
        node.body = self._prune_unreachable_statements(node.body)
        if not node.body:
            node.body = [ast.Pass()]

        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        self.generic_visit(node)
        df = DataFlowAnalyzer(filename=self.filename).analyze(node)
        dead_defs = df.get_dead_definitions()

        if dead_defs:
            dead_nodes = {d.node for d in dead_defs}
            node.body = self._filter_dead_assignments(node.body, dead_nodes)

        node.body = self._prune_unreachable_statements(node.body)
        if not node.body:
            node.body = [ast.Pass()]

        return node

    def visit_Module(self, node: ast.Module) -> ast.AST:
        self.generic_visit(node)
        node.body = self._prune_unreachable_statements(node.body)
        return node

    def _filter_dead_assignments(self, stmts: List[ast.stmt], dead_nodes: Set[ast.AST]) -> List[ast.stmt]:
        """Filter out dead assignments while preserving provenance."""
        new_stmts = []
        for stmt in stmts:
            if stmt in dead_nodes:
                loc = PythonParser.get_location(stmt, self.filename)
                orig_repr = PythonParser.unparse(stmt)
                self.tracker.record(
                    pass_name="DeadCodeElimination",
                    original=orig_repr,
                    transformed="[removed unused assignment]",
                    confidence=Confidence.certain("Eliminated dead assignment with pure expression", TransformationCategory.SIMPLIFIED),
                    location=loc,
                )
                self.num_removed += 1
                continue
            new_stmts.append(stmt)
        return new_stmts

    def _prune_unreachable_statements(self, stmts: List[ast.stmt]) -> List[ast.stmt]:
        """Prune any statements that occur after a terminating statement in the same block."""
        new_stmts = []
        for i, stmt in enumerate(stmts):
            new_stmts.append(stmt)
            if isinstance(stmt, TERMINATING_STATEMENTS):
                unreachable = stmts[i + 1:]
                if unreachable:
                    loc = PythonParser.get_location(unreachable[0], self.filename)
                    orig_repr = "\n".join(PythonParser.unparse(s) for s in unreachable)
                    self.tracker.record(
                        pass_name="DeadCodeElimination",
                        original=orig_repr,
                        transformed="[pruned unreachable statements]",
                        confidence=Confidence.certain(
                            f"Removed {len(unreachable)} unreachable statement(s) following {type(stmt).__name__}",
                            TransformationCategory.SIMPLIFIED,
                        ),
                        location=loc,
                    )
                    self.num_removed += len(unreachable)
                break

        # Remove redundant 'pass' if other statements exist
        if len(new_stmts) > 1:
            filtered = [s for s in new_stmts if not isinstance(s, ast.Pass)]
            if filtered:
                new_stmts = filtered

        return new_stmts


class DeadCodeEliminationPass(Pass):
    """Pass that removes dead assignments, unreachable branches, and dead statements."""

    name = "DeadCodeElimination"
    description = "Eliminates unreachable branches, dead assignments, and post-termination code."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        if not isinstance(target, ast.AST):
            return target

        transformer = DeadCodeTransformer(tracker=tracker, filename=self.filename)
        return transformer.visit(target)
