"""Call graph and function wrapper analysis.

Phase 2: Advanced Python Obfuscation
Provides:
- Call graph extraction
- Pure wrapper function detection
- Constant-returning function detection
- Single-expression function inlining suitability
"""

import ast
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from analysis.dataflow import is_pure_expression
from languages.python.parser import PythonParser


@dataclass
class FunctionSignature:
    """Represents an analyzed function definition."""

    name: str
    node: ast.FunctionDef
    params: List[str]
    is_pure: bool
    is_constant_return: bool = False
    constant_return_val: Optional[Any] = None
    is_simple_wrapper: bool = False
    return_expr: Optional[ast.expr] = None


class CallGraphAnalyzer:
    """Builds call graphs and analyzes functions for inlining."""

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename
        self.functions: Dict[str, FunctionSignature] = {}
        self.callers: Dict[str, Set[str]] = {}  # callee -> callers
        self.callees: Dict[str, Set[str]] = {}  # caller -> callees

    def analyze(self, tree: ast.AST) -> "CallGraphAnalyzer":
        """Analyze all function definitions and call sites in the AST."""
        # 1. Collect all top-level / module-level function definitions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self._analyze_function(node)

        # 2. Build caller-callee relationships
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                caller_name = node.name
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        callee_name = child.func.id
                        self.callees.setdefault(caller_name, set()).add(callee_name)
                        self.callers.setdefault(callee_name, set()).add(caller_name)

        return self

    def _analyze_function(self, node: ast.FunctionDef) -> None:
        params = [arg.arg for arg in node.args.args]

        # Check if function consists of a single return statement
        if len(node.body) == 1 and isinstance(node.body[0], ast.Return) and node.body[0].value:
            ret_expr = node.body[0].value

            # Check if returns constant literal
            if isinstance(ret_expr, ast.Constant):
                sig = FunctionSignature(
                    name=node.name,
                    node=node,
                    params=params,
                    is_pure=True,
                    is_constant_return=True,
                    constant_return_val=ret_expr.value,
                    is_simple_wrapper=True,
                    return_expr=ret_expr,
                )
                self.functions[node.name] = sig
                return

            sig = FunctionSignature(
                name=node.name,
                node=node,
                params=params,
                is_pure=is_pure_expression(ret_expr),
                is_constant_return=False,
                is_simple_wrapper=True,
                return_expr=ret_expr,
            )
            self.functions[node.name] = sig
            return

        # Multi-statement or non-simple function
        is_pure = all(is_pure_expression(stmt) if isinstance(stmt, ast.Expr) else True for stmt in node.body)
        sig = FunctionSignature(
            name=node.name,
            node=node,
            params=params,
            is_pure=is_pure,
            is_constant_return=False,
            is_simple_wrapper=False,
            return_expr=None,
        )
        self.functions[node.name] = sig
