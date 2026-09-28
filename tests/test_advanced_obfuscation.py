"""Integration tests for Advanced Python Obfuscation (Phase 2)."""

import unittest

from core.pipeline import Pipeline
from languages.python.parser import PythonParser
from passes.constant_propagation import ConstantPropagationPass
from passes.dead_code import DeadCodeEliminationPass
from passes.decoder_detection import DecoderDetectionPass
from passes.expression_folding import ExpressionFoldingPass
from passes.function_inlining import FunctionInliningPass
from passes.import_analysis import ImportNormalizationPass
from passes.simplify import SimplificationPass
from passes.string_reconstruction import StringReconstructionPass


class TestAdvancedObfuscation(unittest.TestCase):
    """End-to-end integration tests for Phase 2 transformations."""

    def setUp(self) -> None:
        self.parser = PythonParser()

    def full_pipeline(self, code: str) -> tuple[str, str]:
        tree = self.parser.parse(code)
        pipeline = Pipeline()
        pipeline.add_pass(ImportNormalizationPass(filename="test.py"))
        pipeline.add_pass(FunctionInliningPass(filename="test.py"))
        pipeline.add_pass(ConstantPropagationPass(filename="test.py"))
        pipeline.add_pass(DecoderDetectionPass(filename="test.py"))
        pipeline.add_pass(StringReconstructionPass(filename="test.py"))
        pipeline.add_pass(ExpressionFoldingPass(filename="test.py"))
        pipeline.add_pass(SimplificationPass(filename="test.py"))
        pipeline.add_pass(DeadCodeEliminationPass(filename="test.py"))

        result = pipeline.execute(tree, max_iterations=10, until_convergence=True)
        return self.parser.unparse(result), pipeline.generate_report()

    def test_multi_stage_nested_decoding(self) -> None:
        # Base64 string encoded as Hex:
        # "Hello" -> Base64: "SGVsbG8=" -> Hex: "534756736247383d"
        code = (
            "import base64 as _b\n"
            "from binascii import unhexlify as _uh\n"
            "\n"
            "def retrieve():\n"
            "    hex_data = '534756736247383d'\n"
            "    b64_bytes = _uh(hex_data)\n"
            "    raw_bytes = _b.b64decode(b64_bytes)\n"
            "    text = raw_bytes.decode('utf-8')\n"
            "    return text\n"
        )
        out, report = self.full_pipeline(code)
        self.assertIn("return 'Hello'", out)
        self.assertIn("[CERTAIN]", report)

    def test_wrapper_and_opaque_predicate_deobfuscation(self) -> None:
        code = (
            "def _wrap_flag():\n"
            "    return 'FLAG{deobfuscated_phase_2}'\n"
            "\n"
            "def get_flag():\n"
            "    junk = 100 * 25 + 0\n"
            "    if 10 > 2:\n"
            "        flag = _wrap_flag()\n"
            "    else:\n"
            "        flag = 'fake_flag'\n"
            "    return flag\n"
        )
        out, _ = self.full_pipeline(code)
        self.assertIn("return 'FLAG{deobfuscated_phase_2}'", out)
        self.assertNotIn("fake_flag", out)
        self.assertNotIn("junk", out)


if __name__ == "__main__":
    unittest.main()
