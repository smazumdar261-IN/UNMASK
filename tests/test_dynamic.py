"""Unit and integration tests for Secure Dynamic Analysis (Phase 11).

Per Section 18 & Section 19 of the Master Specification:
- ExecutionPolicy validation and module filtering
- SecureSandbox isolation, resource limits, and timeout enforcement
- Filesystem, network, and module prohibition
- ExecutionTracer step tracking and bounded loop prevention
- DynamicDecoderUnmasker algorithmic decoder unmasking
- CLI integration with --dynamic and --no-dynamic flags
"""

import io
import unittest
from unittest.mock import patch

from core.provenance import ProvenanceTracker
from dynamic.policy import ExecutionPolicy, SandboxResult
from dynamic.sandbox import SecureSandbox, SecurityViolationError
from dynamic.tracer import ExecutionTracer
from dynamic.unmasker import DynamicDecoderUnmasker
from languages.python.parser import PythonParser
import main


class TestExecutionPolicy(unittest.TestCase):
    """Tests security policy rules and module allowance."""

    def test_default_policy_limits(self) -> None:
        policy = ExecutionPolicy()
        self.assertEqual(policy.timeout_seconds, 2.0)
        self.assertEqual(policy.max_memory_bytes, 64 * 1024 * 1024)
        self.assertEqual(policy.max_cpu_time_seconds, 1.0)
        self.assertFalse(policy.allow_network)
        self.assertFalse(policy.allow_filesystem_write)

    def test_module_filtering(self) -> None:
        policy = ExecutionPolicy()
        # Allowed safe modules
        self.assertTrue(policy.is_module_allowed("base64"))
        self.assertTrue(policy.is_module_allowed("math"))
        self.assertTrue(policy.is_module_allowed("json"))
        self.assertTrue(policy.is_module_allowed("itertools"))

        # Blocked dangerous modules
        self.assertFalse(policy.is_module_allowed("os"))
        self.assertFalse(policy.is_module_allowed("sys"))
        self.assertFalse(policy.is_module_allowed("subprocess"))
        self.assertFalse(policy.is_module_allowed("socket"))
        self.assertFalse(policy.is_module_allowed("ctypes"))
        self.assertFalse(policy.is_module_allowed("shutil"))


class TestSecureSandbox(unittest.TestCase):
    """Tests sandbox isolation, resource limits, and execution safety."""

    def setUp(self) -> None:
        self.sandbox = SecureSandbox()

    def test_safe_expression_evaluation(self) -> None:
        res = self.sandbox.evaluate_expression("12 * 12 + 5")
        self.assertTrue(res.success)
        self.assertEqual(res.return_value, 149)

    def test_safe_string_operations(self) -> None:
        code = """
def build_greeting(name):
    return f"Hello, {name}!"
"""
        res = self.sandbox.run_function(code, "build_greeting", args=("World",))
        self.assertTrue(res.success)
        self.assertEqual(res.return_value, "Hello, World!")

    def test_blocked_module_import(self) -> None:
        res = self.sandbox.run_code("import os\nos.listdir('.')")
        self.assertFalse(res.success)
        self.assertTrue(res.security_violation)
        self.assertIn("not allowed in sandbox", res.error or "")

    def test_blocked_socket_import(self) -> None:
        res = self.sandbox.run_code("import socket\ns = socket.socket()")
        self.assertFalse(res.success)
        self.assertTrue(res.security_violation)

    def test_blocked_open_builtin(self) -> None:
        res = self.sandbox.run_code("with open('test.txt', 'w') as f: f.write('data')")
        self.assertFalse(res.success)
        self.assertIn("open", res.error or "")

    def test_timeout_enforcement(self) -> None:
        policy = ExecutionPolicy(timeout_seconds=0.3, allowed_modules={"time"})
        short_sandbox = SecureSandbox(policy=policy)
        res = short_sandbox.run_code("import time\ntime.sleep(5)")
        self.assertFalse(res.success)
        self.assertTrue(res.timed_out)
        self.assertIn("timed out", res.error or "")

    def test_step_count_limit_preventing_infinite_loop(self) -> None:
        policy = ExecutionPolicy(max_trace_steps=50)
        bounded_sandbox = SecureSandbox(policy=policy)
        res = bounded_sandbox.run_code("while True:\n    x = 1")
        self.assertFalse(res.success)
        self.assertIn("Execution step limit exceeded", res.error or "")


class TestExecutionTracer(unittest.TestCase):
    """Tests execution step tracking and string capture."""

    def test_tracer_captures_events(self) -> None:
        tracer = ExecutionTracer()
        tracer.start()

        def sample_routine(x: int) -> str:
            a = "intermediate_string"
            b = x * 2
            return f"result_{b}"

        out = sample_routine(5)
        tracer.stop()

        summary = tracer.get_trace_summary()
        self.assertEqual(out, "result_10")
        self.assertGreater(summary["total_steps"], 0)
        self.assertIn("intermediate_string", summary["captured_strings"])
        self.assertIn("result_10", summary["captured_returns"])


class TestDynamicDecoderUnmasker(unittest.TestCase):
    """Tests AST deobfuscation of complex decoder functions using the sandbox."""

    def test_unmask_xor_cipher_function(self) -> None:
        code = """
def decrypt(data, key):
    out = []
    for c in data:
        out.append(chr(ord(c) ^ key))
    return "".join(out)

secret = decrypt("Vd|{o", 21)
"""
        tree = PythonParser.parse(code)
        tracker = ProvenanceTracker()
        unmasker = DynamicDecoderUnmasker()

        transformed = unmasker.run(tree, tracker)
        unparsed = PythonParser.unparse(transformed)

        # "Vd|{o" XOR 21:
        # 'V' (86) ^ 21 = 67 ('C')
        # 'd' (100) ^ 21 = 113 ('q')
        # ...
        expected = "".join(chr(ord(c) ^ 21) for c in "Vd|{o")
        self.assertIn(repr(expected), unparsed)
        self.assertNotIn('decrypt("Vd|{o", 21)', unparsed)
        self.assertGreater(len(tracker.records), 0)

    def test_unmasker_leaves_non_constant_args_alone(self) -> None:
        code = """
def decode(val):
    return val + 10

result = decode(variable_arg)
"""
        tree = PythonParser.parse(code)
        tracker = ProvenanceTracker()
        unmasker = DynamicDecoderUnmasker()

        transformed = unmasker.run(tree, tracker)
        unparsed = PythonParser.unparse(transformed)
        self.assertIn("decode(variable_arg)", unparsed)
        self.assertEqual(len(tracker.records), 0)


class TestDynamicCLIIntegration(unittest.TestCase):
    """Tests CLI integration of --dynamic and --no-dynamic flags."""

    def test_cli_deobfuscate_without_dynamic(self) -> None:
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = main.main([
                "deobfuscate",
                "tests/samples/dynamic_obfuscated.py",
                "--confidence",
            ])
            self.assertEqual(exit_code, 0)
            output = fake_out.getvalue()
            self.assertIn("Dynamic execution:", output)
            self.assertIn("Not performed", output)
            self.assertIn("xor_decrypt('y^\\\\OY", output)

    def test_cli_deobfuscate_with_dynamic(self) -> None:
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = main.main([
                "deobfuscate",
                "tests/samples/dynamic_obfuscated.py",
                "--dynamic",
                "--confidence",
            ])
            self.assertEqual(exit_code, 0)
            output = fake_out.getvalue()
            self.assertIn("Dynamic execution:", output)
            self.assertIn("Performed: Yes", output)
            self.assertIn("SuperSecretPayload2026", output)


if __name__ == "__main__":
    unittest.main()
