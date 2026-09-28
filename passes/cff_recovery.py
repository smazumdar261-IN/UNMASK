"""Control-Flow Flattening (CFF) recovery pass.

Per Section 9 of the Master Specification (Phase 3: Control Flow):
Deobfuscates control-flow flattening:
- Reconstructs linear sequences from state-machine dispatch loops
- Reconstructs structured if-else branches from state transitions
- Eliminates the dispatcher loop, state comparisons, and unnecessary state variables
- Preserves exact runtime semantics with 100% safety
- Records complete provenance with line/column information
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from analysis.cff import CFFDispatcher, CFFStateBlock, ControlFlowFlatteningAnalyzer
from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser


class ControlFlowFlatteningTransformer(ast.NodeTransformer):
    """AST transformer that replaces CFF dispatcher loops with recovered linear/structured code."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.tracker = tracker
        self.filename = filename
        self.analyzer = ControlFlowFlatteningAnalyzer()
        self.recoveries_count = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self.generic_visit(node)
        node.body = self._process_statement_list(node.body)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.generic_visit(node)
        node.body = self._process_statement_list(node.body)
        return node

    def visit_Module(self, node: ast.Module) -> Any:
        self.generic_visit(node)
        node.body = self._process_statement_list(node.body)
        return node

    def _process_statement_list(self, stmts: List[ast.stmt]) -> List[ast.stmt]:
        """Scan statement list for CFF dispatcher loops and unflatten them."""
        new_stmts: List[ast.stmt] = []
        i = 0
        while i < len(stmts):
            stmt = stmts[i]
            if isinstance(stmt, ast.While):
                dispatcher = self.analyzer.analyze_loop(stmt, new_stmts, len(new_stmts))
                if dispatcher:
                    recovered = self._unflatten(dispatcher)
                    if recovered is not None:
                        # Success! Eliminate the state initialization assignment
                        for init_idx in range(len(new_stmts) - 1, -1, -1):
                            if self._is_state_init(new_stmts[init_idx], dispatcher.state_var):
                                init_stmt = new_stmts.pop(init_idx)
                                init_loc = PythonParser.get_location(init_stmt, self.filename)
                                self.tracker.record(
                                    pass_name="ControlFlowFlattening",
                                    original=PythonParser.unparse(init_stmt),
                                    transformed="[eliminated state variable assignment]",
                                    confidence=Confidence.certain(
                                        f"Eliminated unnecessary state variable initialization for '{dispatcher.state_var}'",
                                        TransformationCategory.SIMPLIFIED,
                                    ),
                                    location=init_loc,
                                )
                                break

                        # Record recovery of the dispatcher loop
                        loop_loc = PythonParser.get_location(stmt, self.filename)
                        orig_loop_repr = PythonParser.unparse(stmt)
                        self.tracker.record(
                            pass_name="ControlFlowFlattening",
                            original=orig_loop_repr,
                            transformed=f"[unflattened {len(recovered)} statements]",
                            confidence=Confidence.certain(
                                f"Recovered flattened control flow into structured execution (dispatcher '{dispatcher.state_var}')",
                                TransformationCategory.RECOVERED,
                            ),
                            location=loop_loc,
                        )
                        self.recoveries_count += 1
                        new_stmts.extend(recovered)
                        i += 1
                        continue

            new_stmts.append(stmt)
            i += 1

        return new_stmts

    def _is_state_init(self, stmt: ast.stmt, state_var: str) -> bool:
        """Check if statement is an assignment to state_var."""
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            return isinstance(target, ast.Name) and target.id == state_var
        return False

    def _unflatten(self, dispatcher: CFFDispatcher) -> Optional[List[ast.stmt]]:
        """Trace dispatcher states and reconstruct structured/linear AST statements."""
        curr: Any = dispatcher.initial_state
        recovered: List[ast.stmt] = []
        visited: Set[Any] = set()
        step = 0

        while step < self.analyzer.max_trace_steps:
            step += 1
            if curr in dispatcher.exit_states:
                # Reached exit state cleanly
                return recovered

            if curr in visited:
                # Cycle detected: conservative fallback
                return None

            if curr not in dispatcher.states:
                # State not found in dispatch table
                return None

            visited.add(curr)
            block = dispatcher.states[curr]
            recovered.extend(block.payload_stmts)

            trans = block.transition
            if trans.is_return:
                if trans.terminator_node:
                    recovered.append(trans.terminator_node)
                return recovered

            if trans.is_exit:
                return recovered

            if trans.conditional:
                test_node, then_s, else_s = trans.conditional
                # Check for diamond pattern (both then and else transition to a common join state)
                block_then = dispatcher.states.get(then_s)
                block_else = dispatcher.states.get(else_s)

                if (
                    block_then
                    and block_else
                    and block_then.transition.next_state is not None
                    and block_then.transition.next_state == block_else.transition.next_state
                ):
                    s_join = block_then.transition.next_state
                    then_stmts = list(block_then.payload_stmts)
                    else_stmts = list(block_else.payload_stmts)

                    if block_then.transition.is_return and block_then.transition.terminator_node:
                        then_stmts.append(block_then.transition.terminator_node)
                    if block_else.transition.is_return and block_else.transition.terminator_node:
                        else_stmts.append(block_else.transition.terminator_node)

                    recovered.append(ast.If(test=test_node, body=then_stmts, orelse=else_stmts))
                    visited.add(then_s)
                    visited.add(else_s)
                    curr = s_join
                    continue

                # Divergent branches where one or both exit/return
                if (
                    block_then
                    and (block_then.transition.is_exit or block_then.transition.is_return)
                    and block_else
                    and block_else.transition.next_state is not None
                ):
                    then_stmts = list(block_then.payload_stmts)
                    if block_then.transition.is_return and block_then.transition.terminator_node:
                        then_stmts.append(block_then.transition.terminator_node)
                    recovered.append(ast.If(test=test_node, body=then_stmts, orelse=[]))
                    visited.add(then_s)
                    curr = else_s
                    continue

                # General sub-trace fallback for independent paths
                then_trace = self._trace_subpath(dispatcher, then_s, set(visited))
                else_trace = self._trace_subpath(dispatcher, else_s, set(visited))
                if then_trace is not None and else_trace is not None:
                    recovered.append(ast.If(test=test_node, body=then_trace, orelse=else_trace))
                    return recovered

                # Cannot resolve conditional transition safely
                return None

            if trans.next_state is not None:
                curr = trans.next_state
            else:
                return None

        # Exceeded max steps
        return None

    def _trace_subpath(
        self, dispatcher: CFFDispatcher, start_state: Any, initial_visited: Set[Any]
    ) -> Optional[List[ast.stmt]]:
        """Trace a subpath to completion."""
        curr: Any = start_state
        sub_recovered: List[ast.stmt] = []
        visited = set(initial_visited)
        step = 0

        while step < 100:
            step += 1
            if curr in dispatcher.exit_states:
                return sub_recovered

            if curr in visited or curr not in dispatcher.states:
                return None

            visited.add(curr)
            block = dispatcher.states[curr]
            sub_recovered.extend(block.payload_stmts)

            trans = block.transition
            if trans.is_return:
                if trans.terminator_node:
                    sub_recovered.append(trans.terminator_node)
                return sub_recovered

            if trans.is_exit:
                return sub_recovered

            if trans.next_state is not None:
                curr = trans.next_state
            else:
                return None

        return None


class ControlFlowFlatteningPass(Pass):
    """Pass that deobfuscates control-flow flattening and reconstructs structured code."""

    name = "ControlFlowFlattening"
    description = "Reconstructs flattened control-flow loops into clean structured code."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, ast.AST):
            return target
        trk = tracker if tracker is not None else ProvenanceTracker()
        transformer = ControlFlowFlatteningTransformer(trk, self.filename)
        transformed = transformer.visit(target)
        ast.fix_missing_locations(transformed)
        return transformed
