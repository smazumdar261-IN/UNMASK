"""Dynamic decoder unmasking engine.

Per Section 18:
Identifies standalone obfuscated decoder routines and unmasks their output
safely within the isolated SecureSandbox.
Operates on AST trees or Common IR.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set, Tuple

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation
from dynamic.policy import ExecutionPolicy, SandboxResult
from dynamic.sandbox import SecureSandbox
from languages.python.parser import PythonParser


def _is_constant_ast(node: ast.AST) -> bool:
    """Check if an AST node evaluates directly to a literal constant."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple)):
        return all(_is_constant_ast(el) for el in node.elts)
    if isinstance(node, ast.Dict):
        return all(_is_constant_ast(k) for k in node.keys if k) and all(_is_constant_ast(v) for v in node.values)
    return False


def _extract_constant_value(node: ast.AST) -> Any:
    """Extract Python literal value from constant AST node."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_extract_constant_value(el) for el in node.elts]
    if isinstance(node, ast.Dict):
        return {
            _extract_constant_value(k): _extract_constant_value(v)
            for k, v in zip(node.keys, node.values)
            if k is not None
        }
    return None


class DynamicDecoderUnmaskerTransformer(ast.NodeTransformer):
    """AST Transformer that replaces sandboxed function calls with evaluated constants."""

    def __init__(
        self,
        function_defs: Dict[str, ast.FunctionDef],
        sandbox: SecureSandbox,
        tracker: Optional[ProvenanceTracker] = None,
    ) -> None:
        self.function_defs = function_defs
        self.sandbox = sandbox
        self.tracker = tracker
        self.unmasked_count: int = 0
        self.unmasked_details: List[Dict[str, Any]] = []

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        # Check if callee is a known local function definition
        if isinstance(node.func, ast.Name) and node.func.id in self.function_defs:
            fn_name = node.func.id
            fn_def = self.function_defs[fn_name]

            # All positional arguments must be constant literals
            if all(_is_constant_ast(arg) for arg in node.args):
                arg_values = tuple(_extract_constant_value(arg) for arg in node.args)

                # Prepare standalone code containing the function definition
                fn_source = ast.unparse(fn_def)
                orig_call_str = ast.unparse(node)

                # Execute in sandbox
                result: SandboxResult = self.sandbox.run_function(
                    code=fn_source,
                    func_name=fn_name,
                    args=arg_values,
                )

                if result.success and result.return_value is not None:
                    ret_val = result.return_value
                    # Only allow primitive, immutable constants
                    if isinstance(ret_val, (str, int, float, bool, bytes)):
                        self.unmasked_count += 1
                        loc = PythonParser.get_location(node)

                        record_info = {
                            "function": fn_name,
                            "original_call": orig_call_str,
                            "result": ret_val,
                            "execution_time": result.execution_time,
                            "trace_steps": result.details.get("total_steps", 0),
                        }
                        self.unmasked_details.append(record_info)

                        replacement = ast.Constant(value=ret_val)
                        ast.copy_location(replacement, node)

                        if self.tracker:
                            self.tracker.record(
                                pass_name="DynamicDecoderUnmasker",
                                original=orig_call_str,
                                transformed=ast.unparse(replacement),
                                confidence=Confidence.high(
                                    reason=f"Unmasked dynamic decoder '{fn_name}' via isolated sandbox execution ({result.execution_time*1000:.1f}ms)",
                                    category=TransformationCategory.RECOVERED,
                                ),
                                location=loc,
                            )
                        return replacement

        return node


class DynamicDecoderUnmasker(Pass):
    """Dynamic deobfuscation pass leveraging the isolated SecureSandbox."""

    name = "DynamicDecoderUnmasker"
    description = "Executes pure decoder functions in an isolated sandbox to unmask hidden payloads"

    def __init__(self, policy: Optional[ExecutionPolicy] = None) -> None:
        self.policy = policy or ExecutionPolicy()
        self.sandbox = SecureSandbox(policy=self.policy)
        self.last_results: List[Dict[str, Any]] = []

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        if not isinstance(target, ast.AST):
            # Dynamic execution pass for Python AST
            return target

        # 1. Harvest local function definitions
        fn_defs: Dict[str, ast.FunctionDef] = {}
        for node in ast.walk(target):
            if isinstance(node, ast.FunctionDef):
                fn_defs[node.name] = node

        if not fn_defs:
            return target

        transformer = DynamicDecoderUnmaskerTransformer(
            function_defs=fn_defs,
            sandbox=self.sandbox,
            tracker=tracker,
        )

        transformed = transformer.visit(target)
        ast.fix_missing_locations(transformed)
        self.last_results = transformer.unmasked_details
        return transformed
