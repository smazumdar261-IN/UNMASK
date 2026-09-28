"""Control Flow Graph (CFG) analysis for Python AST.

Per Section 9 of the Master Specification (Phase 3: Control Flow):
Represents:
- Basic blocks
- Conditional branches (True/False)
- Loops (while, for, break, continue, back-edges)
- Jumps and fallthroughs
- Function returns and exits
- Exception paths (try, except, raise, finally)

Provides:
- Reachability analysis (reachable vs unreachable blocks)
- Dominator tree computation
- Natural loop detection
- ASCII visualization for inspection and debugging
"""

from __future__ import annotations

import ast
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Tuple


class EdgeType(Enum):
    """Types of directed control-flow transitions between basic blocks."""

    NORMAL = auto()
    TRUE_BRANCH = auto()
    FALSE_BRANCH = auto()
    LOOP_BODY = auto()
    LOOP_EXIT = auto()
    LOOP_BACK = auto()
    RETURN = auto()
    RAISE = auto()
    EXCEPTION = auto()
    FINALLY = auto()
    UNCONDITIONAL = auto()


class BasicBlock:
    """A linear sequence of statements with single entry and single exit."""

    def __init__(self, block_id: int, name: str = "") -> None:
        self.block_id: int = block_id
        self.name: str = name or f"block_{block_id}"
        self.statements: List[ast.stmt] = []
        self.predecessors: List[CFGEdge] = []
        self.successors: List[CFGEdge] = []
        self.is_entry: bool = False
        self.is_exit: bool = False

    def add_statement(self, stmt: ast.stmt) -> None:
        """Append an AST statement to this basic block."""
        self.statements.append(stmt)

    @property
    def empty(self) -> bool:
        """True if the block contains no statements."""
        return len(self.statements) == 0

    def __repr__(self) -> str:
        flags = []
        if self.is_entry:
            flags.append("ENTRY")
        if self.is_exit:
            flags.append("EXIT")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        return f"BasicBlock({self.name}, id={self.block_id}{flag_str}, stmts={len(self.statements)})"


class CFGEdge:
    """Directed edge connecting two basic blocks in the CFG."""

    def __init__(
        self,
        source: BasicBlock,
        target: BasicBlock,
        edge_type: EdgeType = EdgeType.NORMAL,
        condition: Optional[ast.expr] = None,
    ) -> None:
        self.source: BasicBlock = source
        self.target: BasicBlock = target
        self.edge_type: EdgeType = edge_type
        self.condition: Optional[ast.expr] = condition

    def __repr__(self) -> str:
        cond_str = f", cond={ast.unparse(self.condition)}" if self.condition else ""
        return f"Edge({self.source.name} -> {self.target.name}, {self.edge_type.name}{cond_str})"


