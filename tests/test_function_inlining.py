"""Unit tests for FunctionInliningPass (Phase 2)."""

import unittest

from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.function_inlining import FunctionInliningPass


class TestFunctionInlining(unittest.TestCase):
    """Test suite for inlining pure constant-returning and single-expression wrappers."""

    def setUp(self) -> None:
        self.parser = PythonParser()

    def inline(self, code: str) -> str:
        tree = self.parser.parse(code)
        tracker = ProvenanceTracker()
        pass_instance = FunctionInliningPass(filename="test.py")
        new_tree = pass_instance.run(tree, tracker)
        return self.parser.unparse(new_tree)

    def test_constant_returning_function(self) -> None:
        code = (
            "def get_secret():\n"
            "    return 'SUPER_SECRET_123'\n"
            "token = get_secret()\n"
        )
        out = self.inline(code)
        self.assertIn("token = 'SUPER_SECRET_123'", out)

    def test_simple_wrapper_function(self) -> None:
        code = (
            "def wrap_decode(data):\n"
            "    return base64.b64decode(data)\n"
            "val = wrap_decode('SGVsbG8=')\n"
        )
        out = self.inline(code)
        self.assertIn("val = base64.b64decode('SGVsbG8=')", out)

    def test_binary_op_wrapper(self) -> None:
        code = (
            "def add_nums(a, b):\n"
            "    return a + b\n"
            "ans = add_nums(10, 20)\n"
        )
        out = self.inline(code)
        self.assertIn("ans = 10 + 20", out)


if __name__ == "__main__":
    unittest.main()
