"""Unit tests for Control-Flow Flattening (CFF) recovery (Phase 3)."""

import ast
import unittest

from core.confidence import ConfidenceLevel
from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.cff_recovery import ControlFlowFlatteningPass


class TestCFFRecovery(unittest.TestCase):
    """Test suite for ControlFlowFlatteningPass."""

    def setUp(self) -> None:
        self.tracker = ProvenanceTracker()
        self.pass_ = ControlFlowFlatteningPass()

    def _transform(self, code: str) -> str:
        tree = ast.parse(code)
        transformed = self.pass_.run(tree, self.tracker)
        return PythonParser.unparse(transformed).strip()

    def test_linear_cff_recovery(self) -> None:
        code = """
def run():
    state = 1
    while state != 0:
        if state == 1:
            a = 10
            state = 2
        elif state == 2:
            b = 20
            state = 3
        elif state == 3:
            c = a + b
            state = 0
    return c
"""
        result = self._transform(code)
        self.assertNotIn("state =", result)
        self.assertNotIn("while", result)
        self.assertIn("a = 10", result)
        self.assertIn("b = 20", result)
        self.assertIn("c = a + b", result)
        self.assertIn("return c", result)

        records = [r for r in self.tracker.records if r.pass_name == "ControlFlowFlattening"]
        self.assertGreater(len(records), 0)
        self.assertTrue(all(r.confidence.level == ConfidenceLevel.CERTAIN for r in records))

    def test_cff_while_true_break(self) -> None:
        code = """
def task():
    state = 1
    while True:
        if state == 1:
            step1()
            state = 2
        elif state == 2:
            step2()
            break
"""
        result = self._transform(code)
        self.assertNotIn("while True:", result)
        self.assertNotIn("state =", result)
        self.assertNotIn("break", result)
        self.assertIn("step1()", result)
        self.assertIn("step2()", result)

    def test_cff_string_states(self) -> None:
        code = """
def construct():
    state = "init"
    while state != "exit":
        if state == "init":
            msg = "part1"
            state = "next"
        elif state == "next":
            msg = msg + "_part2"
            state = "exit"
    return msg
"""
        result = self._transform(code)
        self.assertNotIn("state =", result)
        self.assertNotIn("while", result)
        self.assertIn("msg = 'part1'", result)
        self.assertIn("msg = msg + '_part2'", result)
        self.assertIn("return msg", result)

    def test_cff_conditional_branching_diamond(self) -> None:
        code = """
def evaluate(x):
    state = 1
    while state != 0:
        if state == 1:
            val = x * 2
            if val > 10:
                state = 2
            else:
                state = 3
        elif state == 2:
            tag = "large"
            state = 4
        elif state == 3:
            tag = "small"
            state = 4
        elif state == 4:
            res = tag + "!"
            state = 0
    return res
"""
        result = self._transform(code)
        self.assertNotIn("state =", result)
        self.assertNotIn("while", result)
        self.assertIn("val = x * 2", result)
        self.assertIn("if val > 10:", result)
        self.assertIn("tag = 'large'", result)
        self.assertIn("tag = 'small'", result)
        self.assertIn("res = tag + '!'", result)
        self.assertIn("return res", result)

    def test_cff_return_in_state(self) -> None:
        code = """
def check():
    state = 1
    while state != 0:
        if state == 1:
            ready = True
            state = 2
        elif state == 2:
            status = "OK"
            return status
"""
        result = self._transform(code)
        self.assertNotIn("while", result)
        self.assertNotIn("state =", result)
        self.assertIn("ready = True", result)
        self.assertIn("status = 'OK'", result)
        self.assertIn("return status", result)

    def test_safety_non_cff_loop_untouched(self) -> None:
        code = """
def counter():
    i = 0
    while i < 10:
        i += 1
    return i
"""
        result = self._transform(code)
        self.assertIn("while i < 10:", result)
        self.assertIn("i += 1", result)
        self.assertEqual(len(self.tracker.records), 0)


if __name__ == "__main__":
    unittest.main()
