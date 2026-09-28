"""Unit tests for String Reconstruction (Phase 1C)."""

import unittest

from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.constant_propagation import ConstantPropagationPass
from passes.expression_folding import ExpressionFoldingPass
from passes.string_reconstruction import StringReconstructionPass
from core.pipeline import Pipeline


class TestStringReconstruction(unittest.TestCase):
    """Test suite for static string reconstruction."""

    def setUp(self) -> None:
        self.parser = PythonParser()

    def reconstruct(self, code: str) -> str:
        tree = self.parser.parse(code)
        tracker = ProvenanceTracker()
        pass_instance = StringReconstructionPass(filename="test.py")
        new_tree = pass_instance.run(tree, tracker)
        return self.parser.unparse(new_tree)

    def pipeline_deobfuscate(self, code: str) -> str:
        tree = self.parser.parse(code)
        pipeline = Pipeline()
        pipeline.add_pass(ConstantPropagationPass(filename="test.py"))
        pipeline.add_pass(StringReconstructionPass(filename="test.py"))
        pipeline.add_pass(ExpressionFoldingPass(filename="test.py"))
        result = pipeline.execute(tree, until_convergence=True)
        return self.parser.unparse(result)

    def test_chr_evaluation(self) -> None:
        cases = [
            ("x = chr(65)", "x = 'A'"),
            ("x = chr(10)", "x = '\\n'"),
            ("x = chr(9731)", "x = '☃'"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.reconstruct(src), expected)

    def test_ord_evaluation(self) -> None:
        cases = [
            ("x = ord('A')", "x = 65"),
            ("x = ord('z')", "x = 122"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.reconstruct(src), expected)

    def test_chr_concatenation_pipeline(self) -> None:
        code = "msg = chr(72) + chr(105) + chr(33)"
        res = self.pipeline_deobfuscate(code)
        self.assertEqual(res, "msg = 'Hi!'")

    def test_string_join(self) -> None:
        cases = [
            ("x = ''.join(['a', 'b', 'c'])", "x = 'abc'"),
            ("x = '-'.join(['2026', '09', '24'])", "x = '2026-09-24'"),
            ("x = b':'.join([b'root', b'x', b'0'])", "x = b'root:x:0'"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.reconstruct(src), expected)

    def test_join_with_chr_list(self) -> None:
        code = "res = ''.join([chr(72), chr(101), chr(108), chr(108), chr(111)])"
        out = self.pipeline_deobfuscate(code)
        self.assertEqual(out, "res = 'Hello'")

    def test_bytes_decode(self) -> None:
        cases = [
            ("s = b'Hello World'.decode('utf-8')", "s = 'Hello World'"),
            ("s = b'Admin'.decode()", "s = 'Admin'"),
            ("s = b'\\x41\\x42\\x43'.decode('ascii')", "s = 'ABC'"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.reconstruct(src), expected)

    def test_bytes_constructor_and_decode(self) -> None:
        code = "s = bytes([83, 101, 99, 114, 101, 116]).decode()"
        out = self.pipeline_deobfuscate(code)
        self.assertEqual(out, "s = 'Secret'")

    def test_string_format(self) -> None:
        cases = [
            ("x = 'Hello, {}'.format('Alice')", "x = 'Hello, Alice'"),
            ("x = '{user}:{role}'.format(user='root', role='admin')", "x = 'root:admin'"),
            ("x = 'ID: %04d, Tag: %s' % (7, 'beta')", "x = 'ID: 0007, Tag: beta'"),
        ]
        for src, expected in cases:
            with self.subTest(src=src):
                self.assertEqual(self.reconstruct(src), expected)

    def test_constant_fstring(self) -> None:
        code = "tag = 'v2'\nx = f'version_{tag}_release'"
        out = self.pipeline_deobfuscate(code)
        self.assertEqual(out, "tag = 'v2'\nx = 'version_v2_release'")

    def test_safety_invalid_encoding(self) -> None:
        # Disallowed encoding codec should NOT execute and should leave AST untouched
        code = "s = b'test'.decode('unknown_codec_name')"
        self.assertEqual(self.reconstruct(code), code)

    def test_safety_decode_error(self) -> None:
        # Invalid UTF-8 sequence should not crash
        code = "s = b'\\xff\\xfe'.decode('utf-8')"
        self.assertEqual(self.reconstruct(code), code)

    def test_safety_chr_out_of_range(self) -> None:
        code = "x = chr(999999999)"
        self.assertEqual(self.reconstruct(code), code)

    def test_provenance_recording(self) -> None:
        tree = self.parser.parse("x = chr(65)")
        tracker = ProvenanceTracker()
        pass_instance = StringReconstructionPass(filename="test.py")
        pass_instance.run(tree, tracker)

        self.assertEqual(len(tracker.records), 1)
        rec = tracker.records[0]
        self.assertEqual(rec.pass_name, "StringReconstruction")
        self.assertEqual(rec.original, "chr(65)")
        self.assertEqual(rec.transformed, "'A'")


if __name__ == "__main__":
    unittest.main()
