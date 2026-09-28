"""Control-Flow Flattening (CFF) analysis for Python AST.

Per Section 9 of the Master Specification (Phase 3: Control Flow):
Identifies and decomposes control-flow flattening obfuscation:
- Identifies dispatcher loops (while loops driven by a state variable)
- Extracts state cases from if/elif/else chains or sequential if blocks
- Maps state transitions (unconditional, conditional branches, returns, breaks)
- Reconstructs linear and structured control flow
- Identifies and eliminates unnecessary state variables
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from languages.python.parser import PythonParser


@dataclass
class CFFTransition:
    """Represents a transition out of a flattened state block."""

    is_exit: bool = False
    is_return: bool = False
    next_state: Optional[Any] = None
    # For conditional branches: (condition_node, then_state, else_state)
    conditional: Optional[Tuple[ast.expr, Any, Any]] = None
    terminator_node: Optional[ast.stmt] = None


@dataclass
class CFFStateBlock:
    """A basic block within a flattened control-flow dispatcher."""

    state_val: Any
    payload_stmts: List[ast.stmt] = field(default_factory=list)
    transition: CFFTransition = field(default_factory=CFFTransition)


@dataclass
class CFFDispatcher:
    """A detected control-flow flattening dispatcher structure."""

    loop_node: ast.While
    state_var: str
    initial_state: Any
    exit_states: Set[Any]
    states: Dict[Any, CFFStateBlock]
    preceding_stmt_index: int = -1


class ControlFlowFlatteningAnalyzer:
    """Detects control-flow flattening patterns in AST statement lists."""

    def __init__(self, max_trace_steps: int = 500) -> None:
        self.max_trace_steps = max_trace_steps

    def analyze_loop(
        self,
        while_node: ast.While,
        preceding_stmts: List[ast.stmt],
        stmt_index: int,
    ) -> Optional[CFFDispatcher]:
        """Examine a While loop to determine if it is a control-flow flattening dispatcher."""
        # 1. Identify state variable candidate
        state_var, initial_state, exit_states = self._detect_state_variable(
            while_node, preceding_stmts, stmt_index
        )
        if not state_var:
            return None

        # 2. Extract state blocks from loop body
        states = self._extract_state_blocks(while_node.body, state_var, exit_states)
        if not states or len(states) < 2:
            # Need at least 2 distinct states to be a meaningful flattening dispatcher
            return None

        # Verify initial_state is in states
        if initial_state not in states:
            return None

        return CFFDispatcher(
            loop_node=while_node,
            state_var=state_var,
            initial_state=initial_state,
            exit_states=exit_states,
            states=states,
            preceding_stmt_index=stmt_index - 1 if stmt_index > 0 else -1,
        )

    def _detect_state_variable(
        self,
        while_node: ast.While,
        preceding_stmts: List[ast.stmt],
        stmt_index: int,
    ) -> Tuple[Optional[str], Optional[Any], Set[Any]]:
        """Identify state variable name, its initial constant value, and loop exit states."""
        exit_states: Set[Any] = set()
        candidate_var: Optional[str] = None

        # Check while test: e.g. while state != 0, while state != "end"
        test = while_node.test
        if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
            op = test.ops[0]
            left = test.left
            right = test.comparators[0]
            if isinstance(op, ast.NotEq):
                if isinstance(left, ast.Name) and isinstance(right, ast.Constant):
                    candidate_var = left.id
                    exit_states.add(right.value)
                elif isinstance(right, ast.Name) and isinstance(left, ast.Constant):
                    candidate_var = right.id
                    exit_states.add(left.value)
            elif isinstance(op, ast.Eq):
                # while state == 1 (rare for loop, but possible)
                pass
        elif isinstance(test, ast.Name):
            # while state: (exits when state is 0 or False)
            candidate_var = test.id
            exit_states.add(0)
            exit_states.add(False)
            exit_states.add(None)
        elif isinstance(test, ast.Constant) and bool(test.value):
            # while True: / while 1: (exits on break or return)
            # Find candidate variable from if tests inside body
            candidate_var = self._find_dominant_dispatch_var(while_node.body)

        if not candidate_var:
            return None, None, set()

        # Find initial value by searching backwards in preceding statements
        initial_val: Optional[Any] = None
        for idx in range(stmt_index - 1, -1, -1):
            prev = preceding_stmts[idx]
            if isinstance(prev, ast.Assign) and len(prev.targets) == 1:
                target = prev.targets[0]
                if isinstance(target, ast.Name) and target.id == candidate_var:
                    if isinstance(prev.value, ast.Constant):
                        initial_val = prev.value.value
                        break
                    elif isinstance(prev.value, ast.UnaryOp) and isinstance(prev.value.op, ast.USub):
                        if isinstance(prev.value.operand, ast.Constant):
                            initial_val = -prev.value.operand.value
                            break
            # If candidate_var is modified in other ways (e.g. calls or loops), stop searching
            if any(isinstance(n, ast.Name) and n.id == candidate_var for n in ast.walk(prev)):
                break

        if initial_val is None:
            return None, None, set()

        return candidate_var, initial_val, exit_states

    def _find_dominant_dispatch_var(self, body: List[ast.stmt]) -> Optional[str]:
        """Find a variable compared to constants across multiple if conditions."""
        counts: Dict[str, int] = {}

        def inspect_test(test_node: ast.expr) -> None:
            if isinstance(test_node, ast.Compare) and len(test_node.comparators) == 1:
                if isinstance(test_node.ops[0], (ast.Eq, ast.Is)):
                    if isinstance(test_node.left, ast.Name) and isinstance(test_node.comparators[0], ast.Constant):
                        counts[test_node.left.id] = counts.get(test_node.left.id, 0) + 1
                    elif isinstance(test_node.comparators[0], ast.Name) and isinstance(test_node.left, ast.Constant):
                        counts[test_node.comparators[0].id] = counts.get(test_node.comparators[0].id, 0) + 1

        for stmt in body:
            if isinstance(stmt, ast.If):
                inspect_test(stmt.test)
                curr = stmt
                while curr.orelse and len(curr.orelse) == 1 and isinstance(curr.orelse[0], ast.If):
                    curr = curr.orelse[0]
                    inspect_test(curr.test)

        if counts:
            best_var, count = max(counts.items(), key=lambda kv: kv[1])
            if count >= 2:
                return best_var
        return None

    def _extract_state_blocks(
        self, body: List[ast.stmt], state_var: str, exit_states: Set[Any]
    ) -> Dict[Any, CFFStateBlock]:
        """Extract individual case blocks keyed by state value."""
        states: Dict[Any, CFFStateBlock] = {}

        for stmt in body:
            if isinstance(stmt, ast.If):
                self._collect_if_cases(stmt, state_var, exit_states, states)

        return states

    def _collect_if_cases(
        self,
        if_node: ast.If,
        state_var: str,
        exit_states: Set[Any],
        out_states: Dict[Any, CFFStateBlock],
    ) -> None:
        """Recursively process if / elif chains."""
        state_val = self._extract_trigger_state(if_node.test, state_var)
        if state_val is not None:
            block = self._analyze_case_body(if_node.body, state_var, exit_states, state_val)
            out_states[state_val] = block

        # Check elif in orelse
        if if_node.orelse:
            if len(if_node.orelse) == 1 and isinstance(if_node.orelse[0], ast.If):
                self._collect_if_cases(if_node.orelse[0], state_var, exit_states, out_states)
            else:
                # Sequence of statements in else
                pass

    def _extract_trigger_state(self, test: ast.expr, state_var: str) -> Optional[Any]:
        """Extract constant trigger value from 'state_var == <constant>'."""
        if isinstance(test, ast.Compare) and len(test.comparators) == 1:
            if isinstance(test.ops[0], (ast.Eq, ast.Is)):
                if isinstance(test.left, ast.Name) and test.left.id == state_var:
                    if isinstance(test.comparators[0], ast.Constant):
                        return test.comparators[0].value
                elif isinstance(test.comparators[0], ast.Name) and test.comparators[0].id == state_var:
                    if isinstance(test.left, ast.Constant):
                        return test.left.value
        return None

    def _analyze_case_body(
        self,
        stmts: List[ast.stmt],
        state_var: str,
        exit_states: Set[Any],
        state_val: Any,
    ) -> CFFStateBlock:
        """Separate payload statements from state updates and exits."""
        payload: List[ast.stmt] = []
        transition = CFFTransition()

        for stmt in stmts:
            # Check for return
            if isinstance(stmt, ast.Return):
                transition.is_return = True
                transition.terminator_node = stmt
                break

            # Check for break
            if isinstance(stmt, ast.Break):
                transition.is_exit = True
                transition.terminator_node = stmt
                break

            # Check for state assignment: state_var = <const>
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if isinstance(target, ast.Name) and target.id == state_var:
                    if isinstance(stmt.value, ast.Constant):
                        next_val = stmt.value.value
                        transition.next_state = next_val
                        if next_val in exit_states:
                            transition.is_exit = True
                        continue
                    elif isinstance(stmt.value, ast.UnaryOp) and isinstance(stmt.value.op, ast.USub):
                        if isinstance(stmt.value.operand, ast.Constant):
                            next_val = -stmt.value.operand.value
                            transition.next_state = next_val
                            if next_val in exit_states:
                                transition.is_exit = True
                            continue

            # Check for conditional state assignment:
            # if cond: state_var = A else: state_var = B
            if isinstance(stmt, ast.If):
                cond_trans = self._extract_conditional_transition(stmt, state_var)
                if cond_trans:
                    transition.conditional = cond_trans
                    continue

            payload.append(stmt)

        return CFFStateBlock(state_val=state_val, payload_stmts=payload, transition=transition)

    def _extract_conditional_transition(
        self, if_node: ast.If, state_var: str
    ) -> Optional[Tuple[ast.expr, Any, Any]]:
        """Check if an If statement solely updates the state variable conditionally."""
        if len(if_node.body) != 1 or len(if_node.orelse) != 1:
            return None

        then_stmt = if_node.body[0]
        else_stmt = if_node.orelse[0]

        if not (isinstance(then_stmt, ast.Assign) and isinstance(else_stmt, ast.Assign)):
            return None

        if len(then_stmt.targets) != 1 or len(else_stmt.targets) != 1:
            return None

        t_target = then_stmt.targets[0]
        e_target = else_stmt.targets[0]

        if not (isinstance(t_target, ast.Name) and t_target.id == state_var):
            return None
        if not (isinstance(e_target, ast.Name) and e_target.id == state_var):
            return None

        if isinstance(then_stmt.value, ast.Constant) and isinstance(else_stmt.value, ast.Constant):
            return (if_node.test, then_stmt.value.value, else_stmt.value.value)

        return None