class ControlFlowGraph:
    """Graph structure containing basic blocks and directed control-flow edges."""

    def __init__(self, name: str = "<module>") -> None:
        self.name: str = name
        self.blocks: Dict[int, BasicBlock] = {}
        self.edges: List[CFGEdge] = []
        self._next_id: int = 0
        self.entry_block: Optional[BasicBlock] = None
        self.exit_block: Optional[BasicBlock] = None

    def new_block(self, name: str = "") -> BasicBlock:
        """Allocate a new BasicBlock within this CFG."""
        b_id = self._next_id
        self._next_id += 1
        block = BasicBlock(b_id, name)
        self.blocks[b_id] = block
        return block

    def add_edge(
        self,
        source: BasicBlock,
        target: BasicBlock,
        edge_type: EdgeType = EdgeType.NORMAL,
        condition: Optional[ast.expr] = None,
    ) -> CFGEdge:
        """Create and register a directed edge between two basic blocks."""
        edge = CFGEdge(source, target, edge_type, condition)
        source.successors.append(edge)
        target.predecessors.append(edge)
        self.edges.append(edge)
        return edge

    def compute_reachability(self) -> Set[int]:
        """Compute all block IDs reachable from the entry block via BFS."""
        if not self.entry_block:
            return set()

        visited: Set[int] = set()
        queue: List[BasicBlock] = [self.entry_block]
        visited.add(self.entry_block.block_id)

        while queue:
            current = queue.pop(0)
            for edge in current.successors:
                if edge.target.block_id not in visited:
                    visited.add(edge.target.block_id)
                    queue.append(edge.target)

        return visited

    def get_unreachable_blocks(self) -> List[BasicBlock]:
        """Return all basic blocks not reachable from the entry block."""
        reachable = self.compute_reachability()
        return [b for b_id, b in self.blocks.items() if b_id not in reachable]

    def compute_dominators(self) -> Dict[int, Set[int]]:
        """Compute the dominator set for each basic block.
        
        A block D dominates block N (D in Dom(N)) if every path from entry to N must go through D.
        Uses iterative dataflow: Dom(N) = {N} U (Intersection of Dom(P) for all P in Pred(N)).
        """
        all_blocks = set(self.blocks.keys())
        if not self.entry_block:
            return {}

        dom: Dict[int, Set[int]] = {}
        entry_id = self.entry_block.block_id

        for b_id in all_blocks:
            if b_id == entry_id:
                dom[b_id] = {entry_id}
            else:
                dom[b_id] = set(all_blocks)

        changed = True
        while changed:
            changed = False
            for b_id, block in self.blocks.items():
                if b_id == entry_id:
                    continue

                preds = [e.source.block_id for e in block.predecessors]
                if not preds:
                    new_dom = {b_id}
                else:
                    pred_doms = [dom[p] for p in preds if p in dom]
                    if pred_doms:
                        new_dom = {b_id}.union(set.intersection(*pred_doms))
                    else:
                        new_dom = {b_id}

                if new_dom != dom[b_id]:
                    dom[b_id] = new_dom
                    changed = True

        return dom

    def detect_loops(self) -> List[Tuple[BasicBlock, BasicBlock]]:
        """Identify back-edges (u -> v) where v dominates u, defining natural loops.
        
        Returns a list of (tail, header) basic block pairs.
        """
        doms = self.compute_dominators()
        loops: List[Tuple[BasicBlock, BasicBlock]] = []

        for edge in self.edges:
            src_id = edge.source.block_id
            tgt_id = edge.target.block_id
            # If target dominates source, this is a back-edge representing a loop
            if tgt_id in doms.get(src_id, set()):
                loops.append((edge.source, edge.target))

        return loops

    def to_ascii(self) -> str:
        """Render a readable textual summary of all basic blocks and edges."""
        lines = [f"=== Control Flow Graph: {self.name} ==="]
        reachable = self.compute_reachability()
        for b_id, block in sorted(self.blocks.items()):
            reach_tag = "REACHABLE" if b_id in reachable else "UNREACHABLE"
            lines.append(f"\n[{block.name} (id={b_id})] - {reach_tag}")
            for stmt in block.statements:
                try:
                    stmt_src = ast.unparse(stmt).splitlines()[0]
                    if len(stmt_src) > 50:
                        stmt_src = stmt_src[:47] + "..."
                except Exception:
                    stmt_src = type(stmt).__name__
                lines.append(f"    | {stmt_src}")
            if not block.statements:
                lines.append("    | <empty>")

            for edge in block.successors:
                cond_info = f" [cond: {ast.unparse(edge.condition)}]" if edge.condition else ""
                lines.append(f"    --> {edge.target.name} ({edge.edge_type.name}{cond_info})")

        return "\n".join(lines)


