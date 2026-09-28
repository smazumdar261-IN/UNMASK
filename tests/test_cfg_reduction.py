"""Unit tests for CFG reduction and redundant branch elimination (Phase 3)."""

import ast
import unittest

from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.cfg_reduction import CFGReductionPass


class TestCFGReduction(unittest.TestCase):
    """Test suite for CFGReductionPass."""

    def setUp(self) -> None:
        self.tracker = ProvenanceTracker()
        self.pass_ = CFGReductionPass()

    def _transform(self, code: str) -> str:
        tree = ast.parse(code)
        transformed = self.pass_.run(tree, self.tracker)
        return PythonParser.unparse(transformed).strip()

    def test_eliminate_pure_empty_if(self) -> None:
        code = """
x = 10
if x > 0:
    pass
y = 20
"""
        result = self._transform(code)
        self.assertNotIn("if x > 0", result)
        self.assertNotIn("pass", result)
        self.assertIn("x = 10", result)
        self.assertIn("y = 20", result)
        self.assertGreater(len(self.tracker.records), 0)

    def test_preserve_impure_empty_if(self) -> None:
        code = """
if log_action():
    pass
"""
        result = self._transform(code)
        # Should be converted to expression statement to retain side effect
        self.assertNotIn("pass", result)
        self.assertNotIn("if", result)
        self.assertIn("log_action()", result)

    def test_collapse_identical_branches(self) -> None:
        code = """
if flag:
    return 42
else:
    return 42
"""
        result = self._transform(code)
        self.assertNotIn("if flag", result)
        self.assertNotIn("else", result)
        self.assertEqual(result, "return 42")

    def test_eliminate_while_false(self) -> None:
        code = """
x = 1
while False:
    dead_computation()
y = 2
"""
        result = self._transform(code)
        self.assertNotIn("while False", result)
        self.assertNotIn("dead_computation", result)
        self.assertIn("x = 1", result)
        self.assertIn("y = 2", result)

    def test_eliminate_for_empty_collection(self) -> None:
        code = """
for item in []:
    dead_loop()
for char in "":
    dead_loop2()
alive = True
"""
        result = self._transform(code)
        self.assertNotIn("dead_loop", result)
        self.assertNotIn("for item in []", result)
        self.assertNotIn("for char in ''", result)
        self.assertIn("alive = True", result)

    def test_prune_unreachable_after_return(self) -> None:
        code = """
def calc(x):
    return x * 10
    dead_1 = 1
    dead_2 = 2
"""
        result = self._transform(code)
        self.assertNotIn("dead_1", result)
        self.assertNotIn("dead_2", result)
        self.assertIn("return x * 10", result)


if __name__ == "__main__":
    unittest.main()
