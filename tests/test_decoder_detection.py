"""Unit tests for Decoder Detection pass and end-to-end pipeline (Phase 1D)."""

import unittest

from core.pipeline import Pipeline
from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.constant_propagation import ConstantPropagationPass
from passes.decoder_detection import DecoderDetectionPass
from passes.expression_folding import ExpressionFoldingPass
from passes.string_reconstruction import StringReconstructionPass


class TestDecoderDetection(unittest.TestCase):
    """Test suite for DecoderDetectionPass."""

    def setUp(self) -> None:
        self.parser = PythonParser()

    def deobfuscate(self, code: str) -> str:
        tree = self.parser.parse(code)
        pipeline = Pipeline()
        pipeline.add_pass(ConstantPropagationPass(filename="test.py"))
        pipeline.add_pass(DecoderDetectionPass(filename="test.py"))
        pipeline.add_pass(StringReconstructionPass(filename="test.py"))
        pipeline.add_pass(ExpressionFoldingPass(filename="test.py"))
        result = pipeline.execute(tree, until_convergence=True)
        return self.parser.unparse(result)

    def test_b64decode_evaluation(self) -> None:
        code = "data = base64.b64decode('SGVsbG8gV29ybGQ=')"
        out = self.deobfuscate(code)
        self.assertEqual(out, "data = b'Hello World'")

    def test_bytes_fromhex_evaluation(self) -> None:
        code = "data = bytes.fromhex('536563757265')"
        out = self.deobfuscate(code)
        self.assertEqual(out, "data = b'Secure'")

    def test_unhexlify_evaluation(self) -> None:
        code = "data = binascii.unhexlify('41757468')"
        out = self.deobfuscate(code)
        self.assertEqual(out, "data = b'Auth'")

    def test_url_unquote_evaluation(self) -> None:
        code = "url = urllib.parse.unquote('https%3A%2F%2Fapi%2Esite%2Ecom')"
        out = self.deobfuscate(code)
        self.assertEqual(out, "url = 'https://api.site.com'")

    def test_chained_base64_decode_pipeline(self) -> None:
        # Example directly from Section 8 of the Master Specification:
        # a = "SGVsbG8="
        # b = base64.b64decode(a)
        # c = b.decode()
        # print(c)
        code = (
            "a = 'SGVsbG8='\n"
            "b = base64.b64decode(a)\n"
            "c = b.decode()\n"
            "print(c)"
        )
        out = self.deobfuscate(code)
        self.assertIn("a = 'SGVsbG8='", out)
        self.assertIn("b = b'Hello'", out)
        self.assertIn("c = 'Hello'", out)
        self.assertIn("print('Hello')", out)

    def test_non_constant_call_untouched(self) -> None:
        code = "token = base64.b64decode(fetch_token())"
        out = self.deobfuscate(code)
        self.assertEqual(out, "token = base64.b64decode(fetch_token())")


if __name__ == "__main__":
    unittest.main()
