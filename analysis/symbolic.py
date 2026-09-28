"""Symbolic evaluation and algebraic simplification engine.

Per Section 10 of the Master Specification (Phase 4: Data Flow and Symbolic Analysis):
- Symbolic expression representation (constants, variables, operations)
- Algebraic simplification and canonicalization
- XOR chain folding and key cancellation (e.g. (x ^ k) ^ k -> x)
- Additive/multiplicative cancellation (e.g. (x + 5) - x -> 5, (x + 2) + 3 -> x + 5)
- Conversion between Python AST and symbolic structures
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Set, Tuple


class SymbolicValue(ABC):
    """Base class for all symbolic values and expressions."""

    @abstractmethod
    def is_constant(self) -> bool:
        """True if this symbolic value represents a known compile-time constant."""
        pass

    @abstractmethod
    def simplify(self) -> "SymbolicValue":
        """Apply algebraic reduction rules and return a simplified symbolic value."""
        pass

    @abstractmethod
    def to_ast(self) -> ast.expr:
        """Convert this symbolic value back to a Python AST expression."""
        pass

    @abstractmethod
    def get_variables(self) -> Set[str]:
        """Return the set of free variable names referenced in this expression."""
        pass


class SymbolicConstant(SymbolicValue):
    """Represents a concrete constant value (int, str, bytes, bool, float, None)."""

    def __init__(self, value: Any) -> None:
        self.value: Any = value

    def is_constant(self) -> bool:
        return True

    def simplify(self) -> "SymbolicValue":
        return self

    def to_ast(self) -> ast.expr:
        if isinstance(self.value, int) and self.value < 0:
            return ast.UnaryOp(op=ast.USub(), operand=ast.Constant(value=abs(self.value)))
        return ast.Constant(value=self.value)

    def get_variables(self) -> Set[str]:
        return set()

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, SymbolicConstant):
            return type(self.value) == type(other.value) and self.value == other.value
        return False

    def __hash__(self) -> int:
        try:
            return hash((type(self.value), self.value))
        except TypeError:
            return id(self.value)

    def __repr__(self) -> str:
        return f"SymConst({self.value!r})"


class SymbolicVariable(SymbolicValue):
    """Represents a symbolic identifier / variable."""

    def __init__(self, name: str) -> None:
        self.name: str = name

    def is_constant(self) -> bool:
        return False

    def simplify(self) -> "SymbolicValue":
        return self

    def to_ast(self) -> ast.expr:
        return ast.Name(id=self.name, ctx=ast.Load())

    def get_variables(self) -> Set[str]:
        return {self.name}

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, SymbolicVariable):
            return self.name == other.name
        return False

    def __hash__(self) -> int:
        return hash(("var", self.name))

    def __repr__(self) -> str:
        return f"SymVar({self.name})"


class SymbolicUnaryOp(SymbolicValue):
    """Represents a unary operation on a symbolic expression."""

    def __init__(self, op: str, operand: SymbolicValue) -> None:
        self.op: str = op
        self.operand: SymbolicValue = operand

    def is_constant(self) -> bool:
        return self.operand.is_constant()

    def simplify(self) -> "SymbolicValue":
        simp_operand = self.operand.simplify()

        if simp_operand.is_constant() and isinstance(simp_operand, SymbolicConstant):
            val = simp_operand.value
            try:
                if self.op == "-":
                    return SymbolicConstant(-val)
                elif self.op == "+":
                    return SymbolicConstant(+val)
                elif self.op == "~" and isinstance(val, int):
                    return SymbolicConstant(~val)
                elif self.op == "not":
                    return SymbolicConstant(not val)
            except Exception:
                pass

        # Double negation: -(-x) -> x
        if self.op == "-" and isinstance(simp_operand, SymbolicUnaryOp) and simp_operand.op == "-":
            return simp_operand.operand

        # Double bitwise not: ~(~x) -> x
        if self.op == "~" and isinstance(simp_operand, SymbolicUnaryOp) and simp_operand.op == "~":
            return simp_operand.operand

        return SymbolicUnaryOp(self.op, simp_operand)

    def to_ast(self) -> ast.expr:
        op_map = {
            "-": ast.USub(),
            "+": ast.UAdd(),
            "~": ast.Invert(),
            "not": ast.Not(),
        }
        return ast.UnaryOp(op=op_map.get(self.op, ast.USub()), operand=self.operand.to_ast())

    def get_variables(self) -> Set[str]:
        return self.operand.get_variables()

    def __repr__(self) -> str:
        return f"SymUnary({self.op}, {self.operand})"


class SymbolicBinaryOp(SymbolicValue):
    """Represents a binary operation on two symbolic expressions."""

    def __init__(self, op: str, left: SymbolicValue, right: SymbolicValue) -> None:
        self.op: str = op
        self.left: SymbolicValue = left
        self.right: SymbolicValue = right

    def is_constant(self) -> bool:
        return self.left.is_constant() and self.right.is_constant()

    def simplify(self) -> "SymbolicValue":
        s_left = self.left.simplify()
        s_right = self.right.simplify()

        # 1. Constant folding if both are constants
        if isinstance(s_left, SymbolicConstant) and isinstance(s_right, SymbolicConstant):
            folded = self._fold_constants(s_left.value, s_right.value)
            if folded is not None:
                return SymbolicConstant(folded)

        # 2. XOR Simplification Rules
        if self.op == "^":
            # x ^ 0 -> x, 0 ^ x -> x
            if isinstance(s_right, SymbolicConstant) and s_right.value == 0:
                return s_left
            if isinstance(s_left, SymbolicConstant) and s_left.value == 0:
                return s_right

            # x ^ x -> 0
            if s_left == s_right:
                return SymbolicConstant(0)

            # (x ^ c1) ^ c2 -> x ^ (c1 ^ c2)
            if (
                isinstance(s_left, SymbolicBinaryOp)
                and s_left.op == "^"
                and isinstance(s_left.right, SymbolicConstant)
                and isinstance(s_right, SymbolicConstant)
                and isinstance(s_left.right.value, int)
                and isinstance(s_right.value, int)
            ):
                combined_k = s_left.right.value ^ s_right.value
                if combined_k == 0:
                    return s_left.left
                return SymbolicBinaryOp("^", s_left.left, SymbolicConstant(combined_k))

            # (x ^ y) ^ y -> x
            if isinstance(s_left, SymbolicBinaryOp) and s_left.op == "^":
                if s_left.right == s_right:
                    return s_left.left
                if s_left.left == s_right:
                    return s_left.right

            # y ^ (x ^ y) -> x
            if isinstance(s_right, SymbolicBinaryOp) and s_right.op == "^":
                if s_right.right == s_left:
                    return s_right.left
                if s_right.left == s_left:
                    return s_right.right

        # 3. Additive Simplification Rules
        if self.op == "+":
            # x + 0 -> x, 0 + x -> x
            if isinstance(s_right, SymbolicConstant) and s_right.value == 0:
                return s_left
            if isinstance(s_left, SymbolicConstant) and s_left.value == 0:
                return s_right

            # (x + c1) + c2 -> x + (c1 + c2)
            if (
                isinstance(s_left, SymbolicBinaryOp)
                and s_left.op == "+"
                and isinstance(s_left.right, SymbolicConstant)
                and isinstance(s_right, SymbolicConstant)
                and isinstance(s_left.right.value, (int, float))
                and isinstance(s_right.value, (int, float))
            ):
                return SymbolicBinaryOp("+", s_left.left, SymbolicConstant(s_left.right.value + s_right.value)).simplify()

            # (x - c1) + c2 -> x + (c2 - c1)
            if (
                isinstance(s_left, SymbolicBinaryOp)
                and s_left.op == "-"
                and isinstance(s_left.right, SymbolicConstant)
                and isinstance(s_right, SymbolicConstant)
                and isinstance(s_left.right.value, (int, float))
                and isinstance(s_right.value, (int, float))
            ):
                diff = s_right.value - s_left.right.value
                if diff == 0:
                    return s_left.left
                elif diff > 0:
                    return SymbolicBinaryOp("+", s_left.left, SymbolicConstant(diff))
                else:
                    return SymbolicBinaryOp("-", s_left.left, SymbolicConstant(-diff))

            # (x - y) + y -> x
            if isinstance(s_left, SymbolicBinaryOp) and s_left.op == "-" and s_left.right == s_right:
                return s_left.left

        if self.op == "-":
            # x - 0 -> x
            if isinstance(s_right, SymbolicConstant) and s_right.value == 0:
                return s_left

            # x - x -> 0
            if s_left == s_right:
                return SymbolicConstant(0)

            # (x + c1) - c2 -> x + (c1 - c2)
            if (
                isinstance(s_left, SymbolicBinaryOp)
                and s_left.op == "+"
                and isinstance(s_left.right, SymbolicConstant)
                and isinstance(s_right, SymbolicConstant)
                and isinstance(s_left.right.value, (int, float))
                and isinstance(s_right.value, (int, float))
            ):
                diff = s_left.right.value - s_right.value
                if diff == 0:
                    return s_left.left
                elif diff > 0:
                    return SymbolicBinaryOp("+", s_left.left, SymbolicConstant(diff))
                else:
                    return SymbolicBinaryOp("-", s_left.left, SymbolicConstant(-diff))

            # (x + y) - x -> y, (x + y) - y -> x
            if isinstance(s_left, SymbolicBinaryOp) and s_left.op == "+":
                if s_left.left == s_right:
                    return s_left.right
                if s_left.right == s_right:
                    return s_left.left

        # 4. Multiplicative Simplifications
        if self.op == "*":
            # x * 1 -> x, 1 * x -> x
            if isinstance(s_right, SymbolicConstant) and s_right.value == 1:
                return s_left
            if isinstance(s_left, SymbolicConstant) and s_left.value == 1:
                return s_right

            # x * 0 -> 0, 0 * x -> 0
            if isinstance(s_right, SymbolicConstant) and s_right.value == 0:
                return SymbolicConstant(0)
            if isinstance(s_left, SymbolicConstant) and s_left.value == 0:
                return SymbolicConstant(0)

            # (x * c1) * c2 -> x * (c1 * c2)
            if (
                isinstance(s_left, SymbolicBinaryOp)
                and s_left.op == "*"
                and isinstance(s_left.right, SymbolicConstant)
                and isinstance(s_right, SymbolicConstant)
                and isinstance(s_left.right.value, (int, float))
                and isinstance(s_right.value, (int, float))
            ):
                return SymbolicBinaryOp("*", s_left.left, SymbolicConstant(s_left.right.value * s_right.value))

        # 5. Bitwise & and |
        if self.op == "&":
            if isinstance(s_right, SymbolicConstant) and s_right.value == 0:
                return SymbolicConstant(0)
            if isinstance(s_left, SymbolicConstant) and s_left.value == 0:
                return SymbolicConstant(0)
            if isinstance(s_right, SymbolicConstant) and s_right.value == -1:
                return s_left
            if isinstance(s_left, SymbolicConstant) and s_left.value == -1:
                return s_right
            if s_left == s_right:
                return s_left

        if self.op == "|":
            if isinstance(s_right, SymbolicConstant) and s_right.value == 0:
                return s_left
            if isinstance(s_left, SymbolicConstant) and s_left.value == 0:
                return s_right
            if s_left == s_right:
                return s_left

        return SymbolicBinaryOp(self.op, s_left, s_right)

    def _fold_constants(self, v1: Any, v2: Any) -> Optional[Any]:
        """Safely compute constant arithmetic."""
        try:
            if self.op == "+":
                return v1 + v2
            elif self.op == "-":
                return v1 - v2
            elif self.op == "*":
                if isinstance(v1, (str, bytes)) and isinstance(v2, int):
                    if len(v1) * v2 > 65536:
                        return None
                if isinstance(v2, (str, bytes)) and isinstance(v1, int):
                    if len(v2) * v1 > 65536:
                        return None
                return v1 * v2
            elif self.op == "/":
                return None if v2 == 0 else v1 / v2
            elif self.op == "//":
                return None if v2 == 0 else v1 // v2
            elif self.op == "%":
                return None if v2 == 0 else v1 % v2
            elif self.op == "**":
                if isinstance(v1, int) and isinstance(v2, int) and (v2 < 0 or v2 > 100):
                    return None
                return v1 ** v2
            elif self.op == "^" and isinstance(v1, int) and isinstance(v2, int):
                return v1 ^ v2
            elif self.op == "&" and isinstance(v1, int) and isinstance(v2, int):
                return v1 & v2
            elif self.op == "|" and isinstance(v1, int) and isinstance(v2, int):
                return v1 | v2
            elif self.op == "<<" and isinstance(v1, int) and isinstance(v2, int) and 0 <= v2 <= 64:
                return v1 << v2
            elif self.op == ">>" and isinstance(v1, int) and isinstance(v2, int) and 0 <= v2 <= 64:
                return v1 >> v2
        except Exception:
            return None
        return None

    def to_ast(self) -> ast.expr:
        op_map = {
            "+": ast.Add(),
            "-": ast.Sub(),
            "*": ast.Mult(),
            "/": ast.Div(),
            "//": ast.FloorDiv(),
            "%": ast.Mod(),
            "**": ast.Pow(),
            "^": ast.BitXor(),
            "&": ast.BitAnd(),
            "|": ast.BitOr(),
            "<<": ast.LShift(),
            ">>": ast.RShift(),
        }
        return ast.BinOp(
            left=self.left.to_ast(),
            op=op_map.get(self.op, ast.Add()),
            right=self.right.to_ast(),
        )

    def get_variables(self) -> Set[str]:
        return self.left.get_variables().union(self.right.get_variables())

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, SymbolicBinaryOp):
            return self.op == other.op and self.left == other.left and self.right == other.right
        return False

    def __hash__(self) -> int:
        return hash((self.op, self.left, self.right))

    def __repr__(self) -> str:
        return f"SymBinOp({self.left} {self.op} {self.right})"


class SymbolicEvaluator:
    """Translates Python AST expressions to/from symbolic values and evaluates them."""

    def __init__(self, env: Optional[Dict[str, SymbolicValue]] = None) -> None:
        self.env: Dict[str, SymbolicValue] = dict(env) if env else {}

    def set_variable(self, name: str, value: SymbolicValue) -> None:
        """Bind a variable name to a symbolic value in the environment."""
        self.env[name] = value

    def clear(self) -> None:
        """Clear all bound symbolic variables."""
        self.env.clear()

    def from_ast(self, expr: ast.expr) -> Optional[SymbolicValue]:
        """Convert a Python AST expression into a SymbolicValue using the environment."""
        if isinstance(expr, ast.Constant):
            return SymbolicConstant(expr.value)

        if isinstance(expr, ast.Name):
            # If variable is in environment, substitute its symbolic value
            if expr.id in self.env:
                return self.env[expr.id]
            return SymbolicVariable(expr.id)

        if isinstance(expr, ast.UnaryOp):
            operand_sym = self.from_ast(expr.operand)
            if operand_sym is None:
                return None
            op_sym = self._unary_op_str(expr.op)
            if op_sym:
                return SymbolicUnaryOp(op_sym, operand_sym)

        if isinstance(expr, ast.BinOp):
            left_sym = self.from_ast(expr.left)
            right_sym = self.from_ast(expr.right)
            if left_sym is None or right_sym is None:
                return None
            op_sym = self._bin_op_str(expr.op)
            if op_sym:
                return SymbolicBinaryOp(op_sym, left_sym, right_sym)

        return None

    def evaluate_ast(self, expr: ast.expr) -> Optional[ast.expr]:
        """Convert AST expression to symbolic value, simplify, and convert back to AST if simplified."""
        sym_val = self.from_ast(expr)
        if sym_val is None:
            return None

        simplified = sym_val.simplify()
        # If expression changed or folded to constant
        if simplified != sym_val or simplified.is_constant():
            res_ast = simplified.to_ast()
            ast.copy_location(res_ast, expr)
            return res_ast

        return None

    def _unary_op_str(self, op: ast.unaryop) -> Optional[str]:
        if isinstance(op, ast.USub):
            return "-"
        if isinstance(op, ast.UAdd):
            return "+"
        if isinstance(op, ast.Invert):
            return "~"
        if isinstance(op, ast.Not):
            return "not"
        return None

    def _bin_op_str(self, op: ast.operator) -> Optional[str]:
        mapping = {
            ast.Add: "+",
            ast.Sub: "-",
            ast.Mult: "*",
            ast.Div: "/",
            ast.FloorDiv: "//",
            ast.Mod: "%",
            ast.Pow: "**",
            ast.BitXor: "^",
            ast.BitAnd: "&",
            ast.BitOr: "|",
            ast.LShift: "<<",
            ast.RShift: ">>",
        }
        for cls, s in mapping.items():
            if isinstance(op, cls):
                return s
        return None
