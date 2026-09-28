"""Production Hardening and Adversarial Resilience Tests.

Phase 12: Production Hardening per Sections 22-27 of the Master Specification:
- Adversarial & Malformed Input Hardening across all 5 languages (Python, JS, TS, Java, Go)
- Deeply nested expressions and recursion limits
- Corrupted bytes and non-UTF8 input handling
- Arithmetic edge cases (zero division, modulo zero)
- Semantic preservation across transformations
- CLI subcommand resilience and exit codes
"""

import ast
import tempfile
import unittest
from pathlib import Path

from core.confidence import ConfidenceLevel
from core.exceptions import DeobfuscatorError, ParseError, UnsupportedLanguageError
from languages import registry
import languages.python
import languages.javascript
import languages.typescript
import languages.java
import languages.go
from main import read_source_file, build_parser, main


class TestAdversarialSyntax(unittest.TestCase):
    """Verify that malformed syntax across all languages cleanly raises ParseError."""

    def test_python_malformed_syntax(self) -> None:
        lang = registry.get("python")
        malformed_inputs = [
            "def broken_function(",
            "if True\n    x = 1",
            "x = = 5",
            "1 + * 2",
            "{'a': }",
        ]
        for src in malformed_inputs:
            with self.subTest(src=src):
                with self.assertRaises(ParseError):
                    lang.parse(src)

    def test_python_null_bytes(self) -> None:
        lang = registry.get("python")
        with self.assertRaises(ParseError):
            lang.parse("x = 'hello\x00world'")

    def test_javascript_malformed_syntax(self) -> None:
        lang = registry.get("javascript")
        malformed_inputs = [
            "function broken(",
            "var x = ;",
            "if (true { x = 1; }",
            "x = 5 + + ;",
        ]
        for src in malformed_inputs:
            with self.subTest(src=src):
                with self.assertRaises(ParseError):
                    lang.parse(src)

    def test_typescript_malformed_syntax(self) -> None:
        lang = registry.get("typescript")
        malformed_inputs = [
            "interface User { name: ; }",
            "function test<T(: void {}",
            "let x: = 10;",
        ]
        for src in malformed_inputs:
            with self.subTest(src=src):
                with self.assertRaises(ParseError):
                    lang.parse(src)

    def test_java_malformed_syntax(self) -> None:
        lang = registry.get("java")
        malformed_inputs = [
            "public class Incomplete {",
            "public void test() { int x = ; }",
            "class Foo { int x = (1 + ); }",
        ]
        for src in malformed_inputs:
            with self.subTest(src=src):
                with self.assertRaises(ParseError):
                    lang.parse(src)

    def test_go_malformed_syntax(self) -> None:
        lang = registry.get("go")
        malformed_inputs = [
            "func main(",
            "package main\nvar x = ",
            "package main\nfunc foo() { if true { x := 1 }",
        ]
        for src in malformed_inputs:
            with self.subTest(src=src):
                with self.assertRaises(ParseError):
                    lang.parse(src)


class TestDeepNestingAndResourceLimits(unittest.TestCase):
    """Verify parser resilience against deeply nested expressions and structures."""

    def test_python_deeply_nested_expressions(self) -> None:
        lang = registry.get("python")
        # 100 nested parentheses
        nested_src = "(" * 100 + "42" + ")" * 100
        tree = lang.parse(nested_src)
        self.assertIsNotNone(tree)
        unparsed = lang.unparse(tree)
        self.assertIn("42", unparsed)

    def test_javascript_deeply_nested_expressions(self) -> None:
        lang = registry.get("javascript")
        nested_src = "(" * 100 + "42" + ")" * 100 + ";"
        tree = lang.parse(nested_src)
        self.assertIsNotNone(tree)
        unparsed = lang.unparse(tree)
        self.assertIn("42", unparsed)

    def test_extreme_recursion_handled_cleanly(self) -> None:
        # Extreme nesting that exceeds Python recursion limit
        extreme_src = "(" * 2500 + "1" + ")" * 2500
        for lang_name in ("python", "javascript", "typescript"):
            lang = registry.get(lang_name)
            try:
                lang.parse(extreme_src)
            except ParseError:
                # Clean ParseError expected if recursion limit reached
                pass


