"""Symbolic evaluation and algebraic simplification pass.

Per Section 10 of the Master Specification (Phase 4: Data Flow and Symbolic Analysis):
- Symbolic evaluation of expressions
- Propagates reaching definitions symbolically
- Folds arithmetic, bitwise, and XOR obfuscation chains
- Simplifies identity operations and self-canceling terms (x - x, (x ^ k) ^ k, (x + c1) - c2)
"""

from __future__ import annotations

import ast
from typing import Any, Dict, Optional

from analysis.reaching_definitions import ReachingDefinitionsAnalyzer, StmtUse
from analysis.symbolic import SymbolicConstant, SymbolicEvaluator, SymbolicValue
from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser


class SymbolicEvaluationTransformer(ast.NodeTransformer):
    """Transforms AST expressions by applying symbolic evaluation and algebraic simplification."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.tracker = tracker
        self.filename = filename
        self.analyzer = ReachingDefinitionsAnalyzer(filename=filename)
        self.evaluator = SymbolicEvaluator()
        self.changes_made = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        # Analyze reaching definitions inside function
        self.analyzer.analyze(node)
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.analyzer.analyze(node)
        self.generic_visit(node)
        return node

    def visit_Module(self, node: ast.Module) -> Any:
        self.analyzer.analyze(node)
        self.generic_visit(node)
        return node

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        self.generic_visit(node)
        return self._try_simplify_expression(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        self.generic_visit(node)
        return self._try_simplify_expression(node)

    def _try_simplify_expression(self, expr_node: ast.expr) -> ast.expr:
        """Attempt to symbolically evaluate and simplify the expression."""
        # Setup environment by checking reaching definitions for free variables
        env: Dict[str, SymbolicValue] = {}
        for child in ast.walk(expr_node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                # Look up matching use in analyzer
                matching_use = None
                for u in self.analyzer.uses:
                    if u.node is child:
                        matching_use = u
                        break
                if matching_use:
                    uniq_def = self.analyzer.get_unique_reaching_definition(matching_use)
                    if uniq_def and isinstance(uniq_def.value_node, ast.Constant):
                        env[child.id] = SymbolicConstant(uniq_def.value_node.value)

        evaluator = SymbolicEvaluator(env)
        simplified_ast = evaluator.evaluate_ast(expr_node)

        if simplified_ast is not None:
            orig_src = PythonParser.unparse(expr_node)
            new_src = PythonParser.unparse(simplified_ast)
            if orig_src != new_src:
                self.changes_made += 1
                loc = PythonParser.get_location(expr_node, self.filename)
                self.tracker.record(
                    pass_name="SymbolicEvaluation",
                    original=orig_src,
                    transformed=new_src,
                    confidence=Confidence.certain(
                        "Symbolically evaluated and simplified expression",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=loc,
                )
                return simplified_ast

        return expr_node


class SymbolicEvaluationPass(Pass):
    """Pass that applies symbolic evaluation to expressions across AST."""

    name = "SymbolicEvaluation"
    description = "Symbolically evaluates expressions, simplifies algebraic identities, and collapses XOR chains."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, ast.AST):
            return target
        trk = tracker if tracker is not None else ProvenanceTracker()
        transformer = SymbolicEvaluationTransformer(trk, self.filename)
        transformed = transformer.visit(target)
        ast.fix_missing_locations(transformed)
        return transformed
