"""Constant propagation pass for Python AST.

Phase 1B: Static constant propagation.
Tracks constant assignments within local and lexical scopes and replaces
variable references with their known constant values.

Guarantees:
- Scope-aware (module, function, class definitions)
- Conservative branching invalidation (variables reassigned in branches or loops are invalidated)
- Safe handling of reassignments in linear sequences
- Full provenance recording
"""

import ast
from typing import Any, Dict, List, Optional, Set

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation
from languages.python.parser import PythonParser
from passes.expression_folding import is_safe_constant, extract_constant_value


def collect_assigned_names(node: ast.AST) -> Set[str]:
    """Collect all variable names targeted for assignment within an AST subtree."""
    assigned: Set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            for target in child.targets:
                for target_node in ast.walk(target):
                    if isinstance(target_node, ast.Name):
                        assigned.add(target_node.id)
        elif isinstance(child, (ast.AugAssign, ast.AnnAssign)):
            target = child.target
            for target_node in ast.walk(target):
                if isinstance(target_node, ast.Name):
                    assigned.add(target_node.id)
        elif isinstance(child, (ast.For, ast.AsyncFor)):
            for target_node in ast.walk(child.target):
                if isinstance(target_node, ast.Name):
                    assigned.add(target_node.id)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assigned.add(child.name)
    return assigned


class ScopeContext:
    """Represents a lexical scope for tracking constants."""

    def __init__(self, parent: Optional["ScopeContext"] = None) -> None:
        self.parent = parent
        self.constants: Dict[str, Any] = {}
        self.non_constants: Set[str] = set()

    def get(self, name: str) -> Optional[Any]:
        if name in self.constants:
            return self.constants[name]
        if name in self.non_constants:
            return None
        if self.parent:
            return self.parent.get(name)
        return None

    def set(self, name: str, value: Any) -> None:
        self.constants[name] = value
        self.non_constants.discard(name)

    def invalidate(self, name: str) -> None:
        self.constants.pop(name, None)
        self.non_constants.add(name)


