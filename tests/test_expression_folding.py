"""Unit tests for Expression Folding (Phase 1B)."""

import ast
import unittest

from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.expression_folding import ExpressionFoldingPass


class TestExpressionFolding(unittest.TestCase):
    """Test suite for safe compile-time constant expression folding."""

    def setUp(self) -> None:
        self.parser = PythonParser()

    def fold(self, code: str) -> str:
        tree = self.parser.parse(code)
        tracker = ProvenanceTracker()
        pass_instance = ExpressionFoldingPass(filename="test.py")
        new_tree = pass_instance.run(tree, tracker)
        return self.parser.unparse(new_tree)

    def test_arithmetic_folding(self) -> None:
        cases = [
            ("x = 10 + 20", "x = 30"),
            ("x = 10 * 5", "x = 50"),
            ("x = 100 - 35", "x = 65"),
            ("x = 20 / 4", "x = 5.0"),
            ("x = 23 // 4", "x = 5"),
            ("x = 17 % 5", "x = 2"),
            ("x = 2 ** 8", "x = 256"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.fold(src), expected)

    def test_bitwise_folding(self) -> None:
        cases = [
            ("x = 1 << 4", "x = 16"),
            ("x = 64 >> 2", "x = 16"),
            ("x = 0x0F & 0xFF", "x = 15"),
            ("x = 0x10 | 0x01", "x = 17"),
            ("x = 0xAA ^ 0xFF", "x = 85"),
            ("x = ~0", "x = -1"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.fold(src), expected)

    def test_unary_folding(self) -> None:
        cases = [
            ("x = -(-42)", "x = 42"),
            ("x = not True", "x = False"),
            ("x = not False", "x = True"),
            ("x = +10", "x = 10"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.fold(src), expected)

    def test_string_and_bytes_folding(self) -> None:
        cases = [
            ("x = 'hello' + ' ' + 'world'", "x = 'hello world'"),
            ("x = 'abc' * 3", "x = 'abcabcabc'"),
            ("x = b'abc' + b'def'", "x = b'abcdef'"),
            ("x = 'reversed'[::-1]", "x = 'desrever'"),
            ("x = 'hello'[1]", "x = 'e'"),
            ("x = 'abcdef'[1:4]", "x = 'bcd'"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.fold(src), expected)

    def test_comparisons_and_booleans(self) -> None:
        cases = [
            ("x = 10 > 5", "x = True"),
            ("x = 10 == 20", "x = False"),
            ("x = 'a' in ('a', 'b', 'c')", "x = True"),
            ("x = 'z' not in ('a', 'b')", "x = True"),
            ("x = True and False", "x = False"),
            ("x = True or False", "x = True"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.fold(src), expected)

    def test_safety_division_by_zero(self) -> None:
        code = "x = 10 / 0"
        # Should NOT crash and should leave expression unfolded
        self.assertEqual(self.fold(code), "x = 10 / 0")

    def test_safety_memory_limit(self) -> None:
        code = "x = 'a' * 1000000"
        # Length exceeds MAX_STR_LEN; must remain unfolded
        self.assertEqual(self.fold(code), "x = 'a' * 1000000")

    def test_safety_large_pow(self) -> None:
        code = "x = 2 ** 1000"
        # Exponent exceeds MAX_POW_EXP; must remain unfolded
        self.assertEqual(self.fold(code), "x = 2 ** 1000")

    def test_non_constant_untouched(self) -> None:
        code = "x = y + 10"
        self.assertEqual(self.fold(code), "x = y + 10")

    def test_provenance_records(self) -> None:
        tree = self.parser.parse("x = 10 + 20")
        tracker = ProvenanceTracker()
        pass_instance = ExpressionFoldingPass(filename="test.py")
        pass_instance.run(tree, tracker)

        self.assertEqual(len(tracker.records), 1)
        record = tracker.records[0]
        self.assertEqual(record.pass_name, "ExpressionFolding")
        self.assertEqual(record.original, "10 + 20")
        self.assertEqual(record.transformed, "30")


if __name__ == "__main__":
    unittest.main()
