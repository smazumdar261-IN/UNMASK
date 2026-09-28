"""Tests for JavaScript Deobfuscation Passes (Phase 6).

Per Section 12 of the Master Specification:
Verifies:
- Constant propagation
- Expression folding (arithmetic, string concat, boolean, bitwise)
- Decoder detection (atob, btoa, decodeURIComponent, unescape)
- String reconstruction (String.fromCharCode, array.join, string reversal, split)
- Property normalization (bracket to dot notation)
- IIFE normalization
- Full pipeline integration and confidence tracking
"""

from __future__ import annotations

import unittest

from core.confidence import ConfidenceLevel
from core.pipeline import Pipeline
from core.provenance import ProvenanceTracker
from languages.javascript.parser import JSParser
from languages.javascript.printer import JSPrinter
from languages.javascript.passes.constant_propagation import JSConstantPropagationPass
from languages.javascript.passes.decoders import JSDecoderDetectionPass
from languages.javascript.passes.expression_folding import JSExpressionFoldingPass
from languages.javascript.passes.iife_normalization import JSIIFENormalizationPass
from languages.javascript.passes.property_normalization import JSPropertyNormalizationPass
from languages.javascript.passes.string_reconstruction import JSStringReconstructionPass


class TestJSConstantPropagation(unittest.TestCase):
    """Test suite for JSConstantPropagationPass."""

    def test_basic_constant_propagation(self) -> None:
        source = "var a = 'secret'; console.log(a);"
        tree = JSParser(source).parse()
        tracker = ProvenanceTracker()
        pass_instance = JSConstantPropagationPass()
        result = pass_instance.run(tree, tracker=tracker)
        output = JSPrinter.print_code(result)
        self.assertIn("console.log('secret');", output)
        self.assertGreater(len(tracker.records), 0)

    def test_reassignment_preservation(self) -> None:
        source = "var a = 1; a = 2; console.log(a);"
        tree = JSParser(source).parse()
        tracker = ProvenanceTracker()
        pass_instance = JSConstantPropagationPass()
        result = pass_instance.run(tree, tracker=tracker)
        output = JSPrinter.print_code(result)
        # Should NOT replace a with 1 in console.log(a) because a is reassigned
        self.assertIn("console.log(a);", output)

    def test_parameter_shadowing(self) -> None:
        source = "var x = 100; function foo(x) { return x; }"
        tree = JSParser(source).parse()
        tracker = ProvenanceTracker()
        pass_instance = JSConstantPropagationPass()
        result = pass_instance.run(tree, tracker=tracker)
        output = JSPrinter.print_code(result)
        # x inside foo(x) should NOT be replaced by 100
        self.assertIn("function foo(x) {\n    return x;\n}", output)

    def test_property_name_preserved(self) -> None:
        source = "var log = 'test'; console.log(log);"
        tree = JSParser(source).parse()
        tracker = ProvenanceTracker()
        pass_instance = JSConstantPropagationPass()
        result = pass_instance.run(tree, tracker=tracker)
        output = JSPrinter.print_code(result)
        # console.log should remain console.log, while argument log becomes 'test'
        self.assertIn("console.log('test');", output)


class TestJSExpressionFolding(unittest.TestCase):
    """Test suite for JSExpressionFoldingPass."""

    def test_arithmetic_folding(self) -> None:
        source = "var x = 10 + 20 * 2;"
        tree = JSParser(source).parse()
        result = JSExpressionFoldingPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var x = 50;", output)

    def test_string_concatenation(self) -> None:
        source = "var s = 'hello ' + 'world' + '!';"
        tree = JSParser(source).parse()
        # Run until convergence for chained additions
        p = Pipeline()
        p.add_pass(JSExpressionFoldingPass())
        result = p.execute(tree, until_convergence=True)
        output = JSPrinter.print_code(result)
        self.assertIn("var s = 'hello world!';", output)

    def test_boolean_and_comparisons(self) -> None:
        source = "var a = (1 + 1 === 2); var b = !false;"
        tree = JSParser(source).parse()
        p = Pipeline()
        p.add_pass(JSExpressionFoldingPass())
        result = p.execute(tree, until_convergence=True)
        output = JSPrinter.print_code(result)
        self.assertIn("var a = true;", output)
        self.assertIn("var b = true;", output)

    def test_bitwise_operations(self) -> None:
        source = "var x = 1 ^ 3; var y = ~0;"
        tree = JSParser(source).parse()
        result = JSExpressionFoldingPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var x = 2;", output)
        self.assertIn("var y = -1;", output)

    def test_typeof_operator(self) -> None:
        source = "var t = typeof 'abc';"
        tree = JSParser(source).parse()
        result = JSExpressionFoldingPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var t = 'string';", output)


class TestJSDecoders(unittest.TestCase):
    """Test suite for JSDecoderDetectionPass."""

    def test_atob_decoding(self) -> None:
        source = "var secret = atob('SGVsbG8gV29ybGQh');"
        tree = JSParser(source).parse()
        tracker = ProvenanceTracker()
        result = JSDecoderDetectionPass().run(tree, tracker=tracker)
        output = JSPrinter.print_code(result)
        self.assertIn("var secret = 'Hello World!';", output)
        self.assertEqual(len(tracker.records), 1)
        self.assertEqual(tracker.records[0].confidence.level, ConfidenceLevel.CERTAIN)

    def test_btoa_encoding(self) -> None:
        source = "var b64 = btoa('Hello World!');"
        tree = JSParser(source).parse()
        result = JSDecoderDetectionPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var b64 = 'SGVsbG8gV29ybGQh';", output)

    def test_decode_uri_component(self) -> None:
        source = "var url = decodeURIComponent('%48%65%6c%6c%6f%20%57%6f%72%6c%64');"
        tree = JSParser(source).parse()
        result = JSDecoderDetectionPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var url = 'Hello World';", output)

    def test_unescape_hex_and_unicode(self) -> None:
        source = "var s = unescape('%u0048%u0065%u006c%u006c%u006f');"
        tree = JSParser(source).parse()
        result = JSDecoderDetectionPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var s = 'Hello';", output)

    def test_window_atob_qualifier(self) -> None:
        source = "var secret = window.atob('SGVsbG8=');"
        tree = JSParser(source).parse()
        result = JSDecoderDetectionPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var secret = 'Hello';", output)


