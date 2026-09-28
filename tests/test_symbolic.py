"""Unit tests for symbolic evaluation and algebraic simplification (Phase 4)."""

import ast
import unittest

from analysis.symbolic import (
    SymbolicBinaryOp,
    SymbolicConstant,
    SymbolicEvaluator,
    SymbolicUnaryOp,
    SymbolicVariable,
)


class TestSymbolic(unittest.TestCase):
    """Test suite for SymbolicValue, SymbolicEvaluator, and algebraic reductions."""

    def setUp(self) -> None:
        self.evaluator = SymbolicEvaluator()
        self.x = SymbolicVariable("x")
        self.y = SymbolicVariable("y")

    def test_constant_folding(self) -> None:
        c1 = SymbolicConstant(10)
        c2 = SymbolicConstant(20)
        res = SymbolicBinaryOp("+", c1, c2).simplify()
        self.assertIsInstance(res, SymbolicConstant)
        self.assertEqual(res.value, 30)

    def test_additive_simplifications(self) -> None:
        # x + 0 -> x
        self.assertEqual(SymbolicBinaryOp("+", self.x, SymbolicConstant(0)).simplify(), self.x)
        # 0 + x -> x
        self.assertEqual(SymbolicBinaryOp("+", SymbolicConstant(0), self.x).simplify(), self.x)
        # x - 0 -> x
        self.assertEqual(SymbolicBinaryOp("-", self.x, SymbolicConstant(0)).simplify(), self.x)
        # x - x -> 0
        self.assertEqual(SymbolicBinaryOp("-", self.x, self.x).simplify(), SymbolicConstant(0))

        # (x + 10) + 20 -> x + 30
        op1 = SymbolicBinaryOp("+", SymbolicBinaryOp("+", self.x, SymbolicConstant(10)), SymbolicConstant(20))
        self.assertEqual(op1.simplify(), SymbolicBinaryOp("+", self.x, SymbolicConstant(30)))

        # (x + 5) - x -> 5
        op2 = SymbolicBinaryOp("-", SymbolicBinaryOp("+", self.x, SymbolicConstant(5)), self.x)
        self.assertEqual(op2.simplify(), SymbolicConstant(5))

        # (x - 5) + 5 -> x
        op3 = SymbolicBinaryOp("+", SymbolicBinaryOp("-", self.x, SymbolicConstant(5)), SymbolicConstant(5))
        self.assertEqual(op3.simplify(), self.x)

    def test_xor_simplifications(self) -> None:
        # x ^ 0 -> x
        self.assertEqual(SymbolicBinaryOp("^", self.x, SymbolicConstant(0)).simplify(), self.x)
        # x ^ x -> 0
        self.assertEqual(SymbolicBinaryOp("^", self.x, self.x).simplify(), SymbolicConstant(0))

        # (x ^ 42) ^ 42 -> x
        op1 = SymbolicBinaryOp("^", SymbolicBinaryOp("^", self.x, SymbolicConstant(42)), SymbolicConstant(42))
        self.assertEqual(op1.simplify(), self.x)

        # (x ^ 10) ^ 20 -> x ^ 30 (since 10 ^ 20 = 30)
        op2 = SymbolicBinaryOp("^", SymbolicBinaryOp("^", self.x, SymbolicConstant(10)), SymbolicConstant(20))
        self.assertEqual(op2.simplify(), SymbolicBinaryOp("^", self.x, SymbolicConstant(30)))

        # (x ^ y) ^ y -> x
        op3 = SymbolicBinaryOp("^", SymbolicBinaryOp("^", self.x, self.y), self.y)
        self.assertEqual(op3.simplify(), self.x)

        # y ^ (x ^ y) -> x
        op4 = SymbolicBinaryOp("^", self.y, SymbolicBinaryOp("^", self.x, self.y))
        self.assertEqual(op4.simplify(), self.x)

    def test_multiplicative_simplifications(self) -> None:
        # x * 0 -> 0
        self.assertEqual(SymbolicBinaryOp("*", self.x, SymbolicConstant(0)).simplify(), SymbolicConstant(0))
        # x * 1 -> x
        self.assertEqual(SymbolicBinaryOp("*", self.x, SymbolicConstant(1)).simplify(), self.x)
        # (x * 3) * 4 -> x * 12
        op = SymbolicBinaryOp("*", SymbolicBinaryOp("*", self.x, SymbolicConstant(3)), SymbolicConstant(4))
        self.assertEqual(op.simplify(), SymbolicBinaryOp("*", self.x, SymbolicConstant(12)))

    def test_unary_simplifications(self) -> None:
        # -(-x) -> x
        neg_neg = SymbolicUnaryOp("-", SymbolicUnaryOp("-", self.x))
        self.assertEqual(neg_neg.simplify(), self.x)
        # ~(~x) -> x
        inv_inv = SymbolicUnaryOp("~", SymbolicUnaryOp("~", self.x))
        self.assertEqual(inv_inv.simplify(), self.x)

    def test_ast_evaluation_with_env(self) -> None:
        code_expr = ast.parse("(a ^ 0xFF) ^ 0xFF", mode="eval").body
        evaluator = SymbolicEvaluator()
        result_ast = evaluator.evaluate_ast(code_expr)
        self.assertIsNotNone(result_ast)
        self.assertEqual(ast.unparse(result_ast), "a")


if __name__ == "__main__":
    unittest.main()
