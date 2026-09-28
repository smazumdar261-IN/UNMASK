"""Language-independent constant propagation pass for Common Intermediate Representation.

Per Section 16 & Phase 10:
Tracks and propagates constant assignments across scopes in Common IR trees.
Guarantees:
- Scope-aware (module level, function definitions)
- Function parameters shielded
- Reassignment tracking and invalidation
- Branch & loop mutation invalidation
- Strict provenance tracking
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from core.confidence import Confidence, TransformationCategory
from core.ir import (
    IRAssignment,
    IRBranch,
    IRConstant,
    IRExpression,
    IRFunction,
    IRLoop,
    IRModule,
    IRNode,
    IRStatement,
    IRString,
    IRTransformer,
    IRVariable,
    format_ir,
)
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation


class IRConstantPropagationTransformer(IRTransformer):
    """Propagates constant values in Common IR trees."""

    def __init__(self, tracker: Optional[ProvenanceTracker] = None) -> None:
        self.tracker = tracker
        self.env_stack: List[Dict[str, Any]] = [{}]
        self.shielded_stack: List[Set[str]] = [set()]

    @property
    def current_env(self) -> Dict[str, Any]:
        return self.env_stack[-1]

    @property
    def current_shielded(self) -> Set[str]:
        return self.shielded_stack[-1]

    def visit_IRFunction(self, node: IRFunction) -> IRFunction:
        new_env: Dict[str, Any] = {}
        shielded = set(node.parameters)
        self.env_stack.append(new_env)
        self.shielded_stack.append(shielded)

        node.body = self._process_statement_list(node.body)

        self.shielded_stack.pop()
        self.env_stack.pop()
        return node

    def visit_IRModule(self, node: IRModule) -> IRModule:
        node.body = self._process_statement_list(node.body)
        return node

    def _process_statement_list(self, statements: List[IRStatement]) -> List[IRStatement]:
        new_stmts: List[IRStatement] = []

        for stmt in statements:
            if isinstance(stmt, IRAssignment):
                # First transform value with current constants
                stmt.value = self.visit(stmt.value)

                # Then update environment if assigning to a simple variable
                if isinstance(stmt.target, IRVariable):
                    var_name = stmt.target.name
                    if var_name not in self.current_shielded:
                        if isinstance(stmt.value, IRConstant) and stmt.value.value is not None:
                            self.current_env[var_name] = stmt.value.value
                        else:
                            # Invalidate constant
                            self.current_env.pop(var_name, None)

                new_stmts.append(stmt)

            elif isinstance(stmt, IRBranch):
                stmt.condition = self.visit(stmt.condition)

                # Process then and else in isolated environments
                env_before = dict(self.current_env)
                self.env_stack.append(dict(env_before))
                stmt.body = self._process_statement_list(stmt.body)
                then_env = self.env_stack.pop()

                self.env_stack.append(dict(env_before))
                stmt.orelse = self._process_statement_list(stmt.orelse)
                else_env = self.env_stack.pop()

                # Reconcile after branch: keep only constants that match in both branches
                reconciled: Dict[str, Any] = {}
                for k, v in env_before.items():
                    if then_env.get(k) == v and else_env.get(k) == v:
                        reconciled[k] = v
                self.env_stack[-1] = reconciled
                new_stmts.append(stmt)

            elif isinstance(stmt, IRLoop):
                # Any variable modified in a loop body cannot be treated as constant
                modified = self._collect_assigned_variables(stmt.body)
                for var in modified:
                    self.current_env.pop(var, None)

                if stmt.condition:
                    stmt.condition = self.visit(stmt.condition)
                stmt.body = self._process_statement_list(stmt.body)
                stmt.orelse = self._process_statement_list(stmt.orelse)
                new_stmts.append(stmt)

            else:
                res = self.visit(stmt)
                if res is not None:
                    if isinstance(res, list):
                        new_stmts.extend(res)
                    else:
                        new_stmts.append(res)

        return new_stmts

    def visit_IRVariable(self, node: IRVariable) -> IRExpression:
        name = node.name
        if name not in self.current_shielded and name in self.current_env:
            val = self.current_env[name]
            orig_text = format_ir(node)
            loc = node.location or SourceLocation()

            if isinstance(val, str):
                replacement: IRConstant = IRString(value=val, location=loc)
            else:
                replacement = IRConstant(value=val, location=loc)

            if self.tracker:
                self.tracker.record(
                    pass_name="IRConstantPropagation",
                    original=orig_text,
                    transformed=format_ir(replacement),
                    confidence=Confidence.certain(
                        reason=f"Propagated constant: {name} = {val}",
                        category=TransformationCategory.SIMPLIFIED,
                    ),
                    location=loc,
                )
            return replacement

        return node

    def _collect_assigned_variables(self, statements: List[IRStatement]) -> Set[str]:
        assigned: Set[str] = set()

        class VarCollector(IRTransformer):
            def visit_IRAssignment(self, n: IRAssignment) -> IRAssignment:
                if isinstance(n.target, IRVariable):
                    assigned.add(n.target.name)
                return n

        collector = VarCollector()
        for s in statements:
            collector.visit(s)

        return assigned


class IRConstantPropagation(Pass):
    """Language-independent constant propagation pass on Common IR."""

    name = "IRConstantPropagation"
    description = "Propagates constants across scopes in Common IR"

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        transformer = IRConstantPropagationTransformer(tracker=tracker)
        return transformer.visit(target)