class TestNonUtf8AndCorruptInputs(unittest.TestCase):
    """Verify handling of non-UTF8, binary, or corrupted input bytes."""

    def test_read_source_file_fallback(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            # Write non-UTF-8 bytes (latin-1 high bytes)
            f.write(b"# High byte test: \xff\xfe\xc0\xde\nvalue = 42\n")
            f_path = Path(f.name)

        try:
            content = read_source_file(f_path)
            self.assertIn("value = 42", content)
        finally:
            f_path.unlink(missing_ok=True)

    def test_read_nonexistent_file(self) -> None:
        non_existent = Path("/path/that/does/not/exist_deobf_12345.py")
        with self.assertRaises(DeobfuscatorError):
            read_source_file(non_existent)


class TestArithmeticHardening(unittest.TestCase):
    """Verify that arithmetic anomalies like division by zero do not crash the passes."""

    def test_python_division_by_zero_safe(self) -> None:
        from core.pipeline import Pipeline
        from passes.expression_folding import ExpressionFoldingPass

        lang = registry.get("python")
        src = "result = 1 / 0\nmodulo = 10 % 0\n"
        tree = lang.parse(src)

        pipeline = Pipeline()
        pipeline.add_pass(ExpressionFoldingPass())
        # Should execute safely without raising ZeroDivisionError
        result = pipeline.execute(tree)
        unparsed = lang.unparse(result)
        self.assertIn("1 / 0", unparsed)
        self.assertIn("10 % 0", unparsed)

    def test_javascript_division_by_zero_safe(self) -> None:
        from core.pipeline import Pipeline
        from languages.javascript.passes import JSExpressionFoldingPass

        lang = registry.get("javascript")
        src = "var x = 10 / 0; var y = 5 % 0;"
        tree = lang.parse(src)

        pipeline = Pipeline()
        pipeline.add_pass(JSExpressionFoldingPass())
        result = pipeline.execute(tree)
        unparsed = lang.unparse(result)
        self.assertIsNotNone(unparsed)


class TestSemanticPreservation(unittest.TestCase):
    """Verify Section 23: Semantic Preservation under deobfuscation transformations."""

    def test_python_semantic_preservation(self) -> None:
        from core.pipeline import Pipeline
        from passes.constant_propagation import ConstantPropagationPass
        from passes.expression_folding import ExpressionFoldingPass
        from passes.string_reconstruction import StringReconstructionPass

        lang = registry.get("python")
        src = """
a = 10
b = 20
c = a + b
s = "foo" + "bar"
"""
        tree = lang.parse(src)
        pipeline = Pipeline()
        pipeline.add_pass(ConstantPropagationPass())
        pipeline.add_pass(ExpressionFoldingPass())
        pipeline.add_pass(StringReconstructionPass())
        result = pipeline.execute(tree)

        # Execute both original and deobfuscated in safe local scopes
        scope_orig: dict = {}
        exec(src, {}, scope_orig)

        unparsed = lang.unparse(result)
        scope_deob: dict = {}
        exec(unparsed, {}, scope_deob)

        self.assertEqual(scope_orig["c"], scope_deob["c"])
        self.assertEqual(scope_orig["s"], scope_deob["s"])
        self.assertEqual(scope_deob["c"], 30)
        self.assertEqual(scope_deob["s"], "foobar")

    def test_ir_pipeline_semantic_preservation(self) -> None:
        from core.ir_pipeline import IRPipeline

        lang = registry.get("python")
        src = "x = 5 + 3\ny = x * 2\n"
        tree = lang.parse(src)
        ir_mod = lang.to_ir(tree)

        pipeline = IRPipeline()
        opt_ir = pipeline.execute(ir_mod)
        recovered_tree = lang.from_ir(opt_ir)
        out_code = lang.unparse(recovered_tree)

        scope: dict = {}
        exec(out_code, {}, scope)
        self.assertEqual(scope["x"], 8)
        self.assertEqual(scope["y"], 16)


class TestCLIHardening(unittest.TestCase):
    """Verify CLI error handling, subcommands, and exit codes."""

    def test_cli_missing_file(self) -> None:
        exit_code = main(["deobfuscate", "non_existent_file_deobf_123.py"])
        self.assertEqual(exit_code, 1)

    def test_cli_unsupported_language_override(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"content")
            f_path = Path(f.name)

        try:
            exit_code = main(["parse", str(f_path), "-l", "brainfuck"])
            self.assertEqual(exit_code, 1)
        finally:
            f_path.unlink(missing_ok=True)

    def test_cli_syntax_error_exit_code(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"def broken(\n")
            f_path = Path(f.name)

        try:
            exit_code = main(["parse", str(f_path)])
            self.assertEqual(exit_code, 2)
            exit_code_deob = main(["deobfuscate", str(f_path)])
            self.assertEqual(exit_code_deob, 2)
        finally:
            f_path.unlink(missing_ok=True)

    def test_cli_analyze_subcommand(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"x = 10 + 20\n")
            f_path = Path(f.name)

        try:
            exit_code = main(["analyze", str(f_path)])
            self.assertEqual(exit_code, 0)
        finally:
            f_path.unlink(missing_ok=True)

    def test_cli_report_subcommand(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"import base64\ns = base64.b64decode(b'VGVzdA==')\n")
            f_path = Path(f.name)

        try:
            exit_code = main(["report", str(f_path), "--format", "json"])
            self.assertEqual(exit_code, 0)
        finally:
            f_path.unlink(missing_ok=True)

    def test_cli_ir_subcommand_cfg(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"def check(x):\n    if x > 0:\n        return 1\n    return 0\n")
            f_path = Path(f.name)

        try:
            exit_code = main(["ir", str(f_path), "--cfg"])
            self.assertEqual(exit_code, 0)
        finally:
            f_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
