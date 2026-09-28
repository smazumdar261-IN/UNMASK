"""Control Flow Graph (CFG) analysis for Common Intermediate Representation.

Per Section 16 & Section 9 of the Master Specification:
Provides language-independent control-flow analysis on Common IR:
- Basic block partitioning
- Branching (IRBranch)
- Loops (IRLoop: while, for, break, continue)
- Function calls and returns (IRReturn)
- Exception paths (IRTryExcept, IRRaise)
- Reachability analysis
- Dominator tree computation
- Natural loop detection
- ASCII and DOT export
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from core.ir import (
    IRBlock,
    IRBranch,
    IRBreak,
    IRContinue,
    IRExpression,
    IRFunction,
    IRLoop,
    IRModule,
    IRPass,
    IRRaise,
    IRReturn,
    IRStatement,
    IRTryExcept,
    format_ir,
)


class IREdgeType(Enum):
    """Types of control-flow transitions between IR basic blocks."""

    NORMAL = "normal"
    TRUE_BRANCH = "true_branch"
    FALSE_BRANCH = "false_branch"
    LOOP_BODY = "loop_body"
    LOOP_EXIT = "loop_exit"
    LOOP_BACK = "loop_back"
    RETURN = "return"
    EXCEPTION = "exception"
    UNCONDITIONAL = "unconditional"


class IRBasicBlock:
    """A linear sequence of IR statements with single entry and single exit."""

    def __init__(self, block_id: int, name: str = "") -> None:
        self.block_id: int = block_id
        self.name: str = name or f"block_{block_id}"
        self.statements: List[IRStatement] = []
        self.predecessors: List[IRCFGEdge] = []
        self.successors: List[IRCFGEdge] = []
        self.is_entry: bool = False
        self.is_exit: bool = False

    def add_statement(self, stmt: IRStatement) -> None:
        self.statements.append(stmt)

    @property
    def empty(self) -> bool:
        return len(self.statements) == 0

    def __repr__(self) -> str:
        flags = []
        if self.is_entry:
            flags.append("ENTRY")
        if self.is_exit:
            flags.append("EXIT")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        return f"<IRBasicBlock {self.name} (id={self.block_id}, stmts={len(self.statements)}){flag_str}>"


class IRCFGEdge:
    """A directed edge in the IR Control Flow Graph."""

    def __init__(
        self,
        source: IRBasicBlock,
        target: IRBasicBlock,
        edge_type: IREdgeType = IREdgeType.NORMAL,
        condition: Optional[IRExpression] = None,
    ) -> None:
        self.source: IRBasicBlock = source
        self.target: IRBasicBlock = target
        self.edge_type: IREdgeType = edge_type
        self.condition: Optional[IRExpression] = condition

    def __repr__(self) -> str:
        cond_str = f" [cond]" if self.condition else ""
        return f"Edge({self.source.name} -> {self.target.name}, {self.edge_type.value}{cond_str})"


class IRCFG:
    """Control Flow Graph constructed from Common IR."""

    def __init__(self, name: str = "<entry>") -> None:
        self.name: str = name
        self.entry_block: IRBasicBlock = IRBasicBlock(0, "entry")
        self.entry_block.is_entry = True
        self.exit_block: IRBasicBlock = IRBasicBlock(1, "exit")
        self.exit_block.is_exit = True
        self.blocks: List[IRBasicBlock] = [self.entry_block, self.exit_block]
        self._next_id: int = 2

    def new_block(self, name: str = "") -> IRBasicBlock:
        b = IRBasicBlock(self._next_id, name)
        self._next_id += 1
        self.blocks.append(b)
        return b

    def add_edge(
        self,
        source: IRBasicBlock,
        target: IRBasicBlock,
        edge_type: IREdgeType = IREdgeType.NORMAL,
        condition: Optional[IRExpression] = None,
    ) -> IRCFGEdge:
        edge = IRCFGEdge(source, target, edge_type, condition)
        source.successors.append(edge)
        target.predecessors.append(edge)
        return edge

    @classmethod
    def build_from_function(cls, fn: IRFunction) -> "IRCFG":
        """Build a CFG for an IRFunction."""
        cfg = cls(name=fn.name)
        builder = _IRCFGBuilder(cfg)
        first_content = cfg.new_block("fn_start")
        cfg.add_edge(cfg.entry_block, first_content, IREdgeType.NORMAL)
        last_block = builder.build(fn.body, first_content)
        if last_block and not any(e.target == cfg.exit_block for e in last_block.successors):
            cfg.add_edge(last_block, cfg.exit_block, IREdgeType.NORMAL)
        return cfg

    @classmethod
    def build_from_module(cls, mod: IRModule) -> Dict[str, "IRCFG"]:
        """Build CFGs for the module body and each top-level function."""
        cfgs: Dict[str, IRCFG] = {}

        # Module-level statements
        top_stmts: List[IRStatement] = []
        for s in mod.body:
            if isinstance(s, IRFunction):
                cfgs[s.name] = cls.build_from_function(s)
            else:
                top_stmts.append(s)

        mod_cfg = cls(name=f"module_{mod.name}")
        builder = _IRCFGBuilder(mod_cfg)
        first_content = mod_cfg.new_block("mod_start")
        mod_cfg.add_edge(mod_cfg.entry_block, first_content, IREdgeType.NORMAL)
        last_block = builder.build(top_stmts, first_content)
        if last_block and not any(e.target == mod_cfg.exit_block for e in last_block.successors):
            mod_cfg.add_edge(last_block, mod_cfg.exit_block, IREdgeType.NORMAL)
        cfgs["<module>"] = mod_cfg

        return cfgs

    # -----------------------------------------------------------------------
    # Graph Analysis Methods
    # -----------------------------------------------------------------------

    def reachable_blocks(self) -> Set[int]:
        """Compute the set of block IDs reachable from the entry block."""
        visited: Set[int] = set()
        queue = deque([self.entry_block])

        while queue:
            curr = queue.popleft()
            if curr.block_id in visited:
                continue
            visited.add(curr.block_id)
            for edge in curr.successors:
                if edge.target.block_id not in visited:
                    queue.append(edge.target)

        return visited

    def unreachable_blocks(self) -> Set[int]:
        """Compute the set of block IDs that cannot be reached from entry."""
        reachable = self.reachable_blocks()
        all_ids = {b.block_id for b in self.blocks}
        return all_ids - reachable

    def compute_dominators(self) -> Dict[int, Set[int]]:
        """Compute the dominators for all reachable blocks."""
        reachable = self.reachable_blocks()
        all_reachable = set(reachable)
        dom: Dict[int, Set[int]] = {}

        entry_id = self.entry_block.block_id
        dom[entry_id] = {entry_id}

        for bid in reachable:
            if bid != entry_id:
                dom[bid] = set(all_reachable)

        block_by_id = {b.block_id: b for b in self.blocks}

        changed = True
        while changed:
            changed = False
            for bid in reachable:
                if bid == entry_id:
                    continue
                block = block_by_id[bid]
                preds = [e.source.block_id for e in block.predecessors if e.source.block_id in reachable]
                if not preds:
                    new_dom = {bid}
                else:
                    new_dom = set.intersection(*(dom[p] for p in preds)) | {bid}
                if new_dom != dom[bid]:
                    dom[bid] = new_dom
                    changed = True

        return dom

    def compute_immediate_dominators(self) -> Dict[int, Optional[int]]:
        """Compute the immediate dominator (idom) for each reachable block."""
        dom = self.compute_dominators()
        idom: Dict[int, Optional[int]] = {self.entry_block.block_id: None}

        for bid, dominators in dom.items():
            if bid == self.entry_block.block_id:
                continue
            strictly_dominates = dominators - {bid}
            # idom is the element d in strictly_dominates that is dominated by all others
            current_idom = None
            for d in strictly_dominates:
                if strictly_dominates.issubset(dom[d]):
                    current_idom = d
                    break
            idom[bid] = current_idom

        return idom

    def detect_loops(self) -> List[Dict[str, Any]]:
        """Detect natural loops by identifying back-edges (edges where target dominates source)."""
        dom = self.compute_dominators()
        loops: List[Dict[str, Any]] = []

        block_by_id = {b.block_id: b for b in self.blocks}

        for block in self.blocks:
            bid = block.block_id
            for edge in block.successors:
                header_id = edge.target.block_id
                if header_id in dom.get(bid, set()):
                    # Back-edge found: bid -> header_id
                    # Loop body consists of all nodes that can reach bid without going through header_id
                    loop_nodes: Set[int] = {header_id, bid}
                    worklist = [bid]
                    while worklist:
                        m = worklist.pop()
                        m_block = block_by_id[m]
                        for pred_edge in m_block.predecessors:
                            p = pred_edge.source.block_id
                            if p not in loop_nodes:
                                loop_nodes.add(p)
                                worklist.append(p)

                    loops.append({
                        "header": header_id,
                        "latch": bid,
                        "body": loop_nodes,
                    })

        return loops

    def to_ascii(self) -> str:
        """Render a readable text layout of the CFG."""
        lines = [f"=== IR CFG: {self.name} ==="]
        for b in sorted(self.blocks, key=lambda x: x.block_id):
            flags = []
            if b.is_entry:
                flags.append("ENTRY")
            if b.is_exit:
                flags.append("EXIT")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"Block {b.name} (id={b.block_id}){flag_str}:")
            if not b.statements:
                lines.append("    (empty)")
            for s in b.statements:
                lines.append(f"    {format_ir(s)}")
            for e in b.successors:
                cond = f" [if {format_ir(e.condition)}]" if e.condition else ""
                lines.append(f"    -> {e.target.name} ({e.edge_type.value}{cond})")
            lines.append("")
        return "\n".join(lines)


class _IRCFGBuilder:
    """Internal helper to construct an IRCFG from a list of IR statements."""

    def __init__(self, cfg: IRCFG) -> None:
        self.cfg = cfg
        self.loop_stack: List[Tuple[IRBasicBlock, IRBasicBlock]] = []  # (continue_target, break_target)

    def build(self, statements: List[IRStatement], current_block: IRBasicBlock) -> Optional[IRBasicBlock]:
        curr: Optional[IRBasicBlock] = current_block

        for stmt in statements:
            if curr is None:
                # Unreachable statements get their own block
                curr = self.cfg.new_block("unreachable")

            if isinstance(stmt, IRBranch):
                cond = stmt.condition
                then_entry = self.cfg.new_block("then")
                else_entry = self.cfg.new_block("else")
                merge_block = self.cfg.new_block("merge")

                self.cfg.add_edge(curr, then_entry, IREdgeType.TRUE_BRANCH, cond)
                self.cfg.add_edge(curr, else_entry, IREdgeType.FALSE_BRANCH, cond)

                then_exit = self.build(stmt.body, then_entry)
                if then_exit:
                    self.cfg.add_edge(then_exit, merge_block, IREdgeType.NORMAL)

                else_exit = self.build(stmt.orelse, else_entry) if stmt.orelse else else_entry
                if else_exit:
                    self.cfg.add_edge(else_exit, merge_block, IREdgeType.NORMAL)

                curr = merge_block

            elif isinstance(stmt, IRLoop):
                loop_header = self.cfg.new_block("loop_header")
                loop_body = self.cfg.new_block("loop_body")
                loop_exit = self.cfg.new_block("loop_exit")

                self.cfg.add_edge(curr, loop_header, IREdgeType.NORMAL)
                self.cfg.add_edge(loop_header, loop_body, IREdgeType.LOOP_BODY, stmt.condition)
                self.cfg.add_edge(loop_header, loop_exit, IREdgeType.LOOP_EXIT)

                self.loop_stack.append((loop_header, loop_exit))
                body_exit = self.build(stmt.body, loop_body)
                self.loop_stack.pop()

                if body_exit:
                    self.cfg.add_edge(body_exit, loop_header, IREdgeType.LOOP_BACK)

                curr = loop_exit

            elif isinstance(stmt, IRReturn):
                curr.add_statement(stmt)
                self.cfg.add_edge(curr, self.cfg.exit_block, IREdgeType.RETURN)
                curr = None

            elif isinstance(stmt, IRBreak):
                curr.add_statement(stmt)
                if self.loop_stack:
                    _, break_target = self.loop_stack[-1]
                    self.cfg.add_edge(curr, break_target, IREdgeType.UNCONDITIONAL)
                curr = None

            elif isinstance(stmt, IRContinue):
                curr.add_statement(stmt)
                if self.loop_stack:
                    continue_target, _ = self.loop_stack[-1]
                    self.cfg.add_edge(curr, continue_target, IREdgeType.UNCONDITIONAL)
                curr = None

            elif isinstance(stmt, IRRaise):
                curr.add_statement(stmt)
                self.cfg.add_edge(curr, self.cfg.exit_block, IREdgeType.EXCEPTION)
                curr = None

            elif isinstance(stmt, IRBlock):
                curr = self.build(stmt.statements, curr)

            else:
                curr.add_statement(stmt)

        return curr
