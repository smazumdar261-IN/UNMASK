"""Common Intermediate Representation (IR) foundation.

Per Section 16 of the Master Specification:
A language-neutral intermediate representation for analysis and transformation passes.
It represents concepts such as:
Module, Function, Variable, Constant, Expression, Call, Assignment,
Branch, Loop, Return, Exception, Import, String, BinaryOperation, UnaryOperation.

Language-specific details are captured as metadata.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
import io
from typing import Any, Dict, List, Optional, Sequence, Union

from core.provenance import SourceLocation


@dataclass
class IRNode(ABC):
    """Base node for all Common Intermediate Representation constructs."""

    location: SourceLocation = field(default_factory=SourceLocation)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IRExpression(IRNode):
    """Base class for all IR expressions."""


@dataclass
class IRStatement(IRNode):
    """Base class for all IR statements."""


@dataclass
class IRConstant(IRExpression):
    """Literal constant value (int, float, str, bytes, bool, None)."""

    value: Any = None
    type_name: str = ""

    def __post_init__(self) -> None:
        if not self.type_name and self.value is not None:
            self.type_name = type(self.value).__name__


@dataclass
class IRString(IRConstant):
    """Specialized string literal constant with optional encoding metadata."""

    value: Any = ""
    type_name: str = "str"
    encoding: str = "utf-8"
    is_raw: bool = False

    def __post_init__(self) -> None:
        self.type_name = "str"
        if not isinstance(self.value, str) and self.value is not None:
            self.value = str(self.value)


@dataclass
class IRVariable(IRExpression):
    """Reference to an identifier or variable."""

    name: str = ""


@dataclass
class IRMemberAccess(IRExpression):
    """Member or property access: target.member (e.g., obj.field, pkg.Func)."""

    target: IRExpression = field(default_factory=IRExpression)
    member: str = ""


@dataclass
class IRIndexAccess(IRExpression):
    """Index or subscript access: target[index] (e.g., arr[0], dict[key])."""

    target: IRExpression = field(default_factory=IRExpression)
    index: IRExpression = field(default_factory=IRExpression)


@dataclass
class IRBinaryOperation(IRExpression):
    """Binary operation: left <op> right."""

    op: str = ""
    left: IRExpression = field(default_factory=IRExpression)
    right: IRExpression = field(default_factory=IRExpression)


@dataclass
class IRUnaryOperation(IRExpression):
    """Unary operation: <op> operand."""

    op: str = ""
    operand: IRExpression = field(default_factory=IRExpression)


@dataclass
class IRCall(IRExpression):
    """Function or method call: callee(*args, **kwargs)."""

    callee: IRExpression = field(default_factory=IRExpression)
    args: List[IRExpression] = field(default_factory=list)
    kwargs: Dict[str, IRExpression] = field(default_factory=dict)


@dataclass
class IRListLiteral(IRExpression):
    """List or array literal: [elem1, elem2, ...]."""

    elements: List[IRExpression] = field(default_factory=list)


@dataclass
class IRDictLiteral(IRExpression):
    """Dictionary or map literal: {key1: val1, ...}."""

    keys: List[IRExpression] = field(default_factory=list)
    values: List[IRExpression] = field(default_factory=list)


@dataclass
class IRAssignment(IRStatement):
    """Assignment: target = value."""

    target: Union[IRVariable, IRExpression] = field(default_factory=IRVariable)
    value: IRExpression = field(default_factory=IRExpression)


@dataclass
class IRExpressionStatement(IRStatement):
    """Statement consisting solely of an expression evaluated for side effects."""

    expression: IRExpression = field(default_factory=IRExpression)


@dataclass
class IRBranch(IRStatement):
    """Conditional branching: if condition then body else orelse."""

    condition: IRExpression = field(default_factory=IRExpression)
    body: List[IRStatement] = field(default_factory=list)
    orelse: List[IRStatement] = field(default_factory=list)


@dataclass
class IRLoop(IRStatement):
    """Loop construct: while condition do body (or for loop)."""

    condition: Optional[IRExpression] = None
    body: List[IRStatement] = field(default_factory=list)
    orelse: List[IRStatement] = field(default_factory=list)
    is_for: bool = False
    iterator: Optional[IRExpression] = None
    target: Optional[Union[IRVariable, IRExpression]] = None


@dataclass
class IRBreak(IRStatement):
    """Break statement to exit the current loop."""

    label: Optional[str] = None


@dataclass
class IRContinue(IRStatement):
    """Continue statement to jump to the next loop iteration."""

    label: Optional[str] = None


@dataclass
class IRReturn(IRStatement):
    """Return statement from a function."""

    value: Optional[IRExpression] = None


@dataclass
class IRExceptionHandler(IRNode):
    """Exception handler clause (catch / except block)."""

    exception_type: Optional[str] = None
    variable_name: Optional[str] = None
    body: List[IRStatement] = field(default_factory=list)


@dataclass
class IRTryExcept(IRStatement):
    """Exception handling block: try ... catch/except ... finally."""

    body: List[IRStatement] = field(default_factory=list)
    handlers: List[IRExceptionHandler] = field(default_factory=list)
    orelse: List[IRStatement] = field(default_factory=list)
    finalbody: List[IRStatement] = field(default_factory=list)


@dataclass
class IRRaise(IRStatement):
    """Exception throwing or raising statement."""

    exception: Optional[IRExpression] = None


# Alias for languages using 'throw' terminology
IRThrow = IRRaise


@dataclass
class IRBlock(IRStatement):
    """Grouped sequence of statements."""

    statements: List[IRStatement] = field(default_factory=list)


@dataclass
class IRPass(IRStatement):
    """No-op statement."""


@dataclass
class IRImport(IRStatement):
    """Module import statement."""

    module_name: str = ""
    alias: Optional[str] = None
    imported_names: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class IRFunction(IRStatement):
    """Function definition."""

    name: str = ""
    parameters: List[str] = field(default_factory=list)
    body: List[IRStatement] = field(default_factory=list)
    return_type: Optional[str] = None


@dataclass
class IRModule(IRNode):
    """Top-level module containing statements."""

    name: str = "<module>"
    language: str = "unknown"
    body: List[IRStatement] = field(default_factory=list)


# ---------------------------------------------------------------------------
# IR Visitor & Transformer Infrastructure
# ---------------------------------------------------------------------------


class IRVisitor:
    """Base visitor for traversing Common Intermediate Representation trees."""

    def visit(self, node: Optional[IRNode]) -> Any:
        if node is None:
            return None
        method_name = f"visit_{node.__class__.__name__}"
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: IRNode) -> Any:
        """Called if no explicit visitor function exists for a node."""
        for field_name, value in node.__dict__.items():
            if field_name in ("location", "metadata"):
                continue
            if isinstance(value, IRNode):
                self.visit(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, IRNode):
                        self.visit(item)
            elif isinstance(value, dict):
                for item in value.values():
                    if isinstance(item, IRNode):
                        self.visit(item)
        return None


class IRTransformer(IRVisitor):
    """Base transformer for rewriting Common Intermediate Representation trees.

    Walks the AST and uses the return value of the visitor methods to replace
    or remove the old node. If the return value is None, the node is removed.
    """

    def generic_visit(self, node: IRNode) -> IRNode:
        for field_name, value in list(node.__dict__.items()):
            if field_name in ("location", "metadata"):
                continue
            if isinstance(value, IRNode):
                new_node = self.visit(value)
                setattr(node, field_name, new_node)
            elif isinstance(value, list):
                new_list: List[Any] = []
                for item in value:
                    if isinstance(item, IRNode):
                        new_item = self.visit(item)
                        if new_item is None:
                            continue
                        elif isinstance(new_item, list):
                            new_list.extend(new_item)
                        else:
                            new_list.append(new_item)
                    else:
                        new_list.append(item)
                setattr(node, field_name, new_list)
        return node


# ---------------------------------------------------------------------------
# IR Pretty Printer and Text Dumper
# ---------------------------------------------------------------------------


class IRPrinter:
    """Pretty prints Common IR trees to a clean, language-neutral textual format."""

    def __init__(self, indent_str: str = "    ") -> None:
        self.indent_str = indent_str
        self._indent_level = 0
        self._buffer = io.StringIO()

    def print(self, node: IRNode) -> str:
        self._buffer = io.StringIO()
        self._indent_level = 0
        self._format_node(node)
        return self._buffer.getvalue().strip()

    def _indent(self) -> str:
        return self.indent_str * self._indent_level

    def _write_line(self, line: str = "") -> None:
        if line:
            self._buffer.write(f"{self._indent()}{line}\n")
        else:
            self._buffer.write("\n")

    def _format_node(self, node: Optional[IRNode]) -> None:
        if node is None:
            return

        if isinstance(node, IRModule):
            self._write_line(f"module {node.name} (language={node.language}):")
            self._indent_level += 1
            if not node.body:
                self._write_line("pass")
            else:
                for stmt in node.body:
                    self._format_node(stmt)
            self._indent_level -= 1

        elif isinstance(node, IRFunction):
            params_str = ", ".join(node.parameters)
            ret_str = f" -> {node.return_type}" if node.return_type else ""
            self._write_line(f"def {node.name}({params_str}){ret_str}:")
            self._indent_level += 1
            if not node.body:
                self._write_line("pass")
            else:
                for stmt in node.body:
                    self._format_node(stmt)
            self._indent_level -= 1

        elif isinstance(node, IRAssignment):
            target_str = self._format_expr(node.target)
            val_str = self._format_expr(node.value)
            self._write_line(f"{target_str} = {val_str}")

        elif isinstance(node, IRExpressionStatement):
            self._write_line(self._format_expr(node.expression))

        elif isinstance(node, IRBranch):
            cond_str = self._format_expr(node.condition)
            self._write_line(f"if {cond_str}:")
            self._indent_level += 1
            if not node.body:
                self._write_line("pass")
            else:
                for stmt in node.body:
                    self._format_node(stmt)
            self._indent_level -= 1
            if node.orelse:
                self._write_line("else:")
                self._indent_level += 1
                for stmt in node.orelse:
                    self._format_node(stmt)
                self._indent_level -= 1

        elif isinstance(node, IRLoop):
            if node.is_for:
                target_str = self._format_expr(node.target) if node.target else "_"
                iter_str = self._format_expr(node.iterator) if node.iterator else "[]"
                self._write_line(f"for {target_str} in {iter_str}:")
            else:
                cond_str = self._format_expr(node.condition) if node.condition else "true"
                self._write_line(f"while {cond_str}:")
            self._indent_level += 1
            if not node.body:
                self._write_line("pass")
            else:
                for stmt in node.body:
                    self._format_node(stmt)
            self._indent_level -= 1
            if node.orelse:
                self._write_line("else:")
                self._indent_level += 1
                for stmt in node.orelse:
                    self._format_node(stmt)
                self._indent_level -= 1

        elif isinstance(node, IRReturn):
            if node.value:
                self._write_line(f"return {self._format_expr(node.value)}")
            else:
                self._write_line("return")

        elif isinstance(node, IRBreak):
            lbl = f" {node.label}" if node.label else ""
            self._write_line(f"break{lbl}")

        elif isinstance(node, IRContinue):
            lbl = f" {node.label}" if node.label else ""
            self._write_line(f"continue{lbl}")

        elif isinstance(node, IRPass):
            self._write_line("pass")

        elif isinstance(node, IRRaise):
            if node.exception:
                self._write_line(f"raise {self._format_expr(node.exception)}")
            else:
                self._write_line("raise")

        elif isinstance(node, IRTryExcept):
            self._write_line("try:")
            self._indent_level += 1
            if not node.body:
                self._write_line("pass")
            else:
                for stmt in node.body:
                    self._format_node(stmt)
            self._indent_level -= 1
            for handler in node.handlers:
                exc = f" {handler.exception_type}" if handler.exception_type else ""
                as_var = f" as {handler.variable_name}" if handler.variable_name else ""
                self._write_line(f"catch{exc}{as_var}:")
                self._indent_level += 1
                if not handler.body:
                    self._write_line("pass")
                else:
                    for stmt in handler.body:
                        self._format_node(stmt)
                self._indent_level -= 1
            if node.orelse:
                self._write_line("else:")
                self._indent_level += 1
                for stmt in node.orelse:
                    self._format_node(stmt)
                self._indent_level -= 1
            if node.finalbody:
                self._write_line("finally:")
                self._indent_level += 1
                for stmt in node.finalbody:
                    self._format_node(stmt)
                self._indent_level -= 1

        elif isinstance(node, IRImport):
            if node.imported_names:
                names = ", ".join(
                    f"{orig} as {alias}" if alias else orig
                    for orig, alias in node.imported_names.items()
                )
                self._write_line(f"from {node.module_name} import {names}")
            else:
                alias = f" as {node.alias}" if node.alias else ""
                self._write_line(f"import {node.module_name}{alias}")

        elif isinstance(node, IRBlock):
            for stmt in node.statements:
                self._format_node(stmt)

        else:
            self._write_line(f"/* IR: {type(node).__name__} */")

    def _format_expr(self, expr: Optional[IRExpression]) -> str:
        if expr is None:
            return "null"

        if isinstance(expr, IRConstant):
            if expr.value is None:
                return "null"
            if isinstance(expr.value, str):
                return repr(expr.value)
            if isinstance(expr.value, bool):
                return "true" if expr.value else "false"
            return str(expr.value)

        if isinstance(expr, IRVariable):
            return expr.name

        if isinstance(expr, IRMemberAccess):
            target_str = self._format_expr(expr.target)
            return f"{target_str}.{expr.member}"

        if isinstance(expr, IRIndexAccess):
            target_str = self._format_expr(expr.target)
            idx_str = self._format_expr(expr.index)
            return f"{target_str}[{idx_str}]"

        if isinstance(expr, IRBinaryOperation):
            left_str = self._format_expr(expr.left)
            right_str = self._format_expr(expr.right)
            return f"({left_str} {expr.op} {right_str})"

        if isinstance(expr, IRUnaryOperation):
            operand_str = self._format_expr(expr.operand)
            return f"{expr.op}{operand_str}"

        if isinstance(expr, IRCall):
            callee_str = self._format_expr(expr.callee)
            arg_strs = [self._format_expr(a) for a in expr.args]
            for k, v in expr.kwargs.items():
                arg_strs.append(f"{k}={self._format_expr(v)}")
            return f"{callee_str}({', '.join(arg_strs)})"

        if isinstance(expr, IRListLiteral):
            elements_str = ", ".join(self._format_expr(e) for e in expr.elements)
            return f"[{elements_str}]"

        if isinstance(expr, IRDictLiteral):
            entries = [
                f"{self._format_expr(k)}: {self._format_expr(v)}"
                for k, v in zip(expr.keys, expr.values)
            ]
            return f"{{{', '.join(entries)}}}"

        return f"<expr {type(expr).__name__}>"


def format_ir(node: IRNode) -> str:
    """Format an IR node into readable textual representation."""
    return IRPrinter().print(node)


def dump_ir(node: IRNode) -> str:
    """Alias for format_ir."""
    return format_ir(node)


class IRValidator:
    """Validates structural correctness and integrity of Common IR trees."""

    @classmethod
    def validate(cls, node: IRNode) -> List[str]:
        """Validate an IR tree, returning a list of validation issues found (empty if valid)."""
        issues: List[str] = []

        class ValidationVisitor(IRVisitor):
            def visit_IRAssignment(self, n: IRAssignment) -> None:
                if not n.target:
                    issues.append("IRAssignment has empty target")
                if not n.value:
                    issues.append("IRAssignment has empty value")
                self.generic_visit(n)

            def visit_IRBranch(self, n: IRBranch) -> None:
                if not n.condition:
                    issues.append("IRBranch missing condition")
                self.generic_visit(n)

            def visit_IRBinaryOperation(self, n: IRBinaryOperation) -> None:
                if not n.op:
                    issues.append("IRBinaryOperation missing operator")
                if not n.left or not n.right:
                    issues.append("IRBinaryOperation missing operands")
                self.generic_visit(n)

        ValidationVisitor().visit(node)
        return issues