class TestJSStringReconstruction(unittest.TestCase):
    """Test suite for JSStringReconstructionPass."""

    def test_string_from_char_code(self) -> None:
        source = "var s = String.fromCharCode(72, 101, 108, 108, 111);"
        tree = JSParser(source).parse()
        tracker = ProvenanceTracker()
        result = JSStringReconstructionPass().run(tree, tracker=tracker)
        output = JSPrinter.print_code(result)
        self.assertIn("var s = 'Hello';", output)
        self.assertGreater(len(tracker.records), 0)

    def test_array_join(self) -> None:
        source = "var s = ['H', 'e', 'l', 'l', 'o'].join('');"
        tree = JSParser(source).parse()
        result = JSStringReconstructionPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var s = 'Hello';", output)

    def test_array_join_separator(self) -> None:
        source = "var s = ['a', 'b', 'c'].join('-');"
        tree = JSParser(source).parse()
        result = JSStringReconstructionPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var s = 'a-b-c';", output)

    def test_string_reversal_idiom(self) -> None:
        source = "var s = 'dlrow olleh'.split('').reverse().join('');"
        tree = JSParser(source).parse()
        result = JSStringReconstructionPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var s = 'hello world';", output)

    def test_string_split(self) -> None:
        source = "var arr = 'foo,bar,baz'.split(',');"
        tree = JSParser(source).parse()
        result = JSStringReconstructionPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var arr = ['foo', 'bar', 'baz'];", output)


class TestJSPropertyNormalization(unittest.TestCase):
    """Test suite for JSPropertyNormalizationPass."""

    def test_safe_property_access(self) -> None:
        source = "console['log']('hello'); Math['floor'](4.2);"
        tree = JSParser(source).parse()
        result = JSPropertyNormalizationPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("console.log('hello');", output)
        self.assertIn("Math.floor(4.2);", output)

    def test_keyword_property_preserved(self) -> None:
        source = "obj['default'] = 123; obj['var'] = 456;"
        tree = JSParser(source).parse()
        result = JSPropertyNormalizationPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("obj['default'] = 123;", output)
        self.assertIn("obj['var'] = 456;", output)

    def test_invalid_identifier_property_preserved(self) -> None:
        source = "headers['Content-Type'] = 'text/plain';"
        tree = JSParser(source).parse()
        result = JSPropertyNormalizationPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("headers['Content-Type'] = 'text/plain';", output)


class TestJSIIFENormalization(unittest.TestCase):
    """Test suite for JSIIFENormalizationPass."""

    def test_simple_constant_iife(self) -> None:
        source = "var x = (function() { return 'inlined'; })();"
        tree = JSParser(source).parse()
        result = JSIIFENormalizationPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var x = 'inlined';", output)

    def test_parameterized_iife(self) -> None:
        source = "var val = (function(a, b) { return a + b; })(10, 20);"
        tree = JSParser(source).parse()
        result = JSIIFENormalizationPass().run(tree)
        output = JSPrinter.print_code(result)
        self.assertIn("var val = 10 + 20;", output)


class TestJSPipelineIntegration(unittest.TestCase):
    """End-to-end integration tests for JavaScript deobfuscation pipeline."""

    def test_full_deobfuscation_pipeline(self) -> None:
        # Heavily obfuscated JS pattern combining decoders, String.fromCharCode,
        # array joins, split reversal, bracket property access, and constant propagation
        source = """
        var encoded = 'SGVsbG8gV29ybGQh';
        var secret = atob(encoded);
        var part1 = String.fromCharCode(85, 110, 105, 118, 101, 114, 115, 97, 108);
        var part2 = [' ', 'D', 'e', 'o', 'b', 'f'].join('');
        var title = part1 + part2;
        var reversed = 'edoc'.split('').reverse().join('');
        console['log'](secret, title, reversed);
        """
        tree = JSParser(source).parse()

        pipeline = Pipeline()
        pipeline.add_pass(JSConstantPropagationPass())
        pipeline.add_pass(JSDecoderDetectionPass())
        pipeline.add_pass(JSStringReconstructionPass())
        pipeline.add_pass(JSExpressionFoldingPass())
        pipeline.add_pass(JSPropertyNormalizationPass())
        pipeline.add_pass(JSIIFENormalizationPass())

        result = pipeline.execute(tree, max_iterations=10, until_convergence=True)
        output = JSPrinter.print_code(result)

        # Assert all obfuscated elements were reconstructed
        self.assertIn("console.log(", output)
        self.assertIn("'Hello World!'", output)
        self.assertIn("'Universal Deobf'", output)
        self.assertIn("'code'", output)

        # Verify confidence metrics
        engine = pipeline.tracker.get_engine()
        self.assertGreater(engine.compute_average_confidence(), 0.8)
        self.assertGreater(len(pipeline.tracker.records), 4)


if __name__ == "__main__":
    unittest.main()
