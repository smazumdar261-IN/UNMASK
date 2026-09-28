"""Unit tests for Control Flow Graph (CFG) analysis (Phase 3)."""

import ast
import unittest

from analysis.cfg import BasicBlock, CFGBuilder, ControlFlowGraph, EdgeType


class TestCFG(unittest.TestCase):
    """Test suite for BasicBlock, CFGEdge, ControlFlowGraph, and CFGBuilder."""

    def setUp(self) -> None:
        self.builder = CFGBuilder()

    def test_linear_code_cfg(self) -> None:
        code = """
x = 1
y = 2
z = x + y
"""
        tree = ast.parse(code)
        cfg = self.builder.build(tree, name="linear_test")

        self.assertIsNotNone(cfg.entry_block)
        self.assertIsNotNone(cfg.exit_block)
        # Entry block should have 3 statements
        self.assertEqual(len(cfg.entry_block.statements), 3)

        # Edge from entry to exit
        self.assertEqual(len(cfg.entry_block.successors), 1)
        edge = cfg.entry_block.successors[0]
        self.assertEqual(edge.target, cfg.exit_block)
        self.assertEqual(edge.edge_type, EdgeType.NORMAL)

        # Reachability
        reachable = cfg.compute_reachability()
        self.assertIn(cfg.entry_block.block_id, reachable)
        self.assertIn(cfg.exit_block.block_id, reachable)
        self.assertEqual(len(cfg.get_unreachable_blocks()), 0)

    def test_if_else_cfg(self) -> None:
        code = """
if x > 0:
    y = 1
else:
    y = 2
z = y
"""
        tree = ast.parse(code)
        cfg = self.builder.build(tree, name="if_else_test")

        # Entry block should transition to if_true and if_false
        entry = cfg.entry_block
        succ_types = {e.edge_type for e in entry.successors}
        self.assertIn(EdgeType.TRUE_BRANCH, succ_types)
        self.assertIn(EdgeType.FALSE_BRANCH, succ_types)

        # Both true and false branches should eventually lead to join
        true_edge = [e for e in entry.successors if e.edge_type == EdgeType.TRUE_BRANCH][0]
        false_edge = [e for e in entry.successors if e.edge_type == EdgeType.FALSE_BRANCH][0]

        self.assertEqual(len(true_edge.target.statements), 1)  # y = 1
        self.assertEqual(len(false_edge.target.statements), 1)  # y = 2

        # Reachability
        self.assertEqual(len(cfg.get_unreachable_blocks()), 0)

    def test_while_loop_and_back_edges(self) -> None:
        code = """
i = 0
while i < 10:
    i += 1
done = True
"""
        tree = ast.parse(code)
        cfg = self.builder.build(tree, name="while_test")

        # Detect loop back-edges
        loops = cfg.detect_loops()
        self.assertGreaterEqual(len(loops), 1)
        tail, header = loops[0]
        self.assertEqual(header.name, "while_header")

        # Dominator check: header dominates body
        doms = cfg.compute_dominators()
        self.assertIn(header.block_id, doms[tail.block_id])

    def test_for_loop_and_break_continue(self) -> None:
        code = """
for x in items:
    if x == 0:
        continue
    if x < 0:
        break
    process(x)
"""
        tree = ast.parse(code)
        cfg = self.builder.build(tree, name="for_break_continue")

        # Loop back-edges and exits exist
        edges_types = {e.edge_type for e in cfg.edges}
        self.assertIn(EdgeType.LOOP_BACK, edges_types)
        self.assertIn(EdgeType.LOOP_BODY, edges_types)
        self.assertIn(EdgeType.LOOP_EXIT, edges_types)

    def test_return_terminates_block(self) -> None:
        code = """
def f(x):
    return x * 2
    dead = 123
"""
        tree = ast.parse(code)
        cfg = self.builder.build(tree, name="return_func")

        # Return links directly to exit
        ret_edges = [e for e in cfg.edges if e.edge_type == EdgeType.RETURN]
        self.assertEqual(len(ret_edges), 1)
        self.assertEqual(ret_edges[0].target, cfg.exit_block)

        # Unreachable block for 'dead = 123'
        unreachable = cfg.get_unreachable_blocks()
        self.assertGreaterEqual(len(unreachable), 1)
        unreach_stmts = [s for b in unreachable for s in b.statements]
        self.assertTrue(any(isinstance(s, ast.Assign) for s in unreach_stmts))

    def test_raise_exception_cfg(self) -> None:
        code = """
def validate(x):
    if x < 0:
        raise ValueError("negative")
    return x
"""
        tree = ast.parse(code)
        cfg = self.builder.build(tree, name="raise_test")

        raise_edges = [e for e in cfg.edges if e.edge_type == EdgeType.RAISE]
        self.assertEqual(len(raise_edges), 1)

    def test_try_except_finally_cfg(self) -> None:
        code = """
try:
    risky()
except ValueError:
    handle_val()
except Exception:
    handle_gen()
finally:
    cleanup()
"""
        tree = ast.parse(code)
        cfg = self.builder.build(tree, name="try_test")

        edge_types = {e.edge_type for e in cfg.edges}
        self.assertIn(EdgeType.EXCEPTION, edge_types)
        self.assertIn(EdgeType.FINALLY, edge_types)

    def test_ascii_visualizer(self) -> None:
        code = """
if True:
    print("hi")
"""
        tree = ast.parse(code)
        cfg = self.builder.build(tree, name="ascii_test")
        ascii_out = cfg.to_ascii()
        self.assertIn("=== Control Flow Graph: ascii_test ===", ascii_out)
        self.assertIn("REACHABLE", ascii_out)


if __name__ == "__main__":
    unittest.main()
