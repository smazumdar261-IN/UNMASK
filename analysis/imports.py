"""Import analysis and alias tracking for Python AST.

Phase 2: Advanced Python Obfuscation
Provides:
- Module import mapping (import x as y)
- Function import mapping (from x import y as z)
- Variable function-alias tracking (f = base64.b64decode)
- Normalized representation of imported callable invocations
"""

import ast
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class ResolvedTarget:
    """Represents a fully-qualified resolved module and attribute."""

    module: str
    attribute: Optional[str] = None

    @property
    def qualified_name(self) -> str:
        if self.attribute:
            return f"{self.module}.{self.attribute}"
        return self.module


class ImportAnalyzer:
    """Analyzes import statements and variable aliases to resolve canonical names."""

    def __init__(self) -> None:
        # local_alias -> module_name
        self.module_aliases: Dict[str, str] = {}
        # local_alias -> ResolvedTarget(module, attribute)
        self.symbol_aliases: Dict[str, ResolvedTarget] = {}

    def analyze(self, tree: ast.AST) -> "ImportAnalyzer":
        """Scan AST for imports and alias assignments."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    self.module_aliases[local_name] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    self.symbol_aliases[local_name] = ResolvedTarget(
                        module=node.module,
                        attribute=alias.name,
                    )
            elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    resolved = self.resolve_expr(node.value)
                    if resolved:
                        self.symbol_aliases[target.id] = resolved

        return self

    def resolve_expr(self, expr: ast.AST) -> Optional[ResolvedTarget]:
        """Resolve an expression to a canonical module/symbol target if it is an alias."""
        # Case: local_name
        if isinstance(expr, ast.Name):
            if expr.id in self.symbol_aliases:
                return self.symbol_aliases[expr.id]
            if expr.id in self.module_aliases:
                return ResolvedTarget(module=self.module_aliases[expr.id])

        # Case: module_alias.attribute
        if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            mod_alias = expr.value.id
            if mod_alias in self.module_aliases:
                real_mod = self.module_aliases[mod_alias]
                return ResolvedTarget(module=real_mod, attribute=expr.attr)

        return None
