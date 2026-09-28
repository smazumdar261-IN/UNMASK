"""Unit tests for Python parser (Phase 1A)."""

import ast
import unittest
from pathlib import Path

from core.exceptions import ParseError
from languages.python.parser import PythonParser, PythonLanguage


class TestPythonParser(unittest.TestCase):
    """Test suite for PythonParser implementation."""

    def setUp(self) -> None:
        self.parser = PythonParser()
        self.samples_dir = Path(__file__).parent / "samples"

    def test_parse_valid_code(self) -> None:
        code = "x = 42\ny = 'hello'\nprint(x, y)"
        tree = self.parser.parse(code)
        self.assertIsInstance(tree, ast.Module)
        self.assertEqual(len(tree.body), 3)

    def test_parse_sample_file(self) -> None:
        sample_path = self.samples_dir / "simple.py"
        source = sample_path.read_text(encoding="utf-8")
        tree = self.parser.parse(source, filename=str(sample_path))
        self.assertIsInstance(tree, ast.Module)

    def test_parse_syntax_error_details(self) -> None:
        code = "def foo(\n    return 1\n"
        with self.assertRaises(ParseError) as ctx:
            self.parser.parse(code, filename="test_bad.py")

        err = ctx.exception
        self.assertEqual(err.filename, "test_bad.py")
        self.assertIsNotNone(err.lineno)
        self.assertIn("line", str(err))

    def test_validate_syntax(self) -> None:
        valid_code = "a = 1 + 2"
        is_valid, err = self.parser.validate_syntax(valid_code)
        self.assertTrue(is_valid)
        self.assertIsNone(err)

        invalid_code = "a = 1 +"
        is_valid, err = self.parser.validate_syntax(invalid_code)
        self.assertFalse(is_valid)
        self.assertIsInstance(err, ParseError)

    def test_unparse_roundtrip(self) -> None:
        code = "def add(a: int, b: int) -> int:\n    return a + b"
        tree = self.parser.parse(code)
        regenerated = self.parser.unparse(tree)

        # Unparsed code should parse into an equivalent AST
        tree_second = self.parser.parse(regenerated)
        self.assertEqual(ast.dump(tree), ast.dump(tree_second))

    def test_find_nodes(self) -> None:
        code = "a = 1\nb = 2\ndef f():\n    c = 3\n    return c"
        tree = self.parser.parse(code)
        assign_nodes = self.parser.find_nodes(tree, ast.Assign)
        self.assertEqual(len(assign_nodes), 3)
        func_nodes = self.parser.find_nodes(tree, ast.FunctionDef)
        self.assertEqual(len(func_nodes), 1)
        self.assertEqual(func_nodes[0].name, "f")

    def test_get_location(self) -> None:
        code = "x = 100"
        tree = self.parser.parse(code)
        stmt = tree.body[0]
        loc = self.parser.get_location(stmt, filename="test.py")
        self.assertEqual(loc.start_line, 1)
        self.assertEqual(loc.start_col, 0)
        self.assertEqual(loc.filename, "test.py")


if __name__ == "__main__":
    unittest.main()
