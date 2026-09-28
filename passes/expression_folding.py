"""Expression folding pass for Python AST.

Phase 1B: Safe static expression folding.
Folds deterministic constant expressions without executing arbitrary code:
- Arithmetic: +, -, *, /, //, %, **
- Bitwise: &, |, ^, ~, <<, >>
- Logical / Comparisons: not, and, or, ==, !=, <, <=, >, >=, in, not in, is, is not
- Constant slicing and subscripting: e.g. "abc"[::-1], (1, 2, 3)[0]

Guarantees:
- Strict safety limits (e.g. bounded string multiplication, bounded powers)
- No eval() or exec()
- Full provenance recording
"""

import ast
import operator
from typing import Any, Callable, Dict, Optional, Tuple

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation
from languages.python.parser import PythonParser

# Maximum memory/length limits to prevent memory exhaustion attacks
MAX_STR_LEN = 65536
MAX_POW_EXP = 64
MAX_POW_BASE = 10000
MAX_SHIFT = 64

SAFE_BIN_OPS: Dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.BitOr: operator.or_,
    ast.BitAnd: operator.and_,
    ast.BitXor: operator.xor,
}

SAFE_UNARY_OPS: Dict[type, Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
    ast.Invert: operator.invert,
}

SAFE_CMP_OPS: Dict[type, Callable[[Any, Any], Any]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def is_safe_constant(node: ast.AST) -> bool:
    """Check if an AST node represents a safe immutable constant literal."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float, str, bytes, bool, type(None)))
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, (ast.UAdd, ast.USub)) and isinstance(node.operand, ast.Constant):
            return isinstance(node.operand.value, (int, float))
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(is_safe_constant(el) for el in node.elts)
    return False


def extract_constant_value(node: ast.AST) -> Any:
    """Extract Python literal value from constant AST node."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
            return -node.operand.value
        if isinstance(node.op, ast.UAdd) and isinstance(node.operand, ast.Constant):
            return node.operand.value
    if isinstance(node, ast.Tuple):
        return tuple(extract_constant_value(el) for el in node.elts)
    if isinstance(node, ast.List):
        return [extract_constant_value(el) for el in node.elts]
    raise ValueError(f"Not a constant node: {node}")


class ExpressionFolderTransformer(ast.NodeTransformer):
    """AST transformer that safely evaluates and folds constant expressions."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.tracker = tracker
        self.filename = filename
        self.num_folded = 0

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        # Bottom-up evaluation
        self.generic_visit(node)

        if not (is_safe_constant(node.left) and is_safe_constant(node.right)):
            return node

        op_type = type(node.op)
        if op_type not in SAFE_BIN_OPS:
            return node

        left_val = extract_constant_value(node.left)
        right_val = extract_constant_value(node.right)

        # Safety checks
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod):
            if right_val == 0:
                return node

        if op_type == ast.Pow:
            if not isinstance(left_val, (int, float)) or not isinstance(right_val, (int, float)):
                return node
            if abs(right_val) > MAX_POW_EXP or abs(left_val) > MAX_POW_BASE:
                return node

        if op_type in (ast.LShift, ast.RShift):
            if not isinstance(left_val, int) or not isinstance(right_val, int):
                return node
            if right_val < 0 or right_val > MAX_SHIFT:
                return node

        if op_type == ast.Mult:
            if isinstance(left_val, (str, bytes, tuple, list)) and isinstance(right_val, int):
                if right_val < 0 or len(left_val) * right_val > MAX_STR_LEN:
                    return node
            elif isinstance(right_val, (str, bytes, tuple, list)) and isinstance(left_val, int):
                if left_val < 0 or len(right_val) * left_val > MAX_STR_LEN:
                    return node

        if op_type == ast.Add:
            if isinstance(left_val, (str, bytes)) and isinstance(right_val, (str, bytes)):
                if len(left_val) + len(right_val) > MAX_STR_LEN:
                    return node

        try:
            fn = SAFE_BIN_OPS[op_type]
            result_val = fn(left_val, right_val)

            # Ensure result is a valid supported literal
            if not isinstance(result_val, (int, float, str, bytes, bool, type(None))):
                return node

            orig_repr = PythonParser.unparse(node)
            new_node = ast.Constant(value=result_val)
            ast.copy_location(new_node, node)

            loc = PythonParser.get_location(node, filename=self.filename)
            self.tracker.record(
                pass_name="ExpressionFolding",
                original=orig_repr,
                transformed=PythonParser.unparse(new_node),
                confidence=Confidence.certain("Constant binary expression folded", TransformationCategory.SIMPLIFIED),
                location=loc,
            )
            self.num_folded += 1
            return new_node
        except Exception:
            return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)

        if not is_safe_constant(node.operand):
            return node

        op_type = type(node.op)
        if op_type not in SAFE_UNARY_OPS:
            return node

        operand_val = extract_constant_value(node.operand)

        try:
            fn = SAFE_UNARY_OPS[op_type]
            result_val = fn(operand_val)

            if not isinstance(result_val, (int, float, str, bytes, bool, type(None))):
                return node

            orig_repr = PythonParser.unparse(node)
            new_node = ast.Constant(value=result_val)
            ast.copy_location(new_node, node)

            loc = PythonParser.get_location(node, filename=self.filename)
            self.tracker.record(
                pass_name="ExpressionFolding",
                original=orig_repr,
                transformed=PythonParser.unparse(new_node),
                confidence=Confidence.certain("Constant unary expression folded", TransformationCategory.SIMPLIFIED),
                location=loc,
            )
            self.num_folded += 1
            return new_node
        except Exception:
            return node

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)

        all_nodes = [node.left] + node.comparators
        if not all(is_safe_constant(n) for n in all_nodes):
            return node

        values = [extract_constant_value(n) for n in all_nodes]
        ops = [type(op) for op in node.ops]

        if any(op not in SAFE_CMP_OPS for op in ops):
            return node

        try:
            result = True
            for i, op in enumerate(ops):
                cmp_fn = SAFE_CMP_OPS[op]
                if not cmp_fn(values[i], values[i + 1]):
                    result = False
                    break

            orig_repr = PythonParser.unparse(node)
            new_node = ast.Constant(value=result)
            ast.copy_location(new_node, node)

            loc = PythonParser.get_location(node, filename=self.filename)
            self.tracker.record(
                pass_name="ExpressionFolding",
                original=orig_repr,
                transformed=PythonParser.unparse(new_node),
                confidence=Confidence.certain("Constant comparison folded", TransformationCategory.SIMPLIFIED),
                location=loc,
            )
            self.num_folded += 1
            return new_node
        except Exception:
            return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)

        if not all(is_safe_constant(val) for val in node.values):
            return node

        vals = [extract_constant_value(val) for val in node.values]
        try:
            if isinstance(node.op, ast.And):
                result = vals[0]
                for v in vals[1:]:
                    if not result:
                        break
                    result = v
            elif isinstance(node.op, ast.Or):
                result = vals[0]
                for v in vals[1:]:
                    if result:
                        break
                    result = v
            else:
                return node

            orig_repr = PythonParser.unparse(node)
            new_node = ast.Constant(value=result)
            ast.copy_location(new_node, node)

            loc = PythonParser.get_location(node, filename=self.filename)
            self.tracker.record(
                pass_name="ExpressionFolding",
                original=orig_repr,
                transformed=PythonParser.unparse(new_node),
                confidence=Confidence.certain("Constant boolean operation folded", TransformationCategory.SIMPLIFIED),
                location=loc,
            )
            self.num_folded += 1
            return new_node
        except Exception:
            return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        self.generic_visit(node)

        # Slicing/subscripting only on constant value and constant slice
        if not is_safe_constant(node.value):
            return node

        container = extract_constant_value(node.value)
        if not isinstance(container, (str, bytes, tuple, list)):
            return node

        # Handle slice or single index
        try:
            result_val: Any = None
            if isinstance(node.slice, ast.Constant):
                idx = node.slice.value
                if not isinstance(idx, int):
                    return node
                result_val = container[idx]
            elif isinstance(node.slice, ast.Slice):
                lower = extract_constant_value(node.slice.lower) if node.slice.lower and is_safe_constant(node.slice.lower) else None
                upper = extract_constant_value(node.slice.upper) if node.slice.upper and is_safe_constant(node.slice.upper) else None
                step = extract_constant_value(node.slice.step) if node.slice.step and is_safe_constant(node.slice.step) else None

                if node.slice.lower and lower is None:
                    return node
                if node.slice.upper and upper is None:
                    return node
                if node.slice.step and step is None:
                    return node

                result_val = container[slice(lower, upper, step)]
            else:
                return node

            if not isinstance(result_val, (int, float, str, bytes, bool, type(None))):
                return node

            orig_repr = PythonParser.unparse(node)
            new_node = ast.Constant(value=result_val)
            ast.copy_location(new_node, node)

            loc = PythonParser.get_location(node, filename=self.filename)
            self.tracker.record(
                pass_name="ExpressionFolding",
                original=orig_repr,
                transformed=PythonParser.unparse(new_node),
                confidence=Confidence.certain("Constant subscript/slice folded", TransformationCategory.SIMPLIFIED),
                location=loc,
            )
            self.num_folded += 1
            return new_node
        except Exception:
            return node


class ExpressionFoldingPass(Pass):
    """Pass that simplifies constant expressions within Python AST."""

    name = "ExpressionFolding"
    description = "Folds compile-time constant arithmetic, logical, and string expressions."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        if not isinstance(target, ast.AST):
            return target

        transformer = ExpressionFolderTransformer(tracker=tracker, filename=self.filename)
        return transformer.visit(target)
