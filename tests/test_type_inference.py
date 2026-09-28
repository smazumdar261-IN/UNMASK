"""Unit tests for type inference and type annotation (Phase 4)."""

import ast
import unittest

from analysis.type_inference import TypeInferenceEngine
from core.confidence import ConfidenceLevel
from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.type_annotation import TypeAnnotationPass


class TestTypeInference(unittest.TestCase):
    """Test suite for TypeInferenceEngine and TypeAnnotationPass."""

    def setUp(self) -> None:
        self.engine = TypeInferenceEngine()
        self.tracker = ProvenanceTracker()
        self.pass_ = TypeAnnotationPass()

    def test_expression_type_inference(self) -> None:
        expr1 = ast.parse("10", mode="eval").body
        self.assertEqual(self.engine.infer_expression_type(expr1), "int")

        expr2 = ast.parse("'hello'", mode="eval").body
        self.assertEqual(self.engine.infer_expression_type(expr2), "str")

        expr3 = ast.parse("b'bytes'", mode="eval").body
        self.assertEqual(self.engine.infer_expression_type(expr3), "bytes")

        expr4 = ast.parse("True", mode="eval").body
        self.assertEqual(self.engine.infer_expression_type(expr4), "bool")

        expr5 = ast.parse("10 / 2", mode="eval").body
        self.assertEqual(self.engine.infer_expression_type(expr5), "float")

        expr6 = ast.parse("len([1, 2])", mode="eval").body
        self.assertEqual(self.engine.infer_expression_type(expr6), "int")

        expr7 = ast.parse("payload.decode('utf-8')", mode="eval").body
        self.assertEqual(self.engine.infer_expression_type(expr7), "str")

    def test_function_return_type_annotation(self) -> None:
        code = """
def calculate():
    return 100
"""
        tree = ast.parse(code)
        transformed = self.pass_.run(tree, self.tracker)
        result = PythonParser.unparse(transformed).strip()

        self.assertIn("def calculate() -> int:", result)
        records = [r for r in self.tracker.records if r.pass_name == "TypeAnnotation"]
        self.assertGreater(len(records), 0)
        self.assertTrue(all(r.confidence.level == ConfidenceLevel.CERTAIN for r in records))

    def test_function_none_return_annotation(self) -> None:
        code = """
def do_nothing():
    pass
"""
        tree = ast.parse(code)
        transformed = self.pass_.run(tree, self.tracker)
        result = PythonParser.unparse(transformed).strip()

        self.assertIn("def do_nothing() -> None:", result)

    def test_parameter_type_annotation(self) -> None:
        code = """
def process(count=10, prefix='ID_'):
    return prefix + str(count)
"""
        tree = ast.parse(code)
        transformed = self.pass_.run(tree, self.tracker)
        result = PythonParser.unparse(transformed).strip()

        self.assertIn("count: int=10", result)
        self.assertIn("prefix: str='ID_'", result)
        self.assertIn("-> str:", result)


if __name__ == "__main__":
    unittest.main()
