"""Expression simplification and redundant code elimination pass.

Phase 2: Advanced Python Obfuscation
Features:
- Arithmetic identity simplifications:
    - x + 0, 0 + x -> x
    - x - 0 -> x
    - x * 1, 1 * x -> x
    - x // 1 -> x
- Bitwise identity simplifications:
    - x ^ 0, 0 ^ x -> x
    - x | 0, 0 | x -> x
    - x & -1, -1 & x -> x
    - x ^ x -> 0 (when x is pure identifier)
- Boolean identity simplifications:
    - x and True, True and x -> x
    - x or False, False or x -> x
- Double reversal elimination:
    - s[::-1][::-1] -> s
- Redundant type casting:
    - str('literal') -> 'literal'
    - bytes(b'literal') -> b'literal'
    - int(123) -> 123
    - bool(True) -> True

Guarantees:
- Safe conservative evaluation
- Provenance recording for every simplified expression
"""

import ast
from typing import Any, Optional

from analysis.dataflow import is_pure_expression
from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation
from languages.python.parser import PythonParser
from passes.expression_folding import extract_constant_value, is_safe_constant


class SimplificationTransformer(ast.NodeTransformer):
    """AST transformer that removes identity operations and redundant expressions."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.tracker = tracker
        self.filename = filename
        self.num_simplified = 0

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)

        # 1. Addition / Subtraction by 0
        if isinstance(node.op, ast.Add):
            if is_safe_constant(node.right) and extract_constant_value(node.right) == 0:
                return self._simplify_to(node, node.left, "x + 0 -> x")
            if is_safe_constant(node.left) and extract_constant_value(node.left) == 0:
                return self._simplify_to(node, node.right, "0 + x -> x")

        if isinstance(node.op, ast.Sub):
            if is_safe_constant(node.right) and extract_constant_value(node.right) == 0:
                return self._simplify_to(node, node.left, "x - 0 -> x")

        # 2. Multiplication / Division by 1
        if isinstance(node.op, ast.Mult):
            if is_safe_constant(node.right) and extract_constant_value(node.right) == 1:
                return self._simplify_to(node, node.left, "x * 1 -> x")
            if is_safe_constant(node.left) and extract_constant_value(node.left) == 1:
                return self._simplify_to(node, node.right, "1 * x -> x")

        if isinstance(node.op, ast.FloorDiv):
            if is_safe_constant(node.right) and extract_constant_value(node.right) == 1:
                return self._simplify_to(node, node.left, "x // 1 -> x")

        # 3. Bitwise XOR / OR with 0
        if isinstance(node.op, (ast.BitXor, ast.BitOr)):
            if is_safe_constant(node.right) and extract_constant_value(node.right) == 0:
                return self._simplify_to(node, node.left, "x ^/| 0 -> x")
            if is_safe_constant(node.left) and extract_constant_value(node.left) == 0:
                return self._simplify_to(node, node.right, "0 ^/| x -> x")

        # 4. Bitwise AND with -1 (~0)
        if isinstance(node.op, ast.BitAnd):
            if is_safe_constant(node.right) and extract_constant_value(node.right) == -1:
                return self._simplify_to(node, node.left, "x & -1 -> x")
            if is_safe_constant(node.left) and extract_constant_value(node.left) == -1:
                return self._simplify_to(node, node.right, "-1 & x -> x")

        # 5. XOR of self: x ^ x -> 0 (for pure identifiers)
        if isinstance(node.op, ast.BitXor) and isinstance(node.left, ast.Name) and isinstance(node.right, ast.Name):
            if node.left.id == node.right.id:
                new_node = ast.Constant(value=0)
                return self._simplify_to(node, new_node, "x ^ x -> 0")

        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)

        # x or False -> x, x and True -> x
        if isinstance(node.op, ast.Or):
            new_vals = [v for v in node.values if not (is_safe_constant(v) and extract_constant_value(v) is False)]
            if len(new_vals) == 1:
                return self._simplify_to(node, new_vals[0], "x or False -> x")
            elif new_vals and len(new_vals) < len(node.values):
                node.values = new_vals
                return node

        if isinstance(node.op, ast.And):
            new_vals = [v for v in node.values if not (is_safe_constant(v) and extract_constant_value(v) is True)]
            if len(new_vals) == 1:
                return self._simplify_to(node, new_vals[0], "x and True -> x")
            elif new_vals and len(new_vals) < len(node.values):
                node.values = new_vals
                return node

        return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        self.generic_visit(node)

        # Check for double reversal: x[::-1][::-1] -> x
        if self._is_reverse_slice(node.slice) and isinstance(node.value, ast.Subscript):
            inner = node.value
            if self._is_reverse_slice(inner.slice):
                return self._simplify_to(node, inner.value, "s[::-1][::-1] -> s")

        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        # Redundant type casting on constants of the same type:
        # str('abc') -> 'abc', bytes(b'abc') -> b'abc', int(123) -> 123
        if isinstance(node.func, ast.Name) and len(node.args) == 1 and not node.keywords:
            fn_name = node.func.id
            arg = node.args[0]
            if isinstance(arg, ast.Constant):
                val = arg.value
                if fn_name == "str" and isinstance(val, str):
                    return self._simplify_to(node, arg, "str('...') -> '...'")
                if fn_name == "bytes" and isinstance(val, bytes):
                    return self._simplify_to(node, arg, "bytes(b'...') -> b'...'")
                if fn_name == "int" and isinstance(val, int) and not isinstance(val, bool):
                    return self._simplify_to(node, arg, "int(N) -> N")
                if fn_name == "bool" and isinstance(val, bool):
                    return self._simplify_to(node, arg, "bool(B) -> B")

        return node

    def _is_reverse_slice(self, slice_node: ast.AST) -> bool:
        """Check if slice represents [::-1]."""
        if isinstance(slice_node, ast.Slice):
            if slice_node.lower is None and slice_node.upper is None:
                if isinstance(slice_node.step, ast.Constant) and slice_node.step.value == -1:
                    return True
                # Or UnaryOp(-1)
                if isinstance(slice_node.step, ast.UnaryOp) and isinstance(slice_node.step.op, ast.USub):
                    if isinstance(slice_node.step.operand, ast.Constant) and slice_node.step.operand.value == 1:
                        return True
        return False

    def _simplify_to(self, orig_node: ast.AST, new_node: ast.AST, reason: str) -> ast.AST:
        ast.copy_location(new_node, orig_node)
        loc = PythonParser.get_location(orig_node, self.filename)
        self.tracker.record(
            pass_name="Simplification",
            original=PythonParser.unparse(orig_node),
            transformed=PythonParser.unparse(new_node),
            confidence=Confidence.certain(f"Applied identity simplification: {reason}", TransformationCategory.SIMPLIFIED),
            location=loc,
        )
        self.num_simplified += 1
        return new_node


class SimplificationPass(Pass):
    """Pass that eliminates redundant identity operations and expressions."""

    name = "Simplification"
    description = "Removes algebraic identities (x + 0, x * 1, x ^ 0), redundant casts, and double reversals."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        if not isinstance(target, ast.AST):
            return target

        transformer = SimplificationTransformer(tracker=tracker, filename=self.filename)
        return transformer.visit(target)
