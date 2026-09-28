"""Integration tests for the CLI commands (Phase 0)."""

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from main import main


class TestCLI(unittest.TestCase):
    """Test suite for CLI interface."""

    def setUp(self) -> None:
        self.samples_dir = Path(__file__).parent / "samples"
        self.simple_sample = str(self.samples_dir / "simple.py")
        self.bad_sample = str(self.samples_dir / "invalid_syntax.py")

    def run_cli(self, args: list) -> tuple[int, str, str]:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            try:
                code = main(args)
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 0
        return code, stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_cli_help(self) -> None:
        code, out, _ = self.run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("Universal Deobfuscator", out)

    def test_cli_banner(self) -> None:
        code, out, _ = self.run_cli(["--banner", "--no-rain"])
        self.assertEqual(code, 0)
        self.assertIn("UNMASK", out)
        self.assertIn("DEVELOPED BY : SAYANTAN", out)

    def test_detect_command(self) -> None:
        code, out, _ = self.run_cli(["detect", self.simple_sample])
        self.assertEqual(code, 0)
        self.assertIn("Language: python", out)

    def test_detect_nonexistent_file(self) -> None:
        code, _, err = self.run_cli(["detect", "nonexistent_file.py"])
        self.assertNotEqual(code, 0)
        self.assertIn("not found", err)

    def test_parse_command_valid(self) -> None:
        code, out, _ = self.run_cli(["parse", self.simple_sample, "--unparse"])
        self.assertEqual(code, 0)
        self.assertIn("Successfully parsed", out)
        self.assertIn("def greeting", out)

    def test_parse_command_show_ast(self) -> None:
        code, out, _ = self.run_cli(["parse", self.simple_sample, "--show-ast"])
        self.assertEqual(code, 0)
        self.assertIn("Module(", out)

    def test_parse_command_invalid_syntax(self) -> None:
        code, _, err = self.run_cli(["parse", self.bad_sample])
        self.assertEqual(code, 2)
        self.assertIn("Syntax Error", err)

    def test_deobfuscate_command(self) -> None:
        code, out, _ = self.run_cli(["deobfuscate", self.simple_sample, "--report"])
        self.assertEqual(code, 0)
        self.assertIn("def greeting", out)
        self.assertIn("Universal Deobfuscator Audit Report", out)

    def test_javascript_cli_detect_parse_and_deobfuscate(self) -> None:
        js_sample = str(self.samples_dir / "javascript_obfuscated.js")
        code, out, _ = self.run_cli(["detect", js_sample])
        self.assertEqual(code, 0)
        self.assertIn("Language: javascript", out)

        code, out, _ = self.run_cli(["parse", js_sample, "--unparse"])
        self.assertEqual(code, 0)
        self.assertIn("Successfully parsed", out)

        code, out, _ = self.run_cli(["deobfuscate", js_sample, "--confidence", "--report"])
        self.assertEqual(code, 0)
        self.assertIn("console.log(", out)
        self.assertIn("'Bearer token_secret_12345'", out)
        self.assertIn("Universal Deobfuscator Audit Report", out)

    def test_typescript_cli_detect_parse_and_deobfuscate(self) -> None:
        ts_sample = str(self.samples_dir / "typescript_obfuscated.ts")
        code, out, _ = self.run_cli(["detect", ts_sample])
        self.assertEqual(code, 0)
        self.assertIn("Language: typescript", out)

        code, out, _ = self.run_cli(["parse", ts_sample, "--unparse"])
        self.assertEqual(code, 0)
        self.assertIn("interface ServiceConfig", out)

        # Deobfuscate preserving TypeScript types
        code, out, _ = self.run_cli(["deobfuscate", ts_sample, "--confidence", "--report"])
        self.assertEqual(code, 0)
        self.assertIn("interface ServiceConfig", out)
        self.assertIn("'TK_SUPER_SECRET_2026'", out)
        self.assertIn("Universal Deobfuscator Audit Report", out)

        # Deobfuscate compiling to clean JavaScript
        code, out, _ = self.run_cli(["deobfuscate", ts_sample, "--target-js"])
        self.assertEqual(code, 0)
        self.assertNotIn("interface ServiceConfig", out)
        self.assertIn("var StatusLevel =", out)
        self.assertIn("'TK_SUPER_SECRET_2026'", out)

    def test_java_cli_detect_parse_and_deobfuscate(self) -> None:
        java_sample = str(self.samples_dir / "java_obfuscated.java")
        code, out, _ = self.run_cli(["detect", java_sample])
        self.assertEqual(code, 0)
        self.assertIn("Language: java", out)

        code, out, _ = self.run_cli(["parse", java_sample, "--unparse"])
        self.assertEqual(code, 0)
        self.assertIn("class PayloadRunner", out)

        code, out, _ = self.run_cli(["deobfuscate", java_sample, "--confidence", "--report"])
        self.assertEqual(code, 0)
        self.assertIn("class PayloadRunner", out)
        self.assertIn('"SuperSecretToken2026"', out)
        self.assertIn('"Secret"', out)
        self.assertIn("8080", out)
        self.assertNotIn("Dead branch that should be removed", out)
        self.assertIn("Universal Deobfuscator Audit Report", out)

    def test_go_cli_detect_parse_and_deobfuscate(self) -> None:
        go_sample = str(self.samples_dir / "go_obfuscated.go")
        code, out, _ = self.run_cli(["detect", go_sample])
        self.assertEqual(code, 0)
        self.assertIn("Language: go", out)

        code, out, _ = self.run_cli(["parse", go_sample, "--unparse"])
        self.assertEqual(code, 0)
        self.assertIn("func main()", out)

        code, out, _ = self.run_cli(["deobfuscate", go_sample, "--confidence", "--report"])
        self.assertEqual(code, 0)
        self.assertIn("func main()", out)
        self.assertIn('"SuperSecretToken2026"', out)
        self.assertIn('"Secret"', out)
        self.assertIn('"Golang"', out)
        self.assertIn("54", out)
        self.assertIn("8080", out)
        self.assertNotIn("Dead branch that should be removed", out)
        self.assertIn("Universal Deobfuscator Audit Report", out)




if __name__ == "__main__":
    unittest.main()
