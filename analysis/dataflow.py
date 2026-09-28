"""Data-flow analysis for Python AST.

Phase 1E: Python Data-Flow Analysis
Provides:
- Reaching definitions analysis
- Use-Def (UD) and Def-Use (DU) chains
- Variable liveness and unused assignment detection
- Variable alias tracking
- Pure expression classification (side-effect analysis)
"""

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from core.provenance import SourceLocation
from languages.python.parser import PythonParser


@dataclass(frozen=True)
class Definition:
    """Represents an assignment or definition of a variable."""

    def_id: int
    variable: str
    node: ast.AST
    location: SourceLocation
    is_pure: bool = True

    def __repr__(self) -> str:
        return f"Def({self.variable} at {self.location}, pure={self.is_pure})"


@dataclass(frozen=True)
class VariableUse:
    """Represents a read or reference of a variable (ast.Load)."""

    use_id: int
    variable: str
    node: ast.Name
    location: SourceLocation

    def __repr__(self) -> str:
        return f"Use({self.variable} at {self.location})"


def is_pure_expression(node: ast.AST) -> bool:
    """Check if an AST expression is free of side-effects.

    Constants, identifiers, tuple/list/dict literals of pure expressions,
    and arithmetic/logical/comparison operations between pure expressions are pure.
    Function calls, method calls, yields, and awaits are considered impure.
    """
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(is_pure_expression(el) for el in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            (k is None or is_pure_expression(k)) and is_pure_expression(v)
            for k, v in zip(node.keys, node.values)
        )
    if isinstance(node, ast.UnaryOp):
        return is_pure_expression(node.operand)
    if isinstance(node, ast.BinOp):
        return is_pure_expression(node.left) and is_pure_expression(node.right)
    if isinstance(node, ast.BoolOp):
        return all(is_pure_expression(v) for v in node.values)
    if isinstance(node, ast.Compare):
        return is_pure_expression(node.left) and all(is_pure_expression(c) for c in node.comparators)
    if isinstance(node, ast.Subscript):
        if not is_pure_expression(node.value):
            return False
        if isinstance(node.slice, ast.Slice):
            lower_pure = node.slice.lower is None or is_pure_expression(node.slice.lower)
            upper_pure = node.slice.upper is None or is_pure_expression(node.slice.upper)
            step_pure = node.slice.step is None or is_pure_expression(node.slice.step)
            return lower_pure and upper_pure and step_pure
        return is_pure_expression(node.slice)
    return False


class DataFlowAnalyzer:
    """Analyzes data flow, reaching definitions, use-def chains, and aliases."""

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename
        self.definitions: List[Definition] = []
        self.uses: List[VariableUse] = []
        self.def_to_uses: Dict[Definition, List[VariableUse]] = {}
        self.use_to_defs: Dict[VariableUse, List[Definition]] = {}
        self.aliases: Dict[str, Set[str]] = {}
        self._def_counter: int = 0
        self._use_counter: int = 0

    def analyze(self, tree: ast.AST) -> "DataFlowAnalyzer":
        """Run data-flow analysis on the AST."""
        self._collect_definitions_and_uses(tree)
        self._build_chains()
        self._compute_aliases(tree)
        return self

    def _collect_definitions_and_uses(self, tree: ast.AST) -> None:
        """Traverse AST and record all definition sites and use sites."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                is_pure = is_pure_expression(node.value)
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self._def_counter += 1
                        d = Definition(
                            def_id=self._def_counter,
                            variable=target.id,
                            node=node,
                            location=PythonParser.get_location(target, self.filename),
                            is_pure=is_pure,
                        )
                        self.definitions.append(d)
            elif isinstance(node, ast.AnnAssign):
                if node.value:
                    is_pure = is_pure_expression(node.value)
                    if isinstance(node.target, ast.Name):
                        self._def_counter += 1
                        d = Definition(
                            def_id=self._def_counter,
                            variable=node.target.id,
                            node=node,
                            location=PythonParser.get_location(node.target, self.filename),
                            is_pure=is_pure,
                        )
                        self.definitions.append(d)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                self._use_counter += 1
                u = VariableUse(
                    use_id=self._use_counter,
                    variable=node.id,
                    node=node,
                    location=PythonParser.get_location(node, self.filename),
                )
                self.uses.append(u)

    def _build_chains(self) -> None:
        """Map definitions to uses and uses to definitions."""
        var_to_defs: Dict[str, List[Definition]] = {}
        for d in self.definitions:
            var_to_defs.setdefault(d.variable, []).append(d)
            self.def_to_uses[d] = []

        for u in self.uses:
            reaching = var_to_defs.get(u.variable, [])
            self.use_to_defs[u] = reaching
            for d in reaching:
                self.def_to_uses[d].append(u)

    def _compute_aliases(self, tree: ast.AST) -> None:
        """Find variable-to-variable aliases (e.g. a = b)."""
        direct_aliases: Dict[str, Set[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Name):
                    dest = target.id
                    src = node.value.id
                    direct_aliases.setdefault(dest, set()).add(src)
                    direct_aliases.setdefault(src, set()).add(dest)

        # Transitive closure
        self.aliases = {}
        for var, related in direct_aliases.items():
            closure = set(related)
            changed = True
            while changed:
                before = len(closure)
                for other in list(closure):
                    closure.update(direct_aliases.get(other, set()))
                changed = len(closure) > before
            closure.discard(var)
            self.aliases[var] = closure

    def get_dead_definitions(self) -> List[Definition]:
        """Find all definitions that have zero uses and are safe (pure) to remove."""
        dead: List[Definition] = []
        for d in self.definitions:
            uses = self.def_to_uses.get(d, [])
            if len(uses) == 0 and d.is_pure:
                dead.append(d)
        return dead