class CFGBuilder:
    """Builds a ControlFlowGraph from a Python AST node (Module, FunctionDef, etc.)."""

    def __init__(self) -> None:
        self.cfg: ControlFlowGraph = ControlFlowGraph()
        # Loop stacks for 'break' and 'continue'
        self._loop_continue_targets: List[BasicBlock] = []
        self._loop_break_targets: List[BasicBlock] = []
        # Exception stacks for 'raise' and unhandled errors
        self._exception_targets: List[BasicBlock] = []
        self._finally_targets: List[BasicBlock] = []

    def build(self, node: ast.AST, name: str = "<module>") -> ControlFlowGraph:
        """Construct the complete CFG for the provided AST node."""
        self.cfg = ControlFlowGraph(name=name)
        self.cfg.entry_block = self.cfg.new_block("entry")
        self.cfg.entry_block.is_entry = True

        self.cfg.exit_block = self.cfg.new_block("exit")
        self.cfg.exit_block.is_exit = True

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            final_block = self._build_statements(node.body, self.cfg.entry_block)
        elif isinstance(node, ast.Module):
            # If module contains only a single function definition, build that function's CFG
            if len(node.body) == 1 and isinstance(node.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
                final_block = self._build_statements(node.body[0].body, self.cfg.entry_block)
            else:
                final_block = self._build_statements(node.body, self.cfg.entry_block)
        elif isinstance(node, list):
            final_block = self._build_statements(node, self.cfg.entry_block)
        else:
            final_block = self._build_statements([node], self.cfg.entry_block)

        # If execution can fall off the end, connect to exit_block
        if final_block and not self._is_terminated(final_block):
            if final_block == self.cfg.entry_block or final_block.predecessors:
                self.cfg.add_edge(final_block, self.cfg.exit_block, EdgeType.NORMAL)

        return self.cfg

    def build_function(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> ControlFlowGraph:
        """Construct CFG for a specific function definition."""
        return self.build(func_node, name=func_node.name)

    def _is_terminated(self, block: BasicBlock) -> bool:
        """Check if block ends with an unconditional jump or return."""
        if not block.statements:
            return False
        last = block.statements[-1]
        return isinstance(last, (ast.Return, ast.Raise, ast.Break, ast.Continue))

    def _build_statements(
        self, stmts: List[ast.stmt], current_block: BasicBlock
    ) -> Optional[BasicBlock]:
        """Sequentially process a list of statements into basic blocks."""
        active = current_block

        for stmt in stmts:
            if active is None:
                # Code following a terminator is unreachable, placed in an unreachable block
                active = self.cfg.new_block("unreachable")

            if isinstance(stmt, ast.If):
                active = self._build_if(stmt, active)
            elif isinstance(stmt, ast.While):
                active = self._build_while(stmt, active)
            elif isinstance(stmt, ast.For):
                active = self._build_for(stmt, active)
            elif isinstance(stmt, ast.Return):
                active.add_statement(stmt)
                self.cfg.add_edge(active, self.cfg.exit_block, EdgeType.RETURN)
                active = None
            elif isinstance(stmt, ast.Raise):
                active.add_statement(stmt)
                if self._exception_targets:
                    self.cfg.add_edge(active, self._exception_targets[-1], EdgeType.RAISE)
                else:
                    self.cfg.add_edge(active, self.cfg.exit_block, EdgeType.RAISE)
                active = None
            elif isinstance(stmt, ast.Break):
                active.add_statement(stmt)
                if self._loop_break_targets:
                    self.cfg.add_edge(active, self._loop_break_targets[-1], EdgeType.UNCONDITIONAL)
                active = None
            elif isinstance(stmt, ast.Continue):
                active.add_statement(stmt)
                if self._loop_continue_targets:
                    self.cfg.add_edge(active, self._loop_continue_targets[-1], EdgeType.LOOP_BACK)
                active = None
            elif isinstance(stmt, ast.Try):
                active = self._build_try(stmt, active)
            else:
                active.add_statement(stmt)

        return active

    def _build_if(self, node: ast.If, current_block: BasicBlock) -> BasicBlock:
        """Build CFG branch structures for an ast.If statement."""
        true_block = self.cfg.new_block("if_true")
        false_block = self.cfg.new_block("if_false")
        join_block = self.cfg.new_block("if_join")

        # Edge from current to true/false branches
        self.cfg.add_edge(current_block, true_block, EdgeType.TRUE_BRANCH, condition=node.test)
        self.cfg.add_edge(current_block, false_block, EdgeType.FALSE_BRANCH, condition=node.test)

        # Process then-body
        end_true = self._build_statements(node.body, true_block)
        if end_true and not self._is_terminated(end_true):
            self.cfg.add_edge(end_true, join_block, EdgeType.NORMAL)

        # Process else-body
        if node.orelse:
            end_false = self._build_statements(node.orelse, false_block)
            if end_false and not self._is_terminated(end_false):
                self.cfg.add_edge(end_false, join_block, EdgeType.NORMAL)
        else:
            self.cfg.add_edge(false_block, join_block, EdgeType.NORMAL)

        return join_block

    def _build_while(self, node: ast.While, current_block: BasicBlock) -> BasicBlock:
        """Build CFG loop structures for an ast.While statement."""
        header_block = self.cfg.new_block("while_header")
        body_block = self.cfg.new_block("while_body")
        exit_block = self.cfg.new_block("while_exit")

        # Jump from current into loop header
        self.cfg.add_edge(current_block, header_block, EdgeType.NORMAL)

        # Header tests condition
        self.cfg.add_edge(header_block, body_block, EdgeType.LOOP_BODY, condition=node.test)

        # Push loop contexts for break / continue
        self._loop_continue_targets.append(header_block)
        self._loop_break_targets.append(exit_block)

        # Build loop body
        end_body = self._build_statements(node.body, body_block)
        if end_body and not self._is_terminated(end_body):
            self.cfg.add_edge(end_body, header_block, EdgeType.LOOP_BACK)

        self._loop_continue_targets.pop()
        self._loop_break_targets.pop()

        # Orelse or direct loop exit
        if node.orelse:
            orelse_block = self.cfg.new_block("while_orelse")
            self.cfg.add_edge(header_block, orelse_block, EdgeType.LOOP_EXIT)
            end_orelse = self._build_statements(node.orelse, orelse_block)
            if end_orelse and not self._is_terminated(end_orelse):
                self.cfg.add_edge(end_orelse, exit_block, EdgeType.NORMAL)
        else:
            self.cfg.add_edge(header_block, exit_block, EdgeType.LOOP_EXIT)

        return exit_block

    def _build_for(self, node: ast.For, current_block: BasicBlock) -> BasicBlock:
        """Build CFG loop structures for an ast.For statement."""
        header_block = self.cfg.new_block("for_header")
        body_block = self.cfg.new_block("for_body")
        exit_block = self.cfg.new_block("for_exit")

        self.cfg.add_edge(current_block, header_block, EdgeType.NORMAL)
        self.cfg.add_edge(header_block, body_block, EdgeType.LOOP_BODY)

        self._loop_continue_targets.append(header_block)
        self._loop_break_targets.append(exit_block)

        end_body = self._build_statements(node.body, body_block)
        if end_body and not self._is_terminated(end_body):
            self.cfg.add_edge(end_body, header_block, EdgeType.LOOP_BACK)

        self._loop_continue_targets.pop()
        self._loop_break_targets.pop()

        if node.orelse:
            orelse_block = self.cfg.new_block("for_orelse")
            self.cfg.add_edge(header_block, orelse_block, EdgeType.LOOP_EXIT)
            end_orelse = self._build_statements(node.orelse, orelse_block)
            if end_orelse and not self._is_terminated(end_orelse):
                self.cfg.add_edge(end_orelse, exit_block, EdgeType.NORMAL)
        else:
            self.cfg.add_edge(header_block, exit_block, EdgeType.LOOP_EXIT)

        return exit_block

    def _build_try(self, node: ast.Try, current_block: BasicBlock) -> BasicBlock:
        """Build CFG exception paths for an ast.Try statement."""
        try_body_block = self.cfg.new_block("try_body")
        join_block = self.cfg.new_block("try_join")

        handler_blocks: List[BasicBlock] = []
        for i, _ in enumerate(node.handlers):
            handler_blocks.append(self.cfg.new_block(f"except_{i}"))

        self.cfg.add_edge(current_block, try_body_block, EdgeType.NORMAL)

        # Set up exception target for statements inside try
        if handler_blocks:
            self._exception_targets.append(handler_blocks[0])

        end_try = self._build_statements(node.body, try_body_block)

        if handler_blocks:
            self._exception_targets.pop()

        # Connect try body to exception handlers as potential exception edges
        for h_block in handler_blocks:
            self.cfg.add_edge(try_body_block, h_block, EdgeType.EXCEPTION)

        # If orelse exists, it executes when try_body finishes normally
        if node.orelse:
            orelse_block = self.cfg.new_block("try_orelse")
            if end_try and not self._is_terminated(end_try):
                self.cfg.add_edge(end_try, orelse_block, EdgeType.NORMAL)
            end_orelse = self._build_statements(node.orelse, orelse_block)
            if end_orelse and not self._is_terminated(end_orelse):
                self.cfg.add_edge(end_orelse, join_block, EdgeType.NORMAL)
        else:
            if end_try and not self._is_terminated(end_try):
                self.cfg.add_edge(end_try, join_block, EdgeType.NORMAL)

        # Build each exception handler
        for handler, h_block in zip(node.handlers, handler_blocks):
            end_h = self._build_statements(handler.body, h_block)
            if end_h and not self._is_terminated(end_h):
                self.cfg.add_edge(end_h, join_block, EdgeType.NORMAL)

        # If finalbody exists
        if node.finalbody:
            finally_block = self.cfg.new_block("try_finally")
            self.cfg.add_edge(join_block, finally_block, EdgeType.FINALLY)
            end_finally = self._build_statements(node.finalbody, finally_block)
            post_finally = self.cfg.new_block("post_finally")
            if end_finally and not self._is_terminated(end_finally):
                self.cfg.add_edge(end_finally, post_finally, EdgeType.NORMAL)
            return post_finally

        return join_block
