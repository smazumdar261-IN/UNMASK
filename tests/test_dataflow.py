"""Unit tests for DataFlowAnalyzer (Phase 1E)."""

import ast
import unittest

from analysis.dataflow import DataFlowAnalyzer, is_pure_expression
from languages.python.parser import PythonParser


class TestDataFlow(unittest.TestCase):
    """Test suite for data flow, use-def chains, and purity analysis."""

    def setUp(self) -> None:
        self.parser = PythonParser()

    def test_purity_classification(self) -> None:
        pure_codes = [
            "42",
            "'hello'",
            "True",
            "x",
            "x + y",
            "not x",
            "[1, 2, 3]",
            "{'a': 1}",
            "(x, y)",
            "x == y",
            "'abc'[0]",
        ]
        for src in pure_codes:
            node = ast.parse(src, mode="eval").body
            self.assertTrue(is_pure_expression(node), f"Expected pure: {src}")

        impure_codes = [
            "f()",
            "x.method()",
            "[f() for _ in range(5)]",
            "{'k': f()}",
        ]
        for src in impure_codes:
            node = ast.parse(src, mode="eval").body
            self.assertFalse(is_pure_expression(node), f"Expected impure: {src}")

    def test_def_use_chains(self) -> None:
        code = "x = 10\ny = x + 5\nprint(y)"
        tree = self.parser.parse(code)
        analyzer = DataFlowAnalyzer().analyze(tree)

        self.assertEqual(len(analyzer.definitions), 2)  # x = 10, y = x + 5
        self.assertEqual(len(analyzer.uses), 3)  # x, print, y

        # Verify x reaches y = x + 5
        x_def = next(d for d in analyzer.definitions if d.variable == "x")
        x_uses = analyzer.def_to_uses[x_def]
        self.assertEqual(len(x_uses), 1)
        self.assertEqual(x_uses[0].variable, "x")

    def test_unused_definitions(self) -> None:
        code = "a = 1\nb = 2\nc = a + 10\nprint(c)"  # only b is never used and is pure
        tree = self.parser.parse(code)
        analyzer = DataFlowAnalyzer().analyze(tree)

        dead = analyzer.get_dead_definitions()
        self.assertEqual(len(dead), 1)
        self.assertEqual(dead[0].variable, "b")

    def test_impure_definition_not_marked_dead(self) -> None:
        code = "res = launch_missile()\nprint('done')"
        tree = self.parser.parse(code)
        analyzer = DataFlowAnalyzer().analyze(tree)

        # res is unused, but is impure (function call); must NOT be marked dead
        dead = analyzer.get_dead_definitions()
        self.assertEqual(len(dead), 0)

    def test_alias_tracking(self) -> None:
        code = "a = b\nc = a\nd = 10"
        tree = self.parser.parse(code)
        analyzer = DataFlowAnalyzer().analyze(tree)

        # a, b, c should be recognized as aliases of one another
        self.assertIn("b", analyzer.aliases.get("a", set()))
        self.assertIn("c", analyzer.aliases.get("a", set()))
        self.assertIn("a", analyzer.aliases.get("c", set()))
        self.assertIn("b", analyzer.aliases.get("c", set()))
        self.assertNotIn("d", analyzer.aliases.get("a", set()))


if __name__ == "__main__":
    unittest.main()
