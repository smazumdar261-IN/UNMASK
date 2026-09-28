"""Type annotation pass for inferable functions and variables.

Per Section 10 of the Master Specification (Phase 4: Data Flow and Symbolic Analysis):
- Automatically applies type hints where inferable with certainty
- Annotates function return types when all return statements agree
- Annotates parameters with known constant default values
- Never speculates: preserves unannotated state if types are dynamic or ambiguous
"""

from __future__ import annotations

import ast
from typing import Any, Optional

from analysis.type_inference import TypeInferenceEngine
from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser


class TypeAnnotationTransformer(ast.NodeTransformer):
    """AST transformer that adds type annotations to functions and parameters where inferable."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.tracker = tracker
        self.filename = filename
        self.engine = TypeInferenceEngine()
        self.annotations_added = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self.generic_visit(node)
        self._annotate_function(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.generic_visit(node)
        self._annotate_function(node)
        return node

    def _annotate_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Inspect and annotate return type and default parameter types."""
        # 1. Infer Parameter Types for parameters with default values
        # In Python AST, args.defaults align with the last N positional args
        num_defaults = len(node.args.defaults)
        if num_defaults > 0:
            defaulted_args = node.args.args[-num_defaults:]
            for arg, default in zip(defaulted_args, node.args.defaults):
                if arg.annotation is None:
                    arg_type = self.engine.infer_expression_type(default)
                    if arg_type and arg_type != "None":
                        arg.annotation = ast.Name(id=arg_type, ctx=ast.Load())
                        self.annotations_added += 1
                        loc = PythonParser.get_location(arg, self.filename)
                        self.tracker.record(
                            pass_name="TypeAnnotation",
                            original=f"{arg.arg}",
                            transformed=f"{arg.arg}: {arg_type}",
                            confidence=Confidence.certain(
                                f"Inferred parameter type hint '{arg_type}' from default value for '{arg.arg}'",
                                TransformationCategory.INFERRED,
                            ),
                            location=loc,
                        )

        # 2. Infer Return Type if not already annotated
        if node.returns is None:
            ret_type = self.engine.infer_function_return_type(node)
            if ret_type:
                loc = PythonParser.get_location(node, self.filename)
                if ret_type == "None":
                    node.returns = ast.Constant(value=None)
                else:
                    node.returns = ast.Name(id=ret_type, ctx=ast.Load())

                self.annotations_added += 1
                self.tracker.record(
                    pass_name="TypeAnnotation",
                    original=f"def {node.name}(...)",
                    transformed=f"def {node.name}(...) -> {ret_type}",
                    confidence=Confidence.certain(
                        f"Inferred return type hint '{ret_type}' for function '{node.name}'",
                        TransformationCategory.INFERRED,
                    ),
                    location=loc,
                )


class TypeAnnotationPass(Pass):
    """Pass that infers and applies type hints across AST."""

    name = "TypeAnnotation"
    description = "Infers and applies type hints for function return values and parameters."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, ast.AST):
            return target
        trk = tracker if tracker is not None else ProvenanceTracker()
        transformer = TypeAnnotationTransformer(trk, self.filename)
        transformed = transformer.visit(target)
        ast.fix_missing_locations(transformed)
        return transformed
