"""Unit tests for reaching definitions and dependency tracking (Phase 4)."""

import ast
import unittest

from analysis.reaching_definitions import ReachingDefinitionsAnalyzer


class TestReachingDefinitions(unittest.TestCase):
    """Test suite for ReachingDefinitionsAnalyzer and DependencyGraph."""

    def setUp(self) -> None:
        self.analyzer = ReachingDefinitionsAnalyzer()

    def test_single_definition_reaches_use(self) -> None:
        code = """
x = 10
y = x * 2
"""
        tree = ast.parse(code)
        self.analyzer.analyze(tree)

        # Uses: 1 use of x
        uses_of_x = [u for u in self.analyzer.uses if u.variable == "x"]
        self.assertEqual(len(uses_of_x), 1)

        # Unique reaching definition for x
        uniq_def = self.analyzer.get_unique_reaching_definition(uses_of_x[0])
        self.assertIsNotNone(uniq_def)
        self.assertEqual(uniq_def.variable, "x")
        self.assertIsInstance(uniq_def.value_node, ast.Constant)
        self.assertEqual(uniq_def.value_node.value, 10)

    def test_reassignment_kills_definition(self) -> None:
        code = """
x = 10
x = 20
y = x
"""
        tree = ast.parse(code)
        self.analyzer.analyze(tree)

        uses_of_x = [u for u in self.analyzer.uses if u.variable == "x"]
        self.assertEqual(len(uses_of_x), 1)

        uniq_def = self.analyzer.get_unique_reaching_definition(uses_of_x[0])
        self.assertIsNotNone(uniq_def)
        # Should be x = 20 (second definition), not x = 10
        self.assertEqual(uniq_def.value_node.value, 20)

    def test_branch_merge_multiple_reaching_definitions(self) -> None:
        code = """
if cond:
    x = 1
else:
    x = 2
y = x
"""
        tree = ast.parse(code)
        self.analyzer.analyze(tree)

        uses_of_x = [u for u in self.analyzer.uses if u.variable == "x"]
        self.assertEqual(len(uses_of_x), 1)

        reaching = self.analyzer.get_reaching_definitions_for_use(uses_of_x[0])
        # Two definitions reach this use
        self.assertEqual(len(reaching), 2)
        # Therefore no unique reaching definition
        self.assertIsNone(self.analyzer.get_unique_reaching_definition(uses_of_x[0]))

    def test_dependency_graph_direct_and_transitive(self) -> None:
        code = """
x = 10
y = x * 2
z = y + 5
w = z + 1
"""
        tree = ast.parse(code)
        self.analyzer.analyze(tree)

        graph = self.analyzer.dependency_graph

        # Direct dependencies
        self.assertEqual(graph.get_dependencies("y"), {"x"})
        self.assertEqual(graph.get_dependencies("z"), {"y"})
        self.assertEqual(graph.get_dependencies("w"), {"z"})

        # Transitive dependencies
        self.assertEqual(graph.get_transitive_dependencies("z"), {"x", "y"})
        self.assertEqual(graph.get_transitive_dependencies("w"), {"x", "y", "z"})


if __name__ == "__main__":
    unittest.main()
