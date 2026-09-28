"""Type inference engine for Python AST expressions and functions.

Per Section 10 of the Master Specification (Phase 4: Data Flow and Symbolic Analysis):
- Infer types for literals, expressions, variables, and function returns
- Safe conservative typing (only assigns type hints when provably invariant)
- Infers primitive types (int, float, str, bytes, bool, None) and collections (list, dict, set, tuple)
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set


class TypeInferenceEngine:
    """Infers types of Python expressions and functions from AST structure."""

    def __init__(self) -> None:
        # Known variable types in current lexical scope
        self.var_types: Dict[str, str] = {}

    def infer_expression_type(self, node: ast.expr) -> Optional[str]:
        """Infer the type name of an AST expression, or None if indeterminate."""
        # 1. Constants
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "bool"
            if isinstance(node.value, int):
                return "int"
            if isinstance(node.value, float):
                return "float"
            if isinstance(node.value, str):
                return "str"
            if isinstance(node.value, bytes):
                return "bytes"
            if node.value is None:
                return "None"

        # 2. Identifiers
        if isinstance(node, ast.Name):
            return self.var_types.get(node.id)

        # 3. Collections
        if isinstance(node, ast.List):
            return "list"
        if isinstance(node, ast.Dict):
            return "dict"
        if isinstance(node, ast.Set):
            return "set"
        if isinstance(node, ast.Tuple):
            return "tuple"

        # 4. Comparisons and booleans
        if isinstance(node, ast.Compare):
            return "bool"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return "bool"

        # 5. Unary operations
        if isinstance(node, ast.UnaryOp):
            operand_type = self.infer_expression_type(node.operand)
            if isinstance(node.op, (ast.USub, ast.UAdd)):
                return operand_type if operand_type in ("int", "float") else None
            if isinstance(node.op, ast.Invert):
                return "int" if operand_type == "int" else None

        # 6. Binary operations
        if isinstance(node, ast.BinOp):
            left_t = self.infer_expression_type(node.left)
            right_t = self.infer_expression_type(node.right)

            # Division always produces float in Python 3
            if isinstance(node.op, ast.Div):
                if left_t in ("int", "float") and right_t in ("int", "float"):
                    return "float"

            # Bitwise ops on ints produce int
            if isinstance(node.op, (ast.BitXor, ast.BitAnd, ast.BitOr, ast.LShift, ast.RShift)):
                if left_t == "int" and right_t == "int":
                    return "int"

            # Arithmetic ops
            if isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod, ast.Pow)):
                if left_t == "int" and right_t == "int":
                    return "int"
                if "float" in (left_t, right_t) and all(t in ("int", "float") for t in (left_t, right_t)):
                    return "float"
                if isinstance(node.op, ast.Add) and left_t == "str" and right_t == "str":
                    return "str"
                if isinstance(node.op, ast.Add) and left_t == "bytes" and right_t == "bytes":
                    return "bytes"

        # 7. Function and Method calls
        if isinstance(node, ast.Call):
            return self._infer_call_type(node)

        return None

    def _infer_call_type(self, node: ast.Call) -> Optional[str]:
        """Infer return type of standard known builtin and library calls."""
        # Builtin direct functions
        if isinstance(node.func, ast.Name):
            fname = node.func.id
            if fname in ("len", "ord", "id", "int"):
                return "int"
            if fname in ("chr", "str", "repr", "ascii"):
                return "str"
            if fname in ("bytes", "bytearray"):
                return "bytes"
            if fname in ("bool", "isinstance", "issubclass", "hasattr", "callable"):
                return "bool"
            if fname == "float":
                return "float"
            if fname in ("list", "sorted"):
                return "list"
            if fname == "dict":
                return "dict"
            if fname == "set":
                return "set"
            if fname == "tuple":
                return "tuple"

        # Method calls: e.g. x.decode('utf-8'), x.encode('utf-8'), s.join(...)
        if isinstance(node.func, ast.Attribute):
            mname = node.func.attr
            if mname == "decode":
                return "str"
            if mname == "encode":
                return "bytes"
            if mname == "join":
                return "str"
            if mname in ("split", "splitlines"):
                return "list"
            if mname in ("upper", "lower", "strip", "replace", "format"):
                return "str"
            if mname in ("fromhex", "b64decode", "unhexlify", "decompress"):
                return "bytes"

        return None

    def infer_function_return_type(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> Optional[str]:
        """Infer the unified return type of a function if all return paths agree."""
        saved_types = dict(self.var_types)

        # Seed parameter types from annotations or defaults
        num_defaults = len(func_node.args.defaults)
        defaulted_args = func_node.args.args[-num_defaults:] if num_defaults > 0 else []
        for arg, default in zip(defaulted_args, func_node.args.defaults):
            t = self.infer_expression_type(default)
            if t:
                self.var_types[arg.arg] = t
        for arg in func_node.args.args:
            if arg.annotation and isinstance(arg.annotation, ast.Name):
                self.var_types[arg.arg] = arg.annotation.id

        return_types: Set[str] = set()
        has_return = False

        for stmt in ast.walk(func_node):
            if isinstance(stmt, ast.Return):
                has_return = True
                if stmt.value is None:
                    return_types.add("None")
                else:
                    t = self.infer_expression_type(stmt.value)
                    if t:
                        return_types.add(t)
                    else:
                        # Ambiguous return expression
                        self.var_types = saved_types
                        return None

        self.var_types = saved_types

        if not has_return:
            return "None"

        if len(return_types) == 1:
            return next(iter(return_types))

        return None