class ConstantPropagatorTransformer(ast.NodeTransformer):
    """AST transformer that propagates constant values into variable references."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.tracker = tracker
        self.filename = filename
        self.scope_stack: List[ScopeContext] = [ScopeContext()]
        self.num_propagated = 0

    @property
    def current_scope(self) -> ScopeContext:
        return self.scope_stack[-1]

    def push_scope(self) -> ScopeContext:
        new_scope = ScopeContext(parent=self.current_scope)
        self.scope_stack.append(new_scope)
        return new_scope

    def pop_scope(self) -> ScopeContext:
        return self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        # Function arguments and local assignments shadow any outer constants
        self.push_scope()
        for arg in node.args.args + node.args.kwonlyargs:
            self.current_scope.invalidate(arg.arg)
        if node.args.vararg:
            self.current_scope.invalidate(node.args.vararg.arg)
        if node.args.kwarg:
            self.current_scope.invalidate(node.args.kwarg.arg)

        for local_var in collect_assigned_names(node):
            self.current_scope.invalidate(local_var)

        # Process function body statements sequentially
        node.body = self._process_statement_list(node.body)
        self.pop_scope()
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        self.push_scope()
        for arg in node.args.args + node.args.kwonlyargs:
            self.current_scope.invalidate(arg.arg)
        for local_var in collect_assigned_names(node):
            self.current_scope.invalidate(local_var)
        node.body = self._process_statement_list(node.body)
        self.pop_scope()
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self.push_scope()
        node.body = self._process_statement_list(node.body)
        self.pop_scope()
        return node

    def visit_Module(self, node: ast.Module) -> ast.AST:
        node.body = self._process_statement_list(node.body)
        return node

    def _process_statement_list(self, stmts: List[ast.stmt]) -> List[ast.stmt]:
        new_stmts = []
        for stmt in stmts:
            transformed = self.visit(stmt)
            if transformed is not None:
                if isinstance(transformed, list):
                    new_stmts.extend(transformed)
                else:
                    new_stmts.append(transformed)
        return new_stmts

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        # First visit the value side to allow propagation into the RHS
        node.value = self.visit(node.value)

        # Determine if RHS is a constant
        if is_safe_constant(node.value):
            val = extract_constant_value(node.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.current_scope.set(target.id, val)
                else:
                    for sub in ast.walk(target):
                        if isinstance(sub, ast.Name):
                            self.current_scope.invalidate(sub.id)
        else:
            # Value is not constant: invalidate assigned variables
            for target in node.targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name):
                        self.current_scope.invalidate(sub.id)

        return node

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        node.value = self.visit(node.value)
        # Any augmented assignment modifies target
        if isinstance(node.target, ast.Name):
            self.current_scope.invalidate(node.target.id)
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        if node.value:
            node.value = self.visit(node.value)
            if is_safe_constant(node.value) and isinstance(node.target, ast.Name):
                self.current_scope.set(node.target.id, extract_constant_value(node.value))
            elif isinstance(node.target, ast.Name):
                self.current_scope.invalidate(node.target.id)
        return node

    def visit_If(self, node: ast.If) -> ast.AST:
        node.test = self.visit(node.test)
        body_assigned = collect_assigned_names(node)

        # Process then-branch in a child scope
        self.push_scope()
        if self.current_scope.parent:
            self.current_scope.constants = dict(self.current_scope.parent.constants)
        node.body = self._process_statement_list(node.body)
        self.pop_scope()

        # Process else-branch in a child scope
        self.push_scope()
        if self.current_scope.parent:
            self.current_scope.constants = dict(self.current_scope.parent.constants)
        node.orelse = self._process_statement_list(node.orelse)
        self.pop_scope()

        # Invalidate any variable assigned in either branch at the join point
        for var_name in body_assigned:
            self.current_scope.invalidate(var_name)

        return node

    def visit_For(self, node: ast.For) -> ast.AST:
        node.iter = self.visit(node.iter)
        loop_assigned = collect_assigned_names(node)

        self.push_scope()
        if self.current_scope.parent:
            self.current_scope.constants = dict(self.current_scope.parent.constants)
        for var_name in loop_assigned:
            self.current_scope.invalidate(var_name)
        node.body = self._process_statement_list(node.body)
        node.orelse = self._process_statement_list(node.orelse)
        self.pop_scope()

        for var_name in loop_assigned:
            self.current_scope.invalidate(var_name)
        return node

    def visit_While(self, node: ast.While) -> ast.AST:
        loop_assigned = collect_assigned_names(node)

        self.push_scope()
        if self.current_scope.parent:
            self.current_scope.constants = dict(self.current_scope.parent.constants)
        for var_name in loop_assigned:
            self.current_scope.invalidate(var_name)
        node.test = self.visit(node.test)
        node.body = self._process_statement_list(node.body)
        node.orelse = self._process_statement_list(node.orelse)
        self.pop_scope()

        for var_name in loop_assigned:
            self.current_scope.invalidate(var_name)
        return node

    def visit_Try(self, node: ast.Try) -> ast.AST:
        try_assigned = collect_assigned_names(node)

        self.push_scope()
        if self.current_scope.parent:
            self.current_scope.constants = dict(self.current_scope.parent.constants)
        node.body = self._process_statement_list(node.body)
        self.pop_scope()

        for handler in node.handlers:
            self.push_scope()
            if self.current_scope.parent:
                self.current_scope.constants = dict(self.current_scope.parent.constants)
            if handler.name:
                self.current_scope.invalidate(handler.name)
            handler.body = self._process_statement_list(handler.body)
            self.pop_scope()

        self.push_scope()
        if self.current_scope.parent:
            self.current_scope.constants = dict(self.current_scope.parent.constants)
        node.orelse = self._process_statement_list(node.orelse)
        node.finalbody = self._process_statement_list(node.finalbody)
        self.pop_scope()

        for var_name in try_assigned:
            self.current_scope.invalidate(var_name)

        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        # Only substitute when reading a variable (Load context)
        if isinstance(node.ctx, ast.Load):
            val = self.current_scope.get(node.id)
            if val is not None and isinstance(val, (int, float, str, bytes, bool, type(None))):
                orig_repr = node.id
                new_node = ast.Constant(value=val)
                ast.copy_location(new_node, node)

                loc = PythonParser.get_location(node, filename=self.filename)
                self.tracker.record(
                    pass_name="ConstantPropagation",
                    original=orig_repr,
                    transformed=repr(val),
                    confidence=Confidence.certain(
                        f"Constant propagated from '{node.id}'", TransformationCategory.RECOVERED
                    ),
                    location=loc,
                )
                self.num_propagated += 1
                return new_node

        return node


class ConstantPropagationPass(Pass):
    """Pass that propagates constant values into variable references in Python AST."""

    name = "ConstantPropagation"
    description = "Propagates known constant assignments to variable uses."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        if not isinstance(target, ast.AST):
            return target

        transformer = ConstantPropagatorTransformer(tracker=tracker, filename=self.filename)
        return transformer.visit(target)
