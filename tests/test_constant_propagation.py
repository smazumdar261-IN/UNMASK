"""Unit tests for Constant Propagation (Phase 1B)."""

import unittest

from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.constant_propagation import ConstantPropagationPass
from passes.expression_folding import ExpressionFoldingPass
from core.pipeline import Pipeline


class TestConstantPropagation(unittest.TestCase):
    """Test suite for scope-aware constant propagation."""

    def setUp(self) -> None:
        self.parser = PythonParser()

    def propagate(self, code: str) -> str:
        tree = self.parser.parse(code)
        tracker = ProvenanceTracker()
        pass_instance = ConstantPropagationPass(filename="test.py")
        new_tree = pass_instance.run(tree, tracker)
        return self.parser.unparse(new_tree)

    def pipeline_deobfuscate(self, code: str) -> str:
        tree = self.parser.parse(code)
        pipeline = Pipeline()
        pipeline.add_pass(ConstantPropagationPass(filename="test.py"))
        pipeline.add_pass(ExpressionFoldingPass(filename="test.py"))
        result = pipeline.execute(tree, until_convergence=True)
        return self.parser.unparse(result)

    def test_basic_propagation(self) -> None:
        code = "a = 'Hello'\nb = a\nprint(b)"
        # ConstantPropagation should propagate 'Hello' to both b and print
        res = self.propagate(code)
        self.assertIn("b = 'Hello'", res)
        self.assertIn("print('Hello')", res)

    def test_chained_propagation_and_folding(self) -> None:
        code = "x = 10\ny = x * 2\nz = y + 5"
        res = self.pipeline_deobfuscate(code)
        expected = "x = 10\ny = 20\nz = 25"
        self.assertEqual(res, expected)

    def test_linear_reassignment(self) -> None:
        code = "x = 1\ny = x\nx = 2\nz = x"
        res = self.propagate(code)
        self.assertIn("y = 1", res)
        self.assertIn("z = 2", res)

    def test_non_constant_reassignment_invalidates(self) -> None:
        code = "x = 10\nx = get_value()\ny = x"
        res = self.propagate(code)
        # y = x must NOT be replaced with y = 10 because x was reassigned to a dynamic value
        self.assertIn("y = x", res)

    def test_function_scope_isolation(self) -> None:
        code = "x = 100\ndef test(x):\n    return x\ny = x"
        res = self.propagate(code)
        # Inside test(x), parameter shadows outer constant; return x must remain return x
        self.assertIn("return x", res)
        # In module scope, y = x receives 100
        self.assertIn("y = 100", res)

    def test_branch_invalidation_conservative(self) -> None:
        code = "x = 10\nif condition:\n    x = 20\nprint(x)"
        res = self.propagate(code)
        # print(x) after the branch must NOT assume x is 10 or 20
        self.assertIn("print(x)", res)

    def test_loop_invalidation_conservative(self) -> None:
        code = "x = 0\nfor i in items:\n    x = i\nprint(x)"
        res = self.propagate(code)
        # print(x) after loop must remain print(x)
        self.assertIn("print(x)", res)


if __name__ == "__main__":
    unittest.main()
