"""Unit tests for SimplificationPass (Phase 2)."""

import unittest

from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.simplify import SimplificationPass


class TestSimplify(unittest.TestCase):
    """Test suite for algebraic identity and redundant expression simplification."""

    def setUp(self) -> None:
        self.parser = PythonParser()

    def simplify(self, code: str) -> str:
        tree = self.parser.parse(code)
        tracker = ProvenanceTracker()
        pass_instance = SimplificationPass(filename="test.py")
        new_tree = pass_instance.run(tree, tracker)
        return self.parser.unparse(new_tree)

    def test_arithmetic_identities(self) -> None:
        cases = [
            ("y = x + 0", "y = x"),
            ("y = 0 + x", "y = x"),
            ("y = x - 0", "y = x"),
            ("y = x * 1", "y = x"),
            ("y = 1 * x", "y = x"),
            ("y = x // 1", "y = x"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.simplify(src), expected)

    def test_bitwise_identities(self) -> None:
        cases = [
            ("y = x ^ 0", "y = x"),
            ("y = 0 ^ x", "y = x"),
            ("y = x | 0", "y = x"),
            ("y = x & -1", "y = x"),
            ("y = x ^ x", "y = 0"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.simplify(src), expected)

    def test_boolean_identities(self) -> None:
        cases = [
            ("y = x or False", "y = x"),
            ("y = False or x", "y = x"),
            ("y = x and True", "y = x"),
            ("y = True and x", "y = x"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.simplify(src), expected)

    def test_double_reversal(self) -> None:
        code = "y = secret[::-1][::-1]"
        self.assertEqual(self.simplify(code), "y = secret")

    def test_redundant_casts(self) -> None:
        cases = [
            ("x = str('hello')", "x = 'hello'"),
            ("x = bytes(b'data')", "x = b'data'"),
            ("x = int(42)", "x = 42"),
            ("x = bool(True)", "x = True"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.simplify(src), expected)


if __name__ == "__main__":
    unittest.main()
