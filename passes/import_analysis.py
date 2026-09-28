"""Import normalization pass for Python AST.

Phase 2: Advanced Python Obfuscation
Features:
- Normalizes aliased module calls: e.g. _b.b64decode(...) -> base64.b64decode(...)
- Normalizes aliased symbol calls: e.g. _dec(...) -> base64.b64decode(...)
- Provenance recording with line/column tracking
"""

import ast
from typing import Any, Optional

from analysis.imports import ImportAnalyzer, ResolvedTarget
from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation
from languages.python.parser import PythonParser


class ImportNormalizationTransformer(ast.NodeTransformer):
    """AST transformer that normalizes calls through aliases to canonical targets."""

    def __init__(self, analyzer: ImportAnalyzer, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.analyzer = analyzer
        self.tracker = tracker
        self.filename = filename
        self.num_normalized = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        resolved: Optional[ResolvedTarget] = self.analyzer.resolve_expr(node.func)
        if resolved and resolved.attribute:
            # Check if it was indeed aliased (i.e. not already canonical)
            orig_repr = PythonParser.unparse(node.func)
            canonical_repr = f"{resolved.module}.{resolved.attribute}"

            if orig_repr != canonical_repr:
                loc = PythonParser.get_location(node.func, self.filename)
                # Create canonical Attribute node: module.attribute
                new_func = ast.Attribute(
                    value=ast.Name(id=resolved.module, ctx=ast.Load()),
                    attr=resolved.attribute,
                    ctx=ast.Load(),
                )
                ast.copy_location(new_func, node.func)
                node.func = new_func

                self.tracker.record(
                    pass_name="ImportNormalization",
                    original=orig_repr,
                    transformed=canonical_repr,
                    confidence=Confidence.certain(
                        f"Normalized alias '{orig_repr}' to canonical '{canonical_repr}'",
                        TransformationCategory.SIMPLIFIED,
                    ),
                    location=loc,
                )
                self.num_normalized += 1

        return node


class ImportNormalizationPass(Pass):
    """Pass that normalizes aliased module and function calls to canonical paths."""

    name = "ImportNormalization"
    description = "Normalizes aliased imports and function pointers to canonical module calls."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        if not isinstance(target, ast.AST):
            return target

        analyzer = ImportAnalyzer().analyze(target)
        transformer = ImportNormalizationTransformer(analyzer=analyzer, tracker=tracker, filename=self.filename)
        return transformer.visit(target)
