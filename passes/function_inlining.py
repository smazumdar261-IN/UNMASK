"""Function inlining pass for Python AST.

Phase 2: Advanced Python Obfuscation
Features:
- Inlines constant-returning functions: def key(): return 'XYZ' -> 'XYZ'
- Inlines single-return wrapper functions: def wrap(x): return base64.b64decode(x)
- Substitutes argument expressions safely into wrapper return bodies
- Provenance recording with exact call locations
"""

import ast
import copy
from typing import Any, Dict, Optional

from analysis.callgraph import CallGraphAnalyzer, FunctionSignature
from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation
from languages.python.parser import PythonParser


class ParameterSubstitutor(ast.NodeTransformer):
    """Substitutes formal parameter identifiers with actual argument AST nodes."""

    def __init__(self, mapping: Dict[str, ast.expr]) -> None:
        super().__init__()
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if isinstance(node.ctx, ast.Load) and node.id in self.mapping:
            replacement = copy.deepcopy(self.mapping[node.id])
            ast.copy_location(replacement, node)
            return replacement
        return node


class FunctionInliningTransformer(ast.NodeTransformer):
    """AST transformer that inlines calls to simple wrapper and constant functions."""

    def __init__(self, analyzer: CallGraphAnalyzer, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.analyzer = analyzer
        self.tracker = tracker
        self.filename = filename
        self.num_inlined = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        if not isinstance(node.func, ast.Name):
            return node

        fn_name = node.func.id
        if fn_name not in self.analyzer.functions:
            return node

        sig: FunctionSignature = self.analyzer.functions[fn_name]

        # Case 1: Constant return with no parameters
        if sig.is_constant_return and len(sig.params) == 0 and len(node.args) == 0:
            loc = PythonParser.get_location(node, self.filename)
            orig_repr = PythonParser.unparse(node)
            new_node = ast.Constant(value=sig.constant_return_val)
            ast.copy_location(new_node, node)

            self.tracker.record(
                pass_name="FunctionInlining",
                original=orig_repr,
                transformed=repr(sig.constant_return_val),
                confidence=Confidence.certain(f"Inlined constant-returning function '{fn_name}()'", TransformationCategory.SIMPLIFIED),
                location=loc,
            )
            self.num_inlined += 1
            return new_node

        # Case 2: Simple wrapper function with matching positional argument count
        if sig.is_simple_wrapper and sig.return_expr is not None and len(node.args) == len(sig.params) and not node.keywords:
            loc = PythonParser.get_location(node, self.filename)
            orig_repr = PythonParser.unparse(node)

            param_map = dict(zip(sig.params, node.args))
            substitutor = ParameterSubstitutor(param_map)
            inlined_expr = substitutor.visit(copy.deepcopy(sig.return_expr))
            ast.copy_location(inlined_expr, node)

            self.tracker.record(
                pass_name="FunctionInlining",
                original=orig_repr,
                transformed=PythonParser.unparse(inlined_expr),
                confidence=Confidence.certain(f"Inlined wrapper function '{fn_name}()'", TransformationCategory.SIMPLIFIED),
                location=loc,
            )
            self.num_inlined += 1
            return inlined_expr

        return node


class FunctionInliningPass(Pass):
    """Pass that inlines pure, simple wrapper functions and constant generators."""

    name = "FunctionInlining"
    description = "Inlines calls to constant-returning and single-expression wrapper functions."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        if not isinstance(target, ast.AST):
            return target

        analyzer = CallGraphAnalyzer(filename=self.filename).analyze(target)
        transformer = FunctionInliningTransformer(analyzer=analyzer, tracker=tracker, filename=self.filename)
        return transformer.visit(target)
