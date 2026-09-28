"""Unit tests for SymbolicEvaluationPass (Phase 4)."""

import ast
import unittest

from core.confidence import ConfidenceLevel
from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.symbolic_evaluation import SymbolicEvaluationPass


class TestSymbolicEvaluationPass(unittest.TestCase):
    """Test suite for SymbolicEvaluationPass."""

    def setUp(self) -> None:
        self.tracker = ProvenanceTracker()
        self.pass_ = SymbolicEvaluationPass()

    def _transform(self, code: str) -> str:
        tree = ast.parse(code)
        transformed = self.pass_.run(tree, self.tracker)
        return PythonParser.unparse(transformed).strip()

    def test_section_10_constant_propagation_example(self) -> None:
        # Example specified in Section 10 of README
        code = """
x = 10
y = x * 2
z = y + 5
"""
        # Run until convergence for chained propagation
        tree = ast.parse(code)
        for _ in range(5):
            tree = self.pass_.run(tree, self.tracker)
        result = PythonParser.unparse(tree).strip()

        self.assertIn("x = 10", result)
        self.assertIn("y = 20", result)
        self.assertIn("z = 25", result)

    def test_xor_obfuscation_cancellation(self) -> None:
        code = """
def decrypt(key):
    decoded = (key ^ 12345) ^ 12345
    return decoded
"""
        result = self._transform(code)
        self.assertIn("decoded = key", result)
        self.assertNotIn("12345", result)

        records = [r for r in self.tracker.records if r.pass_name == "SymbolicEvaluation"]
        self.assertGreater(len(records), 0)
        self.assertTrue(all(r.confidence.level == ConfidenceLevel.CERTAIN for r in records))

    def test_self_canceling_arithmetic(self) -> None:
        code = """
offset = (x + 100) - x
"""
        result = self._transform(code)
        self.assertEqual(result, "offset = 100")


if __name__ == "__main__":
    unittest.main()
