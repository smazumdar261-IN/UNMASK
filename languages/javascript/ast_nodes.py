"""ESTree-compatible JavaScript AST node representations.

Per Section 12 and Section 16 of the Master Specification:
Provides structured AST representation for JavaScript (ES6+), supporting:
- Variable declarations (var, let, const)
- Function declarations, function expressions, and arrow functions
- Literals (numbers, hex, strings, booleans, null, undefined)
- Member expressions (dot notation and computed bracket notation)
- Call expressions, binary expressions, unary expressions
- Arrays, objects, control-flow statements (if, while, for, return)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional
from core.provenance import SourceLocation


@dataclass
class JSNode:
    """Base class for all JavaScript AST nodes."""

    location: SourceLocation = field(default_factory=SourceLocation)


@dataclass
class JSStatement(JSNode):
    """Base class for JavaScript statement nodes."""


@dataclass
class JSExpression(JSNode):
    """Base class for JavaScript expression nodes."""


@dataclass
class JSProgram(JSNode):
    """Root program node containing top-level statements."""

    body: List[JSStatement] = field(default_factory=list)


@dataclass
class JSIdentifier(JSExpression):
    """Identifier variable or property name."""

    name: str = ""


@dataclass
class JSLiteral(JSExpression):
    """Constant literal: string, number, boolean, null, etc."""

    value: Any = None
    raw: str = ""


@dataclass
class JSBlockStatement(JSStatement):
    """Block of statements enclosed in braces: { ... }."""

    body: List[JSStatement] = field(default_factory=list)


@dataclass
class JSExpressionStatement(JSStatement):
    """Statement consisting of a single expression: expr;."""

    expression: JSExpression = field(default_factory=JSExpression)


@dataclass
class JSVariableDeclarator(JSNode):
    """Single variable binding: name = init."""

    id: JSIdentifier = field(default_factory=JSIdentifier)
    init: Optional[JSExpression] = None
    type_annotation: Optional[Any] = None


@dataclass
class JSVariableDeclaration(JSStatement):
    """Variable declaration: var / let / const x = 1, y = 2;."""

    kind: str = "var"  # 'var', 'let', 'const'
    declarations: List[JSVariableDeclarator] = field(default_factory=list)


@dataclass
class JSFunctionDeclaration(JSStatement):
    """Function declaration: function name(p1, p2) { ... }."""

    id: Optional[JSIdentifier] = None
    params: List[Any] = field(default_factory=list)
    body: JSBlockStatement = field(default_factory=JSBlockStatement)
    return_type: Optional[Any] = None
    type_parameters: Optional[Any] = None
    decorators: List[Any] = field(default_factory=list)


@dataclass
class JSFunctionExpression(JSExpression):
    """Anonymous or named function expression: function(p) { ... }."""

    id: Optional[JSIdentifier] = None
    params: List[Any] = field(default_factory=list)
    body: JSBlockStatement = field(default_factory=JSBlockStatement)
    return_type: Optional[Any] = None
    type_parameters: Optional[Any] = None


@dataclass
class JSArrowFunctionExpression(JSExpression):
    """Arrow function: (x) => x * 2."""

    params: List[Any] = field(default_factory=list)
    body: Any = field(default_factory=JSBlockStatement)  # JSBlockStatement or JSExpression
    return_type: Optional[Any] = None
    type_parameters: Optional[Any] = None


@dataclass
class JSReturnStatement(JSStatement):
    """Return statement: return expr;."""

    argument: Optional[JSExpression] = None


@dataclass
class JSIfStatement(JSStatement):
    """Conditional statement: if (test) consequent else alternate."""

    test: JSExpression = field(default_factory=JSExpression)
    consequent: JSStatement = field(default_factory=JSStatement)
    alternate: Optional[JSStatement] = None


@dataclass
class JSWhileStatement(JSStatement):
    """While loop: while (test) body."""

    test: JSExpression = field(default_factory=JSExpression)
    body: JSStatement = field(default_factory=JSStatement)


@dataclass
class JSForStatement(JSStatement):
    """For loop: for (init; test; update) body."""

    init: Optional[Any] = None
    test: Optional[JSExpression] = None
    update: Optional[JSExpression] = None
    body: JSStatement = field(default_factory=JSStatement)


@dataclass
class JSBreakStatement(JSStatement):
    """Break statement."""

    label: Optional[str] = None


@dataclass
class JSContinueStatement(JSStatement):
    """Continue statement."""

    label: Optional[str] = None


@dataclass
class JSEmptyStatement(JSStatement):
    """Empty semicolon statement: ;."""


@dataclass
class JSBinaryExpression(JSExpression):
    """Binary operation: left <op> right."""

    operator: str = ""
    left: JSExpression = field(default_factory=JSExpression)
    right: JSExpression = field(default_factory=JSExpression)


@dataclass
class JSUnaryExpression(JSExpression):
    """Unary operation: <op> argument."""

    operator: str = ""
    argument: JSExpression = field(default_factory=JSExpression)
    prefix: bool = True


@dataclass
class JSCallExpression(JSExpression):
    """Function call: callee(arg1, arg2)."""

    callee: JSExpression = field(default_factory=JSExpression)
    arguments: List[JSExpression] = field(default_factory=list)


@dataclass
class JSMemberExpression(JSExpression):
    """Property access: object.property or object[property]."""

    object: JSExpression = field(default_factory=JSExpression)
    property: JSExpression = field(default_factory=JSExpression)
    computed: bool = False  # False for a.b, True for a['b']


@dataclass
class JSArrayExpression(JSExpression):
    """Array literal: [1, 2, 3]."""

    elements: List[JSExpression] = field(default_factory=list)


@dataclass
class JSProperty(JSNode):
    """Property inside object literal: key: value."""

    key: JSExpression = field(default_factory=JSExpression)
    value: JSExpression = field(default_factory=JSExpression)
    computed: bool = False


@dataclass
class JSObjectExpression(JSExpression):
    """Object literal: { a: 1, 'b': 2 }."""

    properties: List[JSProperty] = field(default_factory=list)


@dataclass
class JSAssignmentExpression(JSExpression):
    """Assignment expression: left = right or left += right."""

    operator: str = "="
    left: JSExpression = field(default_factory=JSExpression)
    right: JSExpression = field(default_factory=JSExpression)


@dataclass
class JSConditionalExpression(JSExpression):
    """Ternary operator: test ? consequent : alternate."""

    test: JSExpression = field(default_factory=JSExpression)
    consequent: JSExpression = field(default_factory=JSExpression)
    alternate: JSExpression = field(default_factory=JSExpression)


@dataclass
class JSSequenceExpression(JSExpression):
    """Comma sequence: (expr1, expr2)."""

    expressions: List[JSExpression] = field(default_factory=list)
