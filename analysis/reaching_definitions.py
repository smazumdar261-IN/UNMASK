"""Reaching definitions and dependency tracking analysis.

Per Section 10 of the Master Specification (Phase 4: Data Flow and Symbolic Analysis):
- Reaching definitions analysis (IN, OUT, GEN, KILL sets)
- Fine-grained Use-Def and Def-Use chains
- Data dependency tracking and variable dependency graphs
- Single-definition identification for safe symbolic substitution
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from core.provenance import SourceLocation
from languages.python.parser import PythonParser


@dataclass(frozen=True)
class StmtDef:
    """A variable definition produced by an assignment."""

    def_id: int
    variable: str
    target_node: ast.AST
    value_node: ast.expr
    stmt_node: ast.stmt
    location: SourceLocation

    def __repr__(self) -> str:
        return f"Def({self.variable} at {self.location}, id={self.def_id})"


@dataclass(frozen=True)
class StmtUse:
    """A variable reference (ast.Load)."""

    use_id: int
    variable: str
    node: ast.Name
    stmt_node: ast.stmt
    location: SourceLocation

    def __repr__(self) -> str:
        return f"Use({self.variable} at {self.location}, id={self.use_id})"


class DependencyGraph:
    """Tracks direct and transitive data dependencies between variables."""

    def __init__(self) -> None:
        # var -> set of variables it directly depends on
        self.depends_on: Dict[str, Set[str]] = {}
        # var -> set of variables that depend on it
        self.depended_by: Dict[str, Set[str]] = {}

    def add_dependency(self, target_var: str, source_var: str) -> None:
        """Record that target_var depends on source_var (target = f(source))."""
        self.depends_on.setdefault(target_var, set()).add(source_var)
        self.depended_by.setdefault(source_var, set()).add(target_var)

    def get_dependencies(self, var: str) -> Set[str]:
        """Return all direct dependencies of var."""
        return set(self.depends_on.get(var, set()))

    def get_transitive_dependencies(self, var: str) -> Set[str]:
        """Compute the transitive closure of dependencies for var."""
        result: Set[str] = set()
        queue: List[str] = list(self.depends_on.get(var, set()))

        while queue:
            curr = queue.pop(0)
            if curr not in result:
                result.add(curr)
                queue.extend(self.depends_on.get(curr, set()))

        return result


class ReachingDefinitionsAnalyzer:
    """Computes reaching definitions and dependency tracking across an AST node."""

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename
        self._next_def_id = 0
        self._next_use_id = 0
        self.definitions: List[StmtDef] = []
        self.uses: List[StmtUse] = []
        # Mapping from use -> set of reaching definitions
        self.use_def_chains: Dict[StmtUse, Set[StmtDef]] = {}
        # Mapping from def -> set of uses it reaches
        self.def_use_chains: Dict[StmtDef, Set[StmtUse]] = {}
        # Dependency graph
        self.dependency_graph: DependencyGraph = DependencyGraph()

    def analyze(self, node: ast.AST) -> None:
        """Run reaching definitions analysis on the provided AST node."""
        self._next_def_id = 0
        self._next_use_id = 0
        self.definitions.clear()
        self.uses.clear()
        self.use_def_chains.clear()
        self.def_use_chains.clear()
        self.dependency_graph = DependencyGraph()

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            self._analyze_statements(node.body)
        elif isinstance(node, list):
            self._analyze_statements(node)
        else:
            self._analyze_statements([node])

    def get_reaching_definitions_for_use(self, use: StmtUse) -> Set[StmtDef]:
        """Return all definitions reaching a specific variable use."""
        return self.use_def_chains.get(use, set())

    def get_unique_reaching_definition(self, use: StmtUse) -> Optional[StmtDef]:
        """If exactly one definition reaches this use, return it; otherwise return None."""
        reaching = self.get_reaching_definitions_for_use(use)
        if len(reaching) == 1:
            return next(iter(reaching))
        return None

    def _analyze_statements(self, stmts: List[ast.stmt]) -> None:
        """Forward reaching definitions analysis across a statement sequence."""
        # Active reaching definitions mapped by variable name
        current_reaching: Dict[str, Set[StmtDef]] = {}

        for stmt in stmts:
            if isinstance(stmt, ast.Assign):
                self._process_assign(stmt, current_reaching)
            elif isinstance(stmt, ast.AugAssign):
                self._process_aug_assign(stmt, current_reaching)
            elif isinstance(stmt, ast.If):
                self._process_if(stmt, current_reaching)
            elif isinstance(stmt, (ast.While, ast.For)):
                self._process_loop(stmt, current_reaching)
            else:
                self._process_generic_stmt(stmt, current_reaching)

    def _process_assign(
        self, stmt: ast.Assign, reaching: Dict[str, Set[StmtDef]]
    ) -> None:
        """Process right-hand uses and left-hand definitions of an Assign."""
        # 1. Collect uses in the RHS value expression
        rhs_uses = self._collect_uses_in_expr(stmt.value, stmt)
        rhs_vars: Set[str] = set()
        for u in rhs_uses:
            self.uses.append(u)
            rhs_vars.add(u.variable)
            # Link use to current reaching definitions
            reaching_defs = set(reaching.get(u.variable, set()))
            self.use_def_chains[u] = reaching_defs
            for d in reaching_defs:
                self.def_use_chains.setdefault(d, set()).add(u)

        # 2. Collect definitions in LHS targets
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                var_name = target.id
                loc = PythonParser.get_location(stmt, self.filename)
                d = StmtDef(
                    def_id=self._next_def_id,
                    variable=var_name,
                    target_node=target,
                    value_node=stmt.value,
                    stmt_node=stmt,
                    location=loc,
                )
                self._next_def_id += 1
                self.definitions.append(d)
                self.def_use_chains[d] = set()

                # Record dependencies in graph
                for src_var in rhs_vars:
                    self.dependency_graph.add_dependency(var_name, src_var)

                # KILL previous definitions and GEN this definition
                reaching[var_name] = {d}

    def _process_aug_assign(
        self, stmt: ast.AugAssign, reaching: Dict[str, Set[StmtDef]]
    ) -> None:
        """Process an augmented assignment (e.g. total += 10)."""
        if isinstance(stmt.target, ast.Name):
            # Target is also read
            var_name = stmt.target.id
            use = StmtUse(
                use_id=self._next_use_id,
                variable=var_name,
                node=stmt.target,
                stmt_node=stmt,
                location=PythonParser.get_location(stmt, self.filename),
            )
            self._next_use_id += 1
            self.uses.append(use)
            reaching_defs = set(reaching.get(var_name, set()))
            self.use_def_chains[use] = reaching_defs
            for d in reaching_defs:
                self.def_use_chains.setdefault(d, set()).add(use)

        rhs_uses = self._collect_uses_in_expr(stmt.value, stmt)
        for u in rhs_uses:
            self.uses.append(u)
            reaching_defs = set(reaching.get(u.variable, set()))
            self.use_def_chains[u] = reaching_defs
            for d in reaching_defs:
                self.def_use_chains.setdefault(d, set()).add(u)

        if isinstance(stmt.target, ast.Name):
            var_name = stmt.target.id
            loc = PythonParser.get_location(stmt, self.filename)
            d = StmtDef(
                def_id=self._next_def_id,
                variable=var_name,
                target_node=stmt.target,
                value_node=stmt.value,
                stmt_node=stmt,
                location=loc,
            )
            self._next_def_id += 1
            self.definitions.append(d)
            self.def_use_chains[d] = set()
            reaching[var_name] = {d}

    def _process_if(self, stmt: ast.If, reaching: Dict[str, Set[StmtDef]]) -> None:
        """Process branching with conservative union at merge point."""
        # Uses in test
        for u in self._collect_uses_in_expr(stmt.test, stmt):
            self.uses.append(u)
            reaching_defs = set(reaching.get(u.variable, set()))
            self.use_def_chains[u] = reaching_defs
            for d in reaching_defs:
                self.def_use_chains.setdefault(d, set()).add(u)

        # Clone reaching for then branch
        then_reaching = {v: set(defs) for v, defs in reaching.items()}
        for s in stmt.body:
            self._process_single_stmt(s, then_reaching)

        # Clone reaching for else branch
        else_reaching = {v: set(defs) for v, defs in reaching.items()}
        for s in stmt.orelse:
            self._process_single_stmt(s, else_reaching)

        # Merge reaching sets: IN(join) = OUT(then) U OUT(else)
        all_vars = set(then_reaching.keys()).union(else_reaching.keys())
        for var in all_vars:
            reaching[var] = then_reaching.get(var, set()).union(else_reaching.get(var, set()))

    def _process_loop(self, stmt: ast.stmt, reaching: Dict[str, Set[StmtDef]]) -> None:
        """Conservative loop handling: loop definitions merge into parent."""
        body = stmt.body if hasattr(stmt, "body") else []
        for s in body:
            self._process_single_stmt(s, reaching)

    def _process_generic_stmt(
        self, stmt: ast.stmt, reaching: Dict[str, Set[StmtDef]]
    ) -> None:
        """Process uses in general statements (Expr, Return, etc.)."""
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                use = StmtUse(
                    use_id=self._next_use_id,
                    variable=node.id,
                    node=node,
                    stmt_node=stmt,
                    location=PythonParser.get_location(node, self.filename),
                )
                self._next_use_id += 1
                self.uses.append(use)
                reaching_defs = set(reaching.get(node.id, set()))
                self.use_def_chains[use] = reaching_defs
                for d in reaching_defs:
                    self.def_use_chains.setdefault(d, set()).add(use)

    def _process_single_stmt(
        self, stmt: ast.stmt, reaching: Dict[str, Set[StmtDef]]
    ) -> None:
        """Helper to process a single statement within a sub-block."""
        if isinstance(stmt, ast.Assign):
            self._process_assign(stmt, reaching)
        elif isinstance(stmt, ast.AugAssign):
            self._process_aug_assign(stmt, reaching)
        elif isinstance(stmt, ast.If):
            self._process_if(stmt, reaching)
        elif isinstance(stmt, (ast.While, ast.For)):
            self._process_loop(stmt, reaching)
        else:
            self._process_generic_stmt(stmt, reaching)

    def _collect_uses_in_expr(
        self, expr: ast.expr, parent_stmt: ast.stmt
    ) -> List[StmtUse]:
        """Collect all ast.Load variable names inside an expression."""
        uses: List[StmtUse] = []
        for node in ast.walk(expr):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                loc = PythonParser.get_location(node, self.filename)
                uses.append(
                    StmtUse(
                        use_id=self._next_use_id,
                        variable=node.id,
                        node=node,
                        stmt_node=parent_stmt,
                        location=loc,
                    )
                )
                self._next_use_id += 1
        return uses
