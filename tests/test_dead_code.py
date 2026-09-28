"""Unit tests for DeadCodeEliminationPass (Phase 1E)."""

import unittest

from core.pipeline import Pipeline
from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.constant_propagation import ConstantPropagationPass
from passes.dead_code import DeadCodeEliminationPass
from passes.expression_folding import ExpressionFoldingPass


class TestDeadCodeElimination(unittest.TestCase):
    """Test suite for dead code and unreachable code elimination."""

    def setUp(self) -> None:
        self.parser = PythonParser()

    def run_pass(self, code: str) -> str:
        tree = self.parser.parse(code)
        tracker = ProvenanceTracker()
        pass_instance = DeadCodeEliminationPass(filename="test.py")
        new_tree = pass_instance.run(tree, tracker)
        return self.parser.unparse(new_tree)

    def pipeline_deobfuscate(self, code: str) -> str:
        tree = self.parser.parse(code)
        pipeline = Pipeline()
        pipeline.add_pass(ConstantPropagationPass(filename="test.py"))
        pipeline.add_pass(ExpressionFoldingPass(filename="test.py"))
        pipeline.add_pass(DeadCodeEliminationPass(filename="test.py"))
        result = pipeline.execute(tree, until_convergence=True)
        return self.parser.unparse(result)

    def test_if_true_pruning(self) -> None:
        code = "if True:\n    x = 1\nelse:\n    x = 2"
        out = self.run_pass(code)
        self.assertEqual(out, "x = 1")

    def test_if_false_pruning(self) -> None:
        code = "if False:\n    x = 1\nelse:\n    x = 2"
        out = self.run_pass(code)
        self.assertEqual(out, "x = 2")

    def test_if_false_no_else(self) -> None:
        code = "a = 1\nif False:\n    a = 999\nb = a"
        out = self.run_pass(code)
        self.assertNotIn("999", out)

    def test_unreachable_statements_after_return(self) -> None:
        code = (
            "def foo():\n"
            "    return 42\n"
            "    print('unreachable')\n"
            "    x = 100\n"
        )
        out = self.run_pass(code)
        self.assertEqual(out, "def foo():\n    return 42")

    def test_dead_assignment_elimination_in_function(self) -> None:
        code = (
            "def compute():\n"
            "    junk = 12345\n"
            "    target = 10\n"
            "    return target\n"
        )
        out = self.run_pass(code)
        self.assertNotIn("junk", out)
        self.assertIn("target = 10", out)

    def test_impure_assignment_preserved(self) -> None:
        code = (
            "def process():\n"
            "    unused = side_effect_action()\n"
            "    return 0\n"
        )
        out = self.run_pass(code)
        # Must preserve side_effect_action()
        self.assertIn("unused = side_effect_action()", out)

    def test_opaque_predicate_pipeline(self) -> None:
        # 10 > 5 is folded to True, then DeadCodeElimination prunes the dead else branch
        code = (
            "def check():\n"
            "    if 10 > 5:\n"
            "        result = 'real_branch'\n"
            "    else:\n"
            "        result = 'fake_branch'\n"
            "    return result\n"
        )
        out = self.pipeline_deobfuscate(code)
        self.assertNotIn("fake_branch", out)
        self.assertIn("'real_branch'", out)


if __name__ == "__main__":
    unittest.main()
